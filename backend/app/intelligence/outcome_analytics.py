from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from backend.app.intelligence.outcomes import get_trade_outcomes
from backend.app.intelligence.recovery_attribution import (
    analyze_recovery_chains,
)
from backend.app.intelligence.risk_units import build_risk_units


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    q = max(0.0, min(1.0, q))

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower

    return (
        ordered[lower] * (1.0 - fraction)
        + ordered[upper] * fraction
    )


def _group_key(
    trade: dict[str, Any],
    dimension: str,
) -> str:
    entry = trade.get("entry_context") or {}

    if dimension == "regime":
        return str(entry.get("regime") or "UNKNOWN")
    if dimension == "fit":
        return str(entry.get("fit") or "UNKNOWN")
    if dimension == "risk":
        return str(entry.get("risk_state") or "UNKNOWN")
    if dimension == "origin":
        return str(trade.get("origin_guess") or "UNKNOWN")
    if dimension == "mode":
        return str(trade.get("trading_mode") or "UNKNOWN")
    if dimension == "scalp_context":
        return str(
            trade.get("scalp_context_class") or "NEUTRAL_SCALP"
        )
    if dimension == "duplicate_filter":
        duplicate = entry.get("duplicate_distance") or {}
        enabled = duplicate.get("enabled")

        if enabled is True:
            return "ON"
        if enabled is False:
            return "OFF"

        runtime = entry.get("runtime") or {}
        runtime_enabled = runtime.get(
            "runtime_enable_duplicate_distance_filter"
        )

        if runtime_enabled is True:
            return "ON"
        if runtime_enabled is False:
            return "OFF"

        return "UNKNOWN"

    return "UNKNOWN"


def _runtime_fingerprint(
    trade: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    entry = trade.get("entry_context") or {}
    runtime = entry.get("runtime") or {}

    normalized = {
        key.removeprefix("runtime_"): value
        for key, value in runtime.items()
        if key.startswith("runtime_")
    }

    if not normalized:
        return "UNKNOWN", {}

    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    fingerprint = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()[:12]

    return fingerprint, normalized


def _tail_metrics(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    finals = [
        _f(
            trade.get(
                "final_observed_net_pl_before_disappearance"
            )
        )
        for trade in trades
    ]

    losses = sorted(
        abs(value)
        for value in finals
        if value < 0
    )

    mfe_surrender = []
    positive_capture_ratios = []

    for trade, final_pl in zip(trades, finals):
        mfe = _f(
            trade.get("max_favorable_net_pl_observed")
        )

        if mfe > 0:
            mfe_surrender.append(
                max(0.0, mfe - final_pl)
            )

            if final_pl > 0:
                positive_capture_ratios.append(
                    max(
                        0.0,
                        min(1.0, final_pl / mfe),
                    )
                )

    p50_loss = _percentile(losses, 0.50)
    p90_loss = _percentile(losses, 0.90)
    p95_loss = _percentile(losses, 0.95)

    return {
        "loss_count": len(losses),
        "median_loss_abs": (
            round(p50_loss, 2)
            if p50_loss is not None
            else None
        ),
        "p90_loss_abs": (
            round(p90_loss, 2)
            if p90_loss is not None
            else None
        ),
        "p95_loss_abs": (
            round(p95_loss, 2)
            if p95_loss is not None
            else None
        ),
        "largest_loss_abs": (
            round(max(losses), 2)
            if losses
            else None
        ),
        "average_mfe_surrender": (
            round(
                sum(mfe_surrender)
                / len(mfe_surrender),
                2,
            )
            if mfe_surrender
            else 0.0
        ),
        "average_positive_capture_ratio": (
            round(
                sum(positive_capture_ratios)
                / len(positive_capture_ratios),
                3,
            )
            if positive_capture_ratios
            else None
        ),
    }


def _summarize_group(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    if not trades:
        return {
            "count": 0,
            "positive": 0,
            "negative": 0,
            "positive_rate_pct": 0.0,
            "observed_pl_sum": 0.0,
            "observed_pl_mean": 0.0,
            "average_positive": 0.0,
            "average_negative": 0.0,
            "payoff_ratio_abs": None,
            "average_mfe": 0.0,
            "average_mae": 0.0,
            "average_observed_lifetime_minutes": 0.0,
            "tail": _tail_metrics([]),
        }

    observed = [
        _f(
            trade.get(
                "final_observed_net_pl_before_disappearance"
            )
        )
        for trade in trades
    ]

    positive_values = [
        value
        for value in observed
        if value > 0
    ]
    negative_values = [
        value
        for value in observed
        if value < 0
    ]

    avg_positive = (
        sum(positive_values) / len(positive_values)
        if positive_values
        else 0.0
    )
    avg_negative = (
        sum(negative_values) / len(negative_values)
        if negative_values
        else 0.0
    )

    payoff_ratio = None
    if avg_negative < 0:
        payoff_ratio = avg_positive / abs(avg_negative)

    mfe = [
        _f(trade.get("max_favorable_net_pl_observed"))
        for trade in trades
    ]
    mae = [
        _f(trade.get("max_adverse_net_pl_observed"))
        for trade in trades
    ]
    lifetimes = [
        _f(trade.get("observed_lifetime_minutes"))
        for trade in trades
    ]

    return {
        "count": len(trades),
        "positive": len(positive_values),
        "negative": len(negative_values),
        "positive_rate_pct": round(
            len(positive_values)
            / len(trades)
            * 100.0,
            2,
        ),
        "observed_pl_sum": round(
            sum(observed),
            2,
        ),
        "observed_pl_mean": round(
            sum(observed) / len(trades),
            2,
        ),
        "average_positive": round(
            avg_positive,
            2,
        ),
        "average_negative": round(
            avg_negative,
            2,
        ),
        "payoff_ratio_abs": (
            round(payoff_ratio, 3)
            if payoff_ratio is not None
            else None
        ),
        "average_mfe": round(
            sum(mfe) / len(mfe),
            2,
        ),
        "average_mae": round(
            sum(mae) / len(mae),
            2,
        ),
        "average_observed_lifetime_minutes": round(
            sum(lifetimes) / len(lifetimes),
            2,
        ),
        "tail": _tail_metrics(trades),
    }


def _by_dimension(
    trades: list[dict[str, Any]],
    dimension: str,
) -> dict[str, Any]:
    groups: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for trade in trades:
        groups[
            _group_key(
                trade,
                dimension,
            )
        ].append(trade)

    return {
        key: _summarize_group(group_trades)
        for key, group_trades in sorted(
            groups.items(),
            key=lambda item: (
                -len(item[1]),
                item[0],
            ),
        )
    }


def _parameter_contexts(
    trades: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)
    configs: dict[
        str,
        dict[str, Any],
    ] = {}

    for trade in trades:
        fingerprint, runtime = _runtime_fingerprint(
            trade
        )
        grouped[fingerprint].append(trade)

        if runtime:
            configs[fingerprint] = runtime

    rows = []

    for fingerprint, group in sorted(
        grouped.items(),
        key=lambda item: -len(item[1]),
    ):
        summary = _summarize_group(group)

        rows.append(
            {
                "fingerprint": fingerprint,
                "count": len(group),
                "summary": summary,
                "runtime": configs.get(
                    fingerprint,
                    {},
                ),
            }
        )

    return {
        "unique_runtime_configurations": len(grouped),
        "configurations": rows[:25],
        "note": (
            "A runtime fingerprint identifies the full runtime "
            "configuration observed at first tracking of each ticket."
        ),
    }


def _performance_pl(trade: dict[str, Any]) -> tuple[float, bool]:
    exact = bool(trade.get("exact_realized_pl_available"))
    if exact:
        return _f(trade.get("realized_net_pl")), True
    return _f(trade.get("final_observed_net_pl_before_disappearance")), False


def _performance_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        trades,
        key=lambda trade: (
            _f(trade.get("close_time_epoch")),
            str(trade.get("disappeared_at") or ""),
        ),
    )
    values_and_quality = [_performance_pl(trade) for trade in ordered]
    values = [item[0] for item in values_and_quality]
    exact_count = sum(1 for _value, exact in values_and_quality if exact)
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    cumulative = 0.0
    peak = 0.0
    maximum_drawdown = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)
    count = len(values)
    sample_state = "INSUFFICIENT" if count < 5 else "EARLY" if count < 20 else "EVIDENCE_AVAILABLE"
    return {
        "closed_trades": count,
        "exact_realized_count": exact_count,
        "inferred_count": count - exact_count,
        "sample_state": sample_state,
        "net_pl": round(sum(values), 2),
        "expectancy": round(sum(values) / count, 2) if count else 0.0,
        "win_rate_pct": round(len(wins) / count * 100.0, 2) if count else 0.0,
        "average_win": round(gross_profit / len(wins), 2) if wins else 0.0,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "maximum_closed_trade_drawdown": round(maximum_drawdown, 2),
    }


def _risk_unit_performance_summary(units: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [u for u in units if u.get("state") == "COMPLETE"]
    values = [_f(u.get("realized_net_pl")) for u in completed]
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    net = sum(values)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        running += value
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
    return {
        "closed_risk_units": len(completed),
        "exact_realized_count": sum(1 for u in completed if u.get("exact_realized_pl_available")),
        "inferred_count": sum(1 for u in completed if not u.get("exact_realized_pl_available")),
        "sample_state": "INSUFFICIENT" if len(completed) < 20 else "ESTABLISHING" if len(completed) < 100 else "MATURE",
        "net_pl": round(net, 2),
        "expectancy": round(net / len(completed), 2) if completed else 0.0,
        "win_rate_pct": round(100.0 * len(wins) / len(completed), 2) if completed else 0.0,
        "average_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "average_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (None if gross_win > 0 else 0.0),
        "maximum_closed_unit_drawdown": round(max_dd, 2),
    }


def evaluate_policy_performance(closed_limit: int = 2_000) -> dict[str, Any]:
    """Evaluate strategic performance by completed composite risk unit."""
    payload = get_trade_outcomes(closed_limit=closed_limit, include_active=True)
    risk_report = build_risk_units(payload)
    completed = [u for u in (risk_report.get("units") or []) if u.get("state") == "COMPLETE" and u.get("strategy_learning_eligible")]
    epochs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    modes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    types: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in completed:
        epoch = int(_f(unit.get("policy_epoch")))
        epochs[str(epoch) if epoch > 0 else "UNKNOWN"].append(unit)
        modes[str(unit.get("trading_mode") or "UNKNOWN")].append(unit)
        types[str(unit.get("unit_type") or "UNKNOWN")].append(unit)

    epoch_rows = [{"policy_epoch": key, **_risk_unit_performance_summary(group)} for key, group in epochs.items()]
    epoch_rows.sort(key=lambda row: (row["policy_epoch"] == "UNKNOWN", -int(row["policy_epoch"]) if row["policy_epoch"] != "UNKNOWN" else 0))
    mode_rows = [{"trading_mode": key, **_risk_unit_performance_summary(group)} for key, group in modes.items()]
    type_rows = [{"risk_unit_type": key, **_risk_unit_performance_summary(group)} for key, group in types.items()]
    overall = _risk_unit_performance_summary(completed)
    return {
        "version": "2.0",
        "ready": bool(completed),
        "closed_risk_unit_count": len(completed),
        "active_risk_unit_count": int(risk_report.get("active_unit_count") or 0),
        "ticket_level_closed_count": len(payload.get("closed") or []),
        "consecutive_completed_loss_units": int(risk_report.get("consecutive_completed_loss_units") or 0),
        "overall": overall,
        "by_policy_epoch": epoch_rows,
        "by_trading_mode": mode_rows,
        "by_risk_unit_type": type_rows,
        "quality": {
            "exact_realized_pl_available": overall["exact_realized_count"] > 0,
            "exact_realized_count": overall["exact_realized_count"],
            "inferred_count": overall["inferred_count"],
        },
        "interpretation": (
            "Strategic performance is scored by completed risk unit. Recovery-chain and zone-campaign legs are composite and never count as independent wins/losses while the unit is active."
        ),
    }


def analyze_trade_outcomes(
    closed_limit: int = 2_000,
) -> dict[str, Any]:
    """
    Outcome Analytics v0.2.

    Adds tail-loss severity, MFE surrender, runtime-configuration
    attribution, and composite recovery-chain analysis.
    """
    payload = get_trade_outcomes(
        closed_limit=closed_limit,
        include_active=False,
    )

    closed = [t for t in (payload.get("closed") or []) if t.get("strategy_learning_eligible") and str(t.get("execution_integrity") or "").upper() == "CLEAN"]

    if not closed:
        return {
            "ready": False,
            "closed_count": 0,
            "message": (
                "No closed/disappeared tracked trades "
                "are available yet."
            ),
            "exact_realized_pl_available": False,
        }

    fresh = [
        trade
        for trade in closed
        if trade.get("origin_guess")
        == "FRESH_OR_REENTRY"
    ]

    result_classes = Counter(
        trade.get(
            "observed_result_class",
            "UNKNOWN",
        )
        for trade in closed
    )

    recovery = analyze_recovery_chains(
        closed_limit=closed_limit,
    )

    return {
        "version": "0.2",
        "ready": True,
        "closed_count": len(closed),
        "fresh_or_reentry_count": len(fresh),
        "exact_realized_pl_available": False,
        "outcome_quality": (
            "INFERRED_FROM_OPEN_POSITION_TELEMETRY"
        ),
        "all_tracked": _summarize_group(closed),
        "fresh_or_reentry": _summarize_group(fresh),
        "result_class_counts": dict(
            result_classes.most_common()
        ),
        "by_entry_regime": _by_dimension(
            closed,
            "regime",
        ),
        "by_entry_fit": _by_dimension(
            closed,
            "fit",
        ),
        "by_entry_risk": _by_dimension(
            closed,
            "risk",
        ),
        "by_origin": _by_dimension(
            closed,
            "origin",
        ),
        "by_trading_mode": _by_dimension(
            closed,
            "mode",
        ),
        "by_duplicate_filter": _by_dimension(
            closed,
            "duplicate_filter",
        ),
        "by_scalp_context": _by_dimension(
            closed,
            "scalp_context",
        ),
        "parameter_contexts": _parameter_contexts(
            closed
        ),
        "recovery_attribution": recovery,
        "interpretation_rules": [
            "Observed P/L is the final open-position P/L captured before a ticket disappeared.",
            "Observed P/L must not be treated as exact realised trade profit.",
            "Positive rate alone is insufficient; expectancy, payoff ratio, MFE surrender, MAE and tail-loss severity matter.",
            "Recovery chains must be evaluated as composite units; hedge-child ticket outcomes are not independent strategy trades.",
            "Runtime-configuration comparisons are observational and may be confounded by regime, risk and manual changes.",
            "Duplicate-filter ON/OFF comparisons are observational and may be confounded by changing market conditions.",
            "Do not use these results for automatic parameter optimization yet.",
        ],
    }
