ATLAS ↔ NYAO FULL RUNTIME CONTROL INVENTORY
Runtime-controllable inputs: 156
Immutable infrastructure: MagicNumber, DiscordWebhookURL

[Signal / indicator behavior]
directional_body_lookback | int | default=10 | status=runtime_directional_body_lookback
ema_fast_period | int | default=5 | status=runtime_ema_fast_period
ema_slow_period | int | default=12 | status=runtime_ema_slow_period
slope_lookback | int | default=3 | status=runtime_slope_lookback
rsi_period | int | default=8 | status=runtime_rsi_period
atr_period | int | default=8 | status=runtime_atr_period
atr_avg_lookback | int | default=10 | status=runtime_atr_avg_lookback
min_vol_ratio_to_trade | double | default=0.6 | status=runtime_min_vol_ratio_to_trade
impulse_lookback | int | default=3 | status=runtime_impulse_lookback
impulse_boost_weight | double | default=1.0 | status=runtime_impulse_boost_weight
signal_smoothing_candles | int | default=2 | status=runtime_signal_smoothing_candles
current_candle_blend | double | default=0.40 | status=runtime_current_candle_blend
velocity_window | double | default=2.0 | status=runtime_velocity_window
rsi_overbought | int | default=80 | status=runtime_rsi_overbought
rsi_oversold | int | default=20 | status=runtime_rsi_oversold
rsi_momentum_buy | int | default=60 | status=runtime_rsi_momentum_buy
rsi_momentum_sell | int | default=40 | status=runtime_rsi_momentum_sell

[Score weights]
trend_weight | double | default=1.5 | status=runtime_trend_weight
slope_weight | double | default=1.5 | status=runtime_slope_weight
momentum_base_weight | double | default=1.0 | status=runtime_momentum_base_weight
momentum_trigger_weight | double | default=0.5 | status=runtime_momentum_trigger_weight
body_momentum_weight | double | default=1.5 | status=runtime_body_momentum_weight
chop_score_high | double | default=2.0 | status=runtime_chop_score_high
chop_score_med | double | default=1.0 | status=runtime_chop_score_med
chop_score_low | double | default=0.0 | status=runtime_chop_score_low
volatility_score_high | double | default=1.0 | status=runtime_volatility_score_high
volatility_score_low | double | default=0.0 | status=runtime_volatility_score_low
peak_score_weight | double | default=1.0 | status=runtime_peak_score_weight
wick_rejection_weight | double | default=1.0 | status=runtime_wick_rejection_weight
min_body_ratio | double | default=1.5 | status=runtime_min_body_ratio

[Entry / execution]
enable_buy_orders | bool | default=true | status=runtime_enable_buy_orders
enable_sell_orders | bool | default=true | status=runtime_enable_sell_orders
enable_new_bar_entry_only | bool | default=true | status=runtime_enable_new_bar_entry_only
enable_max_spread_filter | bool | default=true | status=runtime_enable_max_spread_filter
max_spread_points | double | default=0 | status=runtime_max_spread_points
max_spread_atr_ratio | double | default=0.25 | status=runtime_max_spread_atr_ratio
base_lot_size | double | default=0.01 | status=runtime_base_lot_size
max_open_orders | int | default=8 | status=runtime_max_open_orders
max_trades_per_candle | int | default=1 | status=runtime_max_trades_per_candle
consecutive_candle_threshold_boost | double | default=1.0 | status=runtime_consecutive_candle_threshold_boost
max_consecutive_candle_boosts | int | default=3 | status=runtime_max_consecutive_candle_boosts
zone_points | double | default=500 | status=runtime_zone_points
buy_duplicate_multiplier | double | default=1.5 | status=runtime_buy_duplicate_multiplier
sell_duplicate_multiplier | double | default=1.5 | status=runtime_sell_duplicate_multiplier
min_break_even_profit | double | default=0.5 | status=runtime_min_break_even_profit
profit_threshold_multiplier | double | default=1.5 | status=runtime_profit_threshold_multiplier
loss_threshold_multiplier | double | default=2.0 | status=runtime_loss_threshold_multiplier
min_buy_signal_score | double | default=4.5 | status=runtime_min_buy_signal_score
min_sell_signal_score | double | default=4.5 | status=runtime_min_sell_signal_score

[Limit entry]
enable_limit_entry | bool | default=false | status=runtime_enable_limit_entry
limit_entry_anchor | ENUM_LIMIT_ANCHOR | default=LIMIT_ANCHOR_FIXED_ATR | status=runtime_limit_entry_anchor
limit_entry_atr_fraction | double | default=0.25 | status=runtime_limit_entry_atr_fraction
limit_entry_expiry_bars | int | default=1 | status=runtime_limit_entry_expiry_bars
limit_entry_cancel_on_flip | bool | default=true | status=runtime_limit_entry_cancel_on_flip

[Signal dampening]
enable_signal_dampening | bool | default=true | status=runtime_enable_signal_dampening
max_losing_positions_same_dir | int | default=2 | status=runtime_max_losing_positions_same_dir
losing_pos_score_penalty | double | default=1.5 | status=runtime_losing_pos_score_penalty
drawdown_threshold_pct | double | default=3.0 | status=runtime_drawdown_threshold_pct
drawdown_score_boost | double | default=2.0 | status=runtime_drawdown_score_boost
consecutive_losses_before_cooldown | int | default=3 | status=runtime_consecutive_losses_before_cooldown
consecutive_loss_cooldown_bars | int | default=3 | status=runtime_consecutive_loss_cooldown_bars

[Loss / health management]
enable_loss_management | bool | default=true | status=runtime_enable_loss_management
max_holding_loss_positions | int | default=2 | status=runtime_max_holding_loss_positions
min_health_score | double | default=0.40 | status=runtime_min_health_score
max_adverse_atr | double | default=1.5 | status=runtime_max_adverse_atr
health_trend_weight | double | default=0.40 | status=runtime_health_trend_weight
health_rsi_weight | double | default=0.25 | status=runtime_health_rsi_weight
health_atr_weight | double | default=0.25 | status=runtime_health_atr_weight
health_swing_weight | double | default=0.10 | status=runtime_health_swing_weight
health_rsi_buy_min | double | default=40.0 | status=runtime_health_rsi_buy_min
health_rsi_sell_max | double | default=60.0 | status=runtime_health_rsi_sell_max
health_swing_lookback | int | default=20 | status=runtime_health_swing_lookback
health_grace_bars | int | default=2 | status=runtime_health_grace_bars
enable_partial_close | bool | default=true | status=runtime_enable_partial_close
partial_close75_pct | double | default=0.25 | status=runtime_partial_close75_pct
partial_close50_pct | double | default=0.50 | status=runtime_partial_close50_pct
partial_close25_pct | double | default=1.00 | status=runtime_partial_close25_pct
enable_health_sl_tightening | bool | default=true | status=runtime_enable_health_sl_tightening
sl_tighten_atr_multiplier | double | default=2.0 | status=runtime_sl_tighten_atr_multiplier
sl_tighten_min_health_pct | double | default=0.50 | status=runtime_sl_tighten_min_health_pct
enable_break_even_on_spread | bool | default=true | status=runtime_enable_break_even_on_spread
break_even_spread_multiplier | double | default=1.5 | status=runtime_break_even_spread_multiplier
enable_virtual_sl_reentry | bool | default=true | status=runtime_enable_virtual_sl_reentry
reentry_respects_new_bar_gate | bool | default=false | status=runtime_reentry_respects_new_bar_gate
reentry_min_signal_pct | double | default=0.75 | status=runtime_reentry_min_signal_pct
enable_profit_offset_sl | bool | default=true | status=runtime_enable_profit_offset_sl
consecutive_wins_required | int | default=3 | status=runtime_consecutive_wins_required
min_offset_profit | double | default=1.0 | status=runtime_min_offset_profit

[Hedge chain]
enable_hedge_chain | bool | default=true | status=runtime_enable_hedge_chain
hedge_trigger_atr | double | default=1.5 | status=runtime_hedge_trigger_atr
hedge_require_signal | bool | default=true | status=runtime_hedge_require_signal
hedge_min_signal_score | double | default=4.5 | status=runtime_hedge_min_signal_score
hedge_auto_lot | bool | default=true | status=runtime_hedge_auto_lot
hedge_recovery_atr | double | default=1.0 | status=runtime_hedge_recovery_atr
hedge_lot_multiplier | double | default=2.0 | status=runtime_hedge_lot_multiplier
hedge_max_lot | double | default=0.10 | status=runtime_hedge_max_lot
hedge_recovery_pct | double | default=110.0 | status=runtime_hedge_recovery_pct
hedge_roll_min_profit | double | default=0.5 | status=runtime_hedge_roll_min_profit
hedge_cycle_levels | int | default=2 | status=runtime_hedge_cycle_levels
enable_hedge_cycle_reset | bool | default=false | status=runtime_enable_hedge_cycle_reset
hedge_cycle_partial_pct | double | default=50.0 | status=runtime_hedge_cycle_partial_pct
hedge_max_cycles | int | default=3 | status=runtime_hedge_max_cycles
hedge_max_chain_loss_usd | double | default=0.0 | status=runtime_hedge_max_chain_loss_usd
hedge_max_chain_loss_pct | double | default=0.0 | status=runtime_hedge_max_chain_loss_pct
hedge_clear_root_sl | bool | default=true | status=runtime_hedge_clear_root_sl
hedge_trail_atr | double | default=0.5 | status=runtime_hedge_trail_atr

[Dynamic sizing]
enable_dynamic_lots | bool | default=true | status=runtime_enable_dynamic_lots
equity_drop_percent | double | default=5.0 | status=runtime_equity_drop_percent
max_equity_drop_lot_steps | int | default=2 | status=runtime_max_equity_drop_lot_steps
min_signal_strength_for_lot | double | default=8.0 | status=runtime_min_signal_strength_for_lot
lot_step_size | double | default=0.01 | status=runtime_lot_step_size
max_lot_size | double | default=0.05 | status=runtime_max_lot_size

[Equity protection]
enable_basket_stop | bool | default=true | status=runtime_enable_basket_stop
max_basket_loss_pct | double | default=8.0 | status=runtime_max_basket_loss_pct
min_equity_percent | double | default=70.0 | status=runtime_min_equity_percent
max_drawdown_from_peak | double | default=0 | status=runtime_max_drawdown_from_peak
pause_minutes | int | default=5 | status=runtime_pause_minutes
pause_minutes_multiplier | double | default=1.5 | status=runtime_pause_minutes_multiplier
max_pause_minutes | int | default=120 | status=runtime_max_pause_minutes
max_min_equity_triggers | int | default=0 | status=runtime_max_min_equity_triggers
reset_on_new_peak | bool | default=true | status=runtime_reset_on_new_peak
target_equity | double | default=0 | status=runtime_target_equity
minimum_equity | double | default=20 | status=runtime_minimum_equity

[TP / SL / risk reward]
enable_take_profit | bool | default=false | status=runtime_enable_take_profit
tp_input_type | ENUM_INPUT_TYPE | default=INPUT_DOLLAR | status=runtime_tp_input_type
tp_value | double | default=10.0 | status=runtime_tp_value
enable_stop_loss | bool | default=true | status=runtime_enable_stop_loss
sl_input_type | ENUM_INPUT_TYPE | default=INPUT_PERCENT | status=runtime_sl_input_type
sl_value | double | default=10.0 | status=runtime_sl_value
enable_risk_reward | bool | default=false | status=runtime_enable_risk_reward
rr_risk_mode | ENUM_RR_RISK_MODE | default=RR_RISK_ATR | status=runtime_rr_risk_mode
rr_risk_input_type | ENUM_INPUT_TYPE | default=INPUT_POINTS | status=runtime_rr_risk_input_type
rr_risk_value | double | default=200.0 | status=runtime_rr_risk_value
rr_atr_multiplier | double | default=1.5 | status=runtime_rr_atr_multiplier
risk_reward_ratio | double | default=1.5 | status=runtime_risk_reward_ratio

[Trailing]
enable_trailing | bool | default=true | status=runtime_enable_trailing
trailing_enable_break_even_lock | bool | default=true | status=runtime_trailing_enable_break_even_lock
trailing_sl_on_profitable_only | bool | default=true | status=runtime_trailing_sl_on_profitable_only
enable_adaptive_tp | bool | default=true | status=runtime_enable_adaptive_tp
enable_adaptive_sl | bool | default=true | status=runtime_enable_adaptive_sl
ts_input_type | ENUM_INPUT_TYPE | default=INPUT_DOLLAR | status=runtime_ts_input_type
trailing_distance_value | double | default=0.2 | status=runtime_trailing_distance_value
trailing_value_multiplier | double | default=0.2 | status=runtime_trailing_value_multiplier

[Operational filters / diagnostics]
enable_discord_alerts | bool | default=false | status=runtime_enable_discord_alerts
enable_trading_hours | bool | default=false | status=runtime_enable_trading_hours
trading_start_time | string | default="00:00" | status=runtime_trading_start_time
trading_end_time | string | default="23:59" | status=runtime_trading_end_time
enable_reports | bool | default=true | status=runtime_enable_reports
send_report_every_hour | int | default=1 | status=runtime_send_report_every_hour
enable_market_close_filter | bool | default=true | status=runtime_enable_market_close_filter
minutes_before_close | int | default=30 | status=runtime_minutes_before_close
enable_news_filter | bool | default=true | status=runtime_enable_news_filter
news_minutes_before | int | default=30 | status=runtime_news_minutes_before
news_minutes_after | int | default=30 | status=runtime_news_minutes_after
enable_leverage_pause | bool | default=true | status=runtime_enable_leverage_pause
enable_logging | bool | default=false | status=runtime_enable_logging