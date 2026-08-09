from __future__ import annotations

from typing import Any, Dict, List


# Controls that primarily affect creation of fresh exposure.
ENTRY_CONTROLS = {
    "min_buy_signal_score",
    "min_sell_signal_score",
    "enable_new_bar_entry_only",
    "zone_points",
    "buy_duplicate_multiplier",
    "sell_duplicate_multiplier",
    "enable_duplicate_distance_filter",
    "enable_limit_entry",
    "limit_entry_anchor",
    "limit_entry_atr_fraction",
    "limit_entry_expiry_bars",
    "limit_entry_cancel_on_flip",
    "max_trades_per_candle",
    "max_open_orders",
    "base_lot_size",
}

# Signal-generation controls. These are safe to experiment with in shadow,
# but should not silently alter active recovery logic in future AUTO mode.
STRUCTURAL_SIGNAL_CONTROLS = {
    "directional_body_lookback",
    "ema_fast_period",
    "ema_slow_period",
    "slope_lookback",
    "rsi_period",
    "atr_period",
    "atr_avg_lookback",
    "min_vol_ratio_to_trade",
    "impulse_lookback",
    "impulse_boost_weight",
    "signal_smoothing_candles",
    "current_candle_blend",
    "velocity_window",
    "rsi_overbought",
    "rsi_oversold",
    "rsi_momentum_buy",
    "rsi_momentum_sell",
    "trend_weight",
    "slope_weight",
    "momentum_base_weight",
    "momentum_trigger_weight",
    "body_momentum_weight",
    "chop_score_high",
    "chop_score_med",
    "chop_score_low",
    "volatility_score_high",
    "volatility_score_low",
    "peak_score_weight",
    "wick_rejection_weight",
    "min_body_ratio",
}

# Controls that can change management of already-open positions/recovery.
MANAGEMENT_CONTROLS = {
    "min_break_even_profit",
    "profit_threshold_multiplier",
    "loss_threshold_multiplier",
    "enable_signal_dampening",
    "max_losing_positions_same_dir",
    "losing_pos_score_penalty",
    "drawdown_threshold_pct",
    "drawdown_score_boost",
    "consecutive_losses_before_cooldown",
    "consecutive_loss_cooldown_bars",
    "enable_loss_management",
    "max_holding_loss_positions",
    "min_health_score",
    "max_adverse_atr",
    "health_trend_weight",
    "health_rsi_weight",
    "health_atr_weight",
    "health_swing_weight",
    "health_rsi_buy_min",
    "health_rsi_sell_max",
    "health_swing_lookback",
    "health_grace_bars",
    "enable_partial_close",
    "partial_close75_pct",
    "partial_close50_pct",
    "partial_close25_pct",
    "enable_health_sl_tightening",
    "sl_tighten_atr_multiplier",
    "sl_tighten_min_health_pct",
    "enable_break_even_on_spread",
    "break_even_spread_multiplier",
    "enable_virtual_sl_reentry",
    "reentry_respects_new_bar_gate",
    "reentry_min_signal_pct",
    "enable_profit_offset_sl",
    "consecutive_wins_required",
    "min_offset_profit",
    "enable_hedge_chain",
    "hedge_trigger_atr",
    "hedge_require_signal",
    "hedge_min_signal_score",
    "hedge_auto_lot",
    "hedge_recovery_atr",
    "hedge_lot_multiplier",
    "hedge_max_lot",
    "hedge_recovery_pct",
    "hedge_roll_min_profit",
    "hedge_cycle_levels",
    "enable_hedge_cycle_reset",
    "hedge_cycle_partial_pct",
    "hedge_max_cycles",
    "hedge_max_chain_loss_usd",
    "hedge_max_chain_loss_pct",
    "hedge_clear_root_sl",
    "hedge_trail_atr",
    "enable_dynamic_lots",
    "equity_drop_percent",
    "max_equity_drop_lot_steps",
    "min_signal_strength_for_lot",
    "lot_step_size",
    "max_lot_size",
    "enable_take_profit",
    "tp_input_type",
    "tp_value",
    "enable_stop_loss",
    "sl_input_type",
    "sl_value",
    "enable_risk_reward",
    "rr_risk_mode",
    "rr_risk_input_type",
    "rr_risk_value",
    "rr_atr_multiplier",
    "risk_reward_ratio",
    "enable_trailing",
    "trailing_enable_break_even_lock",
    "trailing_sl_on_profitable_only",
    "enable_adaptive_tp",
    "enable_adaptive_sl",
    "ts_input_type",
    "trailing_distance_value",
    "trailing_value_multiplier",
}

# Account / session level controls. These may intentionally affect the whole
# strategy and therefore need explicit transition semantics in AUTO mode.
GLOBAL_RISK_CONTROLS = {
    "enable_basket_stop",
    "max_basket_loss_pct",
    "min_equity_percent",
    "max_drawdown_from_peak",
    "pause_minutes",
    "pause_minutes_multiplier",
    "max_pause_minutes",
    "max_min_equity_triggers",
    "reset_on_new_peak",
    "target_equity",
    "minimum_equity",
    "enable_max_spread_filter",
    "max_spread_points",
    "max_spread_atr_ratio",
    "enable_trading_hours",
    "trading_start_time",
    "trading_end_time",
    "enable_market_close_filter",
    "minutes_before_close",
    "enable_news_filter",
    "news_minutes_before",
    "news_minutes_after",
    "enable_leverage_pause",
}

# Direction toggles are conservative because they can interact with re-entry
# and recovery paths in the current Nyao implementation.
RECOVERY_SENSITIVE_CONTROLS = {
    "enable_buy_orders",
    "enable_sell_orders",
}


def _bucket(control: str) -> str:
    if control in MANAGEMENT_CONTROLS:
        return "MANAGEMENT_SENSITIVE"
    if control in GLOBAL_RISK_CONTROLS:
        return "GLOBAL_RISK"
    if control in RECOVERY_SENSITIVE_CONTROLS:
        return "RECOVERY_SENSITIVE"
    if control in STRUCTURAL_SIGNAL_CONTROLS:
        return "STRUCTURAL_SIGNAL"
    if control in ENTRY_CONTROLS:
        return "FRESH_ENTRY"
    return "UNCLASSIFIED_CONSERVATIVE"


def build_transition_plan(
    status: dict[str, Any],
    changed_controls: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Position-aware transition safety for future AUTO mode.

    This does not apply anything. It answers: if Atlas wanted to apply this
    policy now, which changes could safely affect fresh entries and which
    must be deferred or version-locked for existing positions?
    """
    open_positions = int(status.get("strategy_open_positions") or 0)
    active_hedge_chains = int(status.get("active_hedge_chains") or 0)

    classified: List[Dict[str, Any]] = []
    buckets = set()

    for name, change in changed_controls.items():
        bucket = _bucket(name)
        buckets.add(bucket)
        classified.append({
            "control": name,
            "category": bucket,
            "current": change.get("current"),
            "shadow": change.get("shadow"),
        })

    existing_position_policy_lock_required = bool(
        open_positions > 0
        and any(
            bucket in {
                "MANAGEMENT_SENSITIVE",
                "GLOBAL_RISK",
                "RECOVERY_SENSITIVE",
                "STRUCTURAL_SIGNAL",
                "UNCLASSIFIED_CONSERVATIVE",
            }
            for bucket in buckets
        )
    )

    if open_positions == 0:
        apply_state = "FLAT_SAFE"
        existing_position_action = "NONE"
        rationale = (
            "No strategy positions are open, so there is no existing-position "
            "policy migration problem."
        )
    elif existing_position_policy_lock_required:
        apply_state = "DEFER_OR_VERSION_LOCK"
        existing_position_action = "KEEP_ENTRY_POLICY"
        rationale = (
            "Existing positions are open and at least one proposed control can "
            "affect position management, recovery, global risk handling, or "
            "signal state used by recovery. Future AUTO must not silently "
            "migrate those positions to the new policy."
        )
    else:
        apply_state = "FRESH_ENTRY_ONLY_CAPABLE"
        existing_position_action = "KEEP_ENTRY_POLICY"
        rationale = (
            "The current proposed changes are classified as fresh-entry "
            "controls. Future AUTO may apply them to new entries only, while "
            "existing positions remain on the policy they were opened under."
        )

    if active_hedge_chains > 0 and open_positions > 0:
        # Be stricter while recovery is live.
        if apply_state != "FLAT_SAFE":
            apply_state = "DEFER_OR_VERSION_LOCK"
            existing_position_policy_lock_required = True
            rationale += (
                " An active hedge chain is present, so recovery continuity "
                "takes priority over immediate policy migration."
            )

    return {
        "open_positions": open_positions,
        "active_hedge_chains": active_hedge_chains,
        "apply_state": apply_state,
        "existing_position_action": existing_position_action,
        "existing_position_policy_lock_required": (
            existing_position_policy_lock_required
        ),
        "changed_control_classification": classified,
        "rationale": rationale,
        "future_auto_rule": (
            "Every new position should carry the Atlas policy_epoch active at "
            "entry. Existing positions should keep their entry policy for "
            "management/recovery until flat, unless an explicitly whitelisted "
            "emergency risk-reduction rule is designed to override it."
        ),
    }
