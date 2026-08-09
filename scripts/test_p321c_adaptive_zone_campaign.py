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


from backend.app.intelligence.zone_execution_plan import (  # noqa: E402
    build_zone_execution_plan,
    flatten_zone_execution_directive,
)


def _zone_map() -> dict:
    """
    Synthetic HFM BTC zone.

    Supply:
        65000 - 65010

    M30 ATR:
        1960

    Default zone stop ATR buffer:
        1960 * 0.25 = 490

    SELL stop:
        65010 + 490 = 65500

    This gives us a roughly $500 stop distance and therefore a roughly
    $5 minimum-lot loss on HFM #BTCUSD at 0.01 lot.
    """

    return {
        "state": (
            "DETECTED_NOT_ACTIVATED"
        ),

        "symbol": (
            "#BTCUSD"
        ),

        "map_id": (
            "p321c-map"
        ),

        "current_price": (
            65005.0
        ),

        "composite_bias": (
            "BEARISH"
        ),

        "market_structure": {
            "M30": {
                "atr": (
                    1960.0
                ),
            },
        },

        "zones": [
            {
                "zone_id": (
                    "btc-supply-p321c"
                ),

                "side": (
                    "SUPPLY"
                ),

                "low": (
                    65000.0
                ),

                "high": (
                    65010.0
                ),

                "score": (
                    80.0
                ),

                "timeframe": (
                    "H4"
                ),

                "kind": (
                    "ORDER_BLOCK"
                ),

                "status": (
                    "FRESH"
                ),

                "confluence": [
                    "H1 FVG",
                    "M30 SUPPORT_RESISTANCE",
                ],
            },
        ],
    }


def _status(
    capital: float,
) -> dict:
    return {
        "connected": True,

        "symbol": (
            "#BTCUSD"
        ),

        "account_currency": (
            "USD"
        ),

        "balance": (
            capital
        ),

        "equity": (
            capital
        ),

        "free_margin": (
            capital
        ),

        "account_credit": (
            0.0
        ),

        "account_leverage": (
            1000
        ),

        #
        # Price is inside the supply zone.
        #
        # SELL membership uses BID.
        #
        "bid": (
            65005.0
        ),

        "ask": (
            65006.0
        ),

        "spread_within_limit": (
            True
        ),

        "zone_spread_within_limit": (
            True
        ),

        "trading_paused": (
            False
        ),

        "strategy_open_positions": (
            0
        ),

        "working_limit_orders": (
            0
        ),

        "zone_execution_supported": (
            True
        ),

        "zone_execution_enabled": (
            True
        ),

        #
        # Strong enough SELL evidence for zone confirmation.
        #
        "sell_adjusted_score": (
            8.0
        ),

        "buy_adjusted_score": (
            0.0
        ),

        #
        # HFM #BTCUSD contract captured from MT5.
        #
        "broker_contract_telemetry_version": (
            "atlas-broker-telemetry-v1"
        ),

        "symbol_digits": (
            3
        ),

        "symbol_point": (
            0.001
        ),

        "symbol_tick_size": (
            0.001
        ),

        "symbol_tick_value": (
            0.001
        ),

        "symbol_tick_value_profit": (
            0.001
        ),

        "symbol_tick_value_loss": (
            0.001
        ),

        "symbol_contract_size": (
            1.0
        ),

        "symbol_volume_min": (
            0.01
        ),

        "symbol_volume_max": (
            50.0
        ),

        "symbol_volume_step": (
            0.01
        ),

        "symbol_stops_level": (
            0
        ),

        "symbol_freeze_level": (
            0
        ),

        "symbol_trade_mode": (
            4
        ),

        "symbol_calc_mode": (
            2
        ),
    }


def _capital_sizing(
    *,
    capital: float,
    zone_risk_pct: float,
) -> dict:
    risk_amount = (
        capital
        * zone_risk_pct
        / 100.0
    )

    return {
        "version": (
            "atlas-capital-regime-v1.2"
        ),

        "approved_zone_risk_pct": (
            zone_risk_pct
        ),

        "approved_zone_risk_amount": round(
            risk_amount,
            2,
        ),

        "approved_scalp_risk_pct": (
            0.0
        ),

        "maximum_total_strategy_risk_pct": (
            1.0
        ),

        "veto_new_risk": (
            False
        ),
    }


def _build(
    *,
    capital: float,
    zone_risk_pct: float,
) -> dict:
    return build_zone_execution_plan(
        _zone_map(),
        _status(
            capital
        ),
        _capital_sizing(
            capital=capital,
            zone_risk_pct=zone_risk_pct,
        ),
    )


def test_500_account_blocks_btc_zone_entirely():
    result = _build(
        capital=500,
        zone_risk_pct=0.50,
    )

    assert (
        result["mode"]
        == "ZONE_MODE"
    )

    assert (
        result["state"]
        == "ZONE_CAPITAL_INFEASIBLE"
    )

    assert (
        result[
            "directive_preview"
        ][
            "zone_entry_allowed"
        ]
        is False
    )

    plan = result[
        "zone_plan"
    ]

    assert (
        plan[
            "selected_structure"
        ]
        == "NO_TRADE"
    )

    assert (
        plan[
            "selected_entry_count"
        ]
        == 0
    )

    assert (
        len(
            plan[
                "entries"
            ]
        )
        == 0
    )

    #
    # Atlas still preserves the technical ideal for analysis.
    #
    assert (
        len(
            plan[
                "ideal_entries"
            ]
        )
        == 3
    )


def test_3000_account_selects_one_leg():
    result = _build(
        capital=3000,
        zone_risk_pct=0.35,
    )

    assert (
        result["state"]
        == "ZONE_ENTRY_CONFIRMED"
    )

    plan = result[
        "zone_plan"
    ]

    assert (
        plan[
            "selected_structure"
        ]
        == "ONE_LEG"
    )

    assert (
        plan[
            "selected_entry_count"
        ]
        == 1
    )

    assert (
        len(
            plan[
                "entries"
            ]
        )
        == 1
    )

    assert (
        plan[
            "entries"
        ][0][
            "risk_allocation_pct"
        ]
        == 100.0
    )


def test_5000_account_selects_two_legs():
    result = _build(
        capital=5000,
        zone_risk_pct=0.35,
    )

    assert (
        result["state"]
        == "ZONE_ENTRY_CONFIRMED"
    )

    plan = result[
        "zone_plan"
    ]

    assert (
        plan[
            "selected_structure"
        ]
        == "TWO_LEG"
    )

    assert (
        plan[
            "selected_entry_count"
        ]
        == 2
    )

    assert [
        entry[
            "source_leg"
        ]
        for entry
        in plan[
            "entries"
        ]
    ] == [
        1,
        3,
    ]

    assert [
        entry[
            "risk_allocation_pct"
        ]
        for entry
        in plan[
            "entries"
        ]
    ] == [
        60.0,
        40.0,
    ]


def test_11000_account_selects_three_legs():
    result = _build(
        capital=11000,
        zone_risk_pct=0.30,
    )

    assert (
        result["state"]
        == "ZONE_ENTRY_CONFIRMED"
    )

    plan = result[
        "zone_plan"
    ]

    assert (
        plan[
            "selected_structure"
        ]
        == "THREE_LEG"
    )

    assert (
        plan[
            "selected_entry_count"
        ]
        == 3
    )

    assert [
        entry[
            "risk_allocation_pct"
        ]
        for entry
        in plan[
            "entries"
        ]
    ] == [
        40.0,
        35.0,
        25.0,
    ]


def test_two_leg_directive_only_emits_two_entries():
    result = _build(
        capital=5000,
        zone_risk_pct=0.35,
    )

    directive = (
        flatten_zone_execution_directive(
            result
        )
    )

    assert (
        directive[
            "entry_count"
        ]
        == 2
    )

    assert (
        directive[
            "entry_1_price"
        ]
        > 0
    )

    assert (
        directive[
            "entry_2_price"
        ]
        > 0
    )

    assert (
        directive[
            "entry_3_price"
        ]
        == 0.0
    )

    assert (
        directive[
            "entry_1_risk_pct"
        ]
        == 60.0
    )

    assert (
        directive[
            "entry_2_risk_pct"
        ]
        == 40.0
    )

    assert (
        directive[
            "entry_3_risk_pct"
        ]
        == 0.0
    )


def test_no_trade_directive_emits_zero_entries():
    result = _build(
        capital=500,
        zone_risk_pct=0.50,
    )

    directive = (
        flatten_zone_execution_directive(
            result
        )
    )

    assert (
        directive[
            "entry_count"
        ]
        == 0
    )

    assert (
        directive[
            "zone_entry_allowed"
        ]
        is False
    )

    assert (
        directive[
            "entry_1_price"
        ]
        == 0.0
    )

    assert (
        directive[
            "entry_2_price"
        ]
        == 0.0
    )

    assert (
        directive[
            "entry_3_price"
        ]
        == 0.0
    )


def test_stop_does_not_move_to_make_small_account_fit():
    small = _build(
        capital=500,
        zone_risk_pct=0.50,
    )

    large = _build(
        capital=11000,
        zone_risk_pct=0.30,
    )

    assert (
        small[
            "zone_plan"
        ][
            "stop_loss"
        ]
        == large[
            "zone_plan"
        ][
            "stop_loss"
        ]
    )

    assert (
        small[
            "zone_plan"
        ][
            "stop_loss"
        ]
        == 65500.0
    )

def test_target_geometry_is_invariant_across_capital_structures():
    no_trade = _build(
        capital=500,
        zone_risk_pct=0.50,
    )

    one_leg = _build(
        capital=3000,
        zone_risk_pct=0.35,
    )

    two_leg = _build(
        capital=5000,
        zone_risk_pct=0.35,
    )

    three_leg = _build(
        capital=11000,
        zone_risk_pct=0.30,
    )

    plans = [
        no_trade["zone_plan"],
        one_leg["zone_plan"],
        two_leg["zone_plan"],
        three_leg["zone_plan"],
    ]

    #
    # Structural stop must be identical.
    #
    stop_losses = {
        plan["stop_loss"]
        for plan
        in plans
    }

    assert (
        len(stop_losses)
        == 1
    )

    #
    # Canonical weighted entry must also be identical.
    #
    weighted_entries = {
        plan["weighted_entry_price"]
        for plan
        in plans
    }

    assert (
        len(weighted_entries)
        == 1
    )

    #
    # And therefore every TP must remain identical.
    #
    tp_sets = [
        tuple(
            target["price"]
            for target
            in plan["take_profits"]
        )
        for plan
        in plans
    ]

    assert all(
        targets
        == tp_sets[0]
        for targets
        in tp_sets
    )

    assert all(
        plan[
            "target_geometry_basis"
        ]
        == "IDEAL_ZONE_POLICY_STRUCTURE"
        for plan
        in plans
    )

    #
    # But execution structure MUST still vary.
    #
    assert (
        no_trade[
            "zone_plan"
        ][
            "selected_structure"
        ]
        == "NO_TRADE"
    )

    assert (
        one_leg[
            "zone_plan"
        ][
            "selected_structure"
        ]
        == "ONE_LEG"
    )

    assert (
        two_leg[
            "zone_plan"
        ][
            "selected_structure"
        ]
        == "TWO_LEG"
    )

    assert (
        three_leg[
            "zone_plan"
        ][
            "selected_structure"
        ]
        == "THREE_LEG"
    )
    
    
if __name__ == "__main__":
    test_500_account_blocks_btc_zone_entirely()
    test_3000_account_selects_one_leg()
    test_5000_account_selects_two_legs()
    test_11000_account_selects_three_legs()

    test_two_leg_directive_only_emits_two_entries()
    test_no_trade_directive_emits_zero_entries()

    test_stop_does_not_move_to_make_small_account_fit()
    test_target_geometry_is_invariant_across_capital_structures()

    print(
        "P3.21C adaptive zone campaign tests passed"
    )