from __future__ import annotations

from collections import Counter
from statistics import mean, median
from typing import Any

from backend.app.intelligence.history import get_history
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


def _effective(
    name: str,
    status: dict[str, Any],
    command: dict[str, Any],
    default: Any = None,
) -> Any:
    if command.get(name) is not None:
        return command.get(name)
    runtime = status.get(f"runtime_{name}")
    return runtime if runtime is not None else default


def _capture_metrics(closed: list[dict[str, Any]]) -> dict[str, Any]:
    lifetimes: list[float] = []
    surrenders: list[float] = []
    capture_ratios: list[float] = []
    fresh_count = 0
    for trade in closed:
        if trade.get("origin_guess") == "FRESH_OR_REENTRY":
            fresh_count += 1
        lifetime = _f(trade.get("observed_lifetime_minutes"), -1)
        if lifetime >= 0:
            lifetimes.append(lifetime)
        mfe = _f(trade.get("max_favorable_net_pl_observed"))
        final = _f(
            trade.get("realized_net_pl")
            if trade.get("exact_realized_pl_available")
            else trade.get("final_observed_net_pl_before_disappearance")
        )
        if mfe > 0:
            surrenders.append(max(0.0, mfe - final))
            capture_ratios.append(max(0.0, min(1.0, final / mfe)))
    return {
        "closed_trade_count": len(closed),
        "fresh_or_reentry_count": fresh_count,
        "average_holding_minutes": round(mean(lifetimes), 2) if lifetimes else None,
        "median_holding_minutes": round(median(lifetimes), 2) if lifetimes else None,
        "average_mfe_surrender": round(mean(surrenders), 2) if surrenders else None,
        "average_mfe_capture_ratio": (
            round(mean(capture_ratios), 3) if capture_ratios else None
        ),
        "trades_with_mfe_evidence": len(capture_ratios),
    }


def analyze_scalping_responsiveness(
    status: dict[str, Any],
    current_command: dict[str, Any],
    *,
    history: dict[str, Any] | None = None,
    trade_outcomes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Diagnose responsiveness without treating higher frequency as an objective."""
    history = history or get_history(limit=720)
    trade_outcomes = trade_outcomes or get_trade_outcomes(
        closed_limit=2_000,
        include_active=False,
    )
    records = history.get("records") or []
    closed = trade_outcomes.get("closed") or []

    block_counts: Counter[str] = Counter()
    eligible = 0
    score_gaps: list[float] = []
    for record in records:
        signal = record.get("signal") or {}
        for side in ("buy", "sell"):
            if signal.get(f"{side}_entry_eligible"):
                eligible += 1
            reason = str(signal.get(f"{side}_block_reason") or "NONE").upper()
            if reason not in {
                "", "NONE", "CLEAR", "ELIGIBLE", "SIGNAL_READY",
                "LIMIT_ORDER_PLACED", "MARKET_ORDER_PLACED",
            }:
                block_counts[reason] += 1
            score = _f(signal.get(f"{side}_adjusted_score"))
            threshold = _f(signal.get(f"{side}_effective_threshold"))
            if threshold > score:
                score_gaps.append(threshold - score)

    evaluations = len(records) * 2
    new_bar_only = bool(
        _effective("enable_new_bar_entry_only", status, current_command, True)
    )
    smoothing = _i(
        _effective("signal_smoothing_candles", status, current_command, 2), 2
    )
    limit_entry = bool(_effective("enable_limit_entry", status, current_command, False))
    max_per_candle = _i(
        _effective("max_trades_per_candle", status, current_command, 1), 1
    )
    duplicate_filter = bool(
        _effective("enable_duplicate_distance_filter", status, current_command, True)
    )
    health_grace = _i(_effective("health_grace_bars", status, current_command, 2), 2)
    buy_threshold = _f(
        _effective("min_buy_signal_score", status, current_command, 4.5), 4.5
    )
    sell_threshold = _f(
        _effective("min_sell_signal_score", status, current_command, 4.5), 4.5
    )

    latency_score = 0
    latency_score += 30 if new_bar_only else 0
    latency_score += min(18, max(0, smoothing - 1) * 9)
    latency_score += 18 if limit_entry else 0
    latency_score += min(15, max(0, health_grace) * 5)
    latency_score += min(19, max(0.0, (mean([buy_threshold, sell_threshold]) - 4.0) * 6))
    latency_score = round(min(100.0, latency_score), 1)
    profile = "FAST" if latency_score <= 25 else "BALANCED" if latency_score <= 55 else "SELECTIVE"

    levers: list[dict[str, Any]] = []
    if new_bar_only:
        levers.append({
            "control": "enable_new_bar_entry_only",
            "direction": "CONSIDER_FALSE",
            "effect": "Evaluate qualified entries intrabar instead of waiting for the next candle.",
            "required_companion_controls": {
                "max_trades_per_candle": "must be <= 1",
                "enable_duplicate_distance_filter": "must remain true",
            },
        })
    if smoothing > 1:
        levers.append({
            "control": "signal_smoothing_candles",
            "direction": "CONSIDER_LOWER",
            "effect": "Reduce multi-candle confirmation delay while accepting more signal noise.",
        })
    if limit_entry:
        levers.append({
            "control": "enable_limit_entry",
            "direction": "REGIME_DEPENDENT",
            "effect": "Momentum regimes may favor immediate market entry; slow/choppy regimes may retain pullback limits.",
        })
    if health_grace > 0:
        levers.append({
            "control": "health_grace_bars",
            "direction": "CONSIDER_LOWER",
            "effect": "Allow deteriorating positions to be managed sooner.",
        })

    capture = _capture_metrics(closed)
    evidence_samples = len(records) + len(closed)
    evidence_quality = (
        "MODERATE" if len(records) >= 60 and len(closed) >= 20
        else "EARLY" if evidence_samples >= 20
        else "LIMITED"
    )
    dominant = [
        {"reason": reason, "count": count, "share_pct": round(count / evaluations * 100, 2) if evaluations else 0.0}
        for reason, count in block_counts.most_common(8)
    ]

    return {
        "version": "1.0",
        "symbol": status.get("symbol"),
        "objective": "IMPROVE_NET_SCALPING_RESPONSIVENESS_NOT_RAW_TRADE_COUNT",
        "profile": profile,
        "latency_pressure_score": latency_score,
        "evidence_quality": evidence_quality,
        "current_controls": {
            "enable_new_bar_entry_only": new_bar_only,
            "signal_smoothing_candles": smoothing,
            "enable_limit_entry": limit_entry,
            "max_trades_per_candle": max_per_candle,
            "enable_duplicate_distance_filter": duplicate_filter,
            "health_grace_bars": health_grace,
            "min_buy_signal_score": buy_threshold,
            "min_sell_signal_score": sell_threshold,
        },
        "entry_observations": {
            "history_snapshot_count": len(records),
            "side_evaluation_count": evaluations,
            "eligible_evaluation_count": eligible,
            "eligible_rate_pct": round(eligible / evaluations * 100, 2) if evaluations else None,
            "average_score_deficit_when_blocked": round(mean(score_gaps), 3) if score_gaps else None,
            "dominant_block_reasons": dominant,
            "last_order": {
                "attempted": status.get("last_order_attempted"),
                "successful": status.get("last_order_success"),
                "direction": status.get("last_order_direction"),
                "mode": status.get("last_order_mode"),
                "time_epoch": status.get("last_order_time_epoch"),
            },
        },
        "exit_observations": capture,
        "live_positions": {
            "count": len(status.get("positions") or []),
            "average_age_seconds": (
                round(mean([_f(row.get("age_seconds")) for row in status.get("positions") or []]), 1)
                if status.get("positions") else None
            ),
        },
        "candidate_levers": levers,
        "hard_interaction_rules": [
            "Intrabar entry requires max_trades_per_candle <= 1 and duplicate-distance protection enabled.",
            "Do not lower both entry selectivity and exit protection without a measurable regime-specific thesis.",
            "Judge speed changes by net expectancy, spread/slippage, holding time, MFE capture and tail loss—not trades per hour.",
            "Position-sensitive exit changes apply only through Policy Epoch protection.",
        ],
        "missing_telemetry": [
            "Exact first-signal-to-order latency is not yet emitted by Nyao.",
            "Exact limit-order signal-to-fill latency is not yet persisted.",
            "Commission/slippage attribution may be incomplete when realized exit-deal data is unavailable.",
        ],
    }
