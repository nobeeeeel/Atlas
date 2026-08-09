from __future__ import annotations

import os
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


SIM_FLAG = (
    "ATLAS_DEMO_CAPITAL_SIMULATION"
)

SIM_CAPITAL = (
    "ATLAS_DEMO_RISK_CAPITAL"
)


def status(
    *,
    balance: float = 10998.50,
    equity: float = 10998.50,
    trade_mode: int = 0,
) -> dict:
    return {
        "symbol": "#BTCUSD",

        "account_trade_mode": (
            trade_mode
        ),

        "balance": (
            balance
        ),

        "equity": (
            equity
        ),

        "free_margin": (
            equity
        ),

        "equity_drawdown_pct": (
            0.0
        ),

        "margin_level_pct": (
            100000.0
        ),

        "strategy_open_positions": (
            0
        ),

        "working_limit_orders": (
            0
        ),

        "zone_mode_active": (
            False
        ),

        "zone_plan_id": (
            ""
        ),

        "volatility_ratio": (
            1.0
        ),

        "basket_loss_pct": (
            0.0
        ),

        "runtime_max_basket_loss_pct": (
            8.0
        ),

        "basket_risk_remaining_pct": (
            8.0
        ),

        "buy_lots": (
            0.0
        ),

        "sell_lots": (
            0.0
        ),

        "total_lots": (
            0.0
        ),

        "active_hedge_chains": (
            0
        ),

        "hedge_chain_loss_pct": (
            0.0
        ),

        "max_active_hedge_level": (
            0
        ),

        "max_active_hedge_cycle": (
            0
        ),

        "trading_paused": (
            False
        ),

        "outside_trading_hours": (
            False
        ),

        "near_market_close": (
            False
        ),

        "leverage_changed": (
            False
        ),

        "spread_within_limit": (
            True
        ),

        "zone_spread_within_limit": (
            True
        ),

        "runtime_max_open_orders": (
            3
        ),

        "runtime_enable_duplicate_distance_filter": (
            True
        ),

        "runtime_enable_basket_stop": (
            True
        ),

        "runtime_enable_stop_loss": (
            True
        ),

        "runtime_enable_signal_dampening": (
            True
        ),

        "runtime_enable_loss_management": (
            True
        ),

        "runtime_enable_max_spread_filter": (
            True
        ),
    }


def outcomes():
    return {
        "closed_count": 0,
        "closed": [],
    }


def clear_simulation():
    os.environ.pop(
        SIM_FLAG,
        None,
    )

    os.environ.pop(
        SIM_CAPITAL,
        None,
    )


def enable_simulation(
    capital: float,
):
    os.environ[
        SIM_FLAG
    ] = "true"

    os.environ[
        SIM_CAPITAL
    ] = str(
        capital
    )


def test_disabled_uses_real_demo_capital():
    clear_simulation()

    plan = build_capital_sizing_plan(
        status(),
        outcomes(),
    )

    assert (
        plan[
            "demo_capital_simulation"
        ][
            "active"
        ]
        is False
    )

    assert (
        plan[
            "risk_capital"
        ]
        == 10998.50
    )

    assert (
        plan[
            "capital_regime"
        ]
        == "CAPITAL"
    )


def test_500_simulation_uses_micro():
    enable_simulation(
        500
    )

    plan = build_capital_sizing_plan(
        status(),
        outcomes(),
    )

    assert (
        plan[
            "demo_capital_simulation"
        ][
            "active"
        ]
        is True
    )

    assert (
        plan[
            "real_risk_capital"
        ]
        == 10998.50
    )

    assert (
        plan[
            "risk_capital"
        ]
        == 500.00
    )

    assert (
        plan[
            "risk_capital_method"
        ]
        == "DEMO_SIMULATED_RISK_CAPITAL"
    )

    assert (
        plan[
            "capital_regime"
        ]
        == "MICRO"
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

    #
    # Nyao still receives a percentage of REAL $10,998.50 MT5 equity.
    #
    expected_zone_execution_pct = (
        2.50
        / 10998.50
        * 100.0
    )

    assert abs(
        plan[
            "approved_zone_risk_pct"
        ]
        - expected_zone_execution_pct
    ) < 0.000001


def test_1000_simulation_uses_growth():
    enable_simulation(
        1000
    )

    plan = build_capital_sizing_plan(
        status(),
        outcomes(),
    )

    assert (
        plan[
            "capital_regime"
        ]
        == "GROWTH"
    )

    assert (
        plan[
            "approved_zone_risk_amount"
        ]
        == 4.50
    )


def test_3000_simulation_uses_standard():
    enable_simulation(
        3000
    )

    plan = build_capital_sizing_plan(
        status(),
        outcomes(),
    )

    assert (
        plan[
            "capital_regime"
        ]
        == "STANDARD"
    )

    assert (
        plan[
            "approved_zone_risk_amount"
        ]
        == 10.50
    )


def test_5000_simulation_uses_standard():
    enable_simulation(
        5000
    )

    plan = build_capital_sizing_plan(
        status(),
        outcomes(),
    )

    assert (
        plan[
            "capital_regime"
        ]
        == "STANDARD"
    )

    assert (
        plan[
            "approved_zone_risk_amount"
        ]
        == 17.50
    )


def test_non_demo_account_fails_closed():
    enable_simulation(
        500
    )

    #
    # Any mode other than explicit MT5 DEMO mode must reject simulation.
    #
    plan = build_capital_sizing_plan(
        status(
            trade_mode=1,
        ),
        outcomes(),
    )

    assert (
        plan[
            "demo_capital_simulation"
        ][
            "requested"
        ]
        is True
    )

    assert (
        plan[
            "demo_capital_simulation"
        ][
            "active"
        ]
        is False
    )

    assert (
        plan[
            "demo_capital_simulation"
        ][
            "accepted"
        ]
        is False
    )

    assert (
        plan[
            "veto_new_risk"
        ]
        is True
    )

    assert (
        plan[
            "approved_scalp_risk_pct"
        ]
        == 0.0
    )


def test_missing_simulated_capital_fails_closed():
    clear_simulation()

    os.environ[
        SIM_FLAG
    ] = "true"

    plan = build_capital_sizing_plan(
        status(),
        outcomes(),
    )

    assert (
        plan[
            "demo_capital_simulation"
        ][
            "accepted"
        ]
        is False
    )

    assert (
        plan[
            "veto_new_risk"
        ]
        is True
    )


if __name__ == "__main__":
    try:
        test_disabled_uses_real_demo_capital()
        test_500_simulation_uses_micro()
        test_1000_simulation_uses_growth()
        test_3000_simulation_uses_standard()
        test_5000_simulation_uses_standard()

        test_non_demo_account_fails_closed()
        test_missing_simulated_capital_fails_closed()

        print(
            "P3.22 demo capital simulation tests passed"
        )

    finally:
        clear_simulation()