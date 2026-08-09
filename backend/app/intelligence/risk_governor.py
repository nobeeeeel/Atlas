from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


RISK_GOVERNOR_VERSION = "atlas-risk-governor-v0.3"


@dataclass
class RiskAssessment:
    state: str
    score: int
    exposure_bias: str
    veto_new_risk: bool
    veto_reasons: List[str]
    warnings: List[str]
    protections: List[str]
    metrics: Dict[str, float | int | bool | str]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["version"] = RISK_GOVERNOR_VERSION
        return result


def _f(
    data: dict,
    key: str,
    default: float = 0.0,
) -> float:
    try:
        return float(
            data.get(
                key,
                default,
            )
            or default
        )
    except (TypeError, ValueError):
        return default


def _i(
    data: dict,
    key: str,
    default: int = 0,
) -> int:
    try:
        return int(
            data.get(
                key,
                default,
            )
            or default
        )
    except (TypeError, ValueError):
        return default


def _b(
    data: dict,
    key: str,
    default: bool = False,
) -> bool:
    return bool(
        data.get(
            key,
            default,
        )
    )


def assess_risk(
    status: dict[str, Any],
) -> dict:
    """
    Atlas Risk Governor v0.3.

    Deterministic portfolio/account safety authority.

    The Risk Governor evaluates whether the ACCOUNT is healthy enough to
    accept additional risk.

    It intentionally does NOT own strategy-specific execution gates such as:

        - scalp spread acceptance
        - zone spread acceptance
        - zone confirmation
        - executable quote touch
        - duplicate-entry distance
        - signal threshold
        - market entry timing

    Those belong to their respective execution engines.

    This distinction is important because a scalp spread failure must not
    globally veto an independently valid zone strategy.

    The governor may veto NEW risk because of:

        - high/critical account risk state
        - active pause
        - exhausted basket risk
        - unsafe margin
        - severe drawdown
        - stressed hedge/recovery state

    It does not write commands.json and does not interfere with management
    of existing positions.
    """

    equity = _f(
        status,
        "equity",
    )

    free_margin = _f(
        status,
        "free_margin",
    )

    margin_level = _f(
        status,
        "margin_level_pct",
    )

    drawdown_pct = _f(
        status,
        "equity_drawdown_pct",
    )

    basket_loss_pct = _f(
        status,
        "basket_loss_pct",
    )

    basket_limit_pct = _f(
        status,
        "runtime_max_basket_loss_pct",
    )

    basket_remaining = _f(
        status,
        "basket_risk_remaining_pct",
    )

    buy_lots = _f(
        status,
        "buy_lots",
    )

    sell_lots = _f(
        status,
        "sell_lots",
    )

    total_lots = _f(
        status,
        "total_lots",
    )

    positions = _i(
        status,
        "strategy_open_positions",
    )

    max_orders = _i(
        status,
        "runtime_max_open_orders",
        1,
    )

    hedge_chains = _i(
        status,
        "active_hedge_chains",
    )

    hedge_loss_pct = _f(
        status,
        "hedge_chain_loss_pct",
    )

    hedge_level = _i(
        status,
        "max_active_hedge_level",
    )

    hedge_cycle = _i(
        status,
        "max_active_hedge_cycle",
    )

    #
    # Strategy execution telemetry.
    #
    # These are observed and reported here, but they are NOT global
    # account-risk vetoes.
    #
    scalp_spread_ok = _b(
        status,
        "spread_within_limit",
        True,
    )

    zone_spread_ok = _b(
        status,
        "zone_spread_within_limit",
        True,
    )

    paused = _b(
        status,
        "trading_paused",
    )

    outside_hours = _b(
        status,
        "outside_trading_hours",
    )

    near_close = _b(
        status,
        "near_market_close",
    )

    leverage_changed = _b(
        status,
        "leverage_changed",
    )

    duplicate_filter_enabled = _b(
        status,
        "runtime_enable_duplicate_distance_filter",
        True,
    )

    score = 0

    warnings: List[str] = []

    protections: List[str] = []

    veto_reasons: List[str] = []

    # ------------------------------------------------------------------
    # Drawdown
    # ------------------------------------------------------------------

    if drawdown_pct >= 8:
        score += 35

        warnings.append(
            f"Equity drawdown is high at {drawdown_pct:.2f}%."
        )

    elif drawdown_pct >= 5:
        score += 25

        warnings.append(
            f"Equity drawdown is elevated at {drawdown_pct:.2f}%."
        )

    elif drawdown_pct >= 3:
        score += 15

        warnings.append(
            "Equity drawdown is above the strategy's dampening threshold."
        )

    elif drawdown_pct >= 1:
        score += 6

    # ------------------------------------------------------------------
    # Basket-risk utilization
    # ------------------------------------------------------------------

    if basket_limit_pct > 0:
        utilization = (
            basket_loss_pct
            / basket_limit_pct
        )

        if utilization >= 0.85:
            score += 35

            warnings.append(
                "Basket loss is close to the configured basket stop."
            )

        elif utilization >= 0.60:
            score += 22

            warnings.append(
                "Basket loss has consumed more than 60% "
                "of the basket allowance."
            )

        elif utilization >= 0.35:
            score += 12

    else:
        utilization = 0.0

        warnings.append(
            "Basket stop is disabled."
        )

        score += 10

    # ------------------------------------------------------------------
    # Position utilization and concentration
    # ------------------------------------------------------------------

    order_utilization = (
        positions
        / max(
            max_orders,
            1,
        )
    )

    if order_utilization >= 0.85:
        score += 18

        warnings.append(
            "Open-position count is close to the configured maximum."
        )

    elif order_utilization >= 0.60:
        score += 10

    lot_sum = (
        buy_lots
        + sell_lots
    )

    long_share = (
        buy_lots / lot_sum
        if lot_sum > 0
        else 0.0
    )

    short_share = (
        sell_lots / lot_sum
        if lot_sum > 0
        else 0.0
    )

    if lot_sum <= 0:
        exposure_bias = "FLAT"

    elif long_share >= 0.75:
        exposure_bias = (
            "LONG_HEAVY"
        )

        score += 10

        warnings.append(
            "Directional concentration is long-heavy "
            f"({long_share * 100:.0f}% of lots)."
        )

    elif short_share >= 0.75:
        exposure_bias = (
            "SHORT_HEAVY"
        )

        score += 10

        warnings.append(
            "Directional concentration is short-heavy "
            f"({short_share * 100:.0f}% of lots)."
        )

    else:
        exposure_bias = (
            "BALANCED"
        )

    # ------------------------------------------------------------------
    # Hedge / recovery state
    # ------------------------------------------------------------------

    if hedge_chains > 0:
        score += 8

        warnings.append(
            f"{hedge_chains} active hedge chain(s) "
            "are consuming recovery capacity."
        )

        if hedge_level >= 2:
            score += 12

            warnings.append(
                "Hedge chain has reached "
                f"level {hedge_level}."
            )

        if hedge_cycle >= 1:
            score += 8

            warnings.append(
                "Hedge recovery has entered "
                f"cycle {hedge_cycle}."
            )

        if hedge_loss_pct >= 2:
            score += 12

    # ------------------------------------------------------------------
    # Margin
    # ------------------------------------------------------------------

    if (
        margin_level > 0
        and margin_level < 200
    ):
        score += 30

        warnings.append(
            "Margin level is low at "
            f"{margin_level:.1f}%."
        )

    elif (
        margin_level > 0
        and margin_level < 400
    ):
        score += 15

        warnings.append(
            "Margin level is reduced at "
            f"{margin_level:.1f}%."
        )

    if equity > 0:
        free_margin_ratio = (
            free_margin
            / equity
        )

        if free_margin_ratio < 0.25:
            score += 25

            warnings.append(
                "Free margin is below 25% of equity."
            )

        elif free_margin_ratio < 0.50:
            score += 12

    else:
        free_margin_ratio = 0.0

    # ------------------------------------------------------------------
    # Operational account stress
    # ------------------------------------------------------------------
    #
    # Spread is deliberately excluded.
    #
    # Spread is a strategy execution condition, not an account health
    # condition.
    #

    if paused:
        score += 25

        warnings.append(
            "Nyao is currently paused."
        )

    if outside_hours:
        score += 12

        warnings.append(
            "Current time is outside configured trading hours."
        )

    if near_close:
        score += 12

        warnings.append(
            "Market close is near."
        )

    if leverage_changed:
        score += 18

        warnings.append(
            "Account leverage differs from the initial leverage."
        )

    #
    # Spread remains visible as a warning only.
    #
    # This makes the Risk Governor informative without stealing authority
    # from the scalp and zone execution engines.
    #

    if not scalp_spread_ok:
        warnings.append(
            "Scalp spread filter is currently blocking "
            "ordinary scalp execution."
        )

    if not zone_spread_ok:
        warnings.append(
            "Zone spread filter is currently blocking "
            "zone execution."
        )

    if not duplicate_filter_enabled:
        warnings.append(
            "Duplicate-distance protection is disabled."
        )

    # ------------------------------------------------------------------
    # Existing protections
    # ------------------------------------------------------------------

    if _b(
        status,
        "runtime_enable_basket_stop",
    ):
        protections.append(
            "Basket stop enabled"
        )

    if _b(
        status,
        "runtime_enable_stop_loss",
    ):
        protections.append(
            "Stop loss enabled"
        )

    if _b(
        status,
        "runtime_enable_signal_dampening",
    ):
        protections.append(
            "Signal dampening enabled"
        )

    if _b(
        status,
        "runtime_enable_loss_management",
    ):
        protections.append(
            "Loss management enabled"
        )

    if _b(
        status,
        "runtime_enable_max_spread_filter",
    ):
        protections.append(
            "Scalp spread filter enabled"
        )

    if duplicate_filter_enabled:
        protections.append(
            "Duplicate-distance filter enabled"
        )

    # ------------------------------------------------------------------
    # Risk-state classification
    # ------------------------------------------------------------------

    score = max(
        0,
        min(
            100,
            int(
                round(
                    score
                )
            ),
        ),
    )

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

    # ------------------------------------------------------------------
    # Global new-risk veto policy
    # ------------------------------------------------------------------
    #
    # ONLY account/portfolio safety conditions belong here.
    #
    # Strategy-specific spread failures are deliberately excluded.
    #

    if state in {
        "CRITICAL",
        "HIGH",
    }:
        veto_reasons.append(
            f"Risk state is {state}."
        )

    if paused:
        veto_reasons.append(
            "Nyao is paused."
        )

    if (
        basket_limit_pct > 0
        and utilization >= 0.85
    ):
        veto_reasons.append(
            "Basket risk utilization is at least 85%."
        )

    if (
        margin_level > 0
        and margin_level < 200
    ):
        veto_reasons.append(
            "Margin level is below 200%."
        )

    if drawdown_pct >= 8:
        veto_reasons.append(
            "Equity drawdown is at least 8%."
        )

    if (
        drawdown_pct >= 6
        and hedge_chains > 0
    ):
        veto_reasons.append(
            "Equity drawdown is at least 6% "
            "while hedge recovery is active."
        )

    veto_new_risk = bool(
        veto_reasons
    )

    result = RiskAssessment(
        state=state,
        score=score,
        exposure_bias=exposure_bias,
        veto_new_risk=veto_new_risk,
        veto_reasons=veto_reasons,
        warnings=warnings,
        protections=protections,
        metrics={
            "drawdown_pct": round(
                drawdown_pct,
                4,
            ),
            "basket_loss_pct": round(
                basket_loss_pct,
                4,
            ),
            "basket_limit_pct": round(
                basket_limit_pct,
                4,
            ),
            "basket_remaining_pct": round(
                basket_remaining,
                4,
            ),
            "basket_utilization": round(
                utilization,
                4,
            ),
            "order_utilization": round(
                order_utilization,
                4,
            ),
            "long_share": round(
                long_share,
                4,
            ),
            "short_share": round(
                short_share,
                4,
            ),
            "total_lots": round(
                total_lots,
                4,
            ),
            "active_hedge_chains": (
                hedge_chains
            ),
            "max_hedge_level": (
                hedge_level
            ),
            "max_hedge_cycle": (
                hedge_cycle
            ),
            "hedge_loss_pct": round(
                hedge_loss_pct,
                4,
            ),
            "free_margin_ratio": round(
                free_margin_ratio,
                4,
            ),

            #
            # Strategy execution telemetry.
            #
            # Visible here but NOT global veto inputs.
            #
            "scalp_spread_ok": (
                scalp_spread_ok
            ),
            "zone_spread_ok": (
                zone_spread_ok
            ),
            "spread_is_global_risk_veto": False,

            "paused": (
                paused
            ),
            "outside_hours": (
                outside_hours
            ),
            "near_market_close": (
                near_close
            ),
            "leverage_changed": (
                leverage_changed
            ),
            "duplicate_filter_enabled": (
                duplicate_filter_enabled
            ),
        },
    )

    return result.to_dict()