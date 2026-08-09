from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.advisory_policy_proposal import (
    get_advisory_policy_proposal,
)
from backend.app.intelligence.advisory_review_workflow import (
    get_proposal_review_status,
)
from backend.app.intelligence.risk_governor import assess_risk


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SUPERVISED_COMMAND_STORE_FILE = DATA_DIR / "supervised_command_proposals.json"

_STORE_LOCK = threading.Lock()
MAX_SUPERVISED_COMMAND_PROPOSALS = 10_000
EXPECTED_RUNTIME_CONTROL_COUNT = 157


class SupervisedCommandBuildError(Exception):
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


def _canonical_hash(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _runtime_fingerprint(runtime: dict[str, Any]) -> str:
    return _canonical_hash(runtime)[:16]


def _empty_store() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "proposal_count": 0,
        "proposals": [],
    }


def _read_store_unlocked() -> dict[str, Any]:
    if not SUPERVISED_COMMAND_STORE_FILE.exists():
        return _empty_store()
    try:
        with SUPERVISED_COMMAND_STORE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_store()
    if not isinstance(data, dict) or not isinstance(data.get("proposals"), list):
        return _empty_store()
    return data


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _persist_supervised_command_proposal(
    command_proposal: dict[str, Any],
) -> dict[str, Any]:
    command_id = command_proposal["supervised_command_id"]
    now = _now_iso()
    with _STORE_LOCK:
        store = _read_store_unlocked()
        proposals = list(store.get("proposals") or [])
        index = next(
            (
                i for i, item in enumerate(proposals)
                if item.get("supervised_command_id") == command_id
            ),
            None,
        )
        if index is None:
            stored = {
                **command_proposal,
                "first_built_at": now,
                "last_built_at": now,
                "build_count": 1,
            }
            proposals.append(stored)
            action = "CREATED"
        else:
            existing = proposals[index]
            stored = {
                **command_proposal,
                "first_built_at": existing.get("first_built_at") or now,
                "last_built_at": now,
                "build_count": int(existing.get("build_count") or 0) + 1,
            }
            proposals[index] = stored
            action = "UPDATED_EXISTING"

        if len(proposals) > MAX_SUPERVISED_COMMAND_PROPOSALS:
            proposals = proposals[-MAX_SUPERVISED_COMMAND_PROPOSALS:]

        store["proposals"] = proposals
        store["proposal_count"] = len(proposals)
        store["updated_at"] = now
        _atomic_write(SUPERVISED_COMMAND_STORE_FILE, store)

    return {
        "persisted": True,
        "action": action,
        "supervised_command_id": command_id,
        "proposal_count": len(proposals),
        "store_file": str(SUPERVISED_COMMAND_STORE_FILE),
    }


def get_supervised_command_proposals(limit: int = 100) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 1000))
    with _STORE_LOCK:
        store = _read_store_unlocked()
        proposals = list(store.get("proposals") or [])
    return {
        "proposal_count": len(proposals),
        "returned_count": min(safe_limit, len(proposals)),
        "proposals": proposals[-safe_limit:][::-1],
        "store_file": str(SUPERVISED_COMMAND_STORE_FILE),
    }


def get_supervised_command_proposal(
    supervised_command_id: str,
) -> dict[str, Any] | None:
    with _STORE_LOCK:
        store = _read_store_unlocked()
        for item in store.get("proposals") or []:
            if item.get("supervised_command_id") == supervised_command_id:
                return item
    return None


def _validate_exact_approval(
    proposal: dict[str, Any],
    review_status: dict[str, Any],
    *,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
    expected_review_snapshot_hash: str,
) -> dict[str, Any]:
    approval = dict(review_status.get("approval") or {})

    if approval.get("status") != "APPROVED" or not bool(approval.get("approved")):
        raise SupervisedCommandBuildError(
            "PROPOSAL_NOT_APPROVED",
            "Only an active APPROVED advisory proposal can produce a supervised command proposal.",
            409,
            {"approval_status": approval.get("status")},
        )

    actual_fp = str(proposal.get("runtime_fingerprint") or "")
    actual_epoch = int(proposal.get("proposed_policy_epoch") or 0)
    actual_snapshot = str(review_status.get("review_snapshot_hash") or "")

    if expected_runtime_fingerprint != actual_fp:
        raise SupervisedCommandBuildError(
            "RUNTIME_FINGERPRINT_MISMATCH",
            "The approved runtime fingerprint does not match the expected value.",
            409,
            {"expected": expected_runtime_fingerprint, "actual": actual_fp},
        )
    if int(expected_proposed_policy_epoch) != actual_epoch:
        raise SupervisedCommandBuildError(
            "PROPOSED_EPOCH_MISMATCH",
            "The approved policy epoch does not match the expected value.",
            409,
            {"expected": int(expected_proposed_policy_epoch), "actual": actual_epoch},
        )
    if expected_review_snapshot_hash != actual_snapshot:
        raise SupervisedCommandBuildError(
            "REVIEW_SNAPSHOT_MISMATCH",
            "The approved review snapshot does not match the expected value.",
            409,
            {"expected": expected_review_snapshot_hash, "actual": actual_snapshot},
        )

    approval_fp = str(approval.get("approval_runtime_fingerprint") or "")
    approval_epoch = int(approval.get("approval_proposed_policy_epoch") or 0)
    approval_snapshot = str(approval.get("approval_snapshot_hash") or "")

    if (
        approval_fp != actual_fp
        or approval_epoch != actual_epoch
        or approval_snapshot != actual_snapshot
    ):
        raise SupervisedCommandBuildError(
            "APPROVAL_BINDING_MISMATCH",
            "Stored approval bindings no longer exactly match the advisory proposal.",
            409,
            {
                "proposal_runtime_fingerprint": actual_fp,
                "approval_runtime_fingerprint": approval_fp,
                "proposal_policy_epoch": actual_epoch,
                "approval_policy_epoch": approval_epoch,
                "review_snapshot_hash": actual_snapshot,
                "approval_snapshot_hash": approval_snapshot,
            },
        )
    return approval


def _validate_current_context(
    proposal: dict[str, Any],
    current_proposal: dict[str, Any],
) -> None:
    comparisons = {
        "proposal_id": (proposal.get("proposal_id"), current_proposal.get("proposal_id")),
        "runtime_fingerprint": (
            proposal.get("runtime_fingerprint"),
            current_proposal.get("runtime_fingerprint"),
        ),
        "proposed_policy_epoch": (
            proposal.get("proposed_policy_epoch"),
            current_proposal.get("proposed_policy_epoch"),
        ),
    }
    mismatches = {
        key: {"approved": old, "current": current}
        for key, (old, current) in comparisons.items()
        if old != current
    }
    if mismatches:
        raise SupervisedCommandBuildError(
            "STALE_APPROVAL_CONTEXT",
            "The approved advisory proposal is no longer Atlas's exact current proposal.",
            409,
            mismatches,
        )


def build_supervised_command_proposal(
    proposal_id: str,
    *,
    current_proposal: dict[str, Any],
    current_status: dict[str, Any],
    current_command: dict[str, Any],
    reviewer: str,
    note: str | None,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
    expected_review_snapshot_hash: str,
) -> dict[str, Any]:
    """
    Build a non-executing command candidate from an exact active approval.

    No commands.json write occurs here.
    """
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise SupervisedCommandBuildError(
            "PROPOSAL_NOT_FOUND",
            "Advisory proposal not found.",
            404,
        )

    review_status = get_proposal_review_status(proposal_id)
    approval = _validate_exact_approval(
        proposal,
        review_status,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        expected_proposed_policy_epoch=expected_proposed_policy_epoch,
        expected_review_snapshot_hash=expected_review_snapshot_hash,
    )
    _validate_current_context(proposal, current_proposal)

    runtime = dict(proposal.get("proposed_runtime") or {})
    runtime_count = len(runtime)
    calculated_runtime_fp = _runtime_fingerprint(runtime)

    if runtime_count != EXPECTED_RUNTIME_CONTROL_COUNT:
        raise SupervisedCommandBuildError(
            "RUNTIME_CONTROL_COUNT_MISMATCH",
            "The approved proposal does not contain the complete 157-control runtime.",
            409,
            {"expected": EXPECTED_RUNTIME_CONTROL_COUNT, "actual": runtime_count},
        )
    if calculated_runtime_fp != proposal.get("runtime_fingerprint"):
        raise SupervisedCommandBuildError(
            "RUNTIME_PAYLOAD_FINGERPRINT_MISMATCH",
            "The full runtime payload no longer matches the approved fingerprint.",
            409,
            {
                "expected": proposal.get("runtime_fingerprint"),
                "actual": calculated_runtime_fp,
            },
        )

    risk = assess_risk(current_status)
    risk_gate_passed = not bool(risk.get("veto_new_risk"))

    current_command_version = int(current_command.get("command_version") or 0)
    current_policy_epoch = int(current_command.get("policy_epoch") or 0)
    target_policy_epoch = int(proposal.get("proposed_policy_epoch") or 0)

    if target_policy_epoch < current_policy_epoch:
        raise SupervisedCommandBuildError(
            "POLICY_EPOCH_REGRESSION",
            "The approved proposal would regress the current policy epoch.",
            409,
            {
                "current_policy_epoch": current_policy_epoch,
                "target_policy_epoch": target_policy_epoch,
            },
        )

    build_identity = {
        "builder_version": "0.5",
        "source_proposal_id": proposal_id,
        "runtime_fingerprint": proposal.get("runtime_fingerprint"),
        "proposed_policy_epoch": target_policy_epoch,
        "approval_snapshot_hash": approval.get("approval_snapshot_hash"),
        "baseline_command_version": current_command_version,
        "baseline_policy_epoch": current_policy_epoch,
    }
    supervised_command_id = _canonical_hash(build_identity)[:20]

    state = (
        "READY_FOR_SECOND_HUMAN_ACTION"
        if risk_gate_passed
        else "BLOCKED_BY_RISK_GOVERNOR"
    )

    result = {
        "supervised_command_version": "0.5",
        "mode": "SUPERVISED_COMMAND_PROPOSAL",
        "supervised_command_id": supervised_command_id,
        "state": state,
        "built_at": _now_iso(),
        "built_by": reviewer or "human_operator",
        "note": note,
        "source": {
            "proposal_id": proposal_id,
            "selected_candidate": proposal.get("selected_candidate"),
            "readiness_source": proposal.get("readiness_source"),
            "test_override_active": bool(proposal.get("test_override_active")),
            "runtime_fingerprint": proposal.get("runtime_fingerprint"),
            "proposed_policy_epoch": target_policy_epoch,
            "review_snapshot_hash": review_status.get("review_snapshot_hash"),
            "approval_status": approval.get("status"),
            "approved_by": approval.get("approved_by"),
            "approved_at": approval.get("approved_at"),
            "approval_runtime_fingerprint": approval.get("approval_runtime_fingerprint"),
            "approval_proposed_policy_epoch": approval.get("approval_proposed_policy_epoch"),
            "approval_snapshot_hash": approval.get("approval_snapshot_hash"),
        },
        "current_context": {
            "current_proposal_id": current_proposal.get("proposal_id"),
            "current_runtime_fingerprint": current_proposal.get("runtime_fingerprint"),
            "current_proposed_policy_epoch": current_proposal.get("proposed_policy_epoch"),
            "baseline_command_version": current_command_version,
            "baseline_policy_epoch": current_policy_epoch,
            "exact_context_match": True,
        },
        "risk_governor_recheck": {
            **risk,
            "gate_passed": risk_gate_passed,
            "interpretation": (
                "Risk Governor is re-evaluated at command-build time. "
                "A veto blocks future execution eligibility but does not alter Nyao."
            ),
        },
        "command_preview": {
            "hypothetical_command_version": current_command_version + 1,
            "target_policy_epoch": target_policy_epoch,
            "runtime_control_count": runtime_count,
            "runtime_fingerprint": calculated_runtime_fp,
            "runtime": runtime,
            "updated_at": "<SET_ONLY_AT_FUTURE_EXECUTION_TIME>",
        },
        "second_human_action": {
            "required": True,
            "implemented": False,
            "status": "NOT_AVAILABLE_IN_V0.5",
            "future_rule": (
                "A separate explicit human action must re-check approval, "
                "current context, command baseline, Risk Governor and runtime "
                "validation before any command write."
            ),
        },
        "execution": {
            "eligible_for_future_execution": risk_gate_passed,
            "allowed": False,
            "commands_json_write": False,
            "nyao_mutation": False,
            "reason": (
                "v0.5 builds a supervised command proposal only. "
                "No execution endpoint exists in this version."
            ),
        },
        "safety_contract": [
            "Source advisory proposal must still be actively APPROVED.",
            "Approval must match runtime fingerprint, proposed epoch, and review snapshot.",
            "Approved proposal must still be Atlas's exact current proposal.",
            "Complete runtime must contain exactly 157 controls.",
            "Runtime payload hash must match the approved fingerprint.",
            "Risk Governor is re-checked from current Nyao status.",
            "Current command version/policy epoch are captured as a baseline only.",
            "No commands.json write occurs in v0.5.",
            "No Nyao parameter mutation occurs in v0.5.",
            "A separate second human action is required in a future version.",
        ],
    }

    persistence = _persist_supervised_command_proposal(result)
    return {
        "supervised_command_proposal": result,
        "persistence": persistence,
    }