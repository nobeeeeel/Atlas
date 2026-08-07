from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class RegimeAssessment:
    regime: str
    direction: str
    volatility: str
    execution_environment: str
    confidence: float
    reasons: List[str]
    metrics: Dict[str, float | bool | str]

    def to_dict(self) -> dict:
        return asdict(self)


def _f(data: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(data.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _b(data: dict, key: str, default: bool = False) -> bool:
    return bool(data.get(key, default))


def classify_regime(status: dict[str, Any]) -> dict:
    """
    Deterministic Atlas market-regime classifier.

    v0.1 deliberately uses only Nyao telemetry. No external news, DXY,
    yields, calendar data, or LLM judgment is used here.
    """
    buy_score = _f(status, "buy_score")
    sell_score = _f(status, "sell_score")

    buy_trend = _f(status, "buy_trend_score")
    sell_trend = _f(status, "sell_trend_score")
    buy_momentum = _f(status, "buy_momentum_score")
    sell_momentum = _f(status, "sell_momentum_score")
    buy_chop = _f(status, "buy_chop_score")
    sell_chop = _f(status, "sell_chop_score")
    buy_impulse = _f(status, "buy_impulse_strength")
    sell_impulse = _f(status, "sell_impulse_strength")

    vol_ratio = _f(status, "volatility_ratio")
    spread = _f(status, "spread_points")
    spread_cap = _f(status, "effective_spread_cap_points")
    spread_ok = _b(status, "spread_within_limit", True)

    paused = _b(status, "trading_paused")
    outside_hours = _b(status, "outside_trading_hours")
    near_close = _b(status, "near_market_close")
    leverage_changed = _b(status, "leverage_changed")

    score_gap = buy_score - sell_score
    trend_gap = buy_trend - sell_trend
    momentum_gap = buy_momentum - sell_momentum
    impulse_gap = buy_impulse - sell_impulse

    directional_strength = (
        abs(score_gap) * 0.35
        + abs(trend_gap) * 0.35
        + abs(momentum_gap) * 0.20
        + abs(impulse_gap) * 0.10
    )

    if score_gap > 1.0 and trend_gap > 0.5:
        direction = "BULLISH"
    elif score_gap < -1.0 and trend_gap < -0.5:
        direction = "BEARISH"
    elif abs(score_gap) < 0.75 and abs(trend_gap) < 0.5:
        direction = "NEUTRAL"
    else:
        direction = "MIXED"

    if vol_ratio <= 0:
        volatility = "UNKNOWN"
    elif vol_ratio < 0.75:
        volatility = "COMPRESSED"
    elif vol_ratio <= 1.20:
        volatility = "NORMAL"
    elif vol_ratio <= 1.60:
        volatility = "EXPANDING"
    else:
        volatility = "HIGH"

    average_chop = (buy_chop + sell_chop) / 2.0

    if direction in {"BULLISH", "BEARISH"} and directional_strength >= 1.8:
        structure = "TREND"
    elif average_chop >= 1.5 and abs(score_gap) < 2.0:
        structure = "CHOPPY"
    elif volatility == "COMPRESSED":
        structure = "COMPRESSION"
    elif volatility in {"EXPANDING", "HIGH"}:
        structure = "EXPANSION"
    else:
        structure = "TRANSITION"

    if structure == "TREND":
        regime = f"{direction}_TREND"
    elif structure == "CHOPPY":
        regime = "RANGE_CHOP"
    elif structure == "COMPRESSION":
        regime = "LOW_VOL_COMPRESSION"
    elif structure == "EXPANSION":
        regime = f"{direction}_EXPANSION" if direction in {"BULLISH", "BEARISH"} else "VOLATILITY_EXPANSION"
    else:
        regime = "TRANSITION"

    execution_flags = []
    if not spread_ok:
        execution_flags.append("SPREAD_BLOCKED")
    if paused:
        execution_flags.append("TRADING_PAUSED")
    if outside_hours:
        execution_flags.append("OUTSIDE_TRADING_HOURS")
    if near_close:
        execution_flags.append("NEAR_MARKET_CLOSE")
    if leverage_changed:
        execution_flags.append("LEVERAGE_CHANGED")

    execution_environment = "NORMAL" if not execution_flags else "STRESSED"

    confidence = 50.0
    if direction in {"BULLISH", "BEARISH"}:
        confidence += min(25.0, directional_strength * 5.0)
    elif direction == "NEUTRAL":
        confidence += 8.0

    if volatility != "UNKNOWN":
        confidence += 5.0

    if structure in {"TREND", "CHOPPY", "COMPRESSION", "EXPANSION"}:
        confidence += 7.0

    if execution_environment == "STRESSED":
        confidence -= 12.0

    confidence = max(5.0, min(95.0, confidence))

    reasons = [
        f"BUY/SELL live score gap: {score_gap:.2f}",
        f"Trend component gap: {trend_gap:.2f}",
        f"Momentum component gap: {momentum_gap:.2f}",
        f"Volatility ratio: {vol_ratio:.3f}",
        f"Average chop component: {average_chop:.2f}",
    ]

    if spread_cap > 0:
        reasons.append(f"Spread: {spread:.1f} / {spread_cap:.1f} pts")
    else:
        reasons.append(f"Spread: {spread:.1f} pts")

    if execution_flags:
        reasons.append("Execution flags: " + ", ".join(execution_flags))

    result = RegimeAssessment(
        regime=regime,
        direction=direction,
        volatility=volatility,
        execution_environment=execution_environment,
        confidence=round(confidence, 1),
        reasons=reasons,
        metrics={
            "score_gap": round(score_gap, 4),
            "trend_gap": round(trend_gap, 4),
            "momentum_gap": round(momentum_gap, 4),
            "impulse_gap": round(impulse_gap, 4),
            "directional_strength": round(directional_strength, 4),
            "average_chop": round(average_chop, 4),
            "volatility_ratio": round(vol_ratio, 4),
            "spread_points": round(spread, 2),
            "spread_cap_points": round(spread_cap, 2),
            "spread_ok": spread_ok,
        },
    )

    return result.to_dict()
