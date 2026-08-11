from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.app.intelligence.outcomes import get_trade_outcomes


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


def _effective_chain_id(trade: dict[str, Any]) -> int:
    """
    Recover the best observed hedge-chain identifier.

    A root may begin with chain_id=0 and later be assigned its own ticket as
    chain_id after hedge recovery begins, so latest_position is preferred.
    """
    latest = trade.get("latest_position") or {}
    initial = trade.get("initial_position") or {}

    for candidate in (
        latest.get("chain_id"),
        trade.get("chain_id"),
        initial.get("chain_id"),
    ):
        value = _i(candidate)
        if value > 0:
            return value

    if trade.get("origin_guess") == "HEDGE_ROOT_OR_ORIGINAL":
        return _i(trade.get("ticket"))

    return 0


def _member_summary(trade: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket": trade.get("ticket"),
        "type": trade.get("type"),
        "origin_guess": trade.get("origin_guess"),
        "initial_volume": trade.get("initial_volume"),
        "minimum_volume_observed": trade.get(
            "minimum_volume_observed"
        ),
        "max_hedge_level_observed": trade.get(
            "max_hedge_level_observed"
        ),
        "max_cycle_observed": trade.get(
            "max_cycle_observed"
        ),
        "final_observed_net_pl": trade.get(
            "final_observed_net_pl_before_disappearance"
        ),
        "max_favorable_net_pl_observed": trade.get(
            "max_favorable_net_pl_observed"
        ),
        "max_adverse_net_pl_observed": trade.get(
            "max_adverse_net_pl_observed"
        ),
        "first_seen_at": trade.get("first_seen_at"),
        "disappeared_at": trade.get("disappeared_at"),
    }


def analyze_recovery_chains(
    closed_limit: int = 2_000,
) -> dict[str, Any]:
    """
    Recovery-chain attribution v0.1.

    Groups root + hedge children into one recovery unit when the observed
    chain_id permits it. Monetary values remain observational because exact
    MT5 closed-deal P/L is not yet available.
    """
    payload = get_trade_outcomes(
        closed_limit=closed_limit,
        include_active=True,
    )
    closed = [t for t in (payload.get("closed") or []) if t.get("strategy_learning_eligible") and str(t.get("execution_integrity") or "").upper() == "CLEAN"]
    active = payload.get("active") or []

    all_trades = [
        {**trade, "_atlas_lifecycle_bucket": "CLOSED"}
        for trade in closed
    ] + [
        {**trade, "_atlas_lifecycle_bucket": "ACTIVE"}
        for trade in active
    ]

    chain_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    standalone: list[dict[str, Any]] = []
    unassigned_hedges: list[dict[str, Any]] = []

    for trade in all_trades:
        chain_id = _effective_chain_id(trade)
        origin = trade.get("origin_guess")

        if chain_id > 0:
            chain_groups[chain_id].append(trade)
        elif origin == "HEDGE_CHILD":
            unassigned_hedges.append(trade)
        else:
            standalone.append(trade)

    chains: list[dict[str, Any]] = []

    for chain_id, members in chain_groups.items():
        hedge_members = [
            trade
            for trade in members
            if trade.get("origin_guess") == "HEDGE_CHILD"
            or _i(trade.get("max_hedge_level_observed")) > 0
        ]
        roots = [
            trade
            for trade in members
            if _i(trade.get("ticket")) == chain_id
            or (
                trade.get("origin_guess")
                in {
                    "HEDGE_ROOT_OR_ORIGINAL",
                    "FRESH_OR_REENTRY",
                    "FRESH_MARKET",
                    "RECONSTRUCTED_MT5_HISTORY",
                }
                and _i(trade.get("max_hedge_level_observed")) == 0
            )
        ]

        closed_members = [
            trade
            for trade in members
            if trade.get("_atlas_lifecycle_bucket") == "CLOSED"
        ]
        active_members = [
            trade
            for trade in members
            if trade.get("_atlas_lifecycle_bucket") == "ACTIVE"
        ]

        def member_closed_result(trade: dict[str, Any]) -> float:
            if trade.get("exact_realized_pl_available"):
                return _f(trade.get("realized_net_pl"))
            return _f(trade.get("final_observed_net_pl_before_disappearance"))

        observed_closed_sum = sum(
            member_closed_result(trade)
            for trade in closed_members
        )
        exact_closed_member_count = sum(
            1 for trade in closed_members
            if trade.get("exact_realized_pl_available")
        )

        current_open_sum = sum(
            _f(trade.get("last_observed_net_pl"))
            for trade in active_members
        )

        marked_observed_sum = observed_closed_sum + current_open_sum

        member_mfe_sum = sum(
            _f(trade.get("max_favorable_net_pl_observed"))
            for trade in members
        )
        member_mae_sum = sum(
            _f(trade.get("max_adverse_net_pl_observed"))
            for trade in members
        )

        max_level = max(
            (
                _i(trade.get("max_hedge_level_observed"))
                for trade in members
            ),
            default=0,
        )
        max_cycle = max(
            (
                _i(trade.get("max_cycle_observed"))
                for trade in members
            ),
            default=0,
        )

        root_ticket = None
        root_state = "MISSING"

        if roots:
            root = roots[0]
            root_ticket = root.get("ticket")
            root_state = (
                "ACTIVE"
                if root.get("_atlas_lifecycle_bucket") == "ACTIVE"
                else "CLOSED"
            )

        has_hedge = bool(hedge_members) or max_level > 0

        if active_members:
            chain_state = "ACTIVE"
        elif has_hedge and not roots:
            chain_state = "INCOMPLETE_HISTORY"
        else:
            chain_state = "COMPLETE"

        eligible_for_learning = chain_state == "COMPLETE"

        observed_result_class = "UNSCORED"
        if eligible_for_learning:
            observed_result_class = (
                "POSITIVE"
                if observed_closed_sum > 0
                else "NEGATIVE"
                if observed_closed_sum < 0
                else "FLAT"
            )

        chains.append(
            {
                "chain_id": chain_id,
                "chain_state": chain_state,
                "eligible_for_learning": eligible_for_learning,
                "member_count": len(members),
                "closed_member_count": len(closed_members),
                "active_member_count": len(active_members),
                "root_count": len(roots),
                "root_ticket": root_ticket,
                "root_state": root_state,
                "hedge_child_count": len(hedge_members),
                "max_hedge_level_observed": max_level,
                "max_cycle_observed": max_cycle,
                "observed_closed_member_pl_sum": round(
                    observed_closed_sum,
                    2,
                ),
                "exact_realized_closed_member_count": exact_closed_member_count,
                "exact_realized_chain_pl_available": bool(
                    eligible_for_learning
                    and exact_closed_member_count == len(closed_members)
                ),
                "current_open_member_pl_sum": round(
                    current_open_sum,
                    2,
                ),
                "observed_chain_mark_to_market": round(
                    marked_observed_sum,
                    2,
                ),
                "observed_result_class": observed_result_class,
                "member_mfe_sum_non_synchronous": round(
                    member_mfe_sum,
                    2,
                ),
                "member_mae_sum_non_synchronous": round(
                    member_mae_sum,
                    2,
                ),
                "members": [
                    {
                        **_member_summary(trade),
                        "lifecycle_bucket": trade.get(
                            "_atlas_lifecycle_bucket"
                        ),
                        "current_open_net_pl": (
                            _f(trade.get("last_observed_net_pl"))
                            if trade.get("_atlas_lifecycle_bucket") == "ACTIVE"
                            else None
                        ),
                    }
                    for trade in sorted(
                        members,
                        key=lambda item: str(
                            item.get("first_seen_at") or ""
                        ),
                    )
                ],
            }
        )

    chains.sort(
        key=lambda chain: abs(
            _f(chain.get("observed_member_exit_pl_sum"))
        ),
        reverse=True,
    )

    true_recovery_chains = [
        chain
        for chain in chains
        if chain["hedge_child_count"] > 0
        or chain["max_hedge_level_observed"] > 0
    ]

    complete_chains = [
        chain
        for chain in true_recovery_chains
        if chain["chain_state"] == "COMPLETE"
    ]
    active_chains = [
        chain
        for chain in true_recovery_chains
        if chain["chain_state"] == "ACTIVE"
    ]
    incomplete_chains = [
        chain
        for chain in true_recovery_chains
        if chain["chain_state"] == "INCOMPLETE_HISTORY"
    ]

    positive = sum(
        1
        for chain in complete_chains
        if chain["observed_closed_member_pl_sum"] > 0
    )
    negative = sum(
        1
        for chain in complete_chains
        if chain["observed_closed_member_pl_sum"] < 0
    )

    return {
        "ready": bool(closed or active),
        "closed_ticket_count": len(closed),
        "active_ticket_count": len(active),
        "identified_chain_groups": len(chains),
        "recovery_chain_count": len(true_recovery_chains),
        "complete_recovery_chain_count": len(complete_chains),
        "active_recovery_chain_count": len(active_chains),
        "incomplete_history_chain_count": len(incomplete_chains),
        "standalone_trade_count": len(standalone),
        "unassigned_hedge_ticket_count": len(
            unassigned_hedges
        ),
        "recovery_chain_observed_positive": positive,
        "recovery_chain_observed_negative": negative,
        "recovery_chain_observed_pl_sum": round(
            sum(
                _f(
                    chain.get(
                        "observed_closed_member_pl_sum"
                    )
                )
                for chain in complete_chains
            ),
            2,
        ),
        "active_chain_mark_to_market_sum": round(
            sum(
                _f(
                    chain.get(
                        "observed_chain_mark_to_market"
                    )
                )
                for chain in active_chains
            ),
            2,
        ),
        "chains": true_recovery_chains,
        "limitations": [
            "Chain grouping uses observed chain_id metadata and may be incomplete for trades first tracked before chain telemetry was available.",
            "Closed member P/L uses authoritative MT5 realised deal P/L when available and falls back to the last observed position P/L only for legacy records.",
            "Per-member MFE/MAE extrema are not simultaneous and therefore must not be interpreted as a true chain equity curve.",
            "Only COMPLETE chains are scored for recovery outcome analytics.",
            "ACTIVE chains are monitored mark-to-market and excluded from scoring.",
            "INCOMPLETE_HISTORY chains are excluded from learning because the root or earlier lifecycle is missing.",
            "Recovery chains should be evaluated as composite recovery units rather than judging hedge children independently.",
        ],
    }