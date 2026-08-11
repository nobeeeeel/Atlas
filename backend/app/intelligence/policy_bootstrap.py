from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "atlas-policy-bootstrap-v2"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_file(outcomes: dict[str, Any] | None) -> Path | None:
    raw = str((outcomes or {}).get("file") or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve().with_name("policy_bootstrap.json")
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
    fd, tmp = tempfile.mkstemp(prefix=".atlas-bootstrap-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _market_ready(status: dict[str, Any]) -> bool:
    """Use authoritative P3.50/P3.54 Nyao market fields.

    The original P3.56 bootstrap accidentally read ``session_open`` and
    ``quote_fresh`` while the Status contract publishes
    ``market_session_open`` and ``market_quote_fresh``.  Keep the legacy aliases
    only for tests/backward compatibility; the market_* fields are authoritative.
    """
    session_open = bool(
        status.get("market_session_open", status.get("session_open", False))
    )
    quote_fresh = bool(
        status.get("market_quote_fresh", status.get("quote_fresh", False))
    )
    try:
        bid = float(status.get("bid") or 0.0)
        ask = float(status.get("ask") or 0.0)
    except (TypeError, ValueError):
        bid = ask = 0.0

    # Older fixtures may not carry bid/ask.  Live Nyao telemetry does, and when
    # either key is present we require sane two-sided prices before qualification.
    prices_exported = "bid" in status or "ask" in status
    prices_ready = (bid > 0.0 and ask > 0.0 and ask >= bid) if prices_exported else True
    return session_open and quote_fresh and prices_ready


def evaluate_policy_bootstrap(status: dict[str, Any], outcomes: dict[str, Any] | None) -> dict[str, Any]:
    path = _state_file(outcomes)
    current = _read(path)
    account = str((outcomes or {}).get("account_fingerprint") or status.get("account_fingerprint") or "")
    symbol = str(status.get("symbol") or "")
    closed_count = int((outcomes or {}).get("closed_count") or len((outcomes or {}).get("closed") or []))
    active_count = len((outcomes or {}).get("active") or [])
    market_ready = _market_ready(status)

    same_scope = (
        bool(current)
        and (not current.get("account_fingerprint") or current.get("account_fingerprint") == account)
        and (not current.get("symbol") or current.get("symbol") == symbol)
    )
    if not same_scope:
        current = {}

    qualified = bool(current.get("qualified", False))

    # Account establishment is account-scoped evidence.  A symbol-level policy
    # epoch must NOT make a newly attached MT5 account look established, because
    # command/policy files intentionally survive account changes.
    existing_account = bool(closed_count > 0 or active_count > 0)

    if qualified:
        state = "QUALIFIED"
        pending = False
    elif not account:
        state = "WAITING_FOR_ACCOUNT_IDENTITY"
        pending = False
    elif not market_ready:
        state = "WAITING_FOR_LIVE_MARKET"
        pending = False
    else:
        state = "AUDIT_PENDING" if existing_account else "QUALIFICATION_PENDING"
        pending = True
        current.setdefault("requested_at", _now())

    # A truly new account stays fail-closed for fresh risk from the instant it is
    # identified until Gemini + Critic explicitly qualifies the baseline.  This
    # includes the waiting-for-market phase, not just QUALIFICATION_PENDING.
    fresh_trading_pause_required = bool(account and not qualified and not existing_account)

    value = {
        **current,
        "version": VERSION,
        "account_fingerprint": account,
        "symbol": symbol,
        "state": state,
        "pending": pending,
        "qualified": qualified,
        "existing_account_audit": existing_account,
        "fresh_trading_pause_required": fresh_trading_pause_required,
        "market_ready": market_ready,
        "seed_configuration_authority": (
            "GEMINI_CRITIC_QUALIFIED_BASELINE"
            if qualified
            else "NYAO_DEFAULTS_UNQUALIFIED_SEED"
        ),
        "bootstrap_change_budget": 12,
        "normal_change_budget": 3,
        "state_file": str(path) if path else None,
        "updated_at": _now(),
    }
    _write(path, value)
    return value


def acknowledge_policy_bootstrap(
    status: dict[str, Any],
    outcomes: dict[str, Any] | None,
    *,
    cycle_status: str | None = None,
    llm_proposal_id: str | None = None,
) -> dict[str, Any]:
    path = _state_file(outcomes)
    current = evaluate_policy_bootstrap(status, outcomes)
    if not current.get("pending"):
        return {**current, "acknowledged": False, "ack_reason": "NO_PENDING_BOOTSTRAP"}
    current.update({
        "pending": False,
        "qualified": True,
        "state": "QUALIFIED",
        "fresh_trading_pause_required": False,
        "qualified_at": _now(),
        "qualification_cycle_status": cycle_status,
        "qualification_llm_proposal_id": llm_proposal_id,
        "seed_configuration_authority": "GEMINI_CRITIC_QUALIFIED_BASELINE",
        "updated_at": _now(),
    })
    _write(path, current)
    return {**current, "acknowledged": True, "ack_reason": "BASELINE_QUALIFIED"}
