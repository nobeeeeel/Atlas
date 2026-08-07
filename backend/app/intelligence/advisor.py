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


def generate_advice(status: dict[str, Any]) -> dict:
    """
    Atlas Intelligence Core v0.1.

    Advisory-only. proposed_changes are suggestions for later review and are
    NEVER written to commands.json by this module.
    """
    regime = classify_regime(status)
    risk = assess_risk(status)

    recommendations: List[str] = []
    cautions: List[str] = []
    proposed: Dict[str, float | int | bool] = {}

    current_buy_threshold = float(status.get("runtime_min_buy_signal_score", 4.5) or 4.5)
    current_sell_threshold = float(status.get("runtime_min_sell_signal_score", 4.5) or 4.5)
    current_base_lot = float(status.get("runtime_base_lot_size", 0.01) or 0.01)
    current_max_orders = int(status.get("runtime_max_open_orders", 1) or 1)
    current_intrabar = not bool(status.get("runtime_enable_new_bar_entry_only", True))

    direction = regime["direction"]
    market_regime = regime["regime"]
    risk_state = risk["state"]
    exposure_bias = risk["exposure_bias"]
    veto = bool(risk["veto_new_risk"])

    if veto:
        fit = "POOR"
        recommendations.append("Do not increase strategy risk while the risk governor veto is active.")
        recommendations.append("Preserve or reduce exposure until the veto condition clears.")
        proposed["max_open_orders"] = max(1, min(current_max_orders, int(status.get("strategy_open_positions", 0) or 0) + 1))
        proposed["base_lot_size"] = max(0.01, round(min(current_base_lot, 0.02), 2))
    elif market_regime in {"BULLISH_TREND", "BEARISH_TREND"} and risk_state in {"LOW", "MODERATE"}:
        fit = "GOOD"
        recommendations.append("Current market structure is compatible with directional Nyao entries.")
        recommendations.append("Keep risk sizing unchanged until more advisory outcomes are collected.")
    elif market_regime in {"RANGE_CHOP", "LOW_VOL_COMPRESSION"}:
        fit = "WEAK"
        recommendations.append("Prefer stricter entry selectivity in choppy/compressed conditions.")
        recommendations.append("Avoid increasing trade frequency.")
        proposed["min_buy_signal_score"] = round(min(10.0, current_buy_threshold + 0.5), 2)
        proposed["min_sell_signal_score"] = round(min(10.0, current_sell_threshold + 0.5), 2)
        if current_intrabar:
            proposed["enable_new_bar_entry_only"] = True
    else:
        fit = "NEUTRAL"
        recommendations.append("Maintain current risk settings while the market regime is transitional.")

    if exposure_bias == "LONG_HEAVY":
        recommendations.append("Avoid adding further long concentration unless the signal advantage is unusually strong.")
        if direction == "BULLISH":
            proposed["min_buy_signal_score"] = round(min(10.0, max(current_buy_threshold, current_buy_threshold + 0.3)), 2)
    elif exposure_bias == "SHORT_HEAVY":
        recommendations.append("Avoid adding further short concentration unless the signal advantage is unusually strong.")
        if direction == "BEARISH":
            proposed["min_sell_signal_score"] = round(min(10.0, max(current_sell_threshold, current_sell_threshold + 0.3)), 2)

    active_chains = int(status.get("active_hedge_chains", 0) or 0)
    if active_chains > 0:
        recommendations.append("Treat active hedge recovery as existing risk; do not size fresh entries as if the book were flat.")
        cautions.append(f"{active_chains} hedge chain(s) are currently active.")

    if not bool(status.get("spread_within_limit", True)):
        cautions.append("Spread is outside Nyao's configured execution limit.")

    if bool(status.get("trading_paused", False)):
        cautions.append("Trading is paused by Nyao.")

    if bool(status.get("near_market_close", False)):
        cautions.append("Market-close protection is active or close to activating.")

    if current_intrabar and market_regime == "RANGE_CHOP":
        recommendations.append("Intrabar mode may over-sample noisy conditions; new-bar-only evaluation is safer for this regime.")
        proposed["enable_new_bar_entry_only"] = True

    # Never recommend loosening both threshold and exposure simultaneously in v0.1.
    risk_increase_fields = {"base_lot_size", "max_open_orders"}
    threshold_lowering = (
        proposed.get("min_buy_signal_score", current_buy_threshold) < current_buy_threshold
        or proposed.get("min_sell_signal_score", current_sell_threshold) < current_sell_threshold
    )
    if threshold_lowering and any(k in proposed for k in risk_increase_fields):
        proposed.pop("base_lot_size", None)
        proposed.pop("max_open_orders", None)
        cautions.append("v0.1 suppressed a compound risk increase recommendation.")

    confidence = (
        float(regime.get("confidence", 50.0)) * 0.6
        + (100.0 - float(risk.get("score", 0))) * 0.4
    )
    confidence = max(5.0, min(95.0, confidence))

    if veto:
        summary = f"{market_regime}; risk governor is {risk_state} and currently vetoes additional risk."
    else:
        summary = f"{market_regime}; risk state {risk_state}; exposure {exposure_bias}."

    result = Advice(
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
    )

    return result.to_dict()
