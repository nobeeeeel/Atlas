from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR, InvalidOperation
from typing import Any


BROKER_FEASIBILITY_VERSION = "atlas-broker-feasibility-v1"


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def _f(
    data: dict[str, Any],
    key: str,
    default: float = 0.0,
) -> float:
    try:
        value = data.get(
            key,
            default,
        )

        if value is None:
            return default

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def _positive(
    value: float,
) -> bool:
    return (
        value > 0.0
    )


def _d(
    value: float | str,
) -> Decimal:
    """
    Convert through str so broker-volume flooring does not depend on
    binary floating-point representation.
    """

    return Decimal(
        str(value)
    )


# ---------------------------------------------------------------------------
# Broker contract extraction
# ---------------------------------------------------------------------------


def extract_broker_contract(
    status: dict[str, Any],
) -> dict[str, Any]:
    """
    Read the broker-authoritative symbol specification published by Nyao.

    Atlas does not assume that XAUUSD, BTCUSD, Cent accounts, Standard
    accounts or different brokers share the same contract specification.
    """

    tick_size = _f(
        status,
        "symbol_tick_size",
    )

    tick_value = _f(
        status,
        "symbol_tick_value",
    )

    tick_value_profit = _f(
        status,
        "symbol_tick_value_profit",
    )

    tick_value_loss = _f(
        status,
        "symbol_tick_value_loss",
    )

    contract_size = _f(
        status,
        "symbol_contract_size",
    )

    volume_min = _f(
        status,
        "symbol_volume_min",
    )

    volume_max = _f(
        status,
        "symbol_volume_max",
    )

    volume_step = _f(
        status,
        "symbol_volume_step",
    )

    point = _f(
        status,
        "symbol_point",
    )

    reasons: list[str] = []

    if not _positive(
        tick_size
    ):
        reasons.append(
            "Broker symbol tick size is unavailable."
        )

    if not _positive(
        tick_value_loss
    ) and not _positive(
        tick_value
    ):
        reasons.append(
            "Broker tick value for loss estimation is unavailable."
        )

    if not _positive(
        volume_min
    ):
        reasons.append(
            "Broker minimum volume is unavailable."
        )

    if not _positive(
        volume_step
    ):
        reasons.append(
            "Broker volume step is unavailable."
        )

    if (
        _positive(volume_max)
        and _positive(volume_min)
        and volume_max < volume_min
    ):
        reasons.append(
            "Broker maximum volume is below minimum volume."
        )

    effective_loss_tick_value = (
        tick_value_loss
        if tick_value_loss > 0
        else tick_value
    )

    return {
        "version": (
            BROKER_FEASIBILITY_VERSION
        ),

        "ready": (
            len(reasons) == 0
        ),

        "reasons": (
            reasons
        ),

        "symbol": (
            status.get("symbol")
        ),

        "account_currency": (
            status.get(
                "account_currency"
            )
        ),

        "telemetry_version": (
            status.get(
                "broker_contract_telemetry_version"
            )
        ),

        "digits": int(
            status.get(
                "symbol_digits"
            )
            or 0
        ),

        "point": (
            point
        ),

        "tick_size": (
            tick_size
        ),

        "tick_value": (
            tick_value
        ),

        "tick_value_profit": (
            tick_value_profit
        ),

        "tick_value_loss": (
            tick_value_loss
        ),

        "effective_loss_tick_value": (
            effective_loss_tick_value
        ),

        "contract_size": (
            contract_size
        ),

        "volume_min": (
            volume_min
        ),

        "volume_max": (
            volume_max
        ),

        "volume_step": (
            volume_step
        ),

        "stops_level": int(
            status.get(
                "symbol_stops_level"
            )
            or 0
        ),

        "freeze_level": int(
            status.get(
                "symbol_freeze_level"
            )
            or 0
        ),

        "trade_mode": int(
            status.get(
                "symbol_trade_mode"
            )
            or 0
        ),

        "calc_mode": int(
            status.get(
                "symbol_calc_mode"
            )
            or 0
        ),
    }


# ---------------------------------------------------------------------------
# Broker-volume helpers
# ---------------------------------------------------------------------------


def _floor_volume_to_step(
    *,
    requested_volume: float,
    minimum_volume: float,
    maximum_volume: float,
    volume_step: float,
) -> float:
    """
    Floor volume to the broker step.

    IMPORTANT:

    Atlas NEVER rounds volume upward in order to make a trade possible.

    If the floored amount is below minimum broker volume, zero is returned.
    """

    if (
        requested_volume <= 0
        or minimum_volume <= 0
        or volume_step <= 0
    ):
        return 0.0

    try:
        requested = _d(
            requested_volume
        )

        minimum = _d(
            minimum_volume
        )

        step = _d(
            volume_step
        )

        if maximum_volume > 0:
            maximum = _d(
                maximum_volume
            )

            requested = min(
                requested,
                maximum,
            )

        if requested < minimum:
            return 0.0

        #
        # Broker volume grids normally begin at zero:
        #
        #   0.01
        #   0.02
        #   0.03
        #
        # Flooring requested / step therefore guarantees that we never
        # increase the requested monetary risk.
        #
        steps = (
            requested
            / step
        ).to_integral_value(
            rounding=ROUND_FLOOR
        )

        floored = (
            steps
            * step
        )

        if floored < minimum:
            return 0.0

        return float(
            floored
        )

    except (
        InvalidOperation,
        ValueError,
    ):
        return 0.0


# ---------------------------------------------------------------------------
# Price / stop validation
# ---------------------------------------------------------------------------


def _valid_stop_geometry(
    *,
    side: str,
    entry_price: float,
    stop_loss: float,
) -> tuple[bool, str | None]:
    side = str(
        side
    ).upper()

    if entry_price <= 0:
        return (
            False,
            "Entry price is unavailable.",
        )

    if stop_loss <= 0:
        return (
            False,
            "Stop price is unavailable.",
        )

    if side == "BUY":
        if stop_loss >= entry_price:
            return (
                False,
                "BUY stop must be below entry price.",
            )

        return (
            True,
            None,
        )

    if side == "SELL":
        if stop_loss <= entry_price:
            return (
                False,
                "SELL stop must be above entry price.",
            )

        return (
            True,
            None,
        )

    return (
        False,
        "Trade side must be BUY or SELL.",
    )


# ---------------------------------------------------------------------------
# Tick-value loss estimation
# ---------------------------------------------------------------------------


def estimate_broker_loss(
    *,
    status: dict[str, Any],
    side: str,
    entry_price: float,
    stop_loss: float,
    volume: float,
) -> dict[str, Any]:
    """
    Estimate loss in account currency using broker-published tick values.

    Formula:

        price distance
        ---------------- × tick value loss × volume
           tick size

    This is an ATLAS PREFLIGHT estimate.

    It does NOT replace Nyao's OrderCalcProfit() calculation.

    OrderCalcProfit remains the broker-facing final authority immediately
    before execution.
    """

    contract = extract_broker_contract(
        status
    )

    geometry_ok, geometry_reason = (
        _valid_stop_geometry(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
        )
    )

    reasons = list(
        contract["reasons"]
    )

    if not geometry_ok and geometry_reason:
        reasons.append(
            geometry_reason
        )

    if volume <= 0:
        reasons.append(
            "Requested volume must be positive."
        )

    if reasons:
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "available": False,
            "reasons": reasons,
            "side": str(side).upper(),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "volume": volume,
            "price_distance": None,
            "tick_count": None,
            "estimated_loss": None,
        }

    distance = abs(
        float(entry_price)
        - float(stop_loss)
    )

    tick_size = float(
        contract[
            "tick_size"
        ]
    )

    tick_value_loss = float(
        contract[
            "effective_loss_tick_value"
        ]
    )

    tick_count = (
        distance
        / tick_size
    )

    estimated_loss = (
        tick_count
        * tick_value_loss
        * float(volume)
    )

    return {
        "version": (
            BROKER_FEASIBILITY_VERSION
        ),

        "available": True,

        "reasons": [],

        "side": str(
            side
        ).upper(),

        "entry_price": round(
            float(entry_price),
            10,
        ),

        "stop_loss": round(
            float(stop_loss),
            10,
        ),

        "volume": round(
            float(volume),
            10,
        ),

        "price_distance": round(
            distance,
            10,
        ),

        "tick_count": round(
            tick_count,
            6,
        ),

        "tick_value_loss": (
            tick_value_loss
        ),

        "estimated_loss": round(
            estimated_loss,
            8,
        ),
    }


# ---------------------------------------------------------------------------
# Single-leg feasibility
# ---------------------------------------------------------------------------


def evaluate_leg_feasibility(
    *,
    status: dict[str, Any],
    side: str,
    entry_price: float,
    stop_loss: float,
    risk_budget: float,
) -> dict[str, Any]:
    """
    Determine whether one planned entry can be expressed within the Atlas
    monetary risk budget using the broker's legal volume grid.

    Rules:

    - Never increase the risk budget.
    - Never round volume upward.
    - Broker minimum volume must fit inside the leg budget.
    - Nyao OrderCalcProfit remains final authority at execution time.
    """

    contract = extract_broker_contract(
        status
    )

    if risk_budget <= 0:
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "feasible": False,
            "reason": (
                "Leg has no approved monetary risk budget."
            ),
            "risk_budget": round(
                max(
                    0.0,
                    risk_budget,
                ),
                8,
            ),
            "minimum_volume": (
                contract.get(
                    "volume_min"
                )
            ),
            "maximum_affordable_volume": 0.0,
            "estimated_loss_at_minimum_volume": None,
            "estimated_loss_at_selected_volume": None,
        }

    if not contract[
        "ready"
    ]:
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "feasible": False,
            "reason": (
                "Broker contract telemetry is incomplete."
            ),
            "reasons": list(
                contract[
                    "reasons"
                ]
            ),
            "risk_budget": round(
                risk_budget,
                8,
            ),
            "minimum_volume": (
                contract.get(
                    "volume_min"
                )
            ),
            "maximum_affordable_volume": 0.0,
            "estimated_loss_at_minimum_volume": None,
            "estimated_loss_at_selected_volume": None,
        }

    minimum_volume = float(
        contract[
            "volume_min"
        ]
    )

    minimum_loss = estimate_broker_loss(
        status=status,
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        volume=minimum_volume,
    )

    if not minimum_loss[
        "available"
    ]:
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "feasible": False,
            "reason": (
                "Minimum-volume loss could not be estimated."
            ),
            "reasons": list(
                minimum_loss[
                    "reasons"
                ]
            ),
            "risk_budget": round(
                risk_budget,
                8,
            ),
            "minimum_volume": (
                minimum_volume
            ),
            "maximum_affordable_volume": 0.0,
            "estimated_loss_at_minimum_volume": None,
            "estimated_loss_at_selected_volume": None,
        }

    minimum_loss_amount = float(
        minimum_loss[
            "estimated_loss"
        ]
    )

    if minimum_loss_amount <= 0:
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "feasible": False,
            "reason": (
                "Estimated broker loss is unavailable or zero."
            ),
            "risk_budget": round(
                risk_budget,
                8,
            ),
            "minimum_volume": (
                minimum_volume
            ),
            "maximum_affordable_volume": 0.0,
            "estimated_loss_at_minimum_volume": (
                minimum_loss_amount
            ),
            "estimated_loss_at_selected_volume": None,
        }

    #
    # This is the critical small-account check.
    #
    if minimum_loss_amount > (
        risk_budget
        + 1e-10
    ):
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),

            "feasible": False,

            "reason": (
                "Broker minimum volume would exceed the approved "
                "Atlas leg risk budget."
            ),

            "side": str(
                side
            ).upper(),

            "entry_price": round(
                entry_price,
                10,
            ),

            "stop_loss": round(
                stop_loss,
                10,
            ),

            "risk_budget": round(
                risk_budget,
                8,
            ),

            "minimum_volume": (
                minimum_volume
            ),

            "estimated_loss_at_minimum_volume": round(
                minimum_loss_amount,
                8,
            ),

            "risk_shortfall": round(
                minimum_loss_amount
                - risk_budget,
                8,
            ),

            "maximum_affordable_volume": 0.0,

            "estimated_loss_at_selected_volume": None,

            "broker_ordercalcprofit_required": True,
        }

    #
    # Calculate theoretical affordable volume from the loss per one lot.
    #
    loss_per_one_lot = (
        minimum_loss_amount
        / minimum_volume
    )

    theoretical_volume = (
        risk_budget
        / loss_per_one_lot
    )

    selected_volume = (
        _floor_volume_to_step(
            requested_volume=(
                theoretical_volume
            ),
            minimum_volume=(
                minimum_volume
            ),
            maximum_volume=float(
                contract[
                    "volume_max"
                ]
                or 0.0
            ),
            volume_step=float(
                contract[
                    "volume_step"
                ]
            ),
        )
    )

    if selected_volume <= 0:
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "feasible": False,
            "reason": (
                "Affordable volume falls below the broker minimum."
            ),
            "risk_budget": round(
                risk_budget,
                8,
            ),
            "minimum_volume": (
                minimum_volume
            ),
            "estimated_loss_at_minimum_volume": round(
                minimum_loss_amount,
                8,
            ),
            "maximum_affordable_volume": 0.0,
            "estimated_loss_at_selected_volume": None,
            "broker_ordercalcprofit_required": True,
        }

    selected_loss = estimate_broker_loss(
        status=status,
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        volume=selected_volume,
    )

    selected_loss_amount = float(
        selected_loss.get(
            "estimated_loss"
        )
        or 0.0
    )

    #
    # Defensive safety check. This should already be guaranteed by flooring,
    # but Atlas fails closed if floating arithmetic ever violates it.
    #
    if selected_loss_amount > (
        risk_budget
        + 1e-8
    ):
        return {
            "version": (
                BROKER_FEASIBILITY_VERSION
            ),
            "feasible": False,
            "reason": (
                "Floored broker volume unexpectedly exceeds "
                "the approved risk budget."
            ),
            "risk_budget": round(
                risk_budget,
                8,
            ),
            "minimum_volume": (
                minimum_volume
            ),
            "maximum_affordable_volume": 0.0,
            "estimated_loss_at_minimum_volume": round(
                minimum_loss_amount,
                8,
            ),
            "estimated_loss_at_selected_volume": round(
                selected_loss_amount,
                8,
            ),
            "broker_ordercalcprofit_required": True,
        }

    return {
        "version": (
            BROKER_FEASIBILITY_VERSION
        ),

        "feasible": True,

        "reason": (
            "Broker volume can be expressed without exceeding "
            "the approved Atlas leg risk budget."
        ),

        "side": str(
            side
        ).upper(),

        "entry_price": round(
            entry_price,
            10,
        ),

        "stop_loss": round(
            stop_loss,
            10,
        ),

        "risk_budget": round(
            risk_budget,
            8,
        ),

        "minimum_volume": (
            minimum_volume
        ),

        "volume_step": (
            contract[
                "volume_step"
            ]
        ),

        "estimated_loss_at_minimum_volume": round(
            minimum_loss_amount,
            8,
        ),

        "maximum_affordable_volume": round(
            selected_volume,
            10,
        ),

        "estimated_loss_at_selected_volume": round(
            selected_loss_amount,
            8,
        ),

        "unused_risk_budget": round(
            max(
                0.0,
                risk_budget
                - selected_loss_amount,
            ),
            8,
        ),

        "broker_ordercalcprofit_required": True,

        "execution_authority": (
            "NYAO_FINAL_BROKER_VALIDATION"
        ),
    }


# ---------------------------------------------------------------------------
# Zone campaign structures
# ---------------------------------------------------------------------------


ZONE_STRUCTURE_CANDIDATES: tuple[
    dict[str, Any],
    ...,
] = (
    {
        "name": "THREE_LEG",
        "entry_count": 3,
        "legs": (
            {
                "source_leg": 1,
                "allocation_pct": 40.0,
            },
            {
                "source_leg": 2,
                "allocation_pct": 35.0,
            },
            {
                "source_leg": 3,
                "allocation_pct": 25.0,
            },
        ),
    },
    {
        "name": "TWO_LEG",
        "entry_count": 2,

        #
        # Keep the confirmation entry and deepest pullback entry.
        #
        # We deliberately do not invent new technical entry prices just
        # because account capital is smaller.
        #
        "legs": (
            {
                "source_leg": 1,
                "allocation_pct": 60.0,
            },
            {
                "source_leg": 3,
                "allocation_pct": 40.0,
            },
        ),
    },
    {
        "name": "ONE_LEG",
        "entry_count": 1,
        "legs": (
            {
                "source_leg": 1,
                "allocation_pct": 100.0,
            },
        ),
    },
)


def evaluate_zone_structure(
    *,
    status: dict[str, Any],
    side: str,
    entry_prices: list[float],
    stop_loss: float,
    total_risk_budget: float,
    structure: dict[str, Any],
) -> dict[str, Any]:
    """
    Evaluate one possible zone campaign structure.

    Example:

        THREE_LEG
        40 / 35 / 25

    or:

        TWO_LEG
        source entries 1 + 3
        60 / 40
    """

    required_source_legs = [
        int(
            leg[
                "source_leg"
            ]
        )
        for leg
        in structure[
            "legs"
        ]
    ]

    if any(
        source_leg < 1
        or source_leg > len(
            entry_prices
        )
        for source_leg
        in required_source_legs
    ):
        return {
            "name": (
                structure[
                    "name"
                ]
            ),
            "entry_count": (
                structure[
                    "entry_count"
                ]
            ),
            "feasible": False,
            "reason": (
                "Required source entry price is unavailable."
            ),
            "legs": [],
        }

    evaluated_legs: list[
        dict[str, Any]
    ] = []

    for new_leg_index, leg in enumerate(
        structure[
            "legs"
        ],
        start=1,
    ):
        source_leg = int(
            leg[
                "source_leg"
            ]
        )

        allocation_pct = float(
            leg[
                "allocation_pct"
            ]
        )

        entry_price = float(
            entry_prices[
                source_leg - 1
            ]
        )

        leg_budget = (
            total_risk_budget
            * allocation_pct
            / 100.0
        )

        feasibility = (
            evaluate_leg_feasibility(
                status=status,
                side=side,
                entry_price=entry_price,
                stop_loss=stop_loss,
                risk_budget=leg_budget,
            )
        )

        evaluated_legs.append({
            "leg": (
                new_leg_index
            ),

            "source_leg": (
                source_leg
            ),

            "entry_price": round(
                entry_price,
                10,
            ),

            "allocation_pct": (
                allocation_pct
            ),

            "risk_budget": round(
                leg_budget,
                8,
            ),

            "feasibility": (
                feasibility
            ),
        })

    feasible = all(
        leg[
            "feasibility"
        ][
            "feasible"
        ]
        for leg
        in evaluated_legs
    )

    estimated_selected_risk = sum(
        float(
            leg[
                "feasibility"
            ].get(
                "estimated_loss_at_selected_volume"
            )
            or 0.0
        )
        for leg
        in evaluated_legs
        if leg[
            "feasibility"
        ][
            "feasible"
        ]
    )

    return {
        "name": (
            structure[
                "name"
            ]
        ),

        "entry_count": (
            structure[
                "entry_count"
            ]
        ),

        "feasible": (
            feasible
        ),

        "reason": (
            "All campaign legs fit broker minimum-volume constraints."
            if feasible
            else (
                "At least one campaign leg cannot be funded "
                "within its approved allocation."
            )
        ),

        "total_risk_budget": round(
            total_risk_budget,
            8,
        ),

        "estimated_selected_risk": round(
            estimated_selected_risk,
            8,
        ),

        "legs": (
            evaluated_legs
        ),
    }


def evaluate_zone_campaign_feasibility(
    *,
    status: dict[str, Any],
    side: str,
    entry_prices: list[float],
    stop_loss: float,
    total_risk_budget: float,
) -> dict[str, Any]:
    """
    Evaluate Atlas's zone campaign from richest structure to simplest:

        3 legs
          ↓
        2 legs
          ↓
        1 leg
          ↓
        no trade

    The first fully feasible structure is selected.

    IMPORTANT:

    This function does not consider:

        spread
        zone confirmation
        quote touch
        market hours
        directional quality

    Those remain separate Atlas execution gates.

    This function answers only:

        "Can this campaign structure be expressed within the approved
         monetary risk budget and the broker's legal minimum volume?"

    Nyao still performs OrderCalcProfit immediately before actual order
    execution.
    """

    contract = extract_broker_contract(
        status
    )

    evaluations = [
        evaluate_zone_structure(
            status=status,
            side=side,
            entry_prices=entry_prices,
            stop_loss=stop_loss,
            total_risk_budget=(
                total_risk_budget
            ),
            structure=structure,
        )
        for structure
        in ZONE_STRUCTURE_CANDIDATES
    ]

    selected = next(
        (
            result
            for result
            in evaluations
            if result[
                "feasible"
            ]
        ),
        None,
    )

    if selected is None:
        selected_name = (
            "NO_TRADE"
        )

        selected_entry_count = 0

    else:
        selected_name = str(
            selected[
                "name"
            ]
        )

        selected_entry_count = int(
            selected[
                "entry_count"
            ]
        )

    return {
        "version": (
            BROKER_FEASIBILITY_VERSION
        ),

        "symbol": (
            status.get(
                "symbol"
            )
        ),

        "side": str(
            side
        ).upper(),

        "stop_loss": round(
            stop_loss,
            10,
        ),

        "total_risk_budget": round(
            max(
                0.0,
                total_risk_budget,
            ),
            8,
        ),

        "broker_contract_ready": (
            contract[
                "ready"
            ]
        ),

        "broker_contract": (
            contract
        ),

        "structures": (
            evaluations
        ),

        "selected_structure": (
            selected_name
        ),

        "selected_entry_count": (
            selected_entry_count
        ),

        "selected": (
            selected
        ),

        "campaign_feasible": (
            selected is not None
        ),

        "decision": (
            "ALLOW"
            if selected is not None
            else "NO_TRADE"
        ),

        "decision_reason": (
            (
                f"{selected_name} is the richest campaign structure "
                "that fits the approved risk budget."
            )
            if selected is not None
            else (
                "Even one broker-minimum zone leg exceeds the "
                "approved campaign risk budget."
            )
        ),

        "rules": [
            (
                "Atlas evaluates richer zone structures before "
                "simpler structures."
            ),
            (
                "Atlas never increases campaign risk to make broker "
                "minimum volume fit."
            ),
            (
                "Atlas never rounds estimated position volume upward."
            ),
            (
                "Reducing campaign entry count does not move the "
                "technical stop closer."
            ),
            (
                "Two-leg mode preserves the original confirmation "
                "entry and deepest planned pullback entry."
            ),
            (
                "Nyao OrderCalcProfit remains the final broker-facing "
                "risk calculation before execution."
            ),
        ],
    }