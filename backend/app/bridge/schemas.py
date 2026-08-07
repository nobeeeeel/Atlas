from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SparseCommandModel(BaseModel):
    """Command model that omits unset runtime overrides from JSON output.

    This is important because an absent Atlas override should leave Nyao's
    effective runtime value unchanged rather than serialize as JSON null.
    """

    model_config = ConfigDict(extra="ignore")

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)


class Command(SparseCommandModel):
    # Atlas master controls
    enabled: bool = True
    enable_buy_orders: bool = True
    enable_sell_orders: bool = True

    # Signal / indicator behavior
    directional_body_lookback: Optional[int] = Field(default=None, ge=1, le=500)
    ema_fast_period: Optional[int] = Field(default=None, ge=1, le=500)
    ema_slow_period: Optional[int] = Field(default=None, ge=1, le=500)
    slope_lookback: Optional[int] = Field(default=None, ge=1, le=100)
    rsi_period: Optional[int] = Field(default=None, ge=2, le=500)
    atr_period: Optional[int] = Field(default=None, ge=1, le=500)
    atr_avg_lookback: Optional[int] = Field(default=None, ge=1, le=500)
    min_vol_ratio_to_trade: float = Field(default=0.65, ge=0.0, le=10.0)
    impulse_lookback: Optional[int] = Field(default=None, ge=1, le=100)
    impulse_boost_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    signal_smoothing_candles: Optional[int] = Field(default=None, ge=1, le=10)
    current_candle_blend: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    velocity_window: Optional[float] = Field(default=None, ge=0.0001, le=100.0)
    rsi_overbought: Optional[int] = Field(default=None, ge=0, le=100)
    rsi_oversold: Optional[int] = Field(default=None, ge=0, le=100)
    rsi_momentum_buy: Optional[int] = Field(default=None, ge=0, le=100)
    rsi_momentum_sell: Optional[int] = Field(default=None, ge=0, le=100)

    # Score weights
    trend_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    slope_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    momentum_base_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    momentum_trigger_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    body_momentum_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    chop_score_high: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    chop_score_med: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    chop_score_low: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    volatility_score_high: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    volatility_score_low: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    peak_score_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    wick_rejection_weight: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    min_body_ratio: Optional[float] = Field(default=None, ge=0.0)

    # Entry / execution
    enable_new_bar_entry_only: Optional[bool] = None
    enable_max_spread_filter: Optional[bool] = None
    max_spread_points: Optional[float] = Field(default=None, ge=0.0)
    max_spread_atr_ratio: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    base_lot_size: float = Field(default=0.01, gt=0.0, le=5.0)
    max_open_orders: int = Field(default=3, ge=1, le=50)
    max_trades_per_candle: int = Field(default=1, ge=0, le=20)
    consecutive_candle_threshold_boost: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    max_consecutive_candle_boosts: Optional[int] = Field(default=None, ge=0, le=100)
    zone_points: Optional[float] = Field(default=None, ge=0.0)
    buy_duplicate_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    sell_duplicate_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    min_break_even_profit: Optional[float] = Field(default=None, ge=0.0)
    profit_threshold_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    loss_threshold_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    min_buy_signal_score: float = Field(default=4.5, ge=0.0, le=10.0)
    min_sell_signal_score: float = Field(default=4.5, ge=0.0, le=10.0)

    # Limit entry
    enable_limit_entry: Optional[bool] = None
    limit_entry_anchor: Optional[int] = Field(default=None, ge=0, le=3)
    limit_entry_atr_fraction: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    limit_entry_expiry_bars: Optional[int] = Field(default=None, ge=0, le=1000)
    limit_entry_cancel_on_flip: Optional[bool] = None

    # Signal dampening
    enable_signal_dampening: Optional[bool] = None
    max_losing_positions_same_dir: Optional[int] = Field(default=None, ge=0, le=50)
    losing_pos_score_penalty: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    drawdown_threshold_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    drawdown_score_boost: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    consecutive_losses_before_cooldown: Optional[int] = Field(default=None, ge=0, le=100)
    consecutive_loss_cooldown_bars: Optional[int] = Field(default=None, ge=0, le=1000)

    # Loss / health management
    enable_loss_management: Optional[bool] = None
    max_holding_loss_positions: Optional[int] = Field(default=None, ge=0, le=50)
    min_health_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_adverse_atr: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health_trend_weight: Optional[float] = Field(default=None, ge=0.0)
    health_rsi_weight: Optional[float] = Field(default=None, ge=0.0)
    health_atr_weight: Optional[float] = Field(default=None, ge=0.0)
    health_swing_weight: Optional[float] = Field(default=None, ge=0.0)
    health_rsi_buy_min: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health_rsi_sell_max: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    health_swing_lookback: Optional[int] = Field(default=None, ge=1, le=1000)
    health_grace_bars: Optional[int] = Field(default=None, ge=0, le=1000)
    enable_partial_close: Optional[bool] = None
    partial_close75_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    partial_close50_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    partial_close25_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    enable_health_sl_tightening: Optional[bool] = None
    sl_tighten_atr_multiplier: Optional[float] = Field(default=None, ge=0.0)
    sl_tighten_min_health_pct: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    enable_break_even_on_spread: Optional[bool] = None
    break_even_spread_multiplier: Optional[float] = Field(default=None, ge=0.0)
    enable_virtual_sl_reentry: bool = False
    reentry_respects_new_bar_gate: Optional[bool] = None
    reentry_min_signal_pct: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    enable_profit_offset_sl: Optional[bool] = None
    consecutive_wins_required: Optional[int] = Field(default=None, ge=0, le=100)
    min_offset_profit: Optional[float] = Field(default=None, ge=0.0)

    # Hedge chain
    enable_hedge_chain: bool = False
    hedge_trigger_atr: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    hedge_require_signal: Optional[bool] = None
    hedge_min_signal_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    hedge_auto_lot: Optional[bool] = None
    hedge_recovery_atr: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    hedge_lot_multiplier: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    hedge_max_lot: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    hedge_recovery_pct: Optional[float] = Field(default=None, ge=0.0, le=1000.0)
    hedge_roll_min_profit: Optional[float] = Field(default=None, ge=0.0)
    hedge_cycle_levels: Optional[int] = Field(default=None, ge=1, le=20)
    enable_hedge_cycle_reset: Optional[bool] = None
    hedge_cycle_partial_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    hedge_max_cycles: Optional[int] = Field(default=None, ge=0, le=100)
    hedge_max_chain_loss_usd: Optional[float] = Field(default=None, ge=0.0)
    hedge_max_chain_loss_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    hedge_clear_root_sl: Optional[bool] = None
    hedge_trail_atr: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Dynamic sizing
    enable_dynamic_lots: bool = False
    equity_drop_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_equity_drop_lot_steps: Optional[int] = Field(default=None, ge=0, le=100)
    min_signal_strength_for_lot: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    lot_step_size: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    max_lot_size: Optional[float] = Field(default=None, ge=0.0, le=5.0)

    # Equity protection
    enable_basket_stop: Optional[bool] = None
    max_basket_loss_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    min_equity_percent: Optional[float] = Field(default=None, ge=0.0)
    max_drawdown_from_peak: Optional[float] = Field(default=None, ge=0.0)
    pause_minutes: Optional[int] = Field(default=None, ge=0, le=1440)
    pause_minutes_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    max_pause_minutes: Optional[int] = Field(default=None, ge=0, le=10080)
    max_min_equity_triggers: Optional[int] = Field(default=None, ge=0, le=1000)
    reset_on_new_peak: Optional[bool] = None
    target_equity: Optional[float] = Field(default=None, ge=0.0)
    minimum_equity: Optional[float] = Field(default=None, ge=0.0)

    # TP / SL / risk reward
    enable_take_profit: Optional[bool] = None
    tp_input_type: Optional[int] = Field(default=None, ge=0, le=2)
    tp_value: Optional[float] = Field(default=None, ge=0.0)
    enable_stop_loss: Optional[bool] = None
    sl_input_type: Optional[int] = Field(default=None, ge=0, le=2)
    sl_value: Optional[float] = Field(default=None, ge=0.0)
    enable_risk_reward: Optional[bool] = None
    rr_risk_mode: Optional[int] = Field(default=None, ge=0, le=1)
    rr_risk_input_type: Optional[int] = Field(default=None, ge=0, le=2)
    rr_risk_value: Optional[float] = Field(default=None, ge=0.0)
    rr_atr_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    risk_reward_ratio: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Trailing
    enable_trailing: Optional[bool] = None
    trailing_enable_break_even_lock: Optional[bool] = None
    trailing_sl_on_profitable_only: Optional[bool] = None
    enable_adaptive_tp: Optional[bool] = None
    enable_adaptive_sl: Optional[bool] = None
    ts_input_type: Optional[int] = Field(default=None, ge=0, le=2)
    trailing_distance_value: Optional[float] = Field(default=None, ge=0.0)
    trailing_value_multiplier: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    # Operational filters / diagnostics
    enable_discord_alerts: Optional[bool] = None
    enable_trading_hours: Optional[bool] = None
    trading_start_time: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    trading_end_time: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    enable_reports: Optional[bool] = None
    send_report_every_hour: Optional[int] = Field(default=None, ge=1, le=168)
    enable_market_close_filter: Optional[bool] = None
    minutes_before_close: Optional[int] = Field(default=None, ge=0, le=1440)
    enable_news_filter: Optional[bool] = None
    news_minutes_before: Optional[int] = Field(default=None, ge=0, le=1440)
    news_minutes_after: Optional[int] = Field(default=None, ge=0, le=1440)
    enable_leverage_pause: Optional[bool] = None
    enable_logging: Optional[bool] = None

    # Bridge metadata
    command_version: int = Field(default=1, ge=0)
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class PositionTelemetry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ticket: int = 0
    type: str = ""
    volume: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    net_pl: float = 0.0
    notional_exposure: float = 0.0
    signed_distance_points: float = 0.0
    opened_at_epoch: int = 0
    age_seconds: int = 0

    managed: bool = False
    entry_signal_score: float = 0.0
    partial_close_level: int = 0
    break_even_locked: bool = False

    chain_id: int = 0
    hedge_level: int = 0
    cycle_num: int = 0
    no_rehedge: bool = False
    hedge_graduated: bool = False
    hedge_lock_profit: float = 0.0


class Status(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # Connection / identity
    connected: bool = True
    strategy: str = "nyao"
    symbol: str = "XAUUSD"

    # Account
    balance: float = 0.0
    equity: float = 0.0
    floating_profit: float = 0.0
    open_positions: int = 0

    # Account / capital observability
    account_margin: float = 0.0
    free_margin: float = 0.0
    margin_level_pct: float = 0.0
    account_leverage: int = 0
    peak_equity: float = 0.0
    equity_drawdown_usd: float = 0.0
    equity_drawdown_pct: float = 0.0

    # Strategy position / exposure observability
    strategy_open_positions: int = 0
    buy_positions: int = 0
    sell_positions: int = 0
    winning_positions: int = 0
    losing_positions: int = 0
    working_limit_orders: int = 0
    total_lots: float = 0.0
    buy_lots: float = 0.0
    sell_lots: float = 0.0
    strategy_floating_pl: float = 0.0
    strategy_swap: float = 0.0
    gross_floating_profit: float = 0.0
    gross_floating_loss: float = 0.0
    largest_winning_position: float = 0.0
    largest_losing_position: float = 0.0
    gross_notional_exposure: float = 0.0
    buy_notional_exposure: float = 0.0
    sell_notional_exposure: float = 0.0
    positions: List[PositionTelemetry] = Field(default_factory=list)

    # Hedge / recovery observability
    active_hedge_chains: int = 0
    hedge_chain_positions: int = 0
    hedge_chain_lots: float = 0.0
    hedge_chain_floating_pl: float = 0.0
    hedge_chain_loss_pct: float = 0.0
    max_active_hedge_level: int = 0
    max_active_hedge_cycle: int = 0

    # Basket / risk observability
    basket_floating_pl: float = 0.0
    basket_loss_pct: float = 0.0
    basket_risk_remaining_pct: float = 0.0

    # Market / filter observability
    bid: float = 0.0
    ask: float = 0.0
    spread_points: float = 0.0
    effective_spread_cap_points: float = 0.0
    spread_within_limit: bool = True
    current_atr: float = 0.0
    average_atr: float = 0.0
    atr_points: float = 0.0
    volatility_ratio: float = 0.0
    trading_paused: bool = False
    pause_until_epoch: int = 0
    pause_duration_minutes: int = 0
    total_pause_count: int = 0
    total_pause_duration_minutes: float = 0.0
    outside_trading_hours: bool = False
    near_market_close: bool = False
    leverage_changed: bool = False
    initial_leverage: int = 0

    # Signal component observability
    signal_telemetry_ready: bool = False

    buy_trend_score: float = 0.0
    buy_momentum_score: float = 0.0
    buy_chop_score: float = 0.0
    buy_peak_score: float = 0.0
    buy_volatility_score: float = 0.0
    buy_impulse_strength: float = 0.0
    buy_velocity: float = 0.0
    buy_normalized_velocity: float = 0.0
    buy_body_ratio: float = 0.0
    buy_wick_rejection: float = 0.0
    buy_body_penalty: float = 0.0
    buy_wick_penalty: float = 0.0
    buy_signal_reasoning: str = ""

    sell_trend_score: float = 0.0
    sell_momentum_score: float = 0.0
    sell_chop_score: float = 0.0
    sell_peak_score: float = 0.0
    sell_volatility_score: float = 0.0
    sell_impulse_strength: float = 0.0
    sell_velocity: float = 0.0
    sell_normalized_velocity: float = 0.0
    sell_body_ratio: float = 0.0
    sell_wick_rejection: float = 0.0
    sell_body_penalty: float = 0.0
    sell_wick_penalty: float = 0.0
    sell_signal_reasoning: str = ""

    # Live signal snapshot
    buy_score: float = 0.0
    sell_score: float = 0.0

    # Atlas state / acknowledgement
    atlas_enabled: bool = True
    atlas_buy_enabled: bool = True
    atlas_sell_enabled: bool = True
    applied_command_version: int = -1
    structural_config_dirty: Optional[bool] = None
    last_global_block_reason: Optional[str] = None

    # Effective Nyao runtime configuration
    # Signal / indicator behavior
    runtime_directional_body_lookback: Optional[int] = None
    runtime_ema_fast_period: Optional[int] = None
    runtime_ema_slow_period: Optional[int] = None
    runtime_slope_lookback: Optional[int] = None
    runtime_rsi_period: Optional[int] = None
    runtime_atr_period: Optional[int] = None
    runtime_atr_avg_lookback: Optional[int] = None
    runtime_min_vol_ratio_to_trade: Optional[float] = None
    runtime_impulse_lookback: Optional[int] = None
    runtime_impulse_boost_weight: Optional[float] = None
    runtime_signal_smoothing_candles: Optional[int] = None
    runtime_current_candle_blend: Optional[float] = None
    runtime_velocity_window: Optional[float] = None
    runtime_rsi_overbought: Optional[int] = None
    runtime_rsi_oversold: Optional[int] = None
    runtime_rsi_momentum_buy: Optional[int] = None
    runtime_rsi_momentum_sell: Optional[int] = None

    # Score weights
    runtime_trend_weight: Optional[float] = None
    runtime_slope_weight: Optional[float] = None
    runtime_momentum_base_weight: Optional[float] = None
    runtime_momentum_trigger_weight: Optional[float] = None
    runtime_body_momentum_weight: Optional[float] = None
    runtime_chop_score_high: Optional[float] = None
    runtime_chop_score_med: Optional[float] = None
    runtime_chop_score_low: Optional[float] = None
    runtime_volatility_score_high: Optional[float] = None
    runtime_volatility_score_low: Optional[float] = None
    runtime_peak_score_weight: Optional[float] = None
    runtime_wick_rejection_weight: Optional[float] = None
    runtime_min_body_ratio: Optional[float] = None

    # Entry / execution
    runtime_enable_buy_orders: Optional[bool] = None
    runtime_enable_sell_orders: Optional[bool] = None
    runtime_enable_new_bar_entry_only: Optional[bool] = None
    runtime_enable_max_spread_filter: Optional[bool] = None
    runtime_max_spread_points: Optional[float] = None
    runtime_max_spread_atr_ratio: Optional[float] = None
    runtime_base_lot_size: Optional[float] = None
    runtime_max_open_orders: Optional[int] = None
    runtime_max_trades_per_candle: Optional[int] = None
    runtime_consecutive_candle_threshold_boost: Optional[float] = None
    runtime_max_consecutive_candle_boosts: Optional[int] = None
    runtime_zone_points: Optional[float] = None
    runtime_buy_duplicate_multiplier: Optional[float] = None
    runtime_sell_duplicate_multiplier: Optional[float] = None
    runtime_min_break_even_profit: Optional[float] = None
    runtime_profit_threshold_multiplier: Optional[float] = None
    runtime_loss_threshold_multiplier: Optional[float] = None
    runtime_min_buy_signal_score: Optional[float] = None
    runtime_min_sell_signal_score: Optional[float] = None

    # Limit entry
    runtime_enable_limit_entry: Optional[bool] = None
    runtime_limit_entry_anchor: Optional[int] = None
    runtime_limit_entry_atr_fraction: Optional[float] = None
    runtime_limit_entry_expiry_bars: Optional[int] = None
    runtime_limit_entry_cancel_on_flip: Optional[bool] = None

    # Signal dampening
    runtime_enable_signal_dampening: Optional[bool] = None
    runtime_max_losing_positions_same_dir: Optional[int] = None
    runtime_losing_pos_score_penalty: Optional[float] = None
    runtime_drawdown_threshold_pct: Optional[float] = None
    runtime_drawdown_score_boost: Optional[float] = None
    runtime_consecutive_losses_before_cooldown: Optional[int] = None
    runtime_consecutive_loss_cooldown_bars: Optional[int] = None

    # Loss / health management
    runtime_enable_loss_management: Optional[bool] = None
    runtime_max_holding_loss_positions: Optional[int] = None
    runtime_min_health_score: Optional[float] = None
    runtime_max_adverse_atr: Optional[float] = None
    runtime_health_trend_weight: Optional[float] = None
    runtime_health_rsi_weight: Optional[float] = None
    runtime_health_atr_weight: Optional[float] = None
    runtime_health_swing_weight: Optional[float] = None
    runtime_health_rsi_buy_min: Optional[float] = None
    runtime_health_rsi_sell_max: Optional[float] = None
    runtime_health_swing_lookback: Optional[int] = None
    runtime_health_grace_bars: Optional[int] = None
    runtime_enable_partial_close: Optional[bool] = None
    runtime_partial_close75_pct: Optional[float] = None
    runtime_partial_close50_pct: Optional[float] = None
    runtime_partial_close25_pct: Optional[float] = None
    runtime_enable_health_sl_tightening: Optional[bool] = None
    runtime_sl_tighten_atr_multiplier: Optional[float] = None
    runtime_sl_tighten_min_health_pct: Optional[float] = None
    runtime_enable_break_even_on_spread: Optional[bool] = None
    runtime_break_even_spread_multiplier: Optional[float] = None
    runtime_enable_virtual_sl_reentry: Optional[bool] = None
    runtime_reentry_respects_new_bar_gate: Optional[bool] = None
    runtime_reentry_min_signal_pct: Optional[float] = None
    runtime_enable_profit_offset_sl: Optional[bool] = None
    runtime_consecutive_wins_required: Optional[int] = None
    runtime_min_offset_profit: Optional[float] = None

    # Hedge chain
    runtime_enable_hedge_chain: Optional[bool] = None
    runtime_hedge_trigger_atr: Optional[float] = None
    runtime_hedge_require_signal: Optional[bool] = None
    runtime_hedge_min_signal_score: Optional[float] = None
    runtime_hedge_auto_lot: Optional[bool] = None
    runtime_hedge_recovery_atr: Optional[float] = None
    runtime_hedge_lot_multiplier: Optional[float] = None
    runtime_hedge_max_lot: Optional[float] = None
    runtime_hedge_recovery_pct: Optional[float] = None
    runtime_hedge_roll_min_profit: Optional[float] = None
    runtime_hedge_cycle_levels: Optional[int] = None
    runtime_enable_hedge_cycle_reset: Optional[bool] = None
    runtime_hedge_cycle_partial_pct: Optional[float] = None
    runtime_hedge_max_cycles: Optional[int] = None
    runtime_hedge_max_chain_loss_usd: Optional[float] = None
    runtime_hedge_max_chain_loss_pct: Optional[float] = None
    runtime_hedge_clear_root_sl: Optional[bool] = None
    runtime_hedge_trail_atr: Optional[float] = None

    # Dynamic sizing
    runtime_enable_dynamic_lots: Optional[bool] = None
    runtime_equity_drop_percent: Optional[float] = None
    runtime_max_equity_drop_lot_steps: Optional[int] = None
    runtime_min_signal_strength_for_lot: Optional[float] = None
    runtime_lot_step_size: Optional[float] = None
    runtime_max_lot_size: Optional[float] = None

    # Equity protection
    runtime_enable_basket_stop: Optional[bool] = None
    runtime_max_basket_loss_pct: Optional[float] = None
    runtime_min_equity_percent: Optional[float] = None
    runtime_max_drawdown_from_peak: Optional[float] = None
    runtime_pause_minutes: Optional[int] = None
    runtime_pause_minutes_multiplier: Optional[float] = None
    runtime_max_pause_minutes: Optional[int] = None
    runtime_max_min_equity_triggers: Optional[int] = None
    runtime_reset_on_new_peak: Optional[bool] = None
    runtime_target_equity: Optional[float] = None
    runtime_minimum_equity: Optional[float] = None

    # TP / SL / risk reward
    runtime_enable_take_profit: Optional[bool] = None
    runtime_tp_input_type: Optional[int] = None
    runtime_tp_value: Optional[float] = None
    runtime_enable_stop_loss: Optional[bool] = None
    runtime_sl_input_type: Optional[int] = None
    runtime_sl_value: Optional[float] = None
    runtime_enable_risk_reward: Optional[bool] = None
    runtime_rr_risk_mode: Optional[int] = None
    runtime_rr_risk_input_type: Optional[int] = None
    runtime_rr_risk_value: Optional[float] = None
    runtime_rr_atr_multiplier: Optional[float] = None
    runtime_risk_reward_ratio: Optional[float] = None

    # Trailing
    runtime_enable_trailing: Optional[bool] = None
    runtime_trailing_enable_break_even_lock: Optional[bool] = None
    runtime_trailing_sl_on_profitable_only: Optional[bool] = None
    runtime_enable_adaptive_tp: Optional[bool] = None
    runtime_enable_adaptive_sl: Optional[bool] = None
    runtime_ts_input_type: Optional[int] = None
    runtime_trailing_distance_value: Optional[float] = None
    runtime_trailing_value_multiplier: Optional[float] = None

    # Operational filters / diagnostics
    runtime_enable_discord_alerts: Optional[bool] = None
    runtime_enable_trading_hours: Optional[bool] = None
    runtime_trading_start_time: Optional[str] = None
    runtime_trading_end_time: Optional[str] = None
    runtime_enable_reports: Optional[bool] = None
    runtime_send_report_every_hour: Optional[int] = None
    runtime_enable_market_close_filter: Optional[bool] = None
    runtime_minutes_before_close: Optional[int] = None
    runtime_enable_news_filter: Optional[bool] = None
    runtime_news_minutes_before: Optional[int] = None
    runtime_news_minutes_after: Optional[int] = None
    runtime_enable_leverage_pause: Optional[bool] = None
    runtime_enable_logging: Optional[bool] = None

    # Decision telemetry
    buy_adjusted_score: float = 0.0
    sell_adjusted_score: float = 0.0
    buy_effective_threshold: float = 0.0
    sell_effective_threshold: float = 0.0
    buy_entry_eligible: bool = False
    sell_entry_eligible: bool = False
    buy_block_reason: str = ""
    sell_block_reason: str = ""
    new_bar_entry_only: bool = False
    new_bar_ready: bool = False
    cooldown_active: bool = False
    cooldown_until_epoch: int = 0

    # Last order attempt
    last_order_attempted: bool = False
    last_order_success: bool = False
    last_order_direction: str = ""
    last_order_mode: str = ""
    last_order_retcode: int = 0
    last_order_ticket: int = 0
    last_order_time_epoch: int = 0

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Runtime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    atlas_version: str = "0.1.0"
    environment: str = "demo"
    strategy: str = "nyao"
    last_updated: Optional[datetime] = None