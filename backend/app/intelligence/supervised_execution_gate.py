from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.app.bridge.reader import read_json
from backend.app.bridge.schemas import Command
from backend.app.bridge.writer import write_json
from backend.app.intelligence.advisory_policy_proposal import (
    get_advisory_policy_proposal,
)
from backend.app.intelligence.advisory_review_workflow import (
    get_proposal_review_status,
)
from backend.app.intelligence.risk_governor import assess_risk
from backend.app.intelligence.supervised_command_proposal import (
    get_supervised_command_proposal,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
EXECUTION_EVENT_FILE = DATA_DIR / "supervised_execution_events.json"
BACKUP_DIR = DATA_DIR / "supervised_execution_backups"

EXPECTED_RUNTIME_CONTROL_COUNT = 157
ALLOW_TEST_OVERRIDE_ENV = "ATLAS_ALLOW_TEST_OVERRIDE_EXECUTION"

# Normal supervised execution is account-environment agnostic.
# Demo/live is selected in MT5 by the operator, not by Atlas.
REQUIRED_CONFIRMATION = "EXECUTE_SUPERVISED_COMMAND"
ARM_CONFIRMATION = "ARM_SUPERVISED_EXECUTION"
DEFAULT_ARM_MINUTES = 30
MAX_ARM_MINUTES = 120

_EVENT_LOCK = threading.Lock()
_ARM_LOCK = threading.Lock()
_ARM_STATE = {
    "armed": False,
    "armed_at": None,
    "armed_by": None,
    "expires_at": None,
}


class SupervisedExecutionError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 409,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_true(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def get_execution_arm_state() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with _ARM_LOCK:
        expires = _parse_iso(_ARM_STATE.get("expires_at"))
        if bool(_ARM_STATE.get("armed")) and expires is not None and now >= expires:
            _ARM_STATE.update({
                "armed": False,
                "armed_at": None,
                "armed_by": None,
                "expires_at": None,
            })

        expires = _parse_iso(_ARM_STATE.get("expires_at"))
        remaining = (
            max(0.0, (expires - now).total_seconds())
            if bool(_ARM_STATE.get("armed")) and expires is not None
            else 0.0
        )
        return {
            "armed": bool(_ARM_STATE.get("armed")),
            "armed_at": _ARM_STATE.get("armed_at"),
            "armed_by": _ARM_STATE.get("armed_by"),
            "expires_at": _ARM_STATE.get("expires_at"),
            "remaining_seconds": round(remaining, 3),
            "account_environment_agnostic": True,
            "interpretation": (
                "This is an Atlas operator arming state, not a demo/live mode. "
                "Atlas applies the same supervised execution safety pipeline to "
                "whatever MT5 account the operator has connected."
            ),
        }


def arm_supervised_execution(
    *,
    actor: str,
    confirmation_phrase: str,
    minutes: int = DEFAULT_ARM_MINUTES,
) -> dict[str, Any]:
    if confirmation_phrase != ARM_CONFIRMATION:
        raise SupervisedExecutionError(
            "ARM_CONFIRMATION_PHRASE_MISMATCH",
            f'confirmation_phrase must exactly equal "{ARM_CONFIRMATION}".',
            403,
        )

    duration = max(1, min(int(minutes), MAX_ARM_MINUTES))
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=duration)

    with _ARM_LOCK:
        _ARM_STATE.update({
            "armed": True,
            "armed_at": now.isoformat(),
            "armed_by": actor,
            "expires_at": expires.isoformat(),
        })

    return {
        **get_execution_arm_state(),
        "arm_duration_minutes": duration,
    }


def disarm_supervised_execution(*, actor: str) -> dict[str, Any]:
    with _ARM_LOCK:
        _ARM_STATE.update({
            "armed": False,
            "armed_at": None,
            "armed_by": None,
            "expires_at": None,
        })
    return {
        **get_execution_arm_state(),
        "disarmed_by": actor,
    }


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _runtime_fingerprint(runtime: dict[str, Any]) -> str:
    return _canonical_hash(runtime)[:16]


def _empty_event_store() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "event_count": 0,
        "events": [],
    }


def _read_event_store_unlocked() -> dict[str, Any]:
    if not EXECUTION_EVENT_FILE.exists():
        return _empty_event_store()
    try:
        with EXECUTION_EVENT_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_event_store()
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return _empty_event_store()
    return data


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _append_execution_event(
    *,
    action: str,
    execution_id: str,
    supervised_command_id: str,
    actor: str,
    note: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    with _EVENT_LOCK:
        store = _read_event_store_unlocked()
        events = list(store.get("events") or [])
        previous_hash = events[-1].get("event_hash") if events else None
        sequence = int(store.get("event_count") or 0) + 1

        core = {
            "sequence": sequence,
            "timestamp": _now_iso(),
            "action": action,
            "execution_id": execution_id,
            "supervised_command_id": supervised_command_id,
            "actor": actor,
            "note": note,
            "metadata": metadata,
            "previous_hash": previous_hash,
        }
        event_hash = _canonical_hash(core)
        event = {**core, "event_hash": event_hash}
        events.append(event)

        store["events"] = events
        store["event_count"] = sequence
        store["updated_at"] = event["timestamp"]
        _atomic_write_json(EXECUTION_EVENT_FILE, store)
        return event



def append_execution_lifecycle_event(
    *,
    action: str,
    execution_id: str,
    supervised_command_id: str,
    actor: str,
    note: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Public lifecycle-event hook used by the Nyao acknowledgement tracker."""
    return _append_execution_event(
        action=action,
        execution_id=execution_id,
        supervised_command_id=supervised_command_id,
        actor=actor,
        note=note,
        metadata=metadata,
    )

def get_execution_events(
    *,
    limit: int = 200,
    supervised_command_id: str | None = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 200), 5000))
    with _EVENT_LOCK:
        store = _read_event_store_unlocked()
        events = list(store.get("events") or [])

    if supervised_command_id:
        events = [
            event for event in events
            if event.get("supervised_command_id") == supervised_command_id
        ]

    selected = events[-safe_limit:][::-1]
    return {
        "event_count": len(events),
        "returned_count": len(selected),
        "events": selected,
        "event_file": str(EXECUTION_EVENT_FILE),
    }


def verify_execution_event_chain() -> dict[str, Any]:
    with _EVENT_LOCK:
        store = _read_event_store_unlocked()
        events = list(store.get("events") or [])

    previous_hash = None
    broken_at = None

    for event in events:
        supplied_hash = event.get("event_hash")
        core = {
            key: value
            for key, value in event.items()
            if key != "event_hash"
        }
        if core.get("previous_hash") != previous_hash:
            broken_at = event.get("sequence")
            break
        calculated = _canonical_hash(core)
        if calculated != supplied_hash:
            broken_at = event.get("sequence")
            break
        previous_hash = supplied_hash

    return {
        "valid": broken_at is None,
        "checked_event_count": (
            len(events) if broken_at is None else max(0, int(broken_at) - 1)
        ),
        "broken_at_sequence": broken_at,
        "chain_head": previous_hash,
        "event_file": str(EXECUTION_EVENT_FILE),
        "interpretation": (
            "Local SHA-256 hash-chain verification is tamper-evident. "
            "It is not an external signature or immutable ledger."
        ),
    }


def _events_for_execution(execution_id: str) -> list[dict[str, Any]]:
    with _EVENT_LOCK:
        store = _read_event_store_unlocked()
        return [
            event for event in store.get("events") or []
            if event.get("execution_id") == execution_id
        ]


def _extract_runtime_subset(
    command: dict[str, Any],
    runtime_keys: list[str],
) -> dict[str, Any]:
    return {
        key: command.get(key)
        for key in runtime_keys
    }


def _validate_operator_arm(
    *,
    allow_test_override_execution: bool,
    test_override_active: bool,
) -> dict[str, Any]:
    arm_state = get_execution_arm_state()
    allow_test_env = _env_true(ALLOW_TEST_OVERRIDE_ENV)

    if not arm_state.get("armed"):
        raise SupervisedExecutionError(
            "SUPERVISED_EXECUTION_NOT_ARMED",
            (
                "Supervised execution is disarmed. Arm it from the Atlas Control "
                "page before executing an approved policy."
            ),
            403,
            {
                "arm_state": arm_state,
                "arm_confirmation_phrase": ARM_CONFIRMATION,
            },
        )

    # Synthetic TEST_OVERRIDE proposals remain separately gated. This is a
    # test-harness distinction, not an MT5 demo/live distinction.
    if test_override_active:
        if not allow_test_override_execution or not allow_test_env:
            raise SupervisedExecutionError(
                "TEST_OVERRIDE_EXECUTION_NOT_AUTHORIZED",
                "Synthetic TEST_OVERRIDE proposals require both explicit request authorization and the dedicated environment gate.",
                403,
                {
                    "request_allow_test_override_execution": bool(
                        allow_test_override_execution
                    ),
                    "environment_gate_enabled": allow_test_env,
                    "required_environment_variable": ALLOW_TEST_OVERRIDE_ENV,
                },
            )

    return {
        "operator_arm": arm_state,
        "account_environment_agnostic": True,
        "test_override_environment_gate": allow_test_env,
    }


def _validate_supervised_package(
    package: dict[str, Any],
    *,
    expected_source_proposal_id: str,
    expected_runtime_fingerprint: str,
    expected_target_policy_epoch: int,
    expected_review_snapshot_hash: str,
    expected_baseline_command_version: int,
    expected_baseline_policy_epoch: int,
) -> None:
    if package.get("mode") != "SUPERVISED_COMMAND_PROPOSAL":
        raise SupervisedExecutionError(
            "INVALID_SUPERVISED_PACKAGE",
            "The stored artifact is not a supervised command proposal.",
            409,
        )

    source = package.get("source") or {}
    context = package.get("current_context") or {}
    preview = package.get("command_preview") or {}

    expected_pairs = {
        "source_proposal_id": (
            source.get("proposal_id"),
            expected_source_proposal_id,
        ),
        "runtime_fingerprint": (
            preview.get("runtime_fingerprint"),
            expected_runtime_fingerprint,
        ),
        "target_policy_epoch": (
            preview.get("target_policy_epoch"),
            int(expected_target_policy_epoch),
        ),
        "review_snapshot_hash": (
            source.get("review_snapshot_hash"),
            expected_review_snapshot_hash,
        ),
        "baseline_command_version": (
            context.get("baseline_command_version"),
            int(expected_baseline_command_version),
        ),
        "baseline_policy_epoch": (
            context.get("baseline_policy_epoch"),
            int(expected_baseline_policy_epoch),
        ),
    }

    mismatches = {
        key: {"stored": stored, "expected": expected}
        for key, (stored, expected) in expected_pairs.items()
        if stored != expected
    }
    if mismatches:
        raise SupervisedExecutionError(
            "SECOND_ACTION_BINDING_MISMATCH",
            "The second human action does not exactly match the stored supervised command proposal.",
            409,
            mismatches,
        )

    runtime = dict(preview.get("runtime") or {})
    if len(runtime) != EXPECTED_RUNTIME_CONTROL_COUNT:
        raise SupervisedExecutionError(
            "RUNTIME_CONTROL_COUNT_MISMATCH",
            "The command package does not contain all 157 runtime controls.",
            409,
            {
                "expected": EXPECTED_RUNTIME_CONTROL_COUNT,
                "actual": len(runtime),
            },
        )

    calculated_fp = _runtime_fingerprint(runtime)
    if calculated_fp != preview.get("runtime_fingerprint"):
        raise SupervisedExecutionError(
            "RUNTIME_PAYLOAD_FINGERPRINT_MISMATCH",
            "The stored runtime no longer matches its approved fingerprint.",
            409,
            {
                "stored": preview.get("runtime_fingerprint"),
                "calculated": calculated_fp,
            },
        )


def _validate_source_still_approved_and_current(
    package: dict[str, Any],
    current_proposal: dict[str, Any],
) -> None:
    source = package.get("source") or {}
    proposal_id = str(source.get("proposal_id") or "")

    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise SupervisedExecutionError(
            "SOURCE_PROPOSAL_NOT_FOUND",
            "The source advisory proposal no longer exists.",
            409,
        )

    review = get_proposal_review_status(proposal_id)
    approval = review.get("approval") or {}

    if approval.get("status") != "APPROVED" or not bool(approval.get("approved")):
        raise SupervisedExecutionError(
            "SOURCE_APPROVAL_NOT_ACTIVE",
            "The source advisory approval is no longer active.",
            409,
            {"approval_status": approval.get("status")},
        )

    approval_binding = {
        "runtime_fingerprint": (
            approval.get("approval_runtime_fingerprint"),
            source.get("runtime_fingerprint"),
        ),
        "policy_epoch": (
            approval.get("approval_proposed_policy_epoch"),
            source.get("proposed_policy_epoch"),
        ),
        "snapshot_hash": (
            approval.get("approval_snapshot_hash"),
            source.get("review_snapshot_hash"),
        ),
    }
    binding_mismatches = {
        key: {"approval": left, "package": right}
        for key, (left, right) in approval_binding.items()
        if left != right
    }
    if binding_mismatches:
        raise SupervisedExecutionError(
            "SOURCE_APPROVAL_BINDING_MISMATCH",
            "The active approval no longer matches the supervised command package.",
            409,
            binding_mismatches,
        )

    current_binding = {
        "proposal_id": (
            current_proposal.get("proposal_id"),
            source.get("proposal_id"),
        ),
        "runtime_fingerprint": (
            current_proposal.get("runtime_fingerprint"),
            source.get("runtime_fingerprint"),
        ),
        "proposed_policy_epoch": (
            current_proposal.get("proposed_policy_epoch"),
            source.get("proposed_policy_epoch"),
        ),
    }
    current_mismatches = {
        key: {"current": left, "package": right}
        for key, (left, right) in current_binding.items()
        if left != right
    }
    if current_mismatches:
        raise SupervisedExecutionError(
            "CURRENT_CONTEXT_CHANGED",
            "Atlas's current advisory context no longer matches the approved command package.",
            409,
            current_mismatches,
        )


def preflight_supervised_execution(
    supervised_command_id: str,
    *,
    current_proposal: dict[str, Any],
    current_status: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any]:
    package = get_supervised_command_proposal(supervised_command_id)
    if package is None:
        raise SupervisedExecutionError(
            "SUPERVISED_COMMAND_NOT_FOUND",
            "Supervised command proposal not found.",
            404,
        )

    _validate_source_still_approved_and_current(package, current_proposal)

    context = package.get("current_context") or {}
    preview = package.get("command_preview") or {}
    runtime = dict(preview.get("runtime") or {})

    current_version = int(current_command.get("command_version") or 0)
    current_epoch = int(current_command.get("policy_epoch") or 0)
    baseline_version = int(context.get("baseline_command_version") or 0)
    baseline_epoch = int(context.get("baseline_policy_epoch") or 0)

    baseline_match = (
        current_version == baseline_version
        and current_epoch == baseline_epoch
    )

    risk = assess_risk(current_status)
    risk_gate_passed = not bool(risk.get("veto_new_risk"))
    arm_state = get_execution_arm_state()

    runtime_integrity = (
        len(runtime) == EXPECTED_RUNTIME_CONTROL_COUNT
        and _runtime_fingerprint(runtime) == preview.get("runtime_fingerprint")
    )

    already_executed = any(
        event.get("action") in {"EXECUTED", "EXECUTED_RECOVERED"}
        for event in get_execution_events(
            limit=5000,
            supervised_command_id=supervised_command_id,
        ).get("events") or []
    )

    return {
        "supervised_execution_version": "0.8.1",
        "mode": "SUPERVISED_EXECUTION_PREFLIGHT",
        "supervised_command_id": supervised_command_id,
        "source_proposal_id": (package.get("source") or {}).get("proposal_id"),
        "test_override_active": bool(
            (package.get("source") or {}).get("test_override_active")
        ),
        "baseline": {
            "expected_command_version": baseline_version,
            "actual_command_version": current_version,
            "expected_policy_epoch": baseline_epoch,
            "actual_policy_epoch": current_epoch,
            "match": baseline_match,
        },
        "runtime_integrity": {
            "control_count": len(runtime),
            "fingerprint": _runtime_fingerprint(runtime),
            "expected_fingerprint": preview.get("runtime_fingerprint"),
            "valid": runtime_integrity,
        },
        "risk_governor_recheck": {
            **risk,
            "gate_passed": risk_gate_passed,
        },
        "already_executed": already_executed,
        "operator_arm": arm_state,
        "ready_for_supervised_execution": bool(
            baseline_match
            and runtime_integrity
            and risk_gate_passed
            and not already_executed
            and arm_state.get("armed")
        ),
        # Compatibility alias for older UI clients. It no longer implies demo-only.
        "ready_for_explicit_demo_execution": bool(
            baseline_match
            and runtime_integrity
            and risk_gate_passed
            and not already_executed
            and arm_state.get("armed")
        ),
        "execution": {
            "performed": False,
            "commands_json_write": False,
            "nyao_mutation": False,
        },
    }


def execute_supervised_command(
    supervised_command_id: str,
    *,
    command_file: Path,
    current_proposal: dict[str, Any],
    current_status: dict[str, Any],
    current_command: dict[str, Any],
    actor: str,
    note: str | None,
    confirmation_phrase: str,
    allow_test_override_execution: bool,
    expected_source_proposal_id: str,
    expected_runtime_fingerprint: str,
    expected_target_policy_epoch: int,
    expected_review_snapshot_hash: str,
    expected_baseline_command_version: int,
    expected_baseline_policy_epoch: int,
) -> dict[str, Any]:
    package = get_supervised_command_proposal(supervised_command_id)
    if package is None:
        raise SupervisedExecutionError(
            "SUPERVISED_COMMAND_NOT_FOUND",
            "Supervised command proposal not found.",
            404,
        )

    if confirmation_phrase != REQUIRED_CONFIRMATION:
        raise SupervisedExecutionError(
            "CONFIRMATION_PHRASE_MISMATCH",
            f'confirmation_phrase must exactly equal "{REQUIRED_CONFIRMATION}".',
            403,
        )

    # Replay protection has precedence over approval/context checks.
    # Once this exact supervised command has already completed execution,
    # it must never be considered executable again, regardless of whether
    # its source approval later expires or is invalidated.
    prior_for_command = get_execution_events(
        limit=5000,
        supervised_command_id=supervised_command_id,
    ).get("events") or []
    prior_completed = [
        event for event in prior_for_command
        if event.get("action") in {"EXECUTED", "EXECUTED_RECOVERED"}
    ]
    if prior_completed:
        latest_completed = prior_completed[0]
        raise SupervisedExecutionError(
            "EXECUTION_REPLAY_BLOCKED",
            "This supervised command has already completed execution and cannot be executed again.",
            409,
            {
                "supervised_command_id": supervised_command_id,
                "prior_execution_id": latest_completed.get("execution_id"),
                "prior_action": latest_completed.get("action"),
                "prior_sequence": latest_completed.get("sequence"),
            },
        )

    source = package.get("source") or {}
    preview = package.get("command_preview") or {}
    context = package.get("current_context") or {}
    runtime = dict(preview.get("runtime") or {})

    env_state = _validate_operator_arm(
        allow_test_override_execution=allow_test_override_execution,
        test_override_active=bool(source.get("test_override_active")),
    )

    _validate_supervised_package(
        package,
        expected_source_proposal_id=expected_source_proposal_id,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        expected_target_policy_epoch=expected_target_policy_epoch,
        expected_review_snapshot_hash=expected_review_snapshot_hash,
        expected_baseline_command_version=expected_baseline_command_version,
        expected_baseline_policy_epoch=expected_baseline_policy_epoch,
    )

    _validate_source_still_approved_and_current(package, current_proposal)

    risk = assess_risk(current_status)
    if bool(risk.get("veto_new_risk")):
        raise SupervisedExecutionError(
            "RISK_GOVERNOR_VETO",
            "Risk Governor vetoed new risk at execution time.",
            409,
            {
                "state": risk.get("state"),
                "score": risk.get("score"),
                "veto_reasons": risk.get("veto_reasons") or [],
            },
        )

    current_version = int(current_command.get("command_version") or 0)
    current_epoch = int(current_command.get("policy_epoch") or 0)
    baseline_version = int(context.get("baseline_command_version") or 0)
    baseline_epoch = int(context.get("baseline_policy_epoch") or 0)

    if current_version != baseline_version or current_epoch != baseline_epoch:
        raise SupervisedExecutionError(
            "COMMAND_BASELINE_CHANGED",
            "commands.json changed after the supervised command proposal was built.",
            409,
            {
                "expected_command_version": baseline_version,
                "actual_command_version": current_version,
                "expected_policy_epoch": baseline_epoch,
                "actual_policy_epoch": current_epoch,
            },
        )

    target_epoch = int(preview.get("target_policy_epoch") or 0)
    if target_epoch not in {baseline_epoch, baseline_epoch + 1}:
        raise SupervisedExecutionError(
            "INVALID_TARGET_POLICY_EPOCH",
            "Target policy epoch must be the current epoch or exactly one epoch ahead.",
            409,
            {
                "baseline_policy_epoch": baseline_epoch,
                "target_policy_epoch": target_epoch,
            },
        )

    runtime_fp = _runtime_fingerprint(runtime)
    if len(runtime) != EXPECTED_RUNTIME_CONTROL_COUNT:
        raise SupervisedExecutionError(
            "RUNTIME_CONTROL_COUNT_MISMATCH",
            "Execution payload must contain all 157 runtime controls.",
            409,
        )
    if runtime_fp != preview.get("runtime_fingerprint"):
        raise SupervisedExecutionError(
            "RUNTIME_PAYLOAD_FINGERPRINT_MISMATCH",
            "Execution payload fingerprint does not match the supervised package.",
            409,
        )

    execution_identity = {
        "version": "0.8.1",
        "supervised_command_id": supervised_command_id,
        "source_proposal_id": source.get("proposal_id"),
        "runtime_fingerprint": runtime_fp,
        "baseline_command_version": baseline_version,
        "baseline_policy_epoch": baseline_epoch,
        "target_policy_epoch": target_epoch,
    }
    execution_id = _canonical_hash(execution_identity)[:24]

    prior_events = _events_for_execution(execution_id)
    if any(
        event.get("action") in {"EXECUTED", "EXECUTED_RECOVERED"}
        for event in prior_events
    ):
        raise SupervisedExecutionError(
            "EXECUTION_REPLAY_BLOCKED",
            "This exact supervised command has already executed.",
            409,
            {"execution_id": execution_id},
        )

    # If an earlier process authorized this exact execution and then crashed,
    # reconcile against commands.json before attempting another write.
    if any(event.get("action") == "EXECUTION_AUTHORIZED" for event in prior_events):
        latest_command = read_json(command_file) or {}
        latest_version = int(latest_command.get("command_version") or 0)
        latest_epoch = int(latest_command.get("policy_epoch") or 0)
        latest_subset = _extract_runtime_subset(
            latest_command,
            list(runtime.keys()),
        )
        if (
            latest_version == baseline_version + 1
            and latest_epoch == target_epoch
            and _runtime_fingerprint(latest_subset) == runtime_fp
        ):
            recovered = _append_execution_event(
                action="EXECUTED_RECOVERED",
                execution_id=execution_id,
                supervised_command_id=supervised_command_id,
                actor=actor,
                note="Recovered a previously authorized execution whose command write had already completed.",
                metadata={
                    "command_version": latest_version,
                    "policy_epoch": latest_epoch,
                    "runtime_fingerprint": runtime_fp,
                },
            )
            return {
                "supervised_execution_version": "0.8.1",
                "mode": "SUPERVISED_EXECUTION",
                "execution_id": execution_id,
                "status": "EXECUTED_RECOVERED",
                "command": latest_command,
                "event": recovered,
                "execution_environment": env_state,
            }

        if not (
            latest_version == baseline_version
            and latest_epoch == baseline_epoch
        ):
            raise SupervisedExecutionError(
                "AMBIGUOUS_PRIOR_EXECUTION_ATTEMPT",
                "A prior execution was authorized and commands.json is no longer at either the expected baseline or exact target state.",
                409,
                {
                    "execution_id": execution_id,
                    "actual_command_version": latest_version,
                    "actual_policy_epoch": latest_epoch,
                },
            )

    # Preserve non-runtime command controls such as the global `enabled` flag.
    candidate = {
        **current_command,
        **runtime,
        "command_version": baseline_version + 1,
        "policy_epoch": target_epoch,
        "updated_at": datetime.now(timezone.utc),
    }

    try:
        validated = Command.model_validate(candidate)
    except Exception as exc:
        raise SupervisedExecutionError(
            "COMMAND_SCHEMA_VALIDATION_FAILED",
            "The final command payload failed Atlas Command schema validation.",
            422,
            {"error": str(exc)},
        ) from exc

    validated_dict = validated.model_dump(
        mode="json",
        exclude_none=True,
    )

    # Persist an exact pre-write backup for audit/recovery work.
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_file = BACKUP_DIR / f"{execution_id}_before.json"
    if not backup_file.exists():
        _atomic_write_json(
            backup_file,
            {
                "created_at": _now_iso(),
                "execution_id": execution_id,
                "supervised_command_id": supervised_command_id,
                "command_before": current_command,
            },
        )

    authorized = _append_execution_event(
        action="EXECUTION_AUTHORIZED",
        execution_id=execution_id,
        supervised_command_id=supervised_command_id,
        actor=actor,
        note=note,
        metadata={
            "source_proposal_id": source.get("proposal_id"),
            "runtime_fingerprint": runtime_fp,
            "baseline_command_version": baseline_version,
            "target_command_version": baseline_version + 1,
            "baseline_policy_epoch": baseline_epoch,
            "target_policy_epoch": target_epoch,
            "review_snapshot_hash": source.get("review_snapshot_hash"),
            "risk_state": risk.get("state"),
            "risk_score": risk.get("score"),
            "test_override_active": bool(source.get("test_override_active")),
            "account_environment_agnostic": True,
            "backup_file": str(backup_file),
        },
    )

    try:
        # The ONLY command write in the v0.6 supervised execution gate.
        write_json(validated, command_file)
    except Exception as exc:
        failed = _append_execution_event(
            action="EXECUTION_WRITE_FAILED",
            execution_id=execution_id,
            supervised_command_id=supervised_command_id,
            actor="ATLAS_SYSTEM",
            note=str(exc),
            metadata={"authorized_event_hash": authorized.get("event_hash")},
        )
        raise SupervisedExecutionError(
            "COMMAND_WRITE_FAILED",
            "Atlas failed while writing the validated command payload.",
            500,
            {
                "execution_id": execution_id,
                "failure_event_hash": failed.get("event_hash"),
            },
        ) from exc

    readback = read_json(command_file) or {}
    readback_version = int(readback.get("command_version") or 0)
    readback_epoch = int(readback.get("policy_epoch") or 0)
    readback_runtime = _extract_runtime_subset(
        readback,
        list(runtime.keys()),
    )
    readback_fp = _runtime_fingerprint(readback_runtime)

    if (
        readback_version != baseline_version + 1
        or readback_epoch != target_epoch
        or readback_fp != runtime_fp
    ):
        mismatch = _append_execution_event(
            action="EXECUTION_READBACK_MISMATCH",
            execution_id=execution_id,
            supervised_command_id=supervised_command_id,
            actor="ATLAS_SYSTEM",
            note="Post-write command readback did not exactly match the authorized payload.",
            metadata={
                "expected_command_version": baseline_version + 1,
                "actual_command_version": readback_version,
                "expected_policy_epoch": target_epoch,
                "actual_policy_epoch": readback_epoch,
                "expected_runtime_fingerprint": runtime_fp,
                "actual_runtime_fingerprint": readback_fp,
                "backup_file": str(backup_file),
            },
        )
        raise SupervisedExecutionError(
            "COMMAND_READBACK_MISMATCH",
            "The command file was written but readback verification failed. Treat state as requiring manual inspection.",
            500,
            {
                "execution_id": execution_id,
                "event_hash": mismatch.get("event_hash"),
                "backup_file": str(backup_file),
            },
        )

    executed = _append_execution_event(
        action="EXECUTED",
        execution_id=execution_id,
        supervised_command_id=supervised_command_id,
        actor=actor,
        note=note,
        metadata={
            "source_proposal_id": source.get("proposal_id"),
            "command_version": readback_version,
            "policy_epoch": readback_epoch,
            "runtime_fingerprint": readback_fp,
            "risk_state": risk.get("state"),
            "risk_score": risk.get("score"),
            "authorized_event_hash": authorized.get("event_hash"),
            "backup_file": str(backup_file),
        },
    )

    awaiting_ack = _append_execution_event(
        action="AWAITING_NYAO_ACK",
        execution_id=execution_id,
        supervised_command_id=supervised_command_id,
        actor="ATLAS_SYSTEM",
        note="commands.json write and readback succeeded; awaiting Nyao applied-command acknowledgement.",
        metadata={
            "expected_applied_command_version": readback_version,
            "expected_policy_epoch": readback_epoch,
            "runtime_fingerprint": readback_fp,
            "status": "AWAITING_NYAO_ACK",
        },
    )

    return {
        "supervised_execution_version": "0.8.1",
        "mode": "SUPERVISED_EXECUTION",
        "execution_id": execution_id,
        "status": "EXECUTED",
        "executed_at": executed.get("timestamp"),
        "executed_by": actor,
        "source": {
            "supervised_command_id": supervised_command_id,
            "proposal_id": source.get("proposal_id"),
            "runtime_fingerprint": runtime_fp,
            "review_snapshot_hash": source.get("review_snapshot_hash"),
        },
        "baseline": {
            "command_version": baseline_version,
            "policy_epoch": baseline_epoch,
        },
        "applied": {
            "command_version": readback_version,
            "policy_epoch": readback_epoch,
            "runtime_control_count": len(runtime),
            "runtime_fingerprint": readback_fp,
        },
        "risk_governor_execution_recheck": {
            **risk,
            "gate_passed": True,
        },
        "execution_environment": env_state,
        "backup_file": str(backup_file),
        "event": executed,
        "ack_lifecycle_event": awaiting_ack,
        "ack_status": "AWAITING_NYAO_ACK",
        "readback_verified": True,
        "warning": (
            "Atlas does not distinguish demo from live MT5 accounts for this "
            "execution path. Supervised execution requires an explicit, "
            "time-limited operator arm plus the existing approval, context, "
            "Risk Governor, runtime-integrity and replay checks."
        ),
    }
