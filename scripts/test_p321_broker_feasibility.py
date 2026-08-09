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


from backend.app.intelligence.broker_feasibility import (  # noqa: E402
    estimate_broker_loss,
    evaluate_leg_feasibility,
    evaluate_zone_campaign_feasibility,
    extract_broker_contract,
)

from backend.app.intelligence.capital_sizing import (  # noqa: E402
    build_capital_sizing_plan,
)


# ---------------------------------------------------------------------------
# Real HFM #BTCUSD contract captured from the demo account.
# ---------------------------------------------------------------------------


def btc_status(
    *,
    balance: float,
    equity: float | None = None,
    **overrides,
):
    if equity is None:
        equity = balance

    status = {
        "connected": True,
        "symbol": "#BTCUSD",

        "account_currency": "USD",

        "balance": balance,
        "equity": equity,
        "free_margin": equity,

        "account_credit": 0.0,
        "account_leverage": 1000,

        "margin_level_pct": 100000.0,
        "equity_drawdown_pct": 0.0,

        "spread_within_limit": True,
        "zone_spread_within_limit": True,

        "current_atr": 50.0,
        "average_atr": 50.0,
        "volatility_ratio": 1.0,

        "strategy_open_positions": 0,
        "working_limit_orders": 0,

        "runtime_max_open_orders": 3,

        "basket_loss_pct": 0.0,
        "runtime_max_basket_loss_pct": 8.0,
        "basket_risk_remaining_pct": 8.0,

        "buy_lots": 0.0,
        "sell_lots": 0.0,
        "total_lots": 0.0,

        "active_hedge_chains": 0,
        "hedge_chain_loss_pct": 0.0,
        "max_active_hedge_level": 0,
        "max_active_hedge_cycle": 0,

        "trading_paused": False,
        "outside_trading_hours": False,
        "near_market_close": False,
        "leverage_changed": False,

        "runtime_enable_duplicate_distance_filter": True,
        "runtime_enable_basket_stop": True,
        "runtime_enable_stop_loss": True,
        "runtime_enable_signal_dampening": True,
        "runtime_enable_loss_management": True,
        "runtime_enable_max_spread_filter": True,

        #
        # P3.21A broker telemetry captured from HFM.
        #
        "broker_contract_telemetry_version": (
            "atlas-broker-telemetry-v1"
        ),

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

    status.update(
        overrides
    )

    return status


def outcomes():
    return {
        "closed_count": 0,
        "closed": [],
    }


# ---------------------------------------------------------------------------
# Test geometry
# ---------------------------------------------------------------------------
#
# SELL entries below a stop at 65,500.
#
# We intentionally use a 500-dollar stop distance for entry 1:
#
#     65,000 -> 65,500
#
# HFM BTC:
#
#     tick size       = 0.001
#     tick value loss = 0.001 per 1.0 lot
#
# Therefore:
#
#     500 / 0.001 = 500,000 ticks
#     500,000 * 0.001 = $500 loss at 1.00 lot
#     $500 * 0.01 = $5 loss at broker minimum volume
#
ENTRY_PRICES = [
    65000.0,
    64950.0,
    64900.0,
]

STOP_LOSS = 65500.0


def zone_budget(
    capital: float,
) -> tuple[dict, dict]:
    status = btc_status(
        balance=capital,
        equity=capital,
    )

    sizing = build_capital_sizing_plan(
        status,
        outcomes(),
    )

    return (
        status,
        sizing,
    )


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_hfm_btc_contract_is_ready():
    contract = extract_broker_contract(
        btc_status(
            balance=500,
        )
    )

    assert (
        contract[
            "ready"
        ]
        is True
    )

    assert (
        contract[
            "volume_min"
        ]
        == 0.01
    )

    assert (
        contract[
            "volume_step"
        ]
        == 0.01
    )

    assert (
        contract[
            "tick_size"
        ]
        == 0.001
    )

    assert (
        contract[
            "effective_loss_tick_value"
        ]
        == 0.001
    )


def test_hfm_btc_minimum_lot_loss_is_five_dollars():
    loss = estimate_broker_loss(
        status=btc_status(
            balance=500,
        ),
        side="SELL",
        entry_price=65000.0,
        stop_loss=65500.0,
        volume=0.01,
    )

    assert (
        loss[
            "available"
        ]
        is True
    )

    assert abs(
        loss[
            "estimated_loss"
        ]
        - 5.0
    ) < 0.000001


def test_volume_never_rounds_up():
    result = evaluate_leg_feasibility(
        status=btc_status(
            balance=10000,
        ),
        side="SELL",
        entry_price=65000.0,
        stop_loss=65500.0,

        #
        # $14.99 allows ~0.02998 lot theoretically.
        #
        # Broker step is 0.01, so Atlas must select 0.02.
        #
        risk_budget=14.99,
    )

    assert (
        result[
            "feasible"
        ]
        is True
    )

    assert (
        result[
            "maximum_affordable_volume"
        ]
        == 0.02
    )

    assert (
        result[
            "estimated_loss_at_selected_volume"
        ]
        <= 14.99
    )


# ---------------------------------------------------------------------------
# Small-capital tests
# ---------------------------------------------------------------------------


def test_500_micro_account_cannot_fund_btc_zone():
    status, sizing = zone_budget(
        500
    )

    assert (
        sizing[
            "capital_regime"
        ]
        == "MICRO"
    )

    assert (
        sizing[
            "approved_zone_risk_amount"
        ]
        == 2.50
    )

    result = (
        evaluate_zone_campaign_feasibility(
            status=status,
            side="SELL",
            entry_prices=ENTRY_PRICES,
            stop_loss=STOP_LOSS,
            total_risk_budget=sizing[
                "approved_zone_risk_amount"
            ],
        )
    )

    assert (
        result[
            "campaign_feasible"
        ]
        is False
    )

    assert (
        result[
            "selected_structure"
        ]
        == "NO_TRADE"
    )

    assert (
        result[
            "selected_entry_count"
        ]
        == 0
    )


def test_1000_growth_account_cannot_fund_btc_zone():
    status, sizing = zone_budget(
        1000
    )

    assert (
        sizing[
            "capital_regime"
        ]
        == "GROWTH"
    )

    assert (
        sizing[
            "approved_zone_risk_amount"
        ]
        == 4.50
    )

    result = (
        evaluate_zone_campaign_feasibility(
            status=status,
            side="SELL",
            entry_prices=ENTRY_PRICES,
            stop_loss=STOP_LOSS,
            total_risk_budget=sizing[
                "approved_zone_risk_amount"
            ],
        )
    )

    assert (
        result[
            "selected_structure"
        ]
        == "NO_TRADE"
    )


def test_3000_standard_account_falls_back_to_one_leg():
    status, sizing = zone_budget(
        3000
    )

    assert (
        sizing[
            "capital_regime"
        ]
        == "STANDARD"
    )

    assert (
        sizing[
            "approved_zone_risk_amount"
        ]
        == 10.50
    )

    result = (
        evaluate_zone_campaign_feasibility(
            status=status,
            side="SELL",
            entry_prices=ENTRY_PRICES,
            stop_loss=STOP_LOSS,
            total_risk_budget=sizing[
                "approved_zone_risk_amount"
            ],
        )
    )

    assert (
        result[
            "campaign_feasible"
        ]
        is True
    )

    assert (
        result[
            "selected_structure"
        ]
        == "ONE_LEG"
    )

    assert (
        result[
            "selected_entry_count"
        ]
        == 1
    )


def test_5000_standard_account_can_use_two_legs():
    status, sizing = zone_budget(
        5000
    )

    assert (
        sizing[
            "capital_regime"
        ]
        == "STANDARD"
    )

    assert (
        sizing[
            "approved_zone_risk_amount"
        ]
        == 17.50
    )

    result = (
        evaluate_zone_campaign_feasibility(
            status=status,
            side="SELL",
            entry_prices=ENTRY_PRICES,
            stop_loss=STOP_LOSS,
            total_risk_budget=sizing[
                "approved_zone_risk_amount"
            ],
        )
    )

    assert (
        result[
            "campaign_feasible"
        ]
        is True
    )

    assert (
        result[
            "selected_structure"
        ]
        == "TWO_LEG"
    )

    assert (
        result[
            "selected_entry_count"
        ]
        == 2
    )

    selected = result[
        "selected"
    ]

    assert [
        leg[
            "source_leg"
        ]
        for leg
        in selected[
            "legs"
        ]
    ] == [
        1,
        3,
    ]


def test_11000_capital_account_can_use_three_legs():
    status, sizing = zone_budget(
        11000
    )

    assert (
        sizing[
            "capital_regime"
        ]
        == "CAPITAL"
    )

    assert (
        sizing[
            "approved_zone_risk_amount"
        ]
        == 33.00
    )

    result = (
        evaluate_zone_campaign_feasibility(
            status=status,
            side="SELL",
            entry_prices=ENTRY_PRICES,
            stop_loss=STOP_LOSS,
            total_risk_budget=sizing[
                "approved_zone_risk_amount"
            ],
        )
    )

    assert (
        result[
            "campaign_feasible"
        ]
        is True
    )

    assert (
        result[
            "selected_structure"
        ]
        == "THREE_LEG"
    )

    assert (
        result[
            "selected_entry_count"
        ]
        == 3
    )


# ---------------------------------------------------------------------------
# Safety tests
# ---------------------------------------------------------------------------


def test_bad_sell_stop_geometry_fails_closed():
    result = evaluate_leg_feasibility(
        status=btc_status(
            balance=5000,
        ),
        side="SELL",
        entry_price=65000.0,

        # Invalid SELL stop.
        stop_loss=64900.0,

        risk_budget=100.0,
    )

    assert (
        result[
            "feasible"
        ]
        is False
    )


def test_missing_contract_telemetry_fails_closed():
    status = btc_status(
        balance=5000,
    )

    status[
        "symbol_tick_value_loss"
    ] = 0.0

    status[
        "symbol_tick_value"
    ] = 0.0

    result = evaluate_leg_feasibility(
        status=status,
        side="SELL",
        entry_price=65000.0,
        stop_loss=65500.0,
        risk_budget=100.0,
    )

    assert (
        result[
            "feasible"
        ]
        is False
    )


def test_leverage_does_not_change_stop_loss_risk():
    low_leverage = btc_status(
        balance=5000,
        account_leverage=100,
    )

    high_leverage = btc_status(
        balance=5000,
        account_leverage=1000,
    )

    low = estimate_broker_loss(
        status=low_leverage,
        side="SELL",
        entry_price=65000.0,
        stop_loss=65500.0,
        volume=0.01,
    )

    high = estimate_broker_loss(
        status=high_leverage,
        side="SELL",
        entry_price=65000.0,
        stop_loss=65500.0,
        volume=0.01,
    )

    assert (
        low[
            "estimated_loss"
        ]
        == high[
            "estimated_loss"
        ]
    )


if __name__ == "__main__":
    test_hfm_btc_contract_is_ready()
    test_hfm_btc_minimum_lot_loss_is_five_dollars()
    test_volume_never_rounds_up()

    test_500_micro_account_cannot_fund_btc_zone()
    test_1000_growth_account_cannot_fund_btc_zone()
    test_3000_standard_account_falls_back_to_one_leg()
    test_5000_standard_account_can_use_two_legs()
    test_11000_capital_account_can_use_three_legs()

    test_bad_sell_stop_geometry_fails_closed()
    test_missing_contract_telemetry_fails_closed()
    test_leverage_does_not_change_stop_loss_risk()

    print(
        "P3.21B broker feasibility tests passed"
    )