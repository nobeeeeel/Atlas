from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.intelligence.recovery_attribution import analyze_recovery_chains
from backend.app.intelligence.risk_units import build_risk_units


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _ledger_path(outcomes: dict[str, Any]) -> Path | None:
    raw = str(outcomes.get("file") or "").strip()
    if not raw:
        return None
    return Path(raw).parent / "recovery_risk_ledger.json"


def _load_persisted(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"version": 1, "events": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("not dict")
        payload.setdefault("version", 1)
        payload.setdefault("events", [])
        return payload
    except Exception:
        return {"version": 1, "events": []}


def _persist_event(path: Path | None, payload: dict[str, Any], event: dict[str, Any]) -> None:
    if path is None:
        return
    seq = _i(event.get("event_sequence"))
    chain_id = _i(event.get("chain_id"))
    if seq <= 0 or chain_id <= 0:
        return
    events = list(payload.get("events") or [])
    if any(_i(e.get("event_sequence")) == seq and _i(e.get("chain_id")) == chain_id for e in events):
        return
    events.append(event)
    events = events[-200:]
    payload["events"] = events
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _status_sizing(status: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": status.get("recovery_sizing_version") or "",
        "reason": status.get("recovery_sizing_reason") or "NOT_EVALUATED",
        "chain_id": _i(status.get("recovery_sizing_chain_id")),
        "event_sequence": _i(status.get("recovery_sizing_event_sequence")),
        "evaluated_at_epoch": _i(status.get("recovery_sizing_evaluated_at_epoch")),
        "requested_lot": _f(status.get("recovery_requested_lot")),
        "capital_capped_lot": _f(status.get("recovery_capital_capped_lot")),
        "final_lot": _f(status.get("recovery_final_lot")),
        "anchor_loss_usd": _f(status.get("recovery_anchor_loss_usd")),
        "original_unit_risk_usd": _f(status.get("recovery_original_unit_risk_usd")),
        "unit_budget_multiplier": _f(status.get("recovery_unit_budget_multiplier")),
        "portfolio_budget_usd": _f(status.get("recovery_portfolio_budget_usd")),
        "budget_basis": status.get("recovery_budget_basis") or "",
        "chain_budget_usd": _f(status.get("recovery_chain_budget_usd")),
        "remaining_budget_usd": _f(status.get("recovery_remaining_budget_usd")),
        "target_move_price": _f(status.get("recovery_target_move_price")),
        "estimated_adverse_risk_usd": _f(status.get("recovery_estimated_adverse_risk_usd")),
    }


def build_recovery_risk_ledger(status: dict[str, Any], outcomes: dict[str, Any]) -> dict[str, Any]:
    """Durable recovery-risk ledger and live composite-chain risk view."""
    risk_units = build_risk_units(outcomes)
    attribution = analyze_recovery_chains()
    equity = _f(status.get("equity"))
    portfolio_pct = _f(status.get("maximum_total_strategy_risk_pct"))
    portfolio_budget = equity * portfolio_pct / 100.0 if equity > 0 and portfolio_pct > 0 else 0.0

    path = _ledger_path(outcomes)
    persisted = _load_persisted(path)
    live_sizing = _status_sizing(status)
    if live_sizing["reason"] != "NOT_EVALUATED" and live_sizing["event_sequence"] > 0:
        _persist_event(path, persisted, live_sizing)
        persisted = _load_persisted(path)

    events = list(persisted.get("events") or [])
    last_sizing = events[-1] if events else live_sizing
    by_chain = {str(_i(e.get("chain_id"))): e for e in events if _i(e.get("chain_id")) > 0}

    active_chains = [c for c in (attribution.get("chains") or []) if c.get("chain_state") == "ACTIVE"]
    chain_rows = []
    for chain in active_chains:
        cid = _i(chain.get("chain_id"))
        sizing = by_chain.get(str(cid), {})
        chain_budget = _f(sizing.get("chain_budget_usd"))
        mtm = _f(chain.get("observed_chain_mark_to_market"))
        consumed = max(0.0, -mtm)
        remaining = max(0.0, chain_budget - consumed) if chain_budget > 0 else None
        chain_rows.append({
            "chain_id": cid,
            "root_ticket": chain.get("root_ticket"),
            "root_state": chain.get("root_state"),
            "member_count": chain.get("member_count"),
            "active_member_count": chain.get("active_member_count"),
            "closed_member_count": chain.get("closed_member_count"),
            "mark_to_market": round(mtm, 2),
            "original_unit_risk_usd": round(_f(sizing.get("original_unit_risk_usd")), 2),
            "unit_budget_multiplier": _f(sizing.get("unit_budget_multiplier")),
            "portfolio_hard_budget_usd": round(_f(sizing.get("portfolio_budget_usd")) or portfolio_budget, 2),
            "hard_loss_budget_usd": round(chain_budget, 2) if chain_budget > 0 else None,
            "hard_loss_budget_consumed_usd": round(consumed, 2),
            "hard_loss_budget_remaining_usd": round(remaining, 2) if remaining is not None else None,
            "budget_basis": sizing.get("budget_basis") or "UNOBSERVED",
            "last_sizing_event": sizing or None,
            "eligible_for_learning": bool(chain.get("eligible_for_learning")),
            "strategic_outcome_state": "PROVISIONAL_ACTIVE",
        })

    return {
        "version": 2,
        "ready": bool(status),
        "authority": "ATLAS_DURABLE_COMPOSITE_RECOVERY_RISK_LEDGER",
        "equity": round(equity, 2),
        "maximum_total_strategy_risk_pct": portfolio_pct,
        "portfolio_hard_risk_budget_usd": round(portfolio_budget, 2),
        "last_recovery_sizing": last_sizing,
        "recovery_sizing_event_count": len(events),
        "recovery_sizing_events": events[-20:],
        "ledger_file": str(path) if path is not None else None,
        "active_chain_count": len(chain_rows),
        "active_chains": chain_rows,
        "risk_unit_loss_streak": int(risk_units.get("consecutive_completed_loss_units") or 0),
        "active_composite_risk_units": [
            u for u in (risk_units.get("units") or [])
            if u.get("state") == "ACTIVE" and u.get("unit_type") != "STANDALONE_TRADE"
        ],
        "rules": [
            "The portfolio maximum-total-risk percentage is an outer ceiling, not the default budget for one recovery chain.",
            "A recovery chain freezes a risk-unit budget from the root's original stop risk times the recovery expansion multiplier; explicit chain caps and the portfolio ceiling may only tighten it.",
            "If original stop risk is unavailable for legacy history, anchor loss is used as a conservative fallback rather than granting the whole portfolio budget.",
            "Recovery sizing events are persisted per chain and remain auditable after the immediate sizing tick.",
            "Individual recovery-chain member exits are provisional until the whole chain is flat.",
        ],
    }
