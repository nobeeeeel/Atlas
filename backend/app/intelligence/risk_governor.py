from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class RiskAssessment:
    state: str
    score: int
    exposure_bias: str
    veto_new_risk: bool
    warnings: List[str]
    protections: List[str]
    metrics: Dict[str, float | int | bool | str]

    def to_dict(self) -> dict:
        return asdict(self)


def _f(data: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(data.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _i(data: dict, key: str, default: int = 0) -> int:
    try:
        return int(data.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _b(data: dict, key: str, default: bool = False) -> bool:
    return bool(data.get(key, default))


def assess_risk(status: dict[str, Any]) -> dict:
    """
    Deterministic risk governor.

    The governor is intentionally conservative and has veto authority in the
    advisory pipeline. v0.1 never writes commands automatically.
    """
    equity = _f(status, "equity")
    free_margin = _f(status, "free_margin")
    margin_level = _f(status, "margin_level_pct")
    drawdown_pct = _f(status, "equity_drawdown_pct")

    basket_loss_pct = _f(status, "basket_loss_pct")
    basket_limit_pct = _f(status, "runtime_max_basket_loss_pct")
    basket_remaining = _f(status, "basket_risk_remaining_pct")

    buy_lots = _f(status, "buy_lots")
    sell_lots = _f(status, "sell_lots")
    total_lots = _f(status, "total_lots")
    positions = _i(status, "strategy_open_positions")
    max_orders = _i(status, "runtime_max_open_orders", 1)

    hedge_chains = _i(status, "active_hedge_chains")
    hedge_loss_pct = _f(status, "hedge_chain_loss_pct")
    hedge_level = _i(status, "max_active_hedge_level")
    hedge_cycle = _i(status, "max_active_hedge_cycle")

    spread_ok = _b(status, "spread_within_limit", True)
    paused = _b(status, "trading_paused")
    outside_hours = _b(status, "outside_trading_hours")
    near_close = _b(status, "near_market_close")
    leverage_changed = _b(status, "leverage_changed")

    score = 0
    warnings: List[str] = []
    protections: List[str] = []

    # Drawdown contribution
    if drawdown_pct >= 8:
        score += 35
        warnings.append(f"Equity drawdown is high at {drawdown_pct:.2f}%.")
    elif drawdown_pct >= 5:
        score += 25
        warnings.append(f"Equity drawdown is elevated at {drawdown_pct:.2f}%.")
    elif drawdown_pct >= 3:
        score += 15
        warnings.append(f"Equity drawdown is above the strategy's dampening threshold.")
    elif drawdown_pct >= 1:
        score += 6

    # Basket usage
    if basket_limit_pct > 0:
        utilization = basket_loss_pct / basket_limit_pct
        if utilization >= 0.85:
            score += 35
            warnings.append("Basket loss is close to the configured basket stop.")
        elif utilization >= 0.60:
            score += 22
            warnings.append("Basket loss has consumed more than 60% of the basket allowance.")
        elif utilization >= 0.35:
            score += 12
    else:
        utilization = 0.0
        warnings.append("Basket stop is disabled.")
        score += 10

    # Position concentration / utilization
    order_utilization = positions / max(max_orders, 1)
    if order_utilization >= 0.85:
        score += 18
        warnings.append("Open-position count is close to the configured maximum.")
    elif order_utilization >= 0.60:
        score += 10

    lot_sum = buy_lots + sell_lots
    long_share = buy_lots / lot_sum if lot_sum > 0 else 0.0
    short_share = sell_lots / lot_sum if lot_sum > 0 else 0.0

    if lot_sum <= 0:
        exposure_bias = "FLAT"
    elif long_share >= 0.75:
        exposure_bias = "LONG_HEAVY"
        score += 10
        warnings.append(f"Directional concentration is long-heavy ({long_share*100:.0f}% of lots).")
    elif short_share >= 0.75:
        exposure_bias = "SHORT_HEAVY"
        score += 10
        warnings.append(f"Directional concentration is short-heavy ({short_share*100:.0f}% of lots).")
    else:
        exposure_bias = "BALANCED"

    # Hedge/recovery state
    if hedge_chains > 0:
        score += 8
        warnings.append(f"{hedge_chains} active hedge chain(s) are consuming recovery capacity.")
        if hedge_level >= 2:
            score += 12
            warnings.append(f"Hedge chain has reached level {hedge_level}.")
        if hedge_cycle >= 1:
            score += 8
            warnings.append(f"Hedge recovery has entered cycle {hedge_cycle}.")
        if hedge_loss_pct >= 2:
            score += 12

    # Margin
    if margin_level > 0 and margin_level < 200:
        score += 30
        warnings.append(f"Margin level is low at {margin_level:.1f}%.")
    elif margin_level > 0 and margin_level < 400:
        score += 15
        warnings.append(f"Margin level is reduced at {margin_level:.1f}%.")

    if equity > 0:
        free_margin_ratio = free_margin / equity
        if free_margin_ratio < 0.25:
            score += 25
            warnings.append("Free margin is below 25% of equity.")
        elif free_margin_ratio < 0.50:
            score += 12
    else:
        free_margin_ratio = 0.0

    # Execution stress
    if not spread_ok:
        score += 20
        warnings.append("Spread filter is currently blocking fresh execution.")
    if paused:
        score += 25
        warnings.append("Nyao is currently paused.")
    if outside_hours:
        score += 12
    if near_close:
        score += 12
    if leverage_changed:
        score += 18
        warnings.append("Account leverage differs from the initial leverage.")

    # Existing protections
    if _b(status, "runtime_enable_basket_stop"):
        protections.append("Basket stop enabled")
    if _b(status, "runtime_enable_stop_loss"):
        protections.append("Stop loss enabled")
    if _b(status, "runtime_enable_signal_dampening"):
        protections.append("Signal dampening enabled")
    if _b(status, "runtime_enable_loss_management"):
        protections.append("Loss management enabled")
    if _b(status, "runtime_enable_max_spread_filter"):
        protections.append("Spread filter enabled")

    score = max(0, min(100, int(round(score))))

    if score >= 70:
        state = "CRITICAL"
    elif score >= 50:
        state = "HIGH"
    elif score >= 30:
        state = "ELEVATED"
    elif score >= 15:
        state = "MODERATE"
    else:
        state = "LOW"

    veto_new_risk = (
        state in {"CRITICAL", "HIGH"}
        or not spread_ok
        or paused
        or (basket_limit_pct > 0 and utilization >= 0.85)
        or (margin_level > 0 and margin_level < 200)
    )

    result = RiskAssessment(
        state=state,
        score=score,
        exposure_bias=exposure_bias,
        veto_new_risk=veto_new_risk,
        warnings=warnings,
        protections=protections,
        metrics={
            "drawdown_pct": round(drawdown_pct, 4),
            "basket_loss_pct": round(basket_loss_pct, 4),
            "basket_limit_pct": round(basket_limit_pct, 4),
            "basket_remaining_pct": round(basket_remaining, 4),
            "order_utilization": round(order_utilization, 4),
            "long_share": round(long_share, 4),
            "short_share": round(short_share, 4),
            "total_lots": round(total_lots, 4),
            "active_hedge_chains": hedge_chains,
            "max_hedge_level": hedge_level,
            "max_hedge_cycle": hedge_cycle,
            "free_margin_ratio": round(free_margin_ratio, 4),
            "spread_ok": spread_ok,
        },
    )

    return result.to_dict()
