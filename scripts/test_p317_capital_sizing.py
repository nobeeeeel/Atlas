from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)


from backend.app.intelligence.capital_sizing import (  # noqa: E402
    build_capital_sizing_plan,
)


def status(**overrides):
    base = {
        "balance": 5000,
        "equity": 5000,
        "free_margin": 5000,
        "margin_level_pct": 0,
        "account_leverage": 1000,
        "equity_drawdown_pct": 0,
        "spread_within_limit": True,
        "volatility_ratio": 1.0,
        "strategy_open_positions": 0,
        "working_limit_orders": 0,
        "runtime_max_open_orders": 4,
        "runtime_max_basket_loss_pct": 5,
        "runtime_enable_basket_stop": True,
        "runtime_enable_stop_loss": True,
    }

    base.update(
        overrides
    )

    return base


def outcomes(results):
    closed = [
        {
            "exact_realized_pl_available": True,
            "realized_net_pl": result,
        }
        for result in results
    ]

    return {
        "closed_count": len(closed),
        "closed": closed,
    }


def test_standard_account_keeps_existing_risk_profile():
    plan = build_capital_sizing_plan(
        status(),
        outcomes([]),
    )

    assert plan["decision"] == "ALLOW"

    assert (
        plan["capital_regime"]
        == "STANDARD"
    )

    assert (
        plan["approved_scalp_risk_pct"]
        == 0.25
    )

    assert (
        plan["approved_zone_risk_pct"]
        == 0.35
    )

    assert (
        plan[
            "maximum_total_strategy_risk_pct"
        ]
        == 0.80
    )


def test_micro_account_receives_growth_envelope():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
            free_margin=500,
        ),
        outcomes([]),
    )

    assert (
        plan["capital_regime"]
        == "MICRO"
    )

    assert (
        plan["risk_capital"]
        == 500
    )

    assert (
        plan["approved_scalp_risk_pct"]
        == 0.35
    )

    assert (
        plan["approved_zone_risk_pct"]
        == 0.50
    )

    assert (
        plan[
            "approved_scalp_risk_amount"
        ]
        == 1.75
    )

    assert (
        plan[
            "approved_zone_risk_amount"
        ]
        == 2.50
    )

    assert (
        plan[
            "maximum_total_strategy_risk_pct"
        ]
        == 1.00
    )


def test_capital_regimes_change_with_account_size():
    micro = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
        ),
        outcomes([]),
    )

    growth = build_capital_sizing_plan(
        status(
            balance=1000,
            equity=1000,
        ),
        outcomes([]),
    )

    build = build_capital_sizing_plan(
        status(
            balance=2000,
            equity=2000,
        ),
        outcomes([]),
    )

    standard = build_capital_sizing_plan(
        status(
            balance=5000,
            equity=5000,
        ),
        outcomes([]),
    )

    capital = build_capital_sizing_plan(
        status(
            balance=10000,
            equity=10000,
        ),
        outcomes([]),
    )

    assert micro["capital_regime"] == "MICRO"
    assert growth["capital_regime"] == "GROWTH"
    assert build["capital_regime"] == "BUILD"
    assert standard["capital_regime"] == "STANDARD"
    assert capital["capital_regime"] == "CAPITAL"

    assert (
        micro["approved_scalp_risk_pct"]
        > growth["approved_scalp_risk_pct"]
        > build["approved_scalp_risk_pct"]
        > standard["approved_scalp_risk_pct"]
        > capital["approved_scalp_risk_pct"]
    )


def test_bonus_like_equity_does_not_inflate_risk_capital():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=750,
            free_margin=750,
        ),
        outcomes([]),
    )

    assert (
        plan["capital_regime"]
        == "MICRO"
    )

    assert (
        plan["balance"]
        == 500
    )

    assert (
        plan["equity"]
        == 750
    )

    assert (
        plan["risk_capital"]
        == 500
    )

    assert (
        plan[
            "approved_scalp_risk_amount"
        ]
        == 1.75
    )

    assert (
        plan[
            "approved_zone_risk_amount"
        ]
        == 2.50
    )


def test_floating_loss_contracts_risk_capital():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=450,
            free_margin=450,
        ),
        outcomes([]),
    )

    assert (
        plan["risk_capital"]
        == 450
    )

    # Exact budget is 450 * 0.35% = 1.575.
    # Atlas reports risk conservatively at the current 2-decimal
    # representation, which evaluates to 1.57 in Python.
    assert (
        plan[
            "approved_scalp_risk_amount"
        ]
        == 1.57
    )

    assert (
        plan[
            "approved_zone_risk_amount"
        ]
        == 2.25
    )


def test_losses_only_contract_risk_and_four_veto():
    one = build_capital_sizing_plan(
        status(),
        outcomes([-1]),
    )

    three = build_capital_sizing_plan(
        status(),
        outcomes(
            [-1, -1, -1]
        ),
    )

    four = build_capital_sizing_plan(
        status(),
        outcomes(
            [-1, -1, -1, -1]
        ),
    )

    assert (
        0
        < three[
            "approved_scalp_risk_pct"
        ]
        < one[
            "approved_scalp_risk_pct"
        ]
        < 0.25
    )

    assert (
        four["veto_new_risk"]
        is True
    )

    assert (
        four[
            "approved_scalp_risk_pct"
        ]
        == 0
    )


def test_micro_losses_contract_instead_of_recovery_sizing():
    healthy = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
        ),
        outcomes([]),
    )

    one_loss = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
        ),
        outcomes([-1]),
    )

    two_losses = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
        ),
        outcomes([-1, -1]),
    )

    assert (
        healthy[
            "approved_scalp_risk_pct"
        ]
        == 0.35
    )

    assert (
        one_loss[
            "approved_scalp_risk_pct"
        ]
        < healthy[
            "approved_scalp_risk_pct"
        ]
    )

    assert (
        two_losses[
            "approved_scalp_risk_pct"
        ]
        < one_loss[
            "approved_scalp_risk_pct"
        ]
    )


def test_drawdown_and_existing_exposure_do_not_scale_up():
    reduced = build_capital_sizing_plan(
        status(
            equity_drawdown_pct=2.5,
        ),
        outcomes([]),
    )

    exposed = build_capital_sizing_plan(
        status(
            strategy_open_positions=1,
        ),
        outcomes([]),
    )

    assert (
        reduced[
            "approved_scalp_risk_pct"
        ]
        == 0.125
    )

    assert (
        exposed["veto_new_risk"]
        is True
    )


def test_micro_drawdown_also_contracts_risk():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
            equity_drawdown_pct=2.5,
        ),
        outcomes([]),
    )

    assert (
        plan["capital_regime"]
        == "MICRO"
    )

    assert (
        plan[
            "approved_scalp_risk_pct"
        ]
        == 0.175
    )

    assert (
        plan[
            "approved_zone_risk_pct"
        ]
        == 0.25
    )


def test_live_zone_campaign_retains_shared_budget_but_blocks_new_scalps():
    plan = build_capital_sizing_plan(
        status(
            strategy_open_positions=1,
            zone_mode_active=True,
            zone_plan_id="campaign-1",
        ),
        outcomes([]),
    )

    assert (
        plan[
            "approved_scalp_risk_pct"
        ]
        == 0
    )

    assert (
        plan[
            "approved_zone_risk_pct"
        ]
        == 0.35
    )

    assert (
        plan[
            "continuing_zone_campaign"
        ]
        is True
    )


def test_next_regime_progress_is_reported():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
        ),
        outcomes([]),
    )

    assert (
        plan[
            "next_capital_regime"
        ]
        == "GROWTH"
    )

    assert (
        plan[
            "next_capital_regime_threshold"
        ]
        == 750
    )

    assert (
        plan[
            "amount_to_next_capital_regime"
        ]
        == 250
    )


def test_high_leverage_does_not_change_risk_percentage():
    low_leverage = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
            account_leverage=100,
        ),
        outcomes([]),
    )

    high_leverage = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
            account_leverage=1000,
        ),
        outcomes([]),
    )

    assert (
        low_leverage[
            "approved_scalp_risk_pct"
        ]
        == high_leverage[
            "approved_scalp_risk_pct"
        ]
    )

    assert (
        low_leverage[
            "approved_zone_risk_pct"
        ]
        == high_leverage[
            "approved_zone_risk_pct"
        ]
    )

def test_bonus_equity_execution_percentage_preserves_dollar_budget():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=750,
            free_margin=750,
        ),
        outcomes([]),
    )

    assert (
        plan["capital_regime"]
        == "MICRO"
    )

    assert (
        plan["risk_capital"]
        == 500
    )

    # Atlas's intended MICRO policy remains 0.35% of owned/risk capital.
    assert (
        plan[
            "capital_basis_scalp_risk_pct"
        ]
        == 0.35
    )

    assert (
        plan[
            "approved_scalp_risk_amount"
        ]
        == 1.75
    )

    # Nyao sizes using ACCOUNT_EQUITY.
    # Therefore Atlas sends the equivalent percentage of $750 equity.
    assert abs(
        plan[
            "approved_scalp_risk_pct"
        ]
        - 0.233333
    ) < 0.000001

    # Reconstruct Nyao's monetary budget.
    reconstructed = (
        750
        * plan[
            "approved_scalp_risk_pct"
        ]
        / 100.0
    )

    assert abs(
        reconstructed
        - 1.75
    ) < 0.01
    
def test_scalp_spread_failure_does_not_zero_capital_budget():
    plan = build_capital_sizing_plan(
        status(
            balance=500,
            equity=500,
            spread_within_limit=False,
            zone_spread_within_limit=True,
        ),
        outcomes([]),
    )

    assert (
        plan["capital_regime"]
        == "MICRO"
    )

    # Capital remains available.
    assert (
        plan["veto_new_risk"]
        is False
    )

    assert (
        plan[
            "approved_scalp_risk_pct"
        ]
        == 0.35
    )

    assert (
        plan[
            "approved_zone_risk_pct"
        ]
        == 0.50
    )

    # Execution layers still receive the market-gate state.
    assert (
        plan[
            "execution_gate_snapshot"
        ][
            "scalp_spread_within_limit"
        ]
        is False
    )

    assert (
        plan[
            "execution_gate_snapshot"
        ][
            "zone_spread_within_limit"
        ]
        is True
    )
    
if __name__ == "__main__":
    test_standard_account_keeps_existing_risk_profile()
    test_micro_account_receives_growth_envelope()
    test_capital_regimes_change_with_account_size()
    test_bonus_like_equity_does_not_inflate_risk_capital()
    test_floating_loss_contracts_risk_capital()
    test_losses_only_contract_risk_and_four_veto()
    test_micro_losses_contract_instead_of_recovery_sizing()
    test_drawdown_and_existing_exposure_do_not_scale_up()
    test_micro_drawdown_also_contracts_risk()
    test_live_zone_campaign_retains_shared_budget_but_blocks_new_scalps()
    test_next_regime_progress_is_reported()
    test_high_leverage_does_not_change_risk_percentage()
    test_bonus_equity_execution_percentage_preserves_dollar_budget()
    test_scalp_spread_failure_does_not_zero_capital_budget()

    print(
        "P3.20 capital regime engine tests passed"
    )