from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "atlas-drawdown-risk-efficiency-v1"
REVIEW_DRAWdown_PCT = 3.0
ELEVATED_DRAWDOWN_PCT = 5.0
EMERGENCY_DRAWDOWN_PCT = 8.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def drawdown_band(drawdown_pct: float) -> str:
    if drawdown_pct >= EMERGENCY_DRAWDOWN_PCT:
        return "EMERGENCY"
    if drawdown_pct >= ELEVATED_DRAWDOWN_PCT:
        return "ELEVATED"
    if drawdown_pct >= REVIEW_DRAWdown_PCT:
        return "REVIEW"
    return "NORMAL"


def _rank(band: str) -> int:
    return {"NORMAL": 0, "REVIEW": 1, "ELEVATED": 2, "EMERGENCY": 3}.get(str(band).upper(), 0)


def _state_file(outcomes: dict[str, Any] | None) -> Path | None:
    raw = str((outcomes or {}).get("file") or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve().with_name("drawdown_risk_efficiency.json")
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
    fd, tmp = tempfile.mkstemp(prefix=".atlas-drawdown-efficiency-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def evaluate_drawdown_review(status: dict[str, Any], outcomes: dict[str, Any] | None) -> dict[str, Any]:
    drawdown = float(status.get("equity_drawdown_pct") or status.get("drawdown_pct") or 0.0)
    band = drawdown_band(drawdown)
    path = _state_file(outcomes)
    stored = _read(path)
    account = str((outcomes or {}).get("account_fingerprint") or status.get("account_fingerprint") or "")
    symbol = str(status.get("symbol") or "")
    same_scope = (
        bool(stored)
        and (not stored.get("account_fingerprint") or str(stored.get("account_fingerprint")) == account)
        and (not stored.get("symbol") or str(stored.get("symbol")) == symbol)
    )
    if not same_scope:
        stored = {}

    reviewed_band = str(stored.get("reviewed_band") or "NORMAL").upper()
    pending_band = str(stored.get("pending_band") or "").upper()
    pending = bool(stored.get("pending"))

    # Recovery below a previously reviewed band re-arms that boundary for a
    # future upward transition. No Brain call is needed just for improvement.
    if _rank(band) < _rank(reviewed_band) and not pending:
        reviewed_band = band

    # An upward transition into REVIEW/ELEVATED/EMERGENCY is a reasoning event.
    # REVIEW/ELEVATED do not pause or shrink trading. EMERGENCY remains governed
    # by the deterministic Risk Governor's >=8% hard veto.
    if band != "NORMAL" and _rank(band) > max(_rank(reviewed_band), _rank(pending_band) if pending else -1):
        pending = True
        pending_band = band
        stored["requested_at"] = _now()
        stored["trigger"] = "DRAWDOWN_BAND_ESCALATION"

    value = {
        **stored,
        "version": VERSION,
        "account_fingerprint": account,
        "symbol": symbol,
        "drawdown_pct": round(drawdown, 6),
        "band": band,
        "pending": pending,
        "pending_band": pending_band if pending else None,
        "reviewed_band": reviewed_band,
        "trading_paused_for_review": False,
        "automatic_size_decay": False,
        "emergency_veto_pct": EMERGENCY_DRAWDOWN_PCT,
        "state_file": str(path) if path else None,
        "updated_at": _now(),
    }
    _write(path, value)
    return value


def acknowledge_drawdown_review(status: dict[str, Any], outcomes: dict[str, Any] | None, *, cycle_status: str | None = None, llm_proposal_id: str | None = None) -> dict[str, Any]:
    path = _state_file(outcomes)
    current = evaluate_drawdown_review(status, outcomes)
    if not current.get("pending"):
        return {**current, "acknowledged": False, "ack_reason": "NO_PENDING_DRAWDOWN_REVIEW"}
    pending_band = str(current.get("pending_band") or current.get("band") or "NORMAL").upper()
    current.update({
        "pending": False,
        "pending_band": None,
        "reviewed_band": pending_band,
        "reviewed_at": _now(),
        "review_cycle_status": cycle_status,
        "review_llm_proposal_id": llm_proposal_id,
        "updated_at": _now(),
    })
    _write(path, current)
    return {**current, "acknowledged": True, "ack_reason": "DRAWDOWN_REVIEW_COMPLETED"}
