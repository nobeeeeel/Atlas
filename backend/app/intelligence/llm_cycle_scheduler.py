from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SCHEDULE_FILE = DATA_DIR / "llm_cycle_schedule.json"

DEFAULT_INTERVAL_MINUTES = 240
MIN_INTERVAL_MINUTES = 15
MIN_DWELL_MINUTES = 30
MAX_INTERVAL_MINUTES = 24 * 60
MAX_RUN_HISTORY = 300
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (TypeError, ValueError):
        return None


def _default() -> dict[str, Any]:
    now = _now()
    return {
        "version": 1,
        "enabled": False,
        "interval_minutes": DEFAULT_INTERVAL_MINUTES,
        "execution_mode": "SUPERVISED",
        "minimum_dwell_minutes": DEFAULT_INTERVAL_MINUTES,
        "minimum_confidence": 70.0,
        "running": False,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "next_run_at": None,
        "last_started_at": None,
        "last_completed_at": None,
        "last_trigger": None,
        "last_status": "NEVER_RUN",
        "last_error": None,
        "last_llm_proposal_id": None,
        "last_advisory_proposal_id": None,
        "last_critic_verdict": None,
        "last_auto_apply_status": "NEVER_APPLIED",
        "last_auto_applied_at": None,
        "last_auto_command_version": None,
        "last_auto_policy_epoch": None,
        "last_auto_zone_policy_epoch": None,
        "auto_apply_eligible_at": None,
        "run_count": 0,
        "run_history": [],
    }


def _read_unlocked() -> dict[str, Any]:
    if not SCHEDULE_FILE.exists():
        return _default()
    try:
        value = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default()
    merged = {**_default(), **value} if isinstance(value, dict) else _default()
    if not isinstance(merged.get("run_history"), list):
        merged["run_history"] = []
    return merged


def _write_unlocked(value: dict[str, Any]) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(SCHEDULE_FILE.parent),
        prefix=f".{SCHEDULE_FILE.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, SCHEDULE_FILE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _public(value: dict[str, Any]) -> dict[str, Any]:
    next_run = _parse(value.get("next_run_at"))
    seconds = max(0.0, (next_run - _now()).total_seconds()) if next_run else None
    last_applied = _parse(value.get("last_auto_applied_at"))
    explicit_eligible = _parse(value.get("auto_apply_eligible_at"))
    dwell_seconds = int(value.get("minimum_dwell_minutes") or 0) * 60
    auto_eligible_seconds = (
        max(0.0, (explicit_eligible - _now()).total_seconds())
        if explicit_eligible
        else
        max(0.0, dwell_seconds - (_now() - last_applied).total_seconds())
        if last_applied
        else 0.0
    )
    return {
        **value,
        "seconds_until_next_run": round(seconds, 3) if seconds is not None else None,
        "schedule_file": str(SCHEDULE_FILE),
        "execution_authority": (
            "VALIDATED_AUTONOMOUS" if value.get("execution_mode") == "AUTONOMOUS"
            else "PROPOSAL_ONLY"
        ),
        "manual_application_required": value.get("execution_mode") != "AUTONOMOUS",
        "seconds_until_auto_apply_eligible": round(auto_eligible_seconds, 3),
    }


def get_llm_cycle_schedule() -> dict[str, Any]:
    with _LOCK:
        value = _read_unlocked()
    return _public(value)


def update_llm_cycle_schedule(
    *,
    enabled: bool,
    interval_minutes: int,
    execution_mode: str = "SUPERVISED",
    minimum_dwell_minutes: int | None = None,
    minimum_confidence: float = 70.0,
) -> dict[str, Any]:
    interval = max(
        MIN_INTERVAL_MINUTES,
        min(int(interval_minutes), MAX_INTERVAL_MINUTES),
    )
    now = _now()
    mode = str(execution_mode or "SUPERVISED").upper()
    if mode not in {"SUPERVISED", "AUTONOMOUS"}:
        raise ValueError("execution_mode must be SUPERVISED or AUTONOMOUS.")
    dwell = max(
        MIN_DWELL_MINUTES,
        min(int(minimum_dwell_minutes or interval), MAX_INTERVAL_MINUTES),
    )
    with _LOCK:
        value = _read_unlocked()
        value.update({
            "enabled": bool(enabled),
            "interval_minutes": interval,
            "execution_mode": mode,
            "minimum_dwell_minutes": dwell,
            "minimum_confidence": max(0.0, min(float(minimum_confidence), 100.0)),
            "updated_at": _iso(now),
            "next_run_at": (
                _iso(now + timedelta(minutes=interval)) if enabled else None
            ),
        })
        _write_unlocked(value)
    return _public(value)


def record_autonomous_application(
    *,
    status: str,
    command_version: int | None = None,
    policy_epoch: int | None = None,
    zone_policy_epoch: int | None = None,
    eligible_at: datetime | None = None,
) -> dict[str, Any]:
    now = _now()
    with _LOCK:
        value = _read_unlocked()
        value["last_auto_apply_status"] = status
        if status == "APPLIED":
            value["last_auto_applied_at"] = _iso(now)
            value["auto_apply_eligible_at"] = _iso(
                now + timedelta(minutes=int(value.get("minimum_dwell_minutes") or 0))
            )
        elif eligible_at is not None:
            value["auto_apply_eligible_at"] = _iso(eligible_at)
        if command_version is not None:
            value["last_auto_command_version"] = int(command_version)
        if policy_epoch is not None:
            value["last_auto_policy_epoch"] = int(policy_epoch)
        if zone_policy_epoch is not None:
            value["last_auto_zone_policy_epoch"] = int(zone_policy_epoch)
        value["updated_at"] = _iso(now)
        _write_unlocked(value)
    return _public(value)


def claim_llm_cycle(*, trigger: str, force: bool = False) -> dict[str, Any]:
    now = _now()
    with _LOCK:
        value = _read_unlocked()
        due = bool(
            value.get("enabled")
            and _parse(value.get("next_run_at"))
            and _parse(value.get("next_run_at")) <= now
        )
        if value.get("running"):
            return {"claimed": False, "reason": "ALREADY_RUNNING", **_public(value)}
        if not force and not due:
            return {"claimed": False, "reason": "NOT_DUE", **_public(value)}
        interval = int(value.get("interval_minutes") or DEFAULT_INTERVAL_MINUTES)
        value.update({
            "running": True,
            "last_started_at": _iso(now),
            "last_trigger": trigger,
            "last_status": "RUNNING",
            "last_error": None,
            "updated_at": _iso(now),
            "next_run_at": (
                _iso(now + timedelta(minutes=interval))
                if value.get("enabled")
                else None
            ),
        })
        _write_unlocked(value)
    return {"claimed": True, "reason": "CLAIMED", **_public(value)}


def complete_llm_cycle(
    *,
    status: str,
    llm_proposal_id: str | None = None,
    advisory_proposal_id: str | None = None,
    critic_verdict: str | None = None,
    error: str | None = None,
    run_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    with _LOCK:
        value = _read_unlocked()
        run_number = int(value.get("run_count") or 0) + 1
        completed_at = _iso(now)
        value.update({
            "running": False,
            "last_completed_at": completed_at,
            "last_status": status,
            "last_error": error,
            "last_llm_proposal_id": llm_proposal_id,
            "last_advisory_proposal_id": advisory_proposal_id,
            "last_critic_verdict": critic_verdict,
            "run_count": run_number,
            "updated_at": completed_at,
        })
        row = {
            "run_number": run_number,
            "started_at": value.get("last_started_at"),
            "completed_at": completed_at,
            "trigger": value.get("last_trigger"),
            "status": status,
            "llm_proposal_id": llm_proposal_id,
            "advisory_proposal_id": advisory_proposal_id,
            "critic_verdict": critic_verdict,
            "error": error,
            **dict(run_record or {}),
        }
        history = [dict(item) for item in list(value.get("run_history") or []) if isinstance(item, dict)]
        history.append(row)
        value["run_history"] = history[-MAX_RUN_HISTORY:]
        _write_unlocked(value)
    return _public(value)


def recover_interrupted_llm_cycle() -> dict[str, Any]:
    """Release a persisted running claim left behind by a process restart."""
    now = _now()
    with _LOCK:
        value = _read_unlocked()
        if value.get("running"):
            value.update({
                "running": False,
                "last_completed_at": _iso(now),
                "last_status": "INTERRUPTED_BY_RESTART",
                "last_error": "Atlas restarted before the policy cycle completed.",
                "updated_at": _iso(now),
            })
            _write_unlocked(value)
    return _public(value)
