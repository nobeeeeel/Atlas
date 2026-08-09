from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.capital_sizing import build_capital_sizing_plan  # noqa: E402


def base_status(**overrides):
    data = {
        "balance": 10965.0,
        "equity": 10965.0,
        "free_margin": 10960.0,
        "margin_level_pct": 200000.0,
        "account_leverage": 1000,
        "equity_drawdown_pct": 0.0,
        "spread_within_limit": True,
        "zone_spread_within_limit": True,
        "volatility_ratio": 1.0,
        "strategy_open_positions": 0,
        "working_limit_orders": 0,
        "runtime_max_open_orders": 5,
        "runtime_max_basket_loss_pct": 8.0,
        "runtime_enable_basket_stop": True,
        "runtime_enable_stop_loss": True,
        "symbol_tick_size": 0.001,
        "symbol_tick_value": 0.001,
        "symbol_tick_value_loss": 0.001,
        "symbol_contract_size": 1.0,
        "positions": [],
    }
    data.update(overrides)
    return data


def make_outcomes(tmp: Path):
    outcome_file = tmp / "trade_outcomes.json"
    outcome_file.write_text(json.dumps({"closed": []}), encoding="utf-8")
    return {"file": str(outcome_file), "closed_count": 0, "closed": []}


def write_recovery_ledger(tmp: Path, chain_id: int, budget: float):
    (tmp / "recovery_risk_ledger.json").write_text(
        json.dumps({
            "version": 1,
            "events": [{
                "chain_id": chain_id,
                "event_sequence": 1,
                "reason": "ACTIVE_RECOVERY_CHAIN_ADOPTED",
                "chain_budget_usd": budget,
                "original_unit_risk_usd": budget / 1.5,
                "unit_budget_multiplier": 1.5,
            }],
        }),
        encoding="utf-8",
    )


def recovery_positions(chain_id: int):
    return [
        {
            "ticket": chain_id,
            "type": "SELL",
            "volume": 0.03,
            "entry_price": 64742.752,
            "current_price": 64829.236,
            "sl": 0.0,
            "net_pl": -2.59,
            "chain_id": chain_id,
            "hedge_level": 0,
            "zone_plan_id": "",
        },
        {
            "ticket": chain_id + 110,
            "type": "BUY",
            "volume": 0.10,
            "entry_price": 64793.817,
            "current_price": 64768.089,
            "sl": 0.0,
            "net_pl": -2.57,
            "chain_id": chain_id,
            "hedge_level": 1,
            "zone_plan_id": "",
        },
    ]


def test_active_recovery_reserves_only_its_chain_ceiling():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        outcomes = make_outcomes(tmp)
        chain_id = 231330004
        write_recovery_ledger(tmp, chain_id, 15.09)
        status = base_status(
            strategy_open_positions=2,
            positions=recovery_positions(chain_id),
        )
        plan = build_capital_sizing_plan(status, outcomes)
        allocation = plan["portfolio_allocation"]

        assert plan["veto_new_risk"] is False
        assert allocation["allocation_state"] == "PARTIALLY_ALLOCATED"
        assert allocation["reserved_active_risk_amount"] == 15.09
        assert allocation["remaining_hard_risk_amount"] == 94.56
        assert plan["approved_scalp_risk_amount"] > 0
        assert plan["approved_zone_risk_amount"] > 0
        assert "Existing strategy exposure owns the current risk budget." not in plan["veto_reasons"]


def test_concurrent_capacity_clips_candidate_instead_of_double_promising():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        outcomes = make_outcomes(tmp)
        chain_id = 231330004
        write_recovery_ledger(tmp, chain_id, 95.00)
        status = base_status(
            strategy_open_positions=2,
            positions=recovery_positions(chain_id),
        )
        plan = build_capital_sizing_plan(status, outcomes)
        allocation = plan["portfolio_allocation"]

        assert plan["veto_new_risk"] is False
        assert allocation["remaining_operating_risk_amount"] == 14.65
        assert plan["approved_scalp_risk_amount"] == 14.65
        assert plan["approved_zone_risk_amount"] == 14.65
        assert allocation["capacity_limited"] is True
        assert plan["decision"] == "REDUCE"


def test_full_allocation_vetoes_only_when_capacity_is_exhausted():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        outcomes = make_outcomes(tmp)
        chain_id = 231330004
        write_recovery_ledger(tmp, chain_id, 109.65)
        status = base_status(
            strategy_open_positions=2,
            positions=recovery_positions(chain_id),
        )
        plan = build_capital_sizing_plan(status, outcomes)

        assert plan["veto_new_risk"] is True
        assert plan["portfolio_allocation"]["allocation_state"] == "FULLY_ALLOCATED"
        assert plan["approved_scalp_risk_amount"] == 0.0
        assert plan["approved_zone_risk_amount"] == 0.0
        assert "Portfolio operating risk capacity is fully allocated." in plan["veto_reasons"]


def test_unresolved_recovery_chain_remains_fail_closed_for_independent_risk():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        outcomes = make_outcomes(tmp)
        chain_id = 231330004
        status = base_status(
            strategy_open_positions=2,
            positions=recovery_positions(chain_id),
        )
        plan = build_capital_sizing_plan(status, outcomes)

        assert plan["veto_new_risk"] is True
        assert chain_id in plan["portfolio_allocation"]["unresolved_recovery_chain_ids"]


def test_zone_engine_no_longer_has_blanket_existing_exposure_block():
    source = (PROJECT_ROOT / "backend/app/intelligence/zone_execution_plan.py").read_text(encoding="utf-8")
    assert "Existing strategy exposure must be reconciled before a new zone plan can layer entries." not in source
    assert "zone_capacity_available" in source
    assert "conflicting_zone_campaign" in source
    assert "Concurrent portfolio allocation has no approved zone risk capacity" in source




def test_nyao_counts_recovery_chain_as_one_losing_risk_unit():
    source = (PROJECT_ROOT / "external/nyao/nyao_scalper.mq5").read_text(encoding="utf-8")
    assert '#property version "44.3"' in source
    assert "int CountLosingRiskUnits()" in source
    assert "chainProfit[chainIndex] += profit" in source
    assert "CountLosingRiskUnits() >= MaxHoldingLossPositions" in source
    assert "CountLosingPositions() >= MaxHoldingLossPositions" not in source


def test_dashboard_exposes_partial_allocation_state():
    source = (PROJECT_ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "PARTIALLY ALLOCATED" in source
    assert "Reserved portfolio risk" in source
    assert "Available operating risk" in source
    assert "Existing trades do not automatically block independent opportunities." in source


if __name__ == "__main__":
    test_active_recovery_reserves_only_its_chain_ceiling()
    test_concurrent_capacity_clips_candidate_instead_of_double_promising()
    test_full_allocation_vetoes_only_when_capacity_is_exhausted()
    test_unresolved_recovery_chain_remains_fail_closed_for_independent_risk()
    test_zone_engine_no_longer_has_blanket_existing_exposure_block()
    test_nyao_counts_recovery_chain_as_one_losing_risk_unit()
    test_dashboard_exposes_partial_allocation_state()
    print("P3.31 concurrent portfolio risk allocation regression: PASS")
