from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from backend.app.intelligence.supervised_command_proposal import (
    get_supervised_command_proposal,
)
from backend.app.intelligence.supervised_execution_gate import (
    append_execution_lifecycle_event,
    get_execution_events,
)


ACK_TIMEOUT_ENV = "ATLAS_NYAO_ACK_TIMEOUT_SECONDS"
ACK_TEST_OVERRIDE_ENABLE_ENV = "ATLAS_ACK_TEST_OVERRIDE_ENABLED"
ACK_TEST_MODE_ENV = "ATLAS_ACK_TEST_MODE"
DEFAULT_ACK_TIMEOUT_SECONDS = 30.0

ACK_TEST_MODES = {
    "NONE",
    "FORCE_AWAITING",
    "FORCE_TIMEOUT",
    "FORCE_MISMATCH",
    "FORCE_SUPERSEDED",
}

TERMINAL_ACK_ACTIONS = {
    "NYAO_ACK_CONFIRMED": "CONFIRMED",
    "NYAO_ACK_TIMEOUT": "ACK_TIMEOUT",
    "NYAO_ACK_MISMATCH": "ACK_MISMATCH",
    "NYAO_ACK_SUPERSEDED_UNCONFIRMED": "SUPERSEDED_UNCONFIRMED",
}


class NyaoAckError(Exception):
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


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _ack_timeout_seconds() -> float:
    raw = str(os.getenv(ACK_TIMEOUT_ENV, "")).strip()
    if not raw:
        return DEFAULT_ACK_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_ACK_TIMEOUT_SECONDS
    return max(1.0, min(value, 3600.0))


def _env_true(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def _ack_test_mode(
    *,
    execution: dict[str, Any],
    supervised_command_id: str,
) -> dict[str, Any]:
    """
    Test-only ACK observation override.

    This can never write commands.json or mutate Nyao. It is permitted only
    when:
      1) ATLAS_ACK_TEST_OVERRIDE_ENABLED=true
      2) the source supervised command came from a TEST_OVERRIDE proposal
    """
    enabled = _env_true(ACK_TEST_OVERRIDE_ENABLE_ENV)
    raw_mode = str(os.getenv(ACK_TEST_MODE_ENV, "NONE")).strip().upper() or "NONE"
    mode = raw_mode if raw_mode in ACK_TEST_MODES else "NONE"

    package = get_supervised_command_proposal(supervised_command_id)
    source = dict((package or {}).get("source") or {})
    test_source = bool(source.get("test_override_active"))

    active = enabled and test_source and mode != "NONE"
    return {
        "enabled": enabled,
        "source_is_test_override": test_source,
        "mode": mode,
        "active": active,
        "enable_environment_variable": ACK_TEST_OVERRIDE_ENABLE_ENV,
        "mode_environment_variable": ACK_TEST_MODE_ENV,
        "warning": (
            "ACK test override affects only Atlas acknowledgement observation "
            "for validation. It cannot write commands.json or mutate Nyao."
        ),
    }


def _apply_ack_test_observation(
    *,
    mode: str,
    target_version: int,
    target_epoch: int,
    applied_version: int | None,
    observed_epoch: int | None,
    elapsed_seconds: float,
    timeout_seconds: float,
) -> tuple[int | None, int | None, float]:
    if mode == "FORCE_AWAITING":
        return max(0, target_version - 1), target_epoch, 0.0
    if mode == "FORCE_TIMEOUT":
        return max(0, target_version - 1), target_epoch, timeout_seconds + 1.0
    if mode == "FORCE_MISMATCH":
        return target_version, target_epoch + 1, elapsed_seconds
    if mode == "FORCE_SUPERSEDED":
        return target_version + 1, target_epoch + 1, elapsed_seconds
    return applied_version, observed_epoch, elapsed_seconds


def _all_events_for_execution(execution_id: str) -> list[dict[str, Any]]:
    data = get_execution_events(limit=5000)
    events = [
        event
        for event in (data.get("events") or [])
        if event.get("execution_id") == execution_id
    ]
    return sorted(events, key=lambda event: int(event.get("sequence") or 0))


def _execution_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("action") in {"EXECUTED", "EXECUTED_RECOVERED"}:
            return event
    return None


def _terminal_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("action") in TERMINAL_ACK_ACTIONS:
            return event
    return None


def _first_wait_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event.get("action") == "AWAITING_NYAO_ACK":
            return event
    return None


def _status_applied_command_version(status: dict[str, Any]) -> int | None:
    for key in (
        "applied_command_version",
        "atlas_applied_command_version",
        "command_version_applied",
    ):
        if status.get(key) is not None:
            try:
                return int(status.get(key))
            except (TypeError, ValueError):
                return None
    return None


def _status_policy_epoch(status: dict[str, Any]) -> int | None:
    for key in (
        "policy_epoch",
        "atlas_policy_epoch",
        "current_policy_epoch",
        "runtime_policy_epoch",
    ):
        if status.get(key) is not None:
            try:
                return int(status.get(key))
            except (TypeError, ValueError):
                return None
    return None


def _runtime_field_match_summary(
    status: dict[str, Any],
    supervised_command_id: str,
) -> dict[str, Any]:
    package = get_supervised_command_proposal(supervised_command_id)
    if package is None:
        return {
            "available": False,
            "complete": False,
            "matched": None,
            "reason": "SUPERVISED_COMMAND_PACKAGE_NOT_FOUND",
        }

    runtime = dict((package.get("command_preview") or {}).get("runtime") or {})
    if not runtime:
        return {
            "available": False,
            "complete": False,
            "matched": None,
            "reason": "RUNTIME_PREVIEW_NOT_AVAILABLE",
        }

    present = 0
    matched = 0
    mismatches: list[dict[str, Any]] = []
    for key, expected in runtime.items():
        status_key = f"runtime_{key}"
        if status_key not in status:
            continue
        present += 1
        actual = status.get(status_key)
        if actual == expected:
            matched += 1
        elif len(mismatches) < 20:
            mismatches.append(
                {
                    "control": key,
                    "expected": expected,
                    "actual": actual,
                }
            )

    complete = present == len(runtime)
    return {
        "available": present > 0,
        "complete": complete,
        "present_control_count": present,
        "expected_control_count": len(runtime),
        "matched_control_count": matched,
        "matched": complete and matched == len(runtime),
        "mismatches": mismatches,
        "interpretation": (
            "Runtime telemetry is supplemental confirmation. "
            "The primary Nyao acknowledgement is exact applied_command_version + policy_epoch."
        ),
    }


def _ensure_wait_event(
    *,
    events: list[dict[str, Any]],
    execution: dict[str, Any],
) -> dict[str, Any]:
    existing = _first_wait_event(events)
    if existing is not None:
        return existing

    metadata = execution.get("metadata") or {}
    return append_execution_lifecycle_event(
        action="AWAITING_NYAO_ACK",
        execution_id=str(execution.get("execution_id") or ""),
        supervised_command_id=str(execution.get("supervised_command_id") or ""),
        actor="ATLAS_SYSTEM",
        note="Legacy/recovered execution entered Nyao acknowledgement tracking.",
        metadata={
            "expected_applied_command_version": metadata.get("command_version"),
            "expected_policy_epoch": metadata.get("policy_epoch"),
            "runtime_fingerprint": metadata.get("runtime_fingerprint"),
            "status": "AWAITING_NYAO_ACK",
            "reconciled_from_existing_execution": True,
        },
    )


def evaluate_nyao_ack(
    execution_id: str,
    *,
    current_status: dict[str, Any],
    record_transition: bool,
) -> dict[str, Any]:
    events = _all_events_for_execution(execution_id)
    execution = _execution_event(events)
    if execution is None:
        raise NyaoAckError(
            "EXECUTION_NOT_FOUND",
            "No completed supervised execution exists for this execution_id.",
            404,
            {"execution_id": execution_id},
        )

    terminal = _terminal_event(events)
    if terminal is not None:
        action = str(terminal.get("action") or "")
        return {
            "ack_version": "0.8",
            "execution_id": execution_id,
            "supervised_command_id": execution.get("supervised_command_id"),
            "state": TERMINAL_ACK_ACTIONS[action],
            "terminal": True,
            "terminal_event": terminal,
            "current_observation": {
                "applied_command_version": _status_applied_command_version(current_status),
                "policy_epoch": _status_policy_epoch(current_status),
            },
            "runtime_telemetry_confirmation": _runtime_field_match_summary(
                current_status,
                str(execution.get("supervised_command_id") or ""),
            ),
        }

    if record_transition:
        wait_event = _ensure_wait_event(
            events=events,
            execution=execution,
        )
        events = _all_events_for_execution(execution_id)
    else:
        wait_event = _first_wait_event(events)

    metadata = execution.get("metadata") or {}
    target_version = int(metadata.get("command_version") or 0)
    target_epoch = int(metadata.get("policy_epoch") or 0)
    runtime_fingerprint = metadata.get("runtime_fingerprint")
    supervised_command_id = str(execution.get("supervised_command_id") or "")

    applied_version = _status_applied_command_version(current_status)
    observed_epoch = _status_policy_epoch(current_status)

    started_at = _parse_iso(
        (wait_event or {}).get("timestamp")
        or execution.get("timestamp")
    ) or _now_utc()
    elapsed_seconds = max(
        0.0,
        (_now_utc() - started_at).total_seconds(),
    )
    timeout_seconds = _ack_timeout_seconds()

    ack_test = _ack_test_mode(
        execution=execution,
        supervised_command_id=supervised_command_id,
    )
    raw_observation = {
        "applied_command_version": applied_version,
        "policy_epoch": observed_epoch,
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
    if ack_test.get("active"):
        applied_version, observed_epoch, elapsed_seconds = _apply_ack_test_observation(
            mode=str(ack_test.get("mode") or "NONE"),
            target_version=target_version,
            target_epoch=target_epoch,
            applied_version=applied_version,
            observed_epoch=observed_epoch,
            elapsed_seconds=elapsed_seconds,
            timeout_seconds=timeout_seconds,
        )

    runtime_summary = _runtime_field_match_summary(
        current_status,
        supervised_command_id,
    )

    state = "AWAITING_NYAO_ACK"
    event_action = None
    reason = "Waiting for exact Nyao applied_command_version and policy_epoch acknowledgement."

    if applied_version == target_version and observed_epoch == target_epoch:
        state = "CONFIRMED"
        event_action = "NYAO_ACK_CONFIRMED"
        reason = "Nyao acknowledged the exact executed command_version and policy_epoch."
    elif (
        applied_version == target_version
        and observed_epoch is not None
        and observed_epoch != target_epoch
    ):
        state = "ACK_MISMATCH"
        event_action = "NYAO_ACK_MISMATCH"
        reason = "Nyao applied_command_version matched but policy_epoch did not."
    elif applied_version is not None and applied_version > target_version:
        state = "SUPERSEDED_UNCONFIRMED"
        event_action = "NYAO_ACK_SUPERSEDED_UNCONFIRMED"
        reason = (
            "Nyao is already reporting a newer applied command before this execution "
            "was independently confirmed."
        )
    elif elapsed_seconds >= timeout_seconds:
        state = "ACK_TIMEOUT"
        event_action = "NYAO_ACK_TIMEOUT"
        reason = "Nyao did not acknowledge the exact target before the configured timeout."

    transition_event = None
    if record_transition and event_action is not None:
        # Re-read to make the refresh idempotent.
        latest_events = _all_events_for_execution(execution_id)
        latest_terminal = _terminal_event(latest_events)
        if latest_terminal is None:
            transition_event = append_execution_lifecycle_event(
                action=event_action,
                execution_id=execution_id,
                supervised_command_id=supervised_command_id,
                actor="ATLAS_SYSTEM",
                note=reason,
                metadata={
                    "expected_applied_command_version": target_version,
                    "observed_applied_command_version": applied_version,
                    "expected_policy_epoch": target_epoch,
                    "observed_policy_epoch": observed_epoch,
                    "runtime_fingerprint": runtime_fingerprint,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "timeout_seconds": timeout_seconds,
                    "runtime_telemetry_confirmation": runtime_summary,
                    "ack_test_override": ack_test,
                    "raw_nyao_observation": raw_observation,
                },
            )
        else:
            transition_event = latest_terminal
            state = TERMINAL_ACK_ACTIONS.get(
                str(latest_terminal.get("action") or ""),
                state,
            )

    return {
        "ack_version": "0.8",
        "mode": "NYAO_EXECUTION_CONFIRMATION",
        "execution_id": execution_id,
        "supervised_command_id": supervised_command_id,
        "state": state,
        "terminal": state != "AWAITING_NYAO_ACK",
        "reason": reason,
        "expected": {
            "applied_command_version": target_version,
            "policy_epoch": target_epoch,
            "runtime_fingerprint": runtime_fingerprint,
        },
        "observed": {
            "applied_command_version": applied_version,
            "policy_epoch": observed_epoch,
        },
        "timing": {
            "tracking_started_at": started_at.isoformat(),
            "elapsed_seconds": round(elapsed_seconds, 3),
            "timeout_seconds": timeout_seconds,
            "timeout_environment_variable": ACK_TIMEOUT_ENV,
        },
        "runtime_telemetry_confirmation": runtime_summary,
        "ack_test_override": ack_test,
        "raw_nyao_observation": raw_observation,
        "transition_recorded": transition_event is not None,
        "transition_event": transition_event,
        "confirmation_contract": [
            "CONFIRMED requires exact Nyao applied_command_version equality.",
            "CONFIRMED requires exact Nyao policy_epoch equality.",
            "A newer Nyao command does not retroactively prove this execution was consumed.",
            "Timeout is evaluated on acknowledgement refresh/access; there is no background scheduler in v0.7.",
            "Runtime-control telemetry matching is supplemental when all runtime_* fields are available.",
        ],
    }


def find_latest_execution_id(
    *,
    supervised_command_id: str | None = None,
) -> str | None:
    data = get_execution_events(
        limit=5000,
        supervised_command_id=supervised_command_id,
    )
    for event in data.get("events") or []:
        if event.get("action") in {"EXECUTED", "EXECUTED_RECOVERED"}:
            return str(event.get("execution_id") or "") or None
    return None