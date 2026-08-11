from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.regime import classify_regime
from backend.app.intelligence.risk_units import build_risk_units

VERSION = "atlas-brain-event-bus-v3"
PRIORITY = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
REGIME_CONFIRM_SECONDS = 120


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _state_file(outcomes: dict[str, Any] | None) -> Path | None:
    raw = str((outcomes or {}).get("file") or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve().with_name("brain_event_bus.json")
    except (OSError, RuntimeError, ValueError):
        return None


def _read(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write(path: Path | None, value: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".atlas-events-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(value, h, indent=2, ensure_ascii=False, default=str)
            h.flush()
            os.fsync(h.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def detect_brain_events(status: dict[str, Any], outcomes: dict[str, Any] | None) -> dict[str, Any]:
    path = _state_file(outcomes)
    store = _read(path)
    risk = build_risk_units(outcomes)
    regime = classify_regime(status)
    account = str((outcomes or {}).get("account_fingerprint") or status.get("account_fingerprint") or "")
    symbol = str(status.get("symbol") or "")

    same_scope = (
        bool(store)
        and (not store.get("account_fingerprint") or store.get("account_fingerprint") == account)
        and (not store.get("symbol") or store.get("symbol") == symbol)
    )
    if not same_scope:
        store = {}

    # v2 could detect/consume events in UNIDENTIFIED_ACCOUNT from background
    # loops while the dashboard showed the real account's untouched queue.  On
    # the v3 account-scope migration, never replay those stale pending rows into
    # Gemini.  Preserve them as migration lineage and continue from the durable
    # observation watermark already stored for this account.
    if store and str(store.get("version") or "") != VERSION:
        migrated_at = _now()
        prior_history = list(store.get("history") or [])
        for row in list(store.get("pending_events") or []):
            if isinstance(row, dict):
                prior_history.append({
                    **row,
                    "state": "MIGRATED_WATERMARKED",
                    "acknowledged_at": migrated_at,
                    "cycle_status": "NOT_REPLAYED_AFTER_V3_ACCOUNT_SCOPE_FIX",
                })
        store["history"] = prior_history[-200:]
        store["pending_events"] = []
        store["version"] = VERSION

    events = list(store.get("pending_events") or [])
    history = list(store.get("history") or [])
    seq = int(store.get("sequence") or 0)
    first_observation = not bool(store)

    def emit(kind: str, priority: str, payload: dict[str, Any]) -> None:
        nonlocal seq
        dedupe = f"{kind}:{payload.get('dedupe_key', '')}"
        if any(e.get("dedupe") == dedupe for e in events):
            return
        seq += 1
        events.append({
            "sequence": seq,
            "event": kind,
            "priority": priority,
            "state": "PENDING",
            "created_at": _now(),
            "dedupe": dedupe,
            "payload": payload,
        })

    completed_count = int(risk.get("completed_unit_count") or 0)
    prior_completed = int(store.get("observed_completed_unit_count") or 0)
    if not first_observation and completed_count > prior_completed:
        completed = [u for u in list(risk.get("units") or []) if u.get("eligible_for_loss_streak")]
        latest = completed[-1] if completed else {}
        unit_type = str(latest.get("unit_type") or "RISK_UNIT")
        kind = "RECOVERY_CHAIN_COMPLETED" if unit_type == "RECOVERY_CHAIN" else "RISK_UNIT_COMPLETED"
        emit(kind, "P1", {
            "dedupe_key": str(latest.get("unit_id") or completed_count),
            "completed_unit_count": completed_count,
            "unit": latest,
        })

    # Regime transitions are event-driven but debounced.  The first observation
    # establishes the watermark.  Thereafter a new classifier state must persist
    # for REGIME_CONFIRM_SECONDS before it becomes a material Brain event.  This
    # prevents TRANSITION/BULLISH/TRANSITION/RANGE flicker from spending Gemini
    # cycles while preserving fast P0/P1 execution and lifecycle events.
    current_regime = str(regime.get("regime") or "UNKNOWN")
    confirmed_regime = str(store.get("observed_regime") or "")
    confidence = float(regime.get("confidence") or 0.0)
    candidate_regime = str(store.get("candidate_regime") or "")
    candidate_since = _parse(store.get("candidate_regime_since"))

    if first_observation or not confirmed_regime:
        confirmed_regime = current_regime
        candidate_regime = ""
        candidate_since = None
    elif current_regime == confirmed_regime:
        candidate_regime = ""
        candidate_since = None
    elif confidence < 65.0:
        # Low-confidence classifier flicker cannot establish a material event.
        candidate_regime = ""
        candidate_since = None
    elif current_regime != candidate_regime:
        candidate_regime = current_regime
        candidate_since = _now_dt()
    elif candidate_since and _now_dt() - candidate_since >= timedelta(seconds=REGIME_CONFIRM_SECONDS):
        previous = confirmed_regime
        confirmed_regime = current_regime
        candidate_regime = ""
        candidate_since = None
        emit("REGIME_CHANGED", "P2", {
            "dedupe_key": f"{previous}->{current_regime}:{completed_count}",
            "from": previous,
            "to": current_regime,
            "confidence": confidence,
            "confirmation_seconds": REGIME_CONFIRM_SECONDS,
        })

    lifecycle_rows = status.get("recent_lifecycle_events") if isinstance(status.get("recent_lifecycle_events"), list) else []
    lifecycle_instance = int(status.get("lifecycle_contract_started_at_epoch") or 0)
    observed_lifecycle_instance = int(store.get("observed_lifecycle_instance") or 0)
    observed_lifecycle_sequence = int(store.get("observed_lifecycle_sequence") or 0) if observed_lifecycle_instance == lifecycle_instance else 0
    latest_lifecycle_sequence = max([int((row or {}).get("sequence") or 0) for row in lifecycle_rows if isinstance(row, dict)] or [0])
    if not first_observation:
        for row in lifecycle_rows:
            if not isinstance(row, dict):
                continue
            seq_value = int(row.get("sequence") or 0)
            if seq_value <= observed_lifecycle_sequence:
                continue
            action = str(row.get("action") or "UNKNOWN").upper()
            result = str(row.get("result") or "UNKNOWN").upper()
            payload = {
                "dedupe_key": f"{lifecycle_instance}:{seq_value}",
                "lifecycle_event": row,
                "action": action,
                "result": result,
            }
            if result in {"FAILED", "REJECTED"}:
                emit("EXECUTION_INTEGRITY_FAILURE", "P0", {**payload, "failure_type": action})
            elif action in {"HEDGE_OPEN", "HEDGE_GRADUATED", "RECOVERY_CHAIN_RELEASED"}:
                emit(action if action != "HEDGE_OPEN" else "HEDGE_OPENED", "P1", payload)
            elif action in {"BREAK_EVEN_LOCK", "BREAK_EVEN_OFFSET", "PROFIT_PROTECTION", "HEDGE_PROFIT_PROTECTION"}:
                emit("PROTECTION_LIFECYCLE_CHANGED", "P2", payload)

    # Backward-compatible preflight integrity inference exists only when the new
    # NYAO lifecycle contract is unavailable. Never mix inference with authoritative events.
    if not status.get("lifecycle_contract_version"):
        preflight_state = str(status.get("preflight_state") or "").upper()
        protection_state = str(status.get("preflight_protection_state") or "").upper()
        integrity = None
        if any(x in preflight_state for x in ("FAIL", "REJECT", "INVALID")):
            integrity = ("ENTRY_EXECUTION_FAILURE", preflight_state)
        elif any(x in protection_state for x in ("FAIL", "REJECT", "INVALID", "UNPROTECTED")):
            integrity = ("PROTECTION_MODIFICATION_FAILURE", protection_state)
        if integrity and not first_observation:
            emit("EXECUTION_INTEGRITY_FAILURE", "P0", {
                "dedupe_key": f"legacy:{integrity[0]}:{integrity[1]}:{completed_count}",
                "failure_type": integrity[0],
                "state": integrity[1],
                "source": "LEGACY_INFERENCE",
            })

    events.sort(key=lambda e: (PRIORITY.get(str(e.get("priority")), 9), int(e.get("sequence") or 0)))
    value = {
        "version": VERSION,
        "account_fingerprint": account,
        "symbol": symbol,
        "sequence": seq,
        "pending_events": events[-100:],
        # Preserve acknowledgement lineage; v2 accidentally dropped history on
        # every subsequent detect() call.
        "history": history[-200:],
        "observed_completed_unit_count": completed_count,
        "observed_regime": confirmed_regime,
        "candidate_regime": candidate_regime or None,
        "candidate_regime_since": candidate_since.isoformat() if candidate_since else None,
        "observed_lifecycle_sequence": latest_lifecycle_sequence,
        "observed_lifecycle_instance": lifecycle_instance,
        "regime_confidence": confidence,
        "regime_confirmation_seconds": REGIME_CONFIRM_SECONDS,
        "state_file": str(path) if path else None,
        "updated_at": _now(),
    }
    _write(path, value)
    return value


def next_brain_event(status: dict[str, Any], outcomes: dict[str, Any] | None) -> dict[str, Any] | None:
    store = detect_brain_events(status, outcomes)
    rows = list(store.get("pending_events") or [])
    return rows[0] if rows else None


def acknowledge_brain_event(
    outcomes: dict[str, Any] | None,
    sequence: int,
    *,
    cycle_status: str | None = None,
    llm_proposal_id: str | None = None,
) -> dict[str, Any]:
    path = _state_file(outcomes)
    store = _read(path)
    pending = list(store.get("pending_events") or [])
    target = None
    remain = []
    for row in pending:
        if int(row.get("sequence") or 0) == int(sequence):
            target = row
        else:
            remain.append(row)
    history = list(store.get("history") or [])
    if target:
        history.append({
            **target,
            "state": "ACKNOWLEDGED",
            "acknowledged_at": _now(),
            "cycle_status": cycle_status,
            "llm_proposal_id": llm_proposal_id,
        })
    store.update({
        "pending_events": remain,
        "history": history[-200:],
        "updated_at": _now(),
    })
    _write(path, store)
    return {
        "acknowledged": bool(target),
        "event": target,
        "pending_count": len(remain),
        "state_file": str(path) if path else None,
    }
