from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.zone_execution_plan import (  # noqa: E402
    build_zone_execution_plan,
)
from backend.app.main import DASHBOARD_TEMPLATE  # noqa: E402


def _zone(zone_id: str, side: str, low: float, high: float, score: float = 80.0) -> dict:
    return {
        "zone_id": zone_id,
        "side": side,
        "low": low,
        "high": high,
        "score": score,
        "timeframe": "H4",
        "kind": "ORDER_BLOCK",
        "status": "FRESH",
        "confluence": ["H1 FVG", "M30 SUPPORT_RESISTANCE"],
    }


def _map() -> dict:
    return {
        "state": "DETECTED_NOT_ACTIVATED",
        "symbol": "TESTUSD",
        "map_id": "map-1",
        "current_price": 105.0,
        "market_structure": {"M30": {"atr": 2.0}},
        "composite_bias": "BULLISH",
        "zones": [
            _zone("demand-1", "DEMAND", 99.0, 101.0),
            _zone("demand-2", "DEMAND", 94.0, 96.0, 70.0),
            _zone("supply-1", "SUPPLY", 109.0, 111.0),
            _zone("supply-2", "SUPPLY", 114.0, 116.0, 70.0),
        ],
    }


def _status(price: float) -> dict:
    return {
        "symbol": "TESTUSD",
        "bid": price - 0.05,
        "ask": price + 0.05,
        "equity": 10_000.0,
        "balance": 10_000.0,
        "spread_within_limit": True,
        "trading_paused": False,
        "strategy_open_positions": 0,
        "buy_entry_eligible": True,
        "sell_entry_eligible": True,
        "buy_adjusted_score": 8.0,
        "sell_adjusted_score": 8.0,
    }


def test_outside_zone_preserves_scalp_mode() -> None:
    result = build_zone_execution_plan(_map(), _status(105.0))
    assert result["mode"] == "SCALP_MODE"
    assert result["ordinary_scalping_allowed"] is True
    assert result["zone_plan"] is None
    assert result["execution_authority_active"] is False


def test_inside_demand_builds_layered_buy_plan() -> None:
    first = build_zone_execution_plan(_map(), _status(100.0))
    second = build_zone_execution_plan(_map(), _status(100.5))
    plan = first["zone_plan"]
    assert first["mode"] == "ZONE_MODE"
    assert first["live_price"] == 100.05
    assert first["price_basis"] == "ASK_BUY_EXECUTION"
    assert first["state"] == "ZONE_ENTRY_CONFIRMED"
    assert first["ordinary_scalping_allowed"] is False
    assert first["directive_preview"]["implemented_in_nyao"] is False
    assert plan["side"] == "BUY"
    assert len(plan["entries"]) == 3
    assert plan["entries"][1]["order_type"] == "VIRTUAL_MARKET_ON_TOUCH"
    assert sum(item["risk_allocation_pct"] for item in plan["entries"]) == 100.0
    assert len(plan["take_profits"]) == 3
    assert sum(item["close_allocation_pct"] for item in plan["take_profits"]) == 100.0
    assert plan["stop_loss"] < 99.0
    assert plan["risk"]["maximum_loss_account_currency"] == 50.0
    assert plan["plan_id"] == second["zone_plan"]["plan_id"]


def test_zone_spread_gate_is_independent_from_scalp_gate() -> None:
    status = _status(100.0)
    status["spread_within_limit"] = False
    result = build_zone_execution_plan(_map(), status)
    spread = result["zone_plan"]["confirmation"]["spread_assessment"]
    assert result["state"] == "ZONE_ENTRY_CONFIRMED"
    assert spread["scalp_spread_within_limit"] is False
    assert spread["zone_spread_within_limit"] is True

    status.update({"bid": 99.0, "ask": 101.0})
    result = build_zone_execution_plan(_map(), status)
    assert result["state"] == "ZONE_WAITING_FOR_CONFIRMATION"
    assert result["zone_plan"]["confirmation"]["spread_assessment"]["zone_spread_within_limit"] is False


def test_wide_spread_midpoint_does_not_create_false_zone_membership() -> None:
    zone_map = {
        **_map(),
        "zones": [_zone("supply-boundary", "SUPPLY", 99.0, 101.0)],
    }
    status = _status(100.0)
    status.update({"bid": 98.9, "ask": 101.1})
    result = build_zone_execution_plan(zone_map, status)
    assert result["mode"] == "SCALP_MODE"
    assert result["live_price"] == 98.9
    assert result["price_basis"] == "BID_SELL_EXECUTION"
    assert result["distance_to_nearest_zone"] == 0.1


def test_supply_zone_uses_bid_even_when_ask_is_outside() -> None:
    zone_map = {
        **_map(),
        "zones": [_zone("supply-live", "SUPPLY", 99.0, 101.0)],
    }
    status = _status(100.0)
    status.update({"bid": 100.5, "ask": 101.5})
    result = build_zone_execution_plan(zone_map, status)
    assert result["mode"] == "ZONE_MODE"
    assert result["live_price"] == 100.5
    assert result["price_basis"] == "BID_SELL_EXECUTION"


def test_existing_scalp_exposure_uses_concurrent_capital_capacity() -> None:
    status = _status(100.0)
    status["strategy_open_positions"] = 1
    result = build_zone_execution_plan(
        _map(),
        status,
        {
            "veto_new_risk": False,
            "approved_zone_risk_amount": 10.0,
            "approved_zone_risk_pct": 0.2,
            "approved_scalp_risk_pct": 0.1,
        },
    )
    assert result["mode"] == "ZONE_MODE"
    assert result["state"] in {"ZONE_ENTRY_CONFIRMED", "ZONE_CAPITAL_INFEASIBLE"}
    assert not any("Existing strategy exposure" in item for item in result["blockers"])


def test_existing_same_zone_campaign_can_reconcile_unfilled_layers() -> None:
    initial = build_zone_execution_plan(_map(), _status(100.0))
    status = _status(100.0)
    status.update({
        "strategy_open_positions": 1,
        "zone_mode_active": True,
        "zone_plan_id": initial["zone_plan"]["plan_id"],
    })
    result = build_zone_execution_plan(_map(), status)
    assert result["state"] == "ZONE_ENTRY_CONFIRMED"
    assert result["directive_preview"]["zone_entry_allowed"] is True
    assert not any("Existing strategy exposure" in item for item in result["blockers"])


def test_dashboard_and_endpoint_contract() -> None:
    for marker in (
        "/api/v1/atlas/zone-execution-plan",
        'id="an-zone-execution"',
        'id="an-stage-zone-gate"',
        "function loadZonePlan()",
        "ordinary scalping suspended",
        "ZONE MODE",
    ):
        assert marker in DASHBOARD_TEMPLATE, marker


if __name__ == "__main__":
    test_outside_zone_preserves_scalp_mode()
    test_inside_demand_builds_layered_buy_plan()
    test_zone_spread_gate_is_independent_from_scalp_gate()
    test_wide_spread_midpoint_does_not_create_false_zone_membership()
    test_supply_zone_uses_bid_even_when_ask_is_outside()
    test_existing_scalp_exposure_uses_concurrent_capital_capacity()
    test_existing_same_zone_campaign_can_reconcile_unfilled_layers()
    test_dashboard_and_endpoint_contract()
    print("P3.12 zone execution plan checks passed.")
