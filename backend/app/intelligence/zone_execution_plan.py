from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from backend.app.intelligence.broker_feasibility import evaluate_zone_campaign_feasibility
from backend.app.intelligence.zone_policy import get_zone_policy


PLAN_VERSION = "zone-execution-plan-v0.8"
CAMPAIGN_REATTACH_GRACE_SECONDS = 90


def _quotes(status: dict[str, Any], zone_map: dict[str, Any]) -> dict[str, float]:
    bid = float(status.get("bid") or 0.0)
    ask = float(status.get("ask") or 0.0)
    closed_reference = float(zone_map.get("current_price") or 0.0)
    chart_price = bid or ask or closed_reference
    return {
        "bid": bid,
        "ask": ask,
        "chart_price": chart_price,
        "closed_m30_reference": closed_reference,
    }


def _zone_price(
    zone: dict[str, Any],
    quotes: dict[str, float],
) -> tuple[float, str]:
    """Return the executable quote used to decide membership for this zone."""
    if zone.get("side") == "DEMAND":
        if quotes["ask"] > 0:
            return quotes["ask"], "ASK_BUY_EXECUTION"
        if quotes["bid"] > 0:
            return quotes["bid"], "BID_FALLBACK_FOR_BUY"
    else:
        if quotes["bid"] > 0:
            return quotes["bid"], "BID_SELL_EXECUTION"
        if quotes["ask"] > 0:
            return quotes["ask"], "ASK_FALLBACK_FOR_SELL"
    return quotes["closed_m30_reference"], "LATEST_CLOSED_M30_FALLBACK"


def _distance(price: float, zone: dict[str, Any]) -> float:
    low, high = float(zone["low"]), float(zone["high"])
    if price < low:
        return low - price
    if price > high:
        return price - high
    return 0.0


def _inside(price: float, zone: dict[str, Any]) -> bool:
    return float(zone["low"]) <= price <= float(zone["high"])


def _priority_zones(
    zone_map: dict[str, Any],
    quotes: dict[str, float],
) -> list[dict[str, Any]]:
    zones = list(zone_map.get("zones") or [])
    selected: list[dict[str, Any]] = []
    for side in ("DEMAND", "SUPPLY"):
        side_zones = sorted(
            (zone for zone in zones if zone.get("side") == side),
            key=lambda zone: (
                _distance(_zone_price(zone, quotes)[0], zone),
                -float(zone.get("score") or 0.0),
            ),
        )
        selected.extend(side_zones[:2])
    return selected


def _layer_prices(side: str, low: float, high: float, depths: list[float]) -> list[float]:
    width = high - low
    if side == "BUY":
        return [high - width * depth for depth in depths]
    return [low + width * depth for depth in depths]


def _build_layers(
    side: str,
    low: float,
    high: float,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        {
            "leg": index,
            "entry_price": round(price, 8),
            "risk_allocation_pct": allocation,
            "order_type": (
                "MARKET_ON_CONFIRMATION"
                if index == 1
                else "VIRTUAL_MARKET_ON_TOUCH"
            ),
        }
        for index, (price, allocation) in enumerate(
            zip(
                _layer_prices(side, low, high, list(policy["entry_depths"])),
                policy["entry_allocations"],
            ), start=1
        )
    ]


def _zone_confirmation(
    *,
    zone: dict[str, Any],
    zone_map: dict[str, Any],
    status: dict[str, Any],
    policy_record: dict[str, Any],
    price: float,
) -> dict[str, Any]:
    policy = policy_record["policy"]
    side = "BUY" if zone["side"] == "DEMAND" else "SELL"
    raw_signal = max(0.0, float(status.get(f"{side.lower()}_adjusted_score") or 0.0))
    signal_component = min(100.0, raw_signal * 10.0)
    quality_component = max(0.0, min(100.0, float(zone.get("score") or 0.0)))
    low, high = float(zone["low"]), float(zone["high"])
    width = max(high - low, 1e-8)
    depth = (high - price) / width if side == "BUY" else (price - low) / width
    depth_component = max(0.0, min(100.0, depth * 100.0))
    timeframe_component = {"H4": 100.0, "H1": 82.0, "M30": 68.0}.get(
        str(zone.get("timeframe") or "").upper(), 50.0
    )
    bias = str(zone_map.get("composite_bias") or "NEUTRAL").upper()
    aligned = (side == "BUY" and bias == "BULLISH") or (side == "SELL" and bias == "BEARISH")
    neutral = bias not in {"BULLISH", "BEARISH"}
    structure_component = 100.0 if aligned else 50.0 if neutral else 0.0
    confluence_count = len(zone.get("confluence") or [])
    confluence_bonus = min(
        float(policy["maximum_confluence_bonus"]),
        confluence_count * float(policy["confluence_bonus_per_item"]),
    )
    countertrend_penalty = 0.0 if aligned or neutral else float(policy["countertrend_penalty"])
    weighted = (
        quality_component * float(policy["zone_quality_weight"])
        + signal_component * float(policy["directional_signal_weight"])
        + depth_component * float(policy["location_depth_weight"])
        + timeframe_component * float(policy["timeframe_weight"])
        + structure_component * float(policy["structure_alignment_weight"])
        + confluence_bonus
        - countertrend_penalty
    )
    combined = max(0.0, min(100.0, weighted))
    threshold = float(policy["confirmation_threshold"])
    minimum_signal = float(policy["minimum_directional_score"])
    eligible = bool(
        policy["enabled"]
        and raw_signal >= minimum_signal
        and combined >= threshold
    )
    return {
        "eligible": eligible,
        "combined_score": round(combined, 4),
        "threshold": threshold,
        "directional_score": round(raw_signal, 4),
        "minimum_directional_score": minimum_signal,
        "components": {
            "zone_quality": round(quality_component, 4),
            "directional_signal": round(signal_component, 4),
            "location_depth": round(depth_component, 4),
            "timeframe": timeframe_component,
            "structure_alignment": structure_component,
            "confluence_bonus": round(confluence_bonus, 4),
            "countertrend_penalty": round(countertrend_penalty, 4),
        },
        "policy_epoch": policy_record["policy_epoch"],
        "policy_fingerprint": policy_record["fingerprint"],
    }


def _trade_plan(
    *,
    zone: dict[str, Any],
    zone_map: dict[str, Any],
    status: dict[str, Any],
    policy_record: dict[str, Any],
    live_price: float,
    capital_sizing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build the zone campaign.

    ZonePolicy continues to define the IDEAL technical campaign:

        Entry 1 = 40%
        Entry 2 = 35%
        Entry 3 = 25%

    When Atlas capital sizing is active, broker feasibility then chooses
    the richest executable structure:

        THREE_LEG
            ↓
        TWO_LEG
            ↓
        ONE_LEG
            ↓
        NO_TRADE

    Account size is therefore allowed to change execution STRUCTURE,
    but never the technical invalidation point or total approved risk.
    """

    policy = policy_record["policy"]

    side = (
        "BUY"
        if zone["side"] == "DEMAND"
        else "SELL"
    )

    low = float(
        zone["low"]
    )

    high = float(
        zone["high"]
    )

    width = max(
        high - low,
        1e-8,
    )

    m30_atr = float(
        (
            (
                zone_map.get(
                    "market_structure"
                )
                or {}
            ).get(
                "M30"
            )
            or {}
        ).get(
            "atr"
        )
        or 0.0
    )

    spread = abs(
        float(
            status.get(
                "ask"
            )
            or 0.0
        )
        - float(
            status.get(
                "bid"
            )
            or 0.0
        )
    )

    #
    # Technical invalidation is calculated BEFORE capital adaptation.
    #
    # Atlas must never move the stop closer merely because an account is
    # too small.
    #
    invalidation_buffer = max(
        width
        * float(
            policy[
                "stop_zone_width_buffer"
            ]
        ),

        m30_atr
        * float(
            policy[
                "stop_m30_atr_buffer"
            ]
        ),

        spread
        * float(
            policy[
                "stop_spread_buffer"
            ]
        ),
    )

    stop_loss = (
        low - invalidation_buffer
        if side == "BUY"
        else high + invalidation_buffer
    )

    #
    # Ideal technical structure.
    #
    ideal_layers = _build_layers(
        side,
        low,
        high,
        policy,
    )

    #
    # Capital budget.
    #
    equity = max(
        0.0,
        float(
            status.get(
                "equity"
            )
            or status.get(
                "balance"
            )
            or 0.0
        ),
    )

    approved_zone_risk = float(
        (
            capital_sizing
            or {}
        ).get(
            "approved_zone_risk_pct"
        )
        or 0.0
    )

    account_risk_pct = (
        approved_zone_risk
        if capital_sizing is not None
        else float(
            policy[
                "account_risk_pct"
            ]
        )
    )

    #
    # Prefer the explicit monetary budget produced by the Capital Regime
    # Engine.
    #
    # This avoids reconstructing owned-capital risk from MT5 equity when
    # bonus/credit-supported equity differs from Atlas risk capital.
    #
    explicit_risk_budget = (
        (
            capital_sizing
            or {}
        ).get(
            "approved_zone_risk_amount"
        )
        if capital_sizing is not None
        else None
    )

    risk_budget = (
        max(
            0.0,
            float(
                explicit_risk_budget
            ),
        )
        if explicit_risk_budget is not None
        else (
            equity
            * account_risk_pct
            / 100.0
        )
    )

    #
    # Broker feasibility.
    #
    if capital_sizing is not None:
        broker_feasibility = (
            evaluate_zone_campaign_feasibility(
                status=status,
                side=side,
                entry_prices=[
                    float(
                        item[
                            "entry_price"
                        ]
                    )
                    for item
                    in ideal_layers
                ],
                stop_loss=stop_loss,
                total_risk_budget=risk_budget,
            )
        )

    else:
        #
        # Compatibility path for older callers/tests that intentionally
        # build zone plans without a Capital Regime plan.
        #
        broker_feasibility = {
            "version": (
                "NOT_REQUIRED_LEGACY_PLAN"
            ),
            "broker_contract_ready": False,
            "campaign_feasible": True,
            "decision": (
                "NOT_EVALUATED"
            ),
            "decision_reason": (
                "Capital sizing was not supplied, so broker preflight "
                "is not required for this compatibility plan."
            ),
            "selected_structure": (
                "THREE_LEG"
            ),
            "selected_entry_count": 3,
            "selected": None,
        }

    selected_feasibility = (
        broker_feasibility.get(
            "selected"
        )
        or {}
    )

    selected_legs = list(
        selected_feasibility.get(
            "legs"
        )
        or []
    )

    #
    # Translate the broker-feasibility choice back into actual zone layers.
    #
    layers: list[
        dict[str, Any]
    ] = []

    if capital_sizing is None:
        layers = ideal_layers

    elif broker_feasibility.get(
        "campaign_feasible"
    ):
        for (
            new_leg,
            selected_leg,
        ) in enumerate(
            selected_legs,
            start=1,
        ):
            source_leg = int(
                selected_leg.get(
                    "source_leg"
                )
                or 0
            )

            if (
                source_leg < 1
                or source_leg
                > len(
                    ideal_layers
                )
            ):
                continue

            source = dict(
                ideal_layers[
                    source_leg - 1
                ]
            )

            source.update({
                "leg": (
                    new_leg
                ),

                #
                # Preserve which technical layer this came from.
                #
                "source_leg": (
                    source_leg
                ),

                "risk_allocation_pct": float(
                    selected_leg.get(
                        "allocation_pct"
                    )
                    or 0.0
                ),

                "order_type": (
                    "MARKET_ON_CONFIRMATION"
                    if new_leg == 1
                    else "VIRTUAL_MARKET_ON_TOUCH"
                ),

                "broker_feasibility": (
                    selected_leg.get(
                        "feasibility"
                    )
                    or {}
                ),
            })

            layers.append(
                source
            )

    #
    # P3.21E — Structural Target Invariance
    #
    # TP geometry belongs to the MARKET THESIS, not to account size.
    #
    # The canonical weighted entry therefore always comes from the ideal
    # ZonePolicy campaign (40 / 35 / 25), even when broker/capital
    # feasibility later reduces execution to 2, 1, or 0 legs.
    #
    # Capital may change:
    #
    #     HOW MANY entries participate
    #     HOW MUCH risk each executable leg receives
    #
    # Capital must NOT change:
    #
    #     structural stop
    #     canonical weighted entry
    #     TP geometry
    #
    ideal_total_allocation = sum(
        float(
            item.get(
                "risk_allocation_pct"
            )
            or 0.0
        )
        for item
        in ideal_layers
    )

    if ideal_total_allocation <= 0:
        ideal_total_allocation = 100.0

    weighted_entry = sum(
        float(
            item[
                "entry_price"
            ]
        )
        * float(
            item.get(
                "risk_allocation_pct"
            )
            or 0.0
        )
        / ideal_total_allocation
        for item
        in ideal_layers
    )

    risk_distance = abs(
        weighted_entry
        - stop_loss
    )

    direction = (
        1.0
        if side == "BUY"
        else -1.0
    )

    reward_multiples = list(
        policy[
            "take_profit_reward_multiples"
        ]
    )

    take_profits = [
        {
            "target": index,

            "price": round(
                weighted_entry
                + direction
                * risk_distance
                * multiple,
                8,
            ),

            "close_allocation_pct": (
                allocation
            ),

            "reward_multiple": (
                multiple
            ),
        }
        for (
            index,
            (
                multiple,
                allocation,
            ),
        ) in enumerate(
            zip(
                reward_multiples,
                policy[
                    "take_profit_allocations"
                ],
            ),
            start=1,
        )
    ]

    #
    # Dedicated zone spread gate.
    #
    zone_spread_caps = [
        cap
        for cap
        in (
            m30_atr
            * float(
                policy[
                    "zone_market_spread_atr_ratio"
                ]
            ),

            abs(
                live_price
                - stop_loss
            )
            * float(
                policy[
                    "zone_max_spread_stop_ratio"
                ]
            ),

            abs(
                take_profits[
                    0
                ][
                    "price"
                ]
                - live_price
            )
            * float(
                policy[
                    "zone_max_spread_target_ratio"
                ]
            ),
        )
        if cap > 0
    ]

    zone_spread_cap = (
        min(
            zone_spread_caps
        )
        if zone_spread_caps
        else 0.0
    )

    zone_spread_within_limit = bool(
        not policy[
            "enable_zone_spread_filter"
        ]
        or zone_spread_cap <= 0
        or spread
        <= zone_spread_cap
    )

    zone_confirmation = (
        _zone_confirmation(
            zone=zone,
            zone_map=zone_map,
            status=status,
            policy_record=policy_record,
            price=live_price,
        )
    )

    selected_structure = str(
        broker_feasibility.get(
            "selected_structure"
        )
        or "THREE_LEG"
    )

    #
    # Structure becomes part of campaign identity.
    #
    # A 3-leg and 1-leg campaign against the same zone are not the same
    # campaign.
    #
    plan_identity = {
        "version": (
            PLAN_VERSION
        ),

        "symbol": (
            zone_map.get(
                "symbol"
            )
        ),

        "map_id": (
            zone_map.get(
                "map_id"
            )
        ),

        "zone_id": (
            zone.get(
                "zone_id"
            )
        ),

        "side": (
            side
        ),

        "zone_policy_fingerprint": (
            policy_record[
                "fingerprint"
            ]
        ),

        "broker_structure": (
            selected_structure
        ),
    }

    plan_id = hashlib.sha256(
        json.dumps(
            plan_identity,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )
    ).hexdigest()[
        :20
    ]

    sizing_status = (
        "NYAO_BROKER_TICK_VALUE_REQUIRED"
    )

    if capital_sizing is not None:
        sizing_status = (
            "BROKER_PREFLIGHT_FEASIBLE_"
            "NYAO_FINAL_VALIDATION_REQUIRED"
            if broker_feasibility.get(
                "campaign_feasible"
            )
            else (
                "BROKER_MINIMUM_VOLUME_"
                "NOT_FEASIBLE"
            )
        )

    return {
        "plan_id": (
            plan_id
        ),

        "side": (
            side
        ),

        "source_zone": (
            zone
        ),

        #
        # What Atlas ideally wanted technically.
        #
        "ideal_entries": (
            ideal_layers
        ),

        #
        # What the account/broker can actually support.
        #
        "entries": (
            layers
        ),

        "selected_entry_count": (
            len(
                layers
            )
        ),

        "selected_structure": (
            selected_structure
        ),

        "broker_feasibility": (
            broker_feasibility
        ),

        #
        # Canonical market-thesis weighted entry.
        #
        # This remains identical across 3/2/1/0-leg adaptations.
        #
        "weighted_entry_price": round(
            weighted_entry,
            8,
        ),

        "target_geometry_basis": (
            "IDEAL_ZONE_POLICY_STRUCTURE"
        ),

        "stop_loss": round(
            stop_loss,
            8,
        ),

        "take_profits": (
            take_profits
        ),

        "risk": {
            "account_risk_pct": (
                account_risk_pct
            ),

            "maximum_loss_account_currency": round(
                risk_budget,
                2,
            ),

            "position_size": None,

            "sizing_status": (
                sizing_status
            ),

            "rule": (
                "All entry legs share one total risk budget; "
                "allocations must not each risk the full budget."
            ),
        },

        "confirmation": {
            "required": True,

            "model": (
                "ATLAS_COMBINED_ZONE_CONFIRMATION_V1"
            ),

            "zone_confirmation": (
                zone_confirmation
            ),

            "side_signal_eligible": (
                zone_confirmation[
                    "eligible"
                ]
            ),

            "spread_within_limit": (
                zone_spread_within_limit
            ),

            "broker_feasibility_within_limit": bool(
                broker_feasibility.get(
                    "campaign_feasible",
                    True,
                )
            ),

            "spread_assessment": {
                "strategy": (
                    "ZONE"
                ),

                "enabled": bool(
                    policy[
                        "enable_zone_spread_filter"
                    ]
                ),

                "spread_price": round(
                    spread,
                    8,
                ),

                "effective_cap_price": round(
                    zone_spread_cap,
                    8,
                ),

                "scalp_spread_within_limit": bool(
                    status.get(
                        "spread_within_limit",
                        True,
                    )
                ),

                "zone_spread_within_limit": (
                    zone_spread_within_limit
                ),

                "market_atr_ratio": float(
                    policy[
                        "zone_market_spread_atr_ratio"
                    ]
                ),

                "maximum_stop_ratio": float(
                    policy[
                        "zone_max_spread_stop_ratio"
                    ]
                ),

                "maximum_target_ratio": float(
                    policy[
                        "zone_max_spread_target_ratio"
                    ]
                ),

                "virtual_layer_activation_atr_ratio": float(
                    policy[
                        "virtual_layer_activation_atr_ratio"
                    ]
                ),
            },

            "trading_paused": bool(
                status.get(
                    "trading_paused"
                )
            ),

            "required_conditions": [
                (
                    "Atlas combined zone confirmation remains eligible "
                    "while price is inside the source zone."
                ),
                (
                    "Spread remains within the dedicated zone execution "
                    "limit; the stricter scalp limit is independent."
                ),
                (
                    "The selected 1/2/3-leg campaign fits the broker "
                    "minimum-volume constraints without increasing risk."
                ),
                (
                    "No close beyond the shared invalidation level "
                    "has occurred."
                ),
                (
                    "The zone map and plan identifiers still match "
                    "the active Atlas directive."
                ),
            ],
        },

        "cancellation_conditions": [
            (
                "Price closes beyond the shared stop/invalidation level."
            ),
            (
                "Atlas publishes a replacement zone map."
            ),
            (
                "The opposite directional confirmation becomes eligible "
                "before the first fill."
            ),
            (
                "The account or basket risk governor vetoes new exposure."
            ),
            (
                "Broker feasibility no longer supports the admitted "
                "campaign before the first fill."
            ),
        ],
    }


def build_zone_execution_plan(
    zone_map: dict[str, Any],
    status: dict[str, Any],
    capital_sizing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate Atlas zones into a non-executing scalp/zone mode directive."""
    executor_implemented = bool(
        status.get("zone_execution_supported")
        and status.get("zone_execution_enabled")
    )
    base = {
        "schema_version": "1.0",
        "engine_version": PLAN_VERSION,
        "symbol": zone_map.get("symbol") or status.get("symbol"),
        "zone_map_id": zone_map.get("map_id"),
        "execution_authority_active": bool(status.get("zone_mode_active")),
        "nyao_mutation": False,
        "capital_sizing": capital_sizing,
    }
    quotes = _quotes(status, zone_map)
    base.update({
        "live_bid": round(quotes["bid"], 8) if quotes["bid"] > 0 else None,
        "live_ask": round(quotes["ask"], 8) if quotes["ask"] > 0 else None,
        "chart_price": round(quotes["chart_price"], 8),
        "chart_price_basis": "MT5_BID" if quotes["bid"] > 0 else "FALLBACK",
        "closed_m30_reference": round(quotes["closed_m30_reference"], 8),
    })
    if zone_map.get("state") != "DETECTED_NOT_ACTIVATED":
        return {
            **base,
            "state": "WAITING_FOR_ZONE_MAP",
            "mode": "SCALP_MODE",
            "ordinary_scalping_allowed": True,
            "zone_plan": None,
            "blockers": ["A validated detected zone map is not available."],
        }

    priority = _priority_zones(zone_map, quotes)
    containing = [
        zone for zone in priority
        if _inside(_zone_price(zone, quotes)[0], zone)
    ]
    containing_sides = {zone.get("side") for zone in containing}
    if len(containing_sides) > 1:
        return {
            **base,
            "state": "AMBIGUOUS_OVERLAPPING_ZONES",
            "mode": "ZONE_MODE_BLOCKED",
            "live_price": round(quotes["chart_price"], 8),
            "price_basis": "SIDE_AWARE_EXECUTABLE_QUOTES",
            "ordinary_scalping_allowed": False,
            "zone_plan": None,
            "blockers": ["Live price is inside conflicting priority demand and supply zones."],
        }

    if not containing:
        nearest = min(
            priority,
            key=lambda zone: _distance(_zone_price(zone, quotes)[0], zone),
            default=None,
        )
        nearest_price, nearest_basis = (
            _zone_price(nearest, quotes)
            if nearest is not None
            else (quotes["chart_price"], "MT5_BID")
        )
        return {
            **base,
            "state": "OUTSIDE_PRIORITY_ZONE",
            "mode": "SCALP_MODE",
            "live_price": round(nearest_price, 8),
            "price_basis": nearest_basis,
            "ordinary_scalping_allowed": True,
            "nearest_zone": nearest,
            "distance_to_nearest_zone": (
                round(_distance(nearest_price, nearest), 8) if nearest else None
            ),
            "zone_plan": None,
            "blockers": [],
        }

    zone = max(containing, key=lambda item: float(item.get("score") or 0.0))
    price, price_basis = _zone_price(zone, quotes)
    policy_record = get_zone_policy()
    plan = _trade_plan(
        zone=zone,
        zone_map=zone_map,
        status=status,
        policy_record=policy_record,
        live_price=price,
        capital_sizing=capital_sizing,
    )
    confirmation = plan["confirmation"]
    existing_exposure = int(status.get("strategy_open_positions") or 0) > 0
    existing_zone_plan_id = str(status.get("zone_plan_id") or "").strip()
    continuing_same_campaign = bool(
        existing_exposure
        and status.get("zone_mode_active")
        and existing_zone_plan_id == plan.get("plan_id")
    )
    conflicting_zone_campaign = bool(
        existing_exposure
        and status.get("zone_mode_active")
        and existing_zone_plan_id
        and existing_zone_plan_id != plan.get("plan_id")
    )
    capital_plan = capital_sizing or {}
    zone_capacity_available = bool(
        not capital_plan
        or (
            not capital_plan.get("veto_new_risk", False)
            and float(capital_plan.get("approved_zone_risk_amount") or 0.0) > 0.0
        )
    )
    broker_feasible = bool(
        confirmation.get(
            "broker_feasibility_within_limit",
            True,
        )
    )

    ready = (
        confirmation["side_signal_eligible"]
        and confirmation["spread_within_limit"]
        and broker_feasible
        and not confirmation["trading_paused"]
        and zone_capacity_available
        and not conflicting_zone_campaign
    )
    blockers: list[str] = []
    if not confirmation["side_signal_eligible"]:
        zone_confirmation = confirmation.get("zone_confirmation") or {}
        blockers.append(
            "Atlas zone confirmation is not currently eligible "
            f"({zone_confirmation.get('combined_score', 0):.1f}/"
            f"{zone_confirmation.get('threshold', 0):.1f}; directional "
            f"{zone_confirmation.get('directional_score', 0):.2f}/"
            f"{zone_confirmation.get('minimum_directional_score', 0):.2f})."
        )
    if not confirmation["spread_within_limit"]:
        blockers.append(
            "Current spread is outside the dedicated zone execution limit."
        )

    if not broker_feasible:
        feasibility = (
            plan.get(
                "broker_feasibility"
            )
            or {}
        )

        blockers.append(
            "Broker minimum-volume feasibility blocks this zone campaign: "
            + str(
                feasibility.get(
                    "decision_reason"
                )
                or (
                    "no executable 1/2/3-leg structure fits "
                    "the approved risk budget."
                )
            )
        )
    if confirmation["trading_paused"]:
        blockers.append("Nyao is currently paused.")
    if conflicting_zone_campaign:
        blockers.append("A different live zone campaign already owns the symbol's zone-campaign identity.")
    if not zone_capacity_available:
        blockers.append("Concurrent portfolio allocation has no approved zone risk capacity for this campaign.")

    # ------------------------------------------------------------------
    # P3.23A — Zone-aware scalp fallback
    # ------------------------------------------------------------------
    #
    # A qualified zone can still be valuable market context even when the
    # account cannot afford the broker-minimum zone campaign.
    #
    # In that specific case Atlas releases the ordinary scalp engine instead
    # of leaving the symbol idle.
    #
    # Safety:
    #   - concurrent portfolio capacity remains available
    #   - no global capital veto
    #   - scalp has a positive approved risk budget
    #   - zone campaign itself is broker/capital infeasible
    #
    # Nyao will use the zone side as directional context:
    #
    #   SUPPLY / SELL zone -> SELL scalp only
    #   DEMAND / BUY zone  -> BUY scalp only
    #
    # Normal scalp thresholds and execution gates remain unchanged.
    #
    allow_zone_aware_scalping = bool(
        not broker_feasible
        and not bool(
            capital_plan.get(
                "veto_new_risk",
                False,
            )
        )
        and float(
            capital_plan.get(
                "approved_scalp_risk_pct"
            )
            or 0.0
        ) > 0.0
        and not confirmation[
            "trading_paused"
        ]
    )

    return {
        **base,
        "state": (
            "ZONE_ENTRY_CONFIRMED"
            if ready
            else "ZONE_CAPITAL_INFEASIBLE"
            if (not broker_feasible or not zone_capacity_available)
            else "ZONE_WAITING_FOR_CONFIRMATION"
        ),
        "mode": "ZONE_MODE",
        "live_price": round(price, 8),
        "price_basis": price_basis,
        "ordinary_scalping_allowed": (
            allow_zone_aware_scalping
        ),

        "zone_aware_scalping_active": (
            allow_zone_aware_scalping
        ),

        "zone_aware_scalping_side": (
            plan["side"]
            if allow_zone_aware_scalping
            else "NONE"
        ),

        "zone_plan": plan,
        "blockers": blockers,
        "directive_preview": {
            "suspend_ordinary_scalp_entries": (
                not allow_zone_aware_scalping
            ),

            "zone_entry_allowed": ready,

            "zone_aware_scalping_active": (
                allow_zone_aware_scalping
            ),

            "zone_aware_scalping_side": (
                plan["side"]
                if allow_zone_aware_scalping
                else "NONE"
            ),
            "side": plan["side"],
            "plan_id": plan["plan_id"],
            "implemented_in_nyao": executor_implemented,
        },
    }


def flatten_zone_execution_directive(plan: dict[str, Any]) -> dict[str, Any]:
    """Create the flat, short-lived contract consumed by the MQL5 executor."""
    zone_plan = plan.get("zone_plan") or {}
    entries = list(zone_plan.get("entries") or [])
    targets = list(zone_plan.get("take_profits") or [])
    confirmation = ((zone_plan.get("confirmation") or {}).get("zone_confirmation") or {})
    source_zone = dict(zone_plan.get("source_zone") or {})
    directive: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_at_epoch": int(time.time()),
        "symbol": plan.get("symbol"),
        "zone_map_id": plan.get("zone_map_id") or "",
        "plan_id": zone_plan.get("plan_id") or "",
        "state": plan.get("state"),
        "mode": plan.get("mode"),
        "execution_requested": bool(
            plan.get("mode") == "ZONE_MODE"
            and len(entries) > 0
        ),
        "suspend_ordinary_scalp_entries": not bool(
            plan.get("ordinary_scalping_allowed", True)
        ),
        "zone_entry_allowed": bool(
            (plan.get("directive_preview") or {}).get("zone_entry_allowed")
        ),

        "zone_aware_scalping_active": bool(
            plan.get(
                "zone_aware_scalping_active",
                False,
            )
        ),

        "zone_aware_scalping_side": (
            plan.get(
                "zone_aware_scalping_side"
            )
            or "NONE"
        ),

        "side": zone_plan.get("side") or "NONE",
        "source_zone_id": source_zone.get("zone_id") or "",
        "source_zone_timeframe": source_zone.get("timeframe") or "",
        "source_zone_kind": source_zone.get("kind") or "",
        "source_zone_low": source_zone.get("low") or 0.0,
        "source_zone_high": source_zone.get("high") or 0.0,
        "stop_loss": zone_plan.get("stop_loss") or 0.0,
        "account_risk_pct": (
            (zone_plan.get("risk") or {}).get("account_risk_pct") or 0.0
        ),
        "zone_policy_epoch": confirmation.get("policy_epoch") or 0,
        "zone_policy_fingerprint": confirmation.get("policy_fingerprint") or "",
        "zone_confirmation_score": confirmation.get("combined_score") or 0.0,
        "zone_confirmation_threshold": confirmation.get("threshold") or 0.0,
        "zone_directional_score": confirmation.get("directional_score") or 0.0,
        "zone_minimum_directional_score": confirmation.get("minimum_directional_score") or 0.0,
        "zone_spread_filter_enabled": bool(
            ((zone_plan.get("confirmation") or {}).get("spread_assessment") or {}).get("enabled", True)
        ),
        "zone_market_spread_atr_ratio": (
            ((zone_plan.get("confirmation") or {}).get("spread_assessment") or {}).get("market_atr_ratio") or 0.75
        ),
        "zone_max_spread_stop_ratio": (
            ((zone_plan.get("confirmation") or {}).get("spread_assessment") or {}).get("maximum_stop_ratio") or 0.10
        ),
        "zone_max_spread_target_ratio": (
            ((zone_plan.get("confirmation") or {}).get("spread_assessment") or {}).get("maximum_target_ratio") or 0.15
        ),
        "zone_virtual_layer_activation_atr_ratio": (
            ((zone_plan.get("confirmation") or {}).get("spread_assessment") or {}).get("virtual_layer_activation_atr_ratio") or 0.25
        ),
        "zone_virtual_layer_execution": True,
        "entry_count": len(entries),
        "capital_sizing_version": (plan.get("capital_sizing") or {}).get("version") or "",
        "capital_sizing_active": bool(plan.get("capital_sizing")),
        "capital_veto_new_risk": bool((plan.get("capital_sizing") or {}).get("veto_new_risk", False)),
        "approved_scalp_risk_pct": (plan.get("capital_sizing") or {}).get("approved_scalp_risk_pct") or 0.0,
        "maximum_total_strategy_risk_pct": (plan.get("capital_sizing") or {}).get("maximum_total_strategy_risk_pct") or 0.0,
        # Atlas uses this snapshot to keep the dashboard and executor on the
        # exact same campaign while live broker exposure exists. Nyao ignores
        # this nested metadata and continues to consume the flat contract.
        "plan_snapshot": plan,
    }
    for index in range(3):
        entry = entries[index] if index < len(entries) else {}
        target = targets[index] if index < len(targets) else {}
        leg = index + 1
        directive[f"entry_{leg}_price"] = entry.get("entry_price") or 0.0
        directive[f"entry_{leg}_risk_pct"] = entry.get("risk_allocation_pct") or 0.0
        directive[f"tp_{leg}_price"] = target.get("price") or 0.0
        directive[f"tp_{leg}_close_pct"] = target.get("close_allocation_pct") or 0.0
    return directive


def persist_zone_execution_directive(
    plan: dict[str, Any],
    path: Path,
    status_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status_data = status_data or {}
    existing: dict[str, Any] = {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            existing = parsed
    except (OSError, json.JSONDecodeError):
        pass

    now_epoch = int(time.time())
    exposure_active = bool(
        int(status_data.get("strategy_open_positions") or 0) > 0
        or int(status_data.get("working_limit_orders") or 0) > 0
    )
    acknowledged_plan_id = str(status_data.get("zone_plan_id") or "")
    existing_plan_id = str(existing.get("plan_id") or "")
    active_acknowledged_campaign = bool(
        exposure_active
        and acknowledged_plan_id
        and acknowledged_plan_id == existing_plan_id
    )
    last_exposure_epoch = int(existing.get("campaign_last_exposure_epoch") or 0)
    reattach_grace_active = bool(
        existing.get("campaign_locked")
        and existing_plan_id
        and last_exposure_epoch > 0
        and now_epoch - last_exposure_epoch <= CAMPAIGN_REATTACH_GRACE_SECONDS
        and (
            not exposure_active
            or not acknowledged_plan_id
        )
    )
    lock_existing = active_acknowledged_campaign or reattach_grace_active
    if lock_existing:
        execution_defaults = flatten_zone_execution_directive(plan)
        lock_reason = (
            "ACTIVE_BROKER_EXPOSURE"
            if active_acknowledged_campaign
            else "EA_REATTACH_GRACE"
        )
        directive = {
            **existing,
            "generated_at_epoch": now_epoch,
            # Confirmation admits the campaign once. After Nyao acknowledges
            # it and broker exposure exists, a later score fluctuation must
            # manage—not de-authorize—the already-open campaign. Keeping this
            # true also lets Nyao restore unfilled layers that disappeared.
            "state": "ZONE_CAMPAIGN_ACTIVE",
            "mode": "ZONE_MODE",
            "execution_requested": True,
            "suspend_ordinary_scalp_entries": True,
            "zone_entry_allowed": True,
            "campaign_locked": True,
            "campaign_lock_reason": lock_reason,
            "campaign_last_exposure_epoch": (
                now_epoch
                if active_acknowledged_campaign
                else last_exposure_epoch
            ),
            "campaign_reattach_grace_seconds": CAMPAIGN_REATTACH_GRACE_SECONDS,
        }
        for key in (
            "zone_spread_filter_enabled",
            "zone_market_spread_atr_ratio",
            "zone_max_spread_stop_ratio",
            "zone_max_spread_target_ratio",
            "zone_virtual_layer_activation_atr_ratio",
            "zone_virtual_layer_execution",
        ):
            if key not in directive:
                directive[key] = execution_defaults[key]
    else:
        directive = {
            **flatten_zone_execution_directive(plan),
            "campaign_locked": False,
            "campaign_lock_reason": "",
            "campaign_last_exposure_epoch": 0,
            "campaign_reattach_grace_seconds": CAMPAIGN_REATTACH_GRACE_SECONDS,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    from backend.app.bridge.writer import write_json

    write_json(directive, path)
    return directive
