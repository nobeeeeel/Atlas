from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if PROJECT_ROOT.name != "Atlas":
    PROJECT_ROOT = Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.zone_execution_plan import (
    build_zone_execution_plan,
    flatten_zone_execution_directive,
)


def zone_map() -> dict:
    return {
        "state": "DETECTED_NOT_ACTIVATED",
        "symbol": "#BTCUSD",
        "map_id": "p323a-map",
        "current_price": 65005.0,
        "composite_bias": "BEARISH",
        "market_structure": {"M30": {"atr": 1960.0}},
        "zones": [
            {
                "zone_id": "btc-supply-p323a",
                "side": "SUPPLY",
                "low": 65000.0,
                "high": 65010.0,
                "score": 80.0,
                "timeframe": "H4",
                "kind": "ORDER_BLOCK",
                "status": "FRESH",
                "confluence": ["H1 FVG", "M30 SUPPORT_RESISTANCE"],
            }
        ],
    }


def status(capital: float) -> dict:
    return {
        "connected": True,
        "symbol": "#BTCUSD",
        "account_currency": "USD",
        "balance": capital,
        "equity": capital,
        "free_margin": capital,
        "account_credit": 0.0,
        "account_leverage": 1000,
        "bid": 65005.0,
        "ask": 65006.0,
        "spread_within_limit": True,
        "zone_spread_within_limit": True,
        "trading_paused": False,
        "strategy_open_positions": 0,
        "working_limit_orders": 0,
        "zone_execution_supported": True,
        "zone_execution_enabled": True,
        "sell_adjusted_score": 8.0,
        "buy_adjusted_score": 0.0,
        "broker_contract_telemetry_version": "atlas-broker-telemetry-v1",
        "symbol_digits": 3,
        "symbol_point": 0.001,
        "symbol_tick_size": 0.001,
        "symbol_tick_value": 0.001,
        "symbol_tick_value_profit": 0.001,
        "symbol_tick_value_loss": 0.001,
        "symbol_contract_size": 1.0,
        "symbol_volume_min": 0.01,
        "symbol_volume_max": 50.0,
        "symbol_volume_step": 0.01,
        "symbol_stops_level": 0,
        "symbol_freeze_level": 0,
        "symbol_trade_mode": 4,
        "symbol_calc_mode": 2,
    }


def capital_sizing(capital: float, zone_pct: float, scalp_pct: float, veto: bool = False) -> dict:
    return {
        "version": "atlas-capital-regime-v1.3",
        "approved_zone_risk_pct": zone_pct,
        "approved_zone_risk_amount": round(capital * zone_pct / 100.0, 2),
        "approved_scalp_risk_pct": scalp_pct,
        "approved_scalp_risk_amount": round(capital * scalp_pct / 100.0, 2),
        "maximum_total_strategy_risk_pct": 1.0,
        "veto_new_risk": veto,
    }


def test_capital_infeasible_zone_releases_aligned_scalper():
    result = build_zone_execution_plan(
        zone_map(),
        status(500),
        capital_sizing(500, 0.50, 0.35),
    )
    directive = flatten_zone_execution_directive(result)

    assert result["state"] == "ZONE_CAPITAL_INFEASIBLE"
    assert result["ordinary_scalping_allowed"] is True
    assert result["zone_aware_scalping_active"] is True
    assert result["zone_aware_scalping_side"] == "SELL"

    assert directive["entry_count"] == 0
    assert directive["zone_entry_allowed"] is False
    assert directive["suspend_ordinary_scalp_entries"] is False
    assert directive["execution_requested"] is False
    assert directive["zone_aware_scalping_active"] is True
    assert directive["zone_aware_scalping_side"] == "SELL"


def test_global_capital_veto_does_not_release_scalper():
    result = build_zone_execution_plan(
        zone_map(),
        status(500),
        capital_sizing(500, 0.0, 0.0, veto=True),
    )
    directive = flatten_zone_execution_directive(result)

    assert result["state"] == "ZONE_CAPITAL_INFEASIBLE"
    assert result["ordinary_scalping_allowed"] is False
    assert result["zone_aware_scalping_active"] is False
    assert directive["suspend_ordinary_scalp_entries"] is True
    assert directive["execution_requested"] is False


def test_feasible_zone_still_owns_fresh_entries():
    result = build_zone_execution_plan(
        zone_map(),
        status(11000),
        capital_sizing(11000, 0.30, 0.20),
    )
    directive = flatten_zone_execution_directive(result)

    assert result["zone_plan"]["selected_entry_count"] > 0
    assert result["ordinary_scalping_allowed"] is False
    assert result["zone_aware_scalping_active"] is False
    assert directive["suspend_ordinary_scalp_entries"] is True
    assert directive["execution_requested"] is True


if __name__ == "__main__":
    test_capital_infeasible_zone_releases_aligned_scalper()
    test_global_capital_veto_does_not_release_scalper()
    test_feasible_zone_still_owns_fresh_entries()
    print("P3.23A zone-aware scalp fallback tests passed")
