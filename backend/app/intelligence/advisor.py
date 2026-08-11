from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.intelligence.regime import classify_regime
from backend.app.intelligence.risk_governor import assess_risk


@dataclass
class Advice:
    mode: str
    fit: str
    confidence: float
    summary: str
    recommendations: List[str]
    cautions: List[str]
    proposed_changes: Dict[str, float | int | bool]
    auto_apply_allowed: bool
    generated_at: str
    regime: dict
    risk: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _f(status: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(status.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _i(status: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(status.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def generate_advice(status: dict[str, Any]) -> dict:
    """
    Atlas Intelligence Core v0.3.

    Advisory-only. It never writes commands.json.

    v0.2 fixes the earlier fallback that incorrectly described
    TREND + ELEVATED risk as "transitional", and it coordinates duplicate
    protection recommendations with the deterministic risk governor.
    """
    regime = classify_regime(status)
    risk = assess_risk(status)

    recommendations: List[str] = []
    cautions: List[str] = []
    proposed: Dict[str, float | int | bool] = {}

    current_buy_threshold = _f(
        status, "runtime_min_buy_signal_score", 4.5
    )
    current_sell_threshold = _f(
        status, "runtime_min_sell_signal_score", 4.5
    )
    current_base_lot = _f(
        status, "runtime_base_lot_size", 0.01
    )
    current_max_orders = _i(
        status, "runtime_max_open_orders", 1
    )
    current_positions = _i(
        status, "strategy_open_positions", 0
    )
    current_intrabar = not bool(
        status.get("runtime_enable_new_bar_entry_only", True)
    )
    duplicate_filter_enabled = bool(
        status.get(
            "runtime_enable_duplicate_distance_filter",
            True,
        )
    )

    direction = regime["direction"]
    market_regime = regime["regime"]
    risk_state = risk["state"]
    exposure_bias = risk["exposure_bias"]
    veto = bool(risk["veto_new_risk"])

    is_trend = market_regime in {
        "BULLISH_TREND",
        "BEARISH_TREND",
    }
    is_chop = market_regime in {
        "RANGE_CHOP",
        "LOW_VOL_COMPRESSION",
    }

    if veto:
        fit = "POOR"
        recommendations.append(
            "Do not add strategy risk while the risk governor veto is active."
        )
        recommendations.append(
            "Allow Nyao to manage existing exposure and recovery; fresh risk should remain constrained."
        )

        # Do not encode the veto as a max_open_orders change here.
        # max_open_orders cannot reliably distinguish fresh exposure from
        # recovery/management paths. Shadow Policy carries the veto as the
        # explicit conceptual control `new_risk_allowed = false`.
        proposed["base_lot_size"] = max(
            0.01,
            round(min(current_base_lot, 0.02), 2),
        )

    elif is_trend and risk_state in {"LOW", "MODERATE"}:
        fit = "GOOD"
        recommendations.append(
            "Current market structure is compatible with directional Nyao entries."
        )
        recommendations.append(
            "Keep risk sizing unchanged until more attributed outcomes are collected."
        )

    elif is_trend and risk_state == "ELEVATED":
        fit = "NEUTRAL"
        recommendations.append(
            f"{market_regime} is still directional, but elevated portfolio risk reduces Nyao's fit."
        )
        recommendations.append(
            "Do not increase lot size or maximum orders while risk remains elevated."
        )

        recommendations.append(
            "P3.52 anti-ratchet: do not mechanically raise the current signal threshold; require current-policy attributable outcome evidence before another tightening step."
        )

    elif is_chop:
        fit = "WEAK"
        recommendations.append(
            "Prefer stricter entry selectivity in choppy or compressed conditions."
        )
        recommendations.append(
            "Avoid increasing trade frequency."
        )
        recommendations.append(
            "P3.52 anti-ratchet: treat tighter thresholds/new-bar-only as hypotheses for the Gemini liveness-aware policy layer, not current-value-plus deterministic mutations."
        )

    elif market_regime == "TRANSITION":
        fit = "NEUTRAL"
        recommendations.append(
            "Market structure is transitional; hold risk settings steady until direction becomes clearer."
        )

    else:
        fit = "NEUTRAL"
        recommendations.append(
            f"Maintain conservative settings while Atlas observes {market_regime}."
        )

    if exposure_bias == "LONG_HEAVY":
        recommendations.append(
            "Avoid adding further long concentration unless the BUY signal advantage is unusually strong."
        )
        if direction == "BULLISH" and not veto:
            recommendations.append("P3.52: concentration may justify selectivity, but Atlas will not ratchet the live threshold upward without attributable current-epoch evidence.")
    elif exposure_bias == "SHORT_HEAVY":
        recommendations.append(
            "Avoid adding further short concentration unless the SELL signal advantage is unusually strong."
        )
        if direction == "BEARISH" and not veto:
            recommendations.append("P3.52: concentration may justify selectivity, but Atlas will not ratchet the live threshold upward without attributable current-epoch evidence.")

    active_chains = _i(status, "active_hedge_chains", 0)
    if active_chains > 0:
        recommendations.append(
            "Treat active hedge recovery as existing risk; do not size fresh entries as if the book were flat."
        )
        cautions.append(
            f"{active_chains} hedge chain(s) are currently active."
        )

    if not duplicate_filter_enabled:
        cautions.append(
            "Duplicate-distance protection is currently disabled."
        )
        # v0.2 does not attempt to optimize spacing yet. Until outcome
        # analysis supports a different policy, restore the protection when
        # risk is elevated or recovery is active.
        if risk_state in {"ELEVATED", "HIGH", "CRITICAL"} or active_chains > 0:
            proposed["enable_duplicate_distance_filter"] = True
            recommendations.append(
                "Restore duplicate-distance protection while risk is elevated or hedge recovery is active."
            )

    if not bool(status.get("spread_within_limit", True)):
        cautions.append(
            "Spread is outside Nyao's configured execution limit."
        )

    if bool(status.get("trading_paused", False)):
        cautions.append("Trading is paused by Nyao.")

    if bool(status.get("near_market_close", False)):
        cautions.append(
            "Market-close protection is active or close to activating."
        )

    if current_intrabar and market_regime == "RANGE_CHOP":
        recommendations.append(
            "Intrabar mode may over-sample noisy conditions, but P3.52 leaves temporal gating to the liveness-aware policy layer so new-bar-only cannot become a sticky self-throttling default."
        )

    # Never combine threshold loosening with exposure increases.
    risk_increase_fields = {
        "base_lot_size",
        "max_open_orders",
    }
    threshold_lowering = (
        proposed.get(
            "min_buy_signal_score",
            current_buy_threshold,
        )
        < current_buy_threshold
        or proposed.get(
            "min_sell_signal_score",
            current_sell_threshold,
        )
        < current_sell_threshold
    )
    if threshold_lowering and any(
        key in proposed for key in risk_increase_fields
    ):
        proposed.pop("base_lot_size", None)
        proposed.pop("max_open_orders", None)
        cautions.append(
            "Atlas suppressed a compound risk-increase recommendation."
        )

    confidence = (
        float(regime.get("confidence", 50.0)) * 0.6
        + (100.0 - float(risk.get("score", 0))) * 0.4
    )
    confidence = max(5.0, min(95.0, confidence))

    if veto:
        summary = (
            f"{market_regime}; risk governor is {risk_state} "
            "and vetoes additional risk."
        )
    else:
        summary = (
            f"{market_regime}; risk state {risk_state}; "
            f"exposure {exposure_bias}."
        )

    return Advice(
        mode="ADVISORY",
        fit=fit,
        confidence=round(confidence, 1),
        summary=summary,
        recommendations=recommendations,
        cautions=cautions,
        proposed_changes=proposed,
        auto_apply_allowed=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
        regime=regime,
        risk=risk,
    ).to_dict()