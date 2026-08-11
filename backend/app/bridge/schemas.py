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
    # Atlas-owned policy metadata. Callers may omit this; main.py owns increments.
    policy_epoch: int = Field(default=1, ge=1)

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
    enable_duplicate_distance_filter: Optional[bool] = None
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
    # Telemetry is producer-owned; preserve forward-compatible fields instead of
    # silently deleting them at the Atlas bridge boundary.
    model_config = ConfigDict(extra="allow")

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

    # Authoritative Nyao entry-event telemetry for Atlas replay.
    order_origin: str = ""
    entry_gate_mode: str = ""
    entry_evaluation_event: str = ""
    entry_was_new_bar: bool = False
    trades_on_entry_candle_before_this_entry: int = -1
    total_trades_on_entry_candle_before_this_entry: int = -1
    entry_policy_epoch: int = 0
    scalp_context_class: str = "NEUTRAL_SCALP"
    scalp_context_zone_side: str = "NONE"
    scalp_context_pressure: float = 0.0
    zone_plan_id: str = ""
    zone_layer: int = 0
    identity_restored_from_registry: bool = False
    recovery_probe_entry: bool = False
    recovery_probe_target_risk_pct: float = 0.0
    recovery_probe_max_risk_pct: float = 0.0
    recovery_probe_admission_risk_pct: float = 0.0
    recovery_probe_admission_risk_amount: float = 0.0
    recovery_probe_frozen_risk_amount: float = 0.0

    management_policy_lock_active: bool = False
    management_policy_source: str = ""
    management_policy_resolved_epoch: int = 0
    management_policy_min_health_score: float = 0.0
    management_policy_health_grace_bars: int = 0
    management_policy_enable_partial_close: bool = False
    management_policy_enable_adaptive_tp: bool = False
    management_policy_enable_adaptive_sl: bool = False
    management_policy_trailing_distance_value: float = 0.0

    recovery_policy_lock_active: bool = False
    recovery_policy_source: str = ""
    recovery_policy_resolved_epoch: int = 0
    recovery_policy_enable_virtual_sl_reentry: bool = False
    recovery_policy_reentry_min_signal_pct: float = 0.0
    recovery_policy_enable_hedge_chain: bool = False
    recovery_policy_hedge_trigger_atr: float = 0.0
    recovery_policy_hedge_recovery_pct: float = 0.0
    recovery_policy_hedge_max_lot: float = 0.0
    recovery_policy_hedge_trail_atr: float = 0.0

    trailing_policy_lock_active: bool = False
    trailing_policy_source: str = ""
    trailing_policy_resolved_epoch: int = 0
    trailing_policy_enable_trailing: bool = False
    trailing_policy_break_even_lock: bool = False
    trailing_policy_profitable_only: bool = False
    trailing_policy_ts_input_type: int = 0
    trailing_policy_distance_value: float = 0.0
    trailing_policy_value_multiplier: float = 0.0

    profit_management_state: str = "UNPROTECTED"
    profit_protection_trigger_amount: float = 0.0
    protected_profit_amount: float = 0.0
    protected_profit_pct_of_current_profit: float = 0.0

    partial_close_level: int = 0
    break_even_locked: bool = False

    chain_id: int = 0
    hedge_level: int = 0
    cycle_num: int = 0
    no_rehedge: bool = False
    hedge_graduated: bool = False
    hedge_lock_profit: float = 0.0


class ExitDealTelemetry(BaseModel):
    model_config = ConfigDict(extra="allow")

    sequence: int = 0
    deal_ticket: int = 0
    position_id: int = 0
    order_ticket: int = 0
    time_epoch: int = 0
    time_msc: int = 0
    deal_type: str = ""
    deal_entry: str = ""
    reason: str = ""
    volume: float = 0.0
    price: float = 0.0
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    fee: float = 0.0
    net_pl: float = 0.0
    position_still_open_after_deal: bool = False
    full_close: bool = False
    comment: str = ""

    # P3.28 authoritative entry-side lifecycle metadata. These fields are
    # emitted by Nyao for historical exit deals and must survive the bridge so
    # Atlas can attribute outcomes to the policy that actually opened them.
    entry_order_ticket: int = 0
    entry_time_epoch: int = 0
    entry_time_msc: int = 0
    entry_price: float = 0.0
    entry_volume: float = 0.0
    original_position_type: str = ""
    entry_comment: str = ""
    entry_policy_epoch: int = 0
    entry_order_origin: str = ""
    entry_chain_id: int = 0
    entry_hedge_level: int = 0
    entry_zone_plan_id: str = ""
    entry_zone_layer: int = 0


class Status(BaseModel):
    model_config = ConfigDict(extra="allow")

    # Connection / identity
    connected: bool = True
    strategy: str = "nyao"
    symbol: str = "XAUUSD"

    # Account
    account_login: int = 0
    account_server: str = ""
    account_company: str = ""
    account_currency: str = ""
    account_trade_mode: int = 0
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
    recent_exit_deals: List[ExitDealTelemetry] = Field(default_factory=list)
    lifecycle_contract_version: str = ""
    lifecycle_contract_started_at_epoch: int = 0
    recent_lifecycle_events: List[dict[str, Any]] = Field(default_factory=list)
    recent_exit_deal_count: int = 0
    exit_deal_sequence: int = 0
    policy_epoch: int = 1
    trailing_policy_execution_enabled: bool = False
    trailing_policy_execution_control_count: int = 0
    trailing_policy_snapshot_count: int = 0

    management_policy_execution_enabled: bool = False
    management_policy_execution_control_count: int = 0
    management_policy_snapshot_count: int = 0

    recovery_policy_execution_enabled: bool = False
    recovery_policy_execution_control_count: int = 0
    position_sensitive_execution_control_count: int = 0
    recovery_policy_snapshot_count: int = 0

    position_identity_registry_enabled: bool = False
    position_identity_registry_loaded_count: int = 0
    position_identity_restore_count: int = 0
    position_identity_restore_reject_count: int = 0

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
    market_quote_fresh: bool = False
    market_quote_source: str = ""
    market_quote_age_ms: int = 0
    market_quote_time_msc: int = 0
    market_quote_freshness_limit_ms: int = 2500
    effective_spread_cap_points: float = 0.0
    spread_within_limit: bool = True

    # P3.29 dynamic scalp transaction-cost economics. The ordinary scalp lane
    # adapts its executable SL/TP geometry to the live spread before capital
    # sizing; the fixed spread setting is only an emergency outer ceiling.
    scalp_cost_gate_version: str = ""
    scalp_stop_geometry_basis: str = ""
    scalp_stop_input_lot_dependent: bool = False
    scalp_cost_gate_basis: str = ""
    scalp_cost_limiting_factor: str = ""
    scalp_cost_adjusted: bool = False
    scalp_cost_feasible: bool = True
    scalp_cost_headroom_multiplier: float = 1.0
    scalp_base_stop_points: float = 0.0
    scalp_base_target_points: float = 0.0
    scalp_planned_stop_points: float = 0.0
    scalp_planned_target_points: float = 0.0
    scalp_spread_to_stop_ratio: float = 0.0
    scalp_spread_to_target_ratio: float = 0.0
    scalp_max_spread_stop_ratio: float = 0.0
    scalp_max_spread_target_ratio: float = 0.0
    scalp_cost_ratio_feasible: bool = True
    scalp_structure_feasible: bool = True
    scalp_structure_reason: str = ""
    scalp_stop_expansion_ratio: float = 1.0
    scalp_target_expansion_ratio: float = 1.0
    scalp_planned_stop_atr_ratio: float = 0.0
    scalp_spread_atr_ratio: float = 0.0
    scalp_max_stop_expansion_ratio: float = 0.0
    scalp_max_stop_atr_ratio: float = 0.0
    scalp_max_spread_atr_ratio: float = 0.0

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
    market_session_state: str = "UNKNOWN"
    market_session_open: bool = False
    market_next_close_epoch: int = 0
    market_next_open_epoch: int = 0
    market_session_source: str = ""
    account_ledger: dict[str, Any] = Field(default_factory=dict)
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
    zone_execution_supported: bool = False
    zone_execution_enabled: bool = False
    zone_directive_fresh: bool = False
    zone_mode_active: bool = False
    zone_scalp_suspended: bool = False
    zone_aware_scalping_active: bool = False
    source_zone_invalidated: bool = False
    source_zone_invalidation_reason: str = ""
    zone_directive_state: str = "NOT_SUPPORTED"
    zone_plan_id: str = ""
    zone_map_id: str = ""
    zone_side: str = "NONE"
    zone_orders_submitted: int = 0
    zone_last_execution_reason: str = "NOT_SUPPORTED"
    zone_policy_epoch: int = 0
    zone_policy_fingerprint: str = ""
    zone_confirmation_score: float = 0.0
    zone_confirmation_threshold: float = 0.0
    zone_directional_score: float = 0.0
    zone_minimum_directional_score: float = 0.0
    zone_spread_within_limit: bool = True
    zone_spread_price: float = 0.0
    zone_effective_spread_cap_price: float = 0.0
    zone_virtual_layer_execution: bool = False
    zone_virtual_layers_waiting: int = 0
    capital_sizing_active: bool = False
    capital_sizing_version: str = ""
    capital_veto_new_risk: bool = False
    approved_scalp_risk_pct: float = 0.0
    recovery_probe_active: bool = False
    recovery_probe_target_risk_pct: float = 0.0
    recovery_probe_max_executable_risk_pct: float = 0.0
    recovery_probe_minimum_executable_risk_pct: float = 0.0
    recovery_probe_minimum_executable_risk_amount: float = 0.0
    recovery_probe_minimum_volume: float = 0.0
    recovery_probe_broker_override_active: bool = False
    recovery_probe_feasibility_reason: str = "NOT_EVALUATED"
    recovery_probe_feasibility_fresh: bool = False
    recovery_probe_feasibility_equity: float = 0.0
    recovery_probe_feasibility_evaluated_at_epoch: int = 0
    maximum_total_strategy_risk_pct: float = 0.0
    recovery_sizing_version: str = ""
    recovery_sizing_reason: str = "NOT_EVALUATED"
    recovery_sizing_chain_id: int = 0
    recovery_sizing_event_sequence: int = 0
    recovery_sizing_evaluated_at_epoch: int = 0
    recovery_requested_lot: float = 0.0
    recovery_capital_capped_lot: float = 0.0
    recovery_final_lot: float = 0.0
    recovery_anchor_loss_usd: float = 0.0
    recovery_original_unit_risk_usd: float = 0.0
    recovery_unit_budget_multiplier: float = 0.0
    recovery_portfolio_budget_usd: float = 0.0
    recovery_budget_basis: str = ""
    recovery_chain_budget_usd: float = 0.0
    recovery_remaining_budget_usd: float = 0.0
    recovery_target_move_price: float = 0.0
    recovery_estimated_adverse_risk_usd: float = 0.0
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
    runtime_enable_duplicate_distance_filter: Optional[bool] = None
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
    buy_duplicate_reference_active: bool = False
    sell_duplicate_reference_active: bool = False
    buy_duplicate_blocked: bool = False
    sell_duplicate_blocked: bool = False
    buy_duplicate_reference_ticket: int = 0
    sell_duplicate_reference_ticket: int = 0
    buy_duplicate_distance_points: float = 0.0
    sell_duplicate_distance_points: float = 0.0
    buy_duplicate_required_distance_points: float = 0.0
    sell_duplicate_required_distance_points: float = 0.0
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
    # P3.44 broker-preflight integrity
    preflight_state: str = "NOT_EVALUATED"
    preflight_retry_count: int = 0
    preflight_retcode: int = 0
    preflight_comment: str = ""

    preflight_request_price: float = 0.0
    preflight_request_sl: float = 0.0
    preflight_request_tp: float = 0.0
    preflight_request_volume: float = 0.0

    preflight_bid: float = 0.0
    preflight_ask: float = 0.0

    preflight_stops_level: int = 0
    preflight_freeze_level: int = 0

    preflight_sl_distance_points: float = 0.0
    preflight_tp_distance_points: float = 0.0
    preflight_retry_safety_points: float = 0.0
    preflight_min_distance_points: float = 0.0
    preflight_detached_stops_fallback_attempted: bool = False
    preflight_detached_stops_fallback_accepted: bool = False
    preflight_detached_stops_retcode: int = 0
    preflight_protection_state: str = "NOT_REQUIRED"
    preflight_intended_risk_amount: float = 0.0
    preflight_actual_fill_price: float = 0.0
    preflight_attached_sl: float = 0.0
    preflight_attached_tp: float = 0.0
    preflight_protection_retcode: int = 0
    preflight_entry_price_integrity_state: str = "NOT_EVALUATED"
    preflight_candidate_reference_price: float = 0.0
    preflight_send_reference_price: float = 0.0
    preflight_send_bid: float = 0.0
    preflight_send_ask: float = 0.0
    preflight_fresh_tick_time_msc: int = 0
    preflight_quote_age_ms: int = 0
    preflight_quote_freshness_limit_ms: int = 5000
    preflight_quote_freshness_state: str = "NOT_EVALUATED"
    preflight_candidate_to_send_drift_points: float = 0.0
    preflight_allowed_entry_drift_points: float = 0.0
    preflight_send_to_fill_drift_points: float = 0.0
    # P3.51 structure-aware initial stop authority
    initial_stop_authority: str = "NOT_EVALUATED"
    initial_stop_atr_floor_points: float = 0.0
    initial_stop_swing_price: float = 0.0
    initial_stop_swing_points: float = 0.0
    initial_stop_buffer_points: float = 0.0
    initial_stop_final_points: float = 0.0
    terminal_algo_trading_allowed: Optional[bool] = None
    ea_trading_allowed: Optional[bool] = None
    account_trade_allowed: Optional[bool] = None
    account_expert_trading_allowed: Optional[bool] = None

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Runtime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    atlas_version: str = "0.1.0"
    environment: str = "demo"
    strategy: str = "nyao"
    last_updated: Optional[datetime] = None
