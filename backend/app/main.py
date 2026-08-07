from datetime import datetime, timezone
import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from backend.app.bridge.protocol import COMMANDS_FILE, STATUS_FILE
from backend.app.bridge.reader import read_json
from backend.app.bridge.schemas import Command, Status
from backend.app.bridge.writer import write_json
from backend.app.intelligence.advisor import generate_advice
from backend.app.intelligence.history import (
    get_history,
    get_history_summary,
    record_intelligence_snapshot,
)


app = FastAPI(
    title="Atlas",
    version="0.5.0",
)

RUNTIME_CONTROL_GROUPS = json.loads(
    r'''[{"name":"Entry / execution","controls":[{"name":"enable_buy_orders","mql_type":"bool","default":"true","status_key":"runtime_enable_buy_orders","label":"Enable Buy Orders","kind":"bool"},{"name":"enable_sell_orders","mql_type":"bool","default":"true","status_key":"runtime_enable_sell_orders","label":"Enable Sell Orders","kind":"bool"},{"name":"enable_new_bar_entry_only","mql_type":"bool","default":"true","status_key":"runtime_enable_new_bar_entry_only","label":"Enable New Bar Entry Only","kind":"bool"},{"name":"enable_max_spread_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_max_spread_filter","label":"Enable Max Spread Filter","kind":"bool"},{"name":"max_spread_points","mql_type":"double","default":"0","status_key":"runtime_max_spread_points","label":"Max Spread Points","kind":"number","min":0,"max":100000,"step":1},{"name":"max_spread_atr_ratio","mql_type":"double","default":"0.25","status_key":"runtime_max_spread_atr_ratio","label":"Max Spread ATR Ratio","kind":"number","min":0,"max":10,"step":0.01},{"name":"base_lot_size","mql_type":"double","default":"0.01","status_key":"runtime_base_lot_size","label":"Base Lot Size","kind":"number","min":0.01,"max":5,"step":0.01},{"name":"max_open_orders","mql_type":"int","default":"8","status_key":"runtime_max_open_orders","label":"Max Open Orders","kind":"number","min":1,"max":50,"step":1},{"name":"max_trades_per_candle","mql_type":"int","default":"1","status_key":"runtime_max_trades_per_candle","label":"Max Trades Per Candle","kind":"number","min":0,"max":20,"step":1},{"name":"consecutive_candle_threshold_boost","mql_type":"double","default":"1.0","status_key":"runtime_consecutive_candle_threshold_boost","label":"Consecutive Candle Threshold Boost","kind":"number","min":0,"max":10,"step":0.1},{"name":"max_consecutive_candle_boosts","mql_type":"int","default":"3","status_key":"runtime_max_consecutive_candle_boosts","label":"Max Consecutive Candle Boosts","kind":"number","min":0,"max":100,"step":1},{"name":"zone_points","mql_type":"double","default":"500","status_key":"runtime_zone_points","label":"Zone Points","kind":"number","min":0,"max":1000000,"step":1},{"name":"buy_duplicate_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_buy_duplicate_multiplier","label":"Buy Duplicate Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"sell_duplicate_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_sell_duplicate_multiplier","label":"Sell Duplicate Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"min_break_even_profit","mql_type":"double","default":"0.5","status_key":"runtime_min_break_even_profit","label":"Min Break Even Profit","kind":"number","min":0,"max":1000000,"step":0.1},{"name":"profit_threshold_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_profit_threshold_multiplier","label":"Profit Threshold Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"loss_threshold_multiplier","mql_type":"double","default":"2.0","status_key":"runtime_loss_threshold_multiplier","label":"Loss Threshold Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"min_buy_signal_score","mql_type":"double","default":"4.5","status_key":"runtime_min_buy_signal_score","label":"Min Buy Signal Score","kind":"number","min":0,"max":10,"step":0.1},{"name":"min_sell_signal_score","mql_type":"double","default":"4.5","status_key":"runtime_min_sell_signal_score","label":"Min Sell Signal Score","kind":"number","min":0,"max":10,"step":0.1}],"description":"Controls when fresh positions may open, order frequency, spread gating, lot size and duplicate-entry protection.","danger":false},{"name":"Signal / indicator behavior","controls":[{"name":"directional_body_lookback","mql_type":"int","default":"10","status_key":"runtime_directional_body_lookback","label":"Directional Body Lookback","kind":"number","min":1,"max":500,"step":1},{"name":"ema_fast_period","mql_type":"int","default":"5","status_key":"runtime_ema_fast_period","label":"EMA Fast Period","kind":"number","min":1,"max":500,"step":1},{"name":"ema_slow_period","mql_type":"int","default":"12","status_key":"runtime_ema_slow_period","label":"EMA Slow Period","kind":"number","min":1,"max":500,"step":1},{"name":"slope_lookback","mql_type":"int","default":"3","status_key":"runtime_slope_lookback","label":"Slope Lookback","kind":"number","min":1,"max":100,"step":1},{"name":"rsi_period","mql_type":"int","default":"8","status_key":"runtime_rsi_period","label":"RSI Period","kind":"number","min":2,"max":500,"step":1},{"name":"atr_period","mql_type":"int","default":"8","status_key":"runtime_atr_period","label":"ATR Period","kind":"number","min":1,"max":500,"step":1},{"name":"atr_avg_lookback","mql_type":"int","default":"10","status_key":"runtime_atr_avg_lookback","label":"ATR Avg Lookback","kind":"number","min":1,"max":500,"step":1},{"name":"min_vol_ratio_to_trade","mql_type":"double","default":"0.6","status_key":"runtime_min_vol_ratio_to_trade","label":"Min Vol Ratio To Trade","kind":"number","min":0,"max":10,"step":0.01},{"name":"impulse_lookback","mql_type":"int","default":"3","status_key":"runtime_impulse_lookback","label":"Impulse Lookback","kind":"number","min":1,"max":100,"step":1},{"name":"impulse_boost_weight","mql_type":"double","default":"1.0","status_key":"runtime_impulse_boost_weight","label":"Impulse Boost Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"signal_smoothing_candles","mql_type":"int","default":"2","status_key":"runtime_signal_smoothing_candles","label":"Signal Smoothing Candles","kind":"number","min":1,"max":10,"step":1},{"name":"current_candle_blend","mql_type":"double","default":"0.40","status_key":"runtime_current_candle_blend","label":"Current Candle Blend","kind":"number","min":0,"max":1,"step":0.01},{"name":"velocity_window","mql_type":"double","default":"2.0","status_key":"runtime_velocity_window","label":"Velocity Window","kind":"number","min":0.0001,"max":100,"step":0.1},{"name":"rsi_overbought","mql_type":"int","default":"80","status_key":"runtime_rsi_overbought","label":"RSI Overbought","kind":"number","min":0,"max":100,"step":1},{"name":"rsi_oversold","mql_type":"int","default":"20","status_key":"runtime_rsi_oversold","label":"RSI Oversold","kind":"number","min":0,"max":100,"step":1},{"name":"rsi_momentum_buy","mql_type":"int","default":"60","status_key":"runtime_rsi_momentum_buy","label":"RSI Momentum Buy","kind":"number","min":0,"max":100,"step":1},{"name":"rsi_momentum_sell","mql_type":"int","default":"40","status_key":"runtime_rsi_momentum_sell","label":"RSI Momentum Sell","kind":"number","min":0,"max":100,"step":1}],"description":"Controls indicator periods, smoothing, volatility gating and RSI behavior. EMA/RSI/ATR period changes trigger controlled indicator-handle rebuilds in Nyao.","danger":false},{"name":"Score weights","controls":[{"name":"trend_weight","mql_type":"double","default":"1.5","status_key":"runtime_trend_weight","label":"Trend Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"slope_weight","mql_type":"double","default":"1.5","status_key":"runtime_slope_weight","label":"Slope Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"momentum_base_weight","mql_type":"double","default":"1.0","status_key":"runtime_momentum_base_weight","label":"Momentum Base Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"momentum_trigger_weight","mql_type":"double","default":"0.5","status_key":"runtime_momentum_trigger_weight","label":"Momentum Trigger Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"body_momentum_weight","mql_type":"double","default":"1.5","status_key":"runtime_body_momentum_weight","label":"Body Momentum Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"chop_score_high","mql_type":"double","default":"2.0","status_key":"runtime_chop_score_high","label":"Chop Score High","kind":"number","min":0,"max":10,"step":0.1},{"name":"chop_score_med","mql_type":"double","default":"1.0","status_key":"runtime_chop_score_med","label":"Chop Score Med","kind":"number","min":0,"max":10,"step":0.1},{"name":"chop_score_low","mql_type":"double","default":"0.0","status_key":"runtime_chop_score_low","label":"Chop Score Low","kind":"number","min":0,"max":10,"step":0.1},{"name":"volatility_score_high","mql_type":"double","default":"1.0","status_key":"runtime_volatility_score_high","label":"Volatility Score High","kind":"number","min":0,"max":10,"step":0.1},{"name":"volatility_score_low","mql_type":"double","default":"0.0","status_key":"runtime_volatility_score_low","label":"Volatility Score Low","kind":"number","min":0,"max":10,"step":0.1},{"name":"peak_score_weight","mql_type":"double","default":"1.0","status_key":"runtime_peak_score_weight","label":"Peak Score Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"wick_rejection_weight","mql_type":"double","default":"1.0","status_key":"runtime_wick_rejection_weight","label":"Wick Rejection Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"min_body_ratio","mql_type":"double","default":"1.5","status_key":"runtime_min_body_ratio","label":"Min Body Ratio","kind":"number","min":0,"max":100,"step":0.1}],"description":"Changes how Nyao composes its signal score. Use carefully: these directly change what qualifies as a strong signal.","danger":false},{"name":"Limit entry","controls":[{"name":"enable_limit_entry","mql_type":"bool","default":"false","status_key":"runtime_enable_limit_entry","label":"Enable Limit Entry","kind":"bool"},{"name":"limit_entry_anchor","mql_type":"ENUM_LIMIT_ANCHOR","default":"LIMIT_ANCHOR_FIXED_ATR","status_key":"runtime_limit_entry_anchor","label":"Limit Entry Anchor","kind":"select","options":[{"value":0,"label":"Fixed ATR"},{"value":1,"label":"Swing"},{"value":2,"label":"EMA"},{"value":3,"label":"Smart"}]},{"name":"limit_entry_atr_fraction","mql_type":"double","default":"0.25","status_key":"runtime_limit_entry_atr_fraction","label":"Limit Entry ATR Fraction","kind":"number","min":0,"max":10,"step":0.01},{"name":"limit_entry_expiry_bars","mql_type":"int","default":"1","status_key":"runtime_limit_entry_expiry_bars","label":"Limit Entry Expiry Bars","kind":"number","min":0,"max":1000,"step":1},{"name":"limit_entry_cancel_on_flip","mql_type":"bool","default":"true","status_key":"runtime_limit_entry_cancel_on_flip","label":"Limit Entry Cancel On Flip","kind":"bool"}],"description":"Controls whether fresh entries use pending pullback orders instead of immediate market orders.","danger":false},{"name":"Signal dampening","controls":[{"name":"enable_signal_dampening","mql_type":"bool","default":"true","status_key":"runtime_enable_signal_dampening","label":"Enable Signal Dampening","kind":"bool"},{"name":"max_losing_positions_same_dir","mql_type":"int","default":"2","status_key":"runtime_max_losing_positions_same_dir","label":"Max Losing Positions Same Dir","kind":"number","min":0,"max":50,"step":1},{"name":"losing_pos_score_penalty","mql_type":"double","default":"1.5","status_key":"runtime_losing_pos_score_penalty","label":"Losing Pos Score Penalty","kind":"number","min":0,"max":10,"step":0.1},{"name":"drawdown_threshold_pct","mql_type":"double","default":"3.0","status_key":"runtime_drawdown_threshold_pct","label":"Drawdown Threshold %","kind":"number","min":0,"max":100,"step":0.1},{"name":"drawdown_score_boost","mql_type":"double","default":"2.0","status_key":"runtime_drawdown_score_boost","label":"Drawdown Score Boost","kind":"number","min":0,"max":10,"step":0.1},{"name":"consecutive_losses_before_cooldown","mql_type":"int","default":"3","status_key":"runtime_consecutive_losses_before_cooldown","label":"Consecutive Losses Before Cooldown","kind":"number","min":0,"max":100,"step":1},{"name":"consecutive_loss_cooldown_bars","mql_type":"int","default":"3","status_key":"runtime_consecutive_loss_cooldown_bars","label":"Consecutive Loss Cooldown Bars","kind":"number","min":0,"max":1000,"step":1}],"description":"Reduces repeated entries during drawdown, losing-position clusters and consecutive-loss periods.","danger":false},{"name":"Loss / health management","controls":[{"name":"enable_loss_management","mql_type":"bool","default":"true","status_key":"runtime_enable_loss_management","label":"Enable Loss Management","kind":"bool"},{"name":"max_holding_loss_positions","mql_type":"int","default":"2","status_key":"runtime_max_holding_loss_positions","label":"Max Holding Loss Positions","kind":"number","min":0,"max":50,"step":1},{"name":"min_health_score","mql_type":"double","default":"0.40","status_key":"runtime_min_health_score","label":"Min Health Score","kind":"number","min":0,"max":1,"step":0.01},{"name":"max_adverse_atr","mql_type":"double","default":"1.5","status_key":"runtime_max_adverse_atr","label":"Max Adverse ATR","kind":"number","min":0,"max":100,"step":0.1},{"name":"health_trend_weight","mql_type":"double","default":"0.40","status_key":"runtime_health_trend_weight","label":"Health Trend Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_rsi_weight","mql_type":"double","default":"0.25","status_key":"runtime_health_rsi_weight","label":"Health RSI Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_atr_weight","mql_type":"double","default":"0.25","status_key":"runtime_health_atr_weight","label":"Health ATR Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_swing_weight","mql_type":"double","default":"0.10","status_key":"runtime_health_swing_weight","label":"Health Swing Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_rsi_buy_min","mql_type":"double","default":"40.0","status_key":"runtime_health_rsi_buy_min","label":"Health RSI Buy Min","kind":"number","min":0,"max":100,"step":0.1},{"name":"health_rsi_sell_max","mql_type":"double","default":"60.0","status_key":"runtime_health_rsi_sell_max","label":"Health RSI Sell Max","kind":"number","min":0,"max":100,"step":0.1},{"name":"health_swing_lookback","mql_type":"int","default":"20","status_key":"runtime_health_swing_lookback","label":"Health Swing Lookback","kind":"number","min":1,"max":1000,"step":1},{"name":"health_grace_bars","mql_type":"int","default":"2","status_key":"runtime_health_grace_bars","label":"Health Grace Bars","kind":"number","min":0,"max":1000,"step":1},{"name":"enable_partial_close","mql_type":"bool","default":"true","status_key":"runtime_enable_partial_close","label":"Enable Partial Close","kind":"bool"},{"name":"partial_close75_pct","mql_type":"double","default":"0.25","status_key":"runtime_partial_close75_pct","label":"Partial Close 75 %","kind":"number","min":0,"max":1,"step":0.01},{"name":"partial_close50_pct","mql_type":"double","default":"0.50","status_key":"runtime_partial_close50_pct","label":"Partial Close 50 %","kind":"number","min":0,"max":1,"step":0.01},{"name":"partial_close25_pct","mql_type":"double","default":"1.00","status_key":"runtime_partial_close25_pct","label":"Partial Close 25 %","kind":"number","min":0,"max":1,"step":0.01},{"name":"enable_health_sl_tightening","mql_type":"bool","default":"true","status_key":"runtime_enable_health_sl_tightening","label":"Enable Health SL Tightening","kind":"bool"},{"name":"sl_tighten_atr_multiplier","mql_type":"double","default":"2.0","status_key":"runtime_sl_tighten_atr_multiplier","label":"SL Tighten ATR Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"sl_tighten_min_health_pct","mql_type":"double","default":"0.50","status_key":"runtime_sl_tighten_min_health_pct","label":"SL Tighten Min Health %","kind":"number","min":0,"max":1,"step":0.01},{"name":"enable_break_even_on_spread","mql_type":"bool","default":"true","status_key":"runtime_enable_break_even_on_spread","label":"Enable Break Even On Spread","kind":"bool"},{"name":"break_even_spread_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_break_even_spread_multiplier","label":"Break Even Spread Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"enable_virtual_sl_reentry","mql_type":"bool","default":"true","status_key":"runtime_enable_virtual_sl_reentry","label":"Enable Virtual SL Reentry","kind":"bool"},{"name":"reentry_respects_new_bar_gate","mql_type":"bool","default":"false","status_key":"runtime_reentry_respects_new_bar_gate","label":"Reentry Respects New Bar Gate","kind":"bool"},{"name":"reentry_min_signal_pct","mql_type":"double","default":"0.75","status_key":"runtime_reentry_min_signal_pct","label":"Reentry Min Signal %","kind":"number","min":0,"max":2,"step":0.01},{"name":"enable_profit_offset_sl","mql_type":"bool","default":"true","status_key":"runtime_enable_profit_offset_sl","label":"Enable Profit Offset SL","kind":"bool"},{"name":"consecutive_wins_required","mql_type":"int","default":"3","status_key":"runtime_consecutive_wins_required","label":"Consecutive Wins Required","kind":"number","min":0,"max":100,"step":1},{"name":"min_offset_profit","mql_type":"double","default":"1.0","status_key":"runtime_min_offset_profit","label":"Min Offset Profit","kind":"number","min":0,"max":1000000,"step":0.1}],"description":"Controls position health scoring, partial closes, break-even behavior, SL tightening and virtual-SL re-entry.","danger":true},{"name":"Hedge chain","controls":[{"name":"enable_hedge_chain","mql_type":"bool","default":"true","status_key":"runtime_enable_hedge_chain","label":"Enable Hedge Chain","kind":"bool"},{"name":"hedge_trigger_atr","mql_type":"double","default":"1.5","status_key":"runtime_hedge_trigger_atr","label":"Hedge Trigger ATR","kind":"number","min":0,"max":100,"step":0.1},{"name":"hedge_require_signal","mql_type":"bool","default":"true","status_key":"runtime_hedge_require_signal","label":"Hedge Require Signal","kind":"bool"},{"name":"hedge_min_signal_score","mql_type":"double","default":"4.5","status_key":"runtime_hedge_min_signal_score","label":"Hedge Min Signal Score","kind":"number","min":0,"max":10,"step":0.1},{"name":"hedge_auto_lot","mql_type":"bool","default":"true","status_key":"runtime_hedge_auto_lot","label":"Hedge Auto Lot","kind":"bool"},{"name":"hedge_recovery_atr","mql_type":"double","default":"1.0","status_key":"runtime_hedge_recovery_atr","label":"Hedge Recovery ATR","kind":"number","min":0,"max":100,"step":0.1},{"name":"hedge_lot_multiplier","mql_type":"double","default":"2.0","status_key":"runtime_hedge_lot_multiplier","label":"Hedge Lot Multiplier","kind":"number","min":0,"max":20,"step":0.1},{"name":"hedge_max_lot","mql_type":"double","default":"0.10","status_key":"runtime_hedge_max_lot","label":"Hedge Max Lot","kind":"number","min":0.01,"max":5,"step":0.01},{"name":"hedge_recovery_pct","mql_type":"double","default":"110.0","status_key":"runtime_hedge_recovery_pct","label":"Hedge Recovery %","kind":"number","min":0,"max":1000,"step":1},{"name":"hedge_roll_min_profit","mql_type":"double","default":"0.5","status_key":"runtime_hedge_roll_min_profit","label":"Hedge Roll Min Profit","kind":"number","min":0,"max":1000000,"step":0.1},{"name":"hedge_cycle_levels","mql_type":"int","default":"2","status_key":"runtime_hedge_cycle_levels","label":"Hedge Cycle Levels","kind":"number","min":1,"max":20,"step":1},{"name":"enable_hedge_cycle_reset","mql_type":"bool","default":"false","status_key":"runtime_enable_hedge_cycle_reset","label":"Enable Hedge Cycle Reset","kind":"bool"},{"name":"hedge_cycle_partial_pct","mql_type":"double","default":"50.0","status_key":"runtime_hedge_cycle_partial_pct","label":"Hedge Cycle Partial %","kind":"number","min":0,"max":100,"step":1},{"name":"hedge_max_cycles","mql_type":"int","default":"3","status_key":"runtime_hedge_max_cycles","label":"Hedge Max Cycles","kind":"number","min":0,"max":100,"step":1},{"name":"hedge_max_chain_loss_usd","mql_type":"double","default":"0.0","status_key":"runtime_hedge_max_chain_loss_usd","label":"Hedge Max Chain Loss USD","kind":"number","min":0,"max":100000000,"step":1},{"name":"hedge_max_chain_loss_pct","mql_type":"double","default":"0.0","status_key":"runtime_hedge_max_chain_loss_pct","label":"Hedge Max Chain Loss %","kind":"number","min":0,"max":100,"step":0.1},{"name":"hedge_clear_root_sl","mql_type":"bool","default":"true","status_key":"runtime_hedge_clear_root_sl","label":"Hedge Clear Root SL","kind":"bool"},{"name":"hedge_trail_atr","mql_type":"double","default":"0.5","status_key":"runtime_hedge_trail_atr","label":"Hedge Trail ATR","kind":"number","min":0,"max":100,"step":0.1}],"description":"High-risk recovery subsystem. Changes can affect existing recovery chains and exposure.","danger":true},{"name":"Dynamic sizing","controls":[{"name":"enable_dynamic_lots","mql_type":"bool","default":"true","status_key":"runtime_enable_dynamic_lots","label":"Enable Dynamic Lots","kind":"bool"},{"name":"equity_drop_percent","mql_type":"double","default":"5.0","status_key":"runtime_equity_drop_percent","label":"Equity Drop Percent","kind":"number","min":0,"max":100,"step":0.1},{"name":"max_equity_drop_lot_steps","mql_type":"int","default":"2","status_key":"runtime_max_equity_drop_lot_steps","label":"Max Equity Drop Lot Steps","kind":"number","min":0,"max":100,"step":1},{"name":"min_signal_strength_for_lot","mql_type":"double","default":"8.0","status_key":"runtime_min_signal_strength_for_lot","label":"Min Signal Strength For Lot","kind":"number","min":0,"max":10,"step":0.1},{"name":"lot_step_size","mql_type":"double","default":"0.01","status_key":"runtime_lot_step_size","label":"Lot Step Size","kind":"number","min":0,"max":5,"step":0.01},{"name":"max_lot_size","mql_type":"double","default":"0.05","status_key":"runtime_max_lot_size","label":"Max Lot Size","kind":"number","min":0.01,"max":5,"step":0.01}],"description":"Controls drawdown/signal-based lot increases. Changes can alter future position size.","danger":true},{"name":"Equity protection","controls":[{"name":"enable_basket_stop","mql_type":"bool","default":"true","status_key":"runtime_enable_basket_stop","label":"Enable Basket Stop","kind":"bool"},{"name":"max_basket_loss_pct","mql_type":"double","default":"8.0","status_key":"runtime_max_basket_loss_pct","label":"Max Basket Loss %","kind":"number","min":0,"max":100,"step":0.1},{"name":"min_equity_percent","mql_type":"double","default":"70.0","status_key":"runtime_min_equity_percent","label":"Min Equity Percent","kind":"number","min":0,"max":1000,"step":0.1},{"name":"max_drawdown_from_peak","mql_type":"double","default":"0","status_key":"runtime_max_drawdown_from_peak","label":"Max Drawdown From Peak","kind":"number","min":0,"max":100000000,"step":1},{"name":"pause_minutes","mql_type":"int","default":"5","status_key":"runtime_pause_minutes","label":"Pause Minutes","kind":"number","min":0,"max":1440,"step":1},{"name":"pause_minutes_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_pause_minutes_multiplier","label":"Pause Minutes Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"max_pause_minutes","mql_type":"int","default":"120","status_key":"runtime_max_pause_minutes","label":"Max Pause Minutes","kind":"number","min":0,"max":10080,"step":1},{"name":"max_min_equity_triggers","mql_type":"int","default":"0","status_key":"runtime_max_min_equity_triggers","label":"Max Min Equity Triggers","kind":"number","min":0,"max":1000,"step":1},{"name":"reset_on_new_peak","mql_type":"bool","default":"true","status_key":"runtime_reset_on_new_peak","label":"Reset On New Peak","kind":"bool"},{"name":"target_equity","mql_type":"double","default":"0","status_key":"runtime_target_equity","label":"Target Equity","kind":"number","min":0,"max":1000000000,"step":1},{"name":"minimum_equity","mql_type":"double","default":"20","status_key":"runtime_minimum_equity","label":"Minimum Equity","kind":"number","min":0,"max":1000000000,"step":1}],"description":"Account-level circuit breakers, basket loss limits, trading pauses and equity targets.","danger":true},{"name":"TP / SL / risk reward","controls":[{"name":"enable_take_profit","mql_type":"bool","default":"false","status_key":"runtime_enable_take_profit","label":"Enable Take Profit","kind":"bool"},{"name":"tp_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_DOLLAR","status_key":"runtime_tp_input_type","label":"TP Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"tp_value","mql_type":"double","default":"10.0","status_key":"runtime_tp_value","label":"TP Value","kind":"number","min":0,"max":100000000,"step":0.1},{"name":"enable_stop_loss","mql_type":"bool","default":"true","status_key":"runtime_enable_stop_loss","label":"Enable Stop Loss","kind":"bool"},{"name":"sl_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_PERCENT","status_key":"runtime_sl_input_type","label":"SL Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"sl_value","mql_type":"double","default":"10.0","status_key":"runtime_sl_value","label":"SL Value","kind":"number","min":0,"max":100000000,"step":0.1},{"name":"enable_risk_reward","mql_type":"bool","default":"false","status_key":"runtime_enable_risk_reward","label":"Enable Risk Reward","kind":"bool"},{"name":"rr_risk_mode","mql_type":"ENUM_RR_RISK_MODE","default":"RR_RISK_ATR","status_key":"runtime_rr_risk_mode","label":"R:R Risk Mode","kind":"select","options":[{"value":0,"label":"Manual"},{"value":1,"label":"ATR"}]},{"name":"rr_risk_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_POINTS","status_key":"runtime_rr_risk_input_type","label":"R:R Risk Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"rr_risk_value","mql_type":"double","default":"200.0","status_key":"runtime_rr_risk_value","label":"R:R Risk Value","kind":"number","min":0,"max":100000000,"step":0.1},{"name":"rr_atr_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_rr_atr_multiplier","label":"R:R ATR Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"risk_reward_ratio","mql_type":"double","default":"1.5","status_key":"runtime_risk_reward_ratio","label":"Risk Reward Ratio","kind":"number","min":0,"max":100,"step":0.1}],"description":"Controls initial take-profit, stop-loss and independent risk:reward placement.","danger":true},{"name":"Trailing","controls":[{"name":"enable_trailing","mql_type":"bool","default":"true","status_key":"runtime_enable_trailing","label":"Enable Trailing","kind":"bool"},{"name":"trailing_enable_break_even_lock","mql_type":"bool","default":"true","status_key":"runtime_trailing_enable_break_even_lock","label":"Trailing Enable Break Even Lock","kind":"bool"},{"name":"trailing_sl_on_profitable_only","mql_type":"bool","default":"true","status_key":"runtime_trailing_sl_on_profitable_only","label":"Trailing SL On Profitable Only","kind":"bool"},{"name":"enable_adaptive_tp","mql_type":"bool","default":"true","status_key":"runtime_enable_adaptive_tp","label":"Enable Adaptive TP","kind":"bool"},{"name":"enable_adaptive_sl","mql_type":"bool","default":"true","status_key":"runtime_enable_adaptive_sl","label":"Enable Adaptive SL","kind":"bool"},{"name":"ts_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_DOLLAR","status_key":"runtime_ts_input_type","label":"Ts Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"trailing_distance_value","mql_type":"double","default":"0.2","status_key":"runtime_trailing_distance_value","label":"Trailing Distance Value","kind":"number","min":0,"max":100000000,"step":0.01},{"name":"trailing_value_multiplier","mql_type":"double","default":"0.2","status_key":"runtime_trailing_value_multiplier","label":"Trailing Value Multiplier","kind":"number","min":0,"max":100,"step":0.01}],"description":"Controls trailing, break-even locks and adaptive exit behavior.","danger":true},{"name":"Operational filters / diagnostics","controls":[{"name":"enable_discord_alerts","mql_type":"bool","default":"false","status_key":"runtime_enable_discord_alerts","label":"Enable Discord Alerts","kind":"bool"},{"name":"enable_trading_hours","mql_type":"bool","default":"false","status_key":"runtime_enable_trading_hours","label":"Enable Trading Hours","kind":"bool"},{"name":"trading_start_time","mql_type":"string","default":"\"00:00\"","status_key":"runtime_trading_start_time","label":"Trading Start Time","kind":"time"},{"name":"trading_end_time","mql_type":"string","default":"\"23:59\"","status_key":"runtime_trading_end_time","label":"Trading End Time","kind":"time"},{"name":"enable_reports","mql_type":"bool","default":"true","status_key":"runtime_enable_reports","label":"Enable Reports","kind":"bool"},{"name":"send_report_every_hour","mql_type":"int","default":"1","status_key":"runtime_send_report_every_hour","label":"Send Report Every Hour","kind":"number","min":1,"max":168,"step":1},{"name":"enable_market_close_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_market_close_filter","label":"Enable Market Close Filter","kind":"bool"},{"name":"minutes_before_close","mql_type":"int","default":"30","status_key":"runtime_minutes_before_close","label":"Minutes Before Close","kind":"number","min":0,"max":1440,"step":1},{"name":"enable_news_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_news_filter","label":"Enable News Filter","kind":"bool"},{"name":"news_minutes_before","mql_type":"int","default":"30","status_key":"runtime_news_minutes_before","label":"News Minutes Before","kind":"number","min":0,"max":1440,"step":1},{"name":"news_minutes_after","mql_type":"int","default":"30","status_key":"runtime_news_minutes_after","label":"News Minutes After","kind":"number","min":0,"max":1440,"step":1},{"name":"enable_leverage_pause","mql_type":"bool","default":"true","status_key":"runtime_enable_leverage_pause","label":"Enable Leverage Pause","kind":"bool"},{"name":"enable_logging","mql_type":"bool","default":"false","status_key":"runtime_enable_logging","label":"Enable Logging","kind":"bool"}],"description":"Trading hours, market-close/news/leverage filters plus reports, alerts and logging.","danger":false}]'''
)


def _model_dump(model: Any, *, exclude_none: bool = False, exclude_unset: bool = False) -> dict:
    return model.model_dump(
        mode="json",
        exclude_none=exclude_none,
        exclude_unset=exclude_unset,
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to Atlas"}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "running",
        "version": "0.5.0",
        "strategy": "nyao",
        "environment": "demo",
    }


@app.get("/api/v1/nyao/command")
def get_nyao_command() -> dict:
    command_data = read_json(COMMANDS_FILE)

    if not command_data:
        command = Command()
        write_json(command, COMMANDS_FILE)
        return _model_dump(command, exclude_none=True)

    command = Command.model_validate(command_data)
    return _model_dump(command, exclude_none=True)


@app.put("/api/v1/nyao/command")
def update_nyao_command(command: Command) -> dict:
    """
    Merge only fields explicitly supplied by the caller into the current
    command, then increment command_version.

    This prevents a narrow dashboard edit from resetting the other 150+
    Nyao runtime settings.
    """
    existing_data = read_json(COMMANDS_FILE) or {}
    existing = _model_dump(
        Command.model_validate(existing_data),
        exclude_none=True,
    )

    incoming = _model_dump(
        command,
        exclude_none=True,
        exclude_unset=True,
    )

    # Atlas owns these two fields.
    incoming.pop("command_version", None)
    incoming.pop("updated_at", None)

    merged = {**existing, **incoming}
    previous_version = int(existing.get("command_version", 0))

    merged["command_version"] = previous_version + 1
    merged["updated_at"] = datetime.now(timezone.utc)

    try:
        validated = Command.model_validate(merged)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    write_json(validated, COMMANDS_FILE)
    return _model_dump(validated, exclude_none=True)


@app.get("/api/v1/nyao/status")
def get_nyao_status() -> dict:
    status_data = read_json(STATUS_FILE)

    if not status_data:
        return _model_dump(Status(connected=False))

    return _model_dump(Status.model_validate(status_data))


@app.post("/api/v1/nyao/status")
def receive_nyao_status(status: Status) -> dict[str, object]:
    write_json(status, STATUS_FILE)

    return {
        "accepted": True,
        "timestamp": status.timestamp,
    }


@app.get("/api/v1/atlas/intelligence")
def get_atlas_intelligence() -> dict:
    status_data = read_json(STATUS_FILE)

    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)

    history_result = record_intelligence_snapshot(
        status_payload,
        intelligence,
    )

    intelligence["history"] = history_result
    return intelligence


@app.get("/api/v1/atlas/history")
def get_atlas_history(
    limit: int = 200,
    regime: str | None = None,
    risk_state: str | None = None,
) -> dict:
    return get_history(
        limit=limit,
        regime=regime,
        risk_state=risk_state,
    )


@app.get("/api/v1/atlas/history/summary")
def get_atlas_history_summary() -> dict:
    return get_history_summary()


@app.post("/api/v1/atlas/history/snapshot")
def force_atlas_history_snapshot() -> dict:
    status_data = read_json(STATUS_FILE)

    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)

    result = record_intelligence_snapshot(
        status_payload,
        intelligence,
        force=True,
    )

    return {
        "accepted": True,
        "history": result,
        "intelligence": intelligence,
    }


@app.get("/api/v1/nyao/control-schema")
def get_nyao_control_schema() -> list[dict]:
    return RUNTIME_CONTROL_GROUPS


DASHBOARD_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Atlas Control Center</title>

    <style>
        :root {
            color-scheme: dark;
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            --bg: #06080d;
            --panel: rgba(20, 27, 43, 0.92);
            --panel-2: rgba(13, 19, 31, 0.95);
            --panel-3: rgba(255,255,255,0.035);
            --border: rgba(255,255,255,0.08);
            --text: #f5f7fb;
            --muted: #8f9bb0;
            --green: #4dd889;
            --red: #ff6b73;
            --blue: #6aa7ff;
            --amber: #f1c66d;
            --purple: #b995ff;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            min-height: 100vh;
            background:
                radial-gradient(circle at top, #172033 0%, #0a0e17 44%, #06080d 100%);
            color: var(--text);
        }

        button, input, select { font: inherit; }

        .container {
            width: min(1480px, calc(100% - 28px));
            margin: 0 auto;
            padding: 28px 0 60px;
        }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            margin-bottom: 20px;
        }

        .brand h1 {
            margin: 0;
            font-size: 31px;
            letter-spacing: 0.09em;
        }

        .brand p {
            margin: 7px 0 0;
            color: var(--muted);
        }

        .header-right {
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 10px;
        }

        .pill {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 9px 13px;
            border: 1px solid var(--border);
            background: rgba(255,255,255,0.05);
            border-radius: 999px;
            color: #ccd5e3;
            font-size: 12px;
        }

        .dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: var(--red);
        }

        .dot.connected { background: var(--green); }

        .sync-ok { color: var(--green); font-weight: 700; }
        .sync-waiting { color: var(--amber); font-weight: 700; }

        .top-grid {
            display: grid;
            grid-template-columns: repeat(5, minmax(0,1fr));
            gap: 13px;
        }

        .card {
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 17px;
            padding: 18px;
        }

        .card-label {
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: .08em;
        }

        .card-value {
            margin-top: 8px;
            font-size: 26px;
            font-weight: 750;
        }

        .positive { color: var(--green); }
        .negative { color: var(--red); }
        .warning { color: var(--amber); }

        .section { margin-top: 15px; }

        .section-heading {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 15px;
            margin-bottom: 14px;
        }

        .section-title {
            margin: 0;
            font-size: 17px;
        }

        .section-note {
            color: var(--muted);
            font-size: 12px;
            margin-top: 5px;
            max-width: 850px;
            line-height: 1.45;
        }

        .score-grid, .decision-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 13px;
        }

        .score {
            font-size: 37px;
            font-weight: 780;
            margin: 7px 0 7px;
        }

        .score-meta {
            font-size: 12px;
            color: var(--muted);
            margin-bottom: 12px;
        }

        .bar {
            height: 9px;
            border-radius: 999px;
            background: rgba(255,255,255,.07);
            overflow: hidden;
        }

        .bar-fill {
            width: 0;
            height: 100%;
            border-radius: inherit;
            transition: width .25s ease;
        }

        .buy-fill { background: linear-gradient(90deg,#278f63,#55e89a); }
        .sell-fill { background: linear-gradient(90deg,#b33f52,#ff6d78); }

        .decision-card {
            background: var(--panel-2);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px;
        }

        .decision-card.buy { border-top: 2px solid rgba(77,216,137,.8); }
        .decision-card.sell { border-top: 2px solid rgba(255,107,115,.8); }

        .decision-top {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
        }

        .decision-side {
            font-size: 18px;
            font-weight: 800;
            letter-spacing: .07em;
        }

        .badge {
            border-radius: 999px;
            padding: 6px 9px;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: .06em;
            text-transform: uppercase;
            background: rgba(255,255,255,.07);
        }

        .badge.ready { color: #a1f4c0; background: rgba(77,216,137,.13); }
        .badge.blocked { color: #f5d78c; background: rgba(241,198,109,.12); }
        .badge.danger { color: #ffc0c4; background: rgba(255,107,115,.12); }

        .decision-stats {
            display: grid;
            grid-template-columns: repeat(3,minmax(0,1fr));
            gap: 9px;
            margin-top: 14px;
        }

        .mini {
            border: 1px solid rgba(255,255,255,.055);
            background: var(--panel-3);
            border-radius: 11px;
            padding: 11px;
        }

        .mini .label {
            color: var(--muted);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: .06em;
        }

        .mini .value {
            margin-top: 6px;
            font-size: 17px;
            font-weight: 750;
        }

        .reason {
            margin-top: 11px;
            border: 1px solid rgba(255,255,255,.055);
            background: var(--panel-3);
            border-radius: 11px;
            padding: 11px;
        }

        .reason code {
            display: block;
            margin-top: 6px;
            color: #dce4f0;
            overflow-wrap: anywhere;
            font-size: 12px;
        }

        .gates {
            display: grid;
            grid-template-columns: repeat(4,minmax(0,1fr));
            gap: 10px;
            margin-top: 11px;
        }

        .master-grid {
            display: grid;
            grid-template-columns: repeat(4,minmax(0,1fr));
            gap: 11px;
        }

        .master-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            border: 1px solid rgba(255,255,255,.055);
            background: var(--panel-3);
            border-radius: 12px;
            padding: 12px;
        }

        button {
            border: 0;
            border-radius: 10px;
            padding: 9px 13px;
            cursor: pointer;
            font-weight: 700;
            transition: transform .13s ease, opacity .13s ease;
        }

        button:hover { transform: translateY(-1px); }
        button:disabled { opacity:.45; cursor:not-allowed; transform:none; }

        .enabled-button { background:#245f44; color:#baffd4; }
        .disabled-button { background:#642d38; color:#ffd1d5; }
        .neutral-button { background:#27354f; color:#dce8ff; }
        .primary-button { background:#315f9d; color:white; }
        .danger-button { background:#71323e; color:#ffd7da; }

        .control-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 12px;
        }

        .search {
            min-width: min(420px,100%);
            flex: 1;
            max-width: 520px;
            border: 1px solid rgba(255,255,255,.12);
            background: rgba(255,255,255,.045);
            color: white;
            border-radius: 10px;
            padding: 10px 12px;
            outline: none;
        }

        .search:focus {
            border-color: rgba(106,167,255,.7);
            box-shadow: 0 0 0 3px rgba(106,167,255,.08);
        }

        .dirty {
            color: var(--amber);
            font-size: 12px;
        }

        .clean {
            color: var(--muted);
            font-size: 12px;
        }

        .groups {
            display: grid;
            gap: 11px;
        }

        details.group {
            border: 1px solid var(--border);
            border-radius: 14px;
            background: var(--panel-2);
            overflow: hidden;
        }

        details.group[open] {
            border-color: rgba(106,167,255,.18);
        }

        details.group > summary {
            list-style: none;
            cursor: pointer;
            padding: 14px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            user-select: none;
        }

        details.group > summary::-webkit-details-marker { display:none; }

        .group-title {
            display: flex;
            align-items: center;
            gap: 9px;
            font-weight: 750;
        }

        .count {
            padding: 3px 7px;
            border-radius: 999px;
            background: rgba(255,255,255,.06);
            color: var(--muted);
            font-size: 10px;
        }

        .group-description {
            padding: 0 16px 13px;
            color: var(--muted);
            font-size: 12px;
            line-height: 1.45;
        }

        .control-grid {
            display: grid;
            grid-template-columns: repeat(3,minmax(0,1fr));
            gap: 10px;
            padding: 0 13px 14px;
        }

        .runtime-control {
            border: 1px solid rgba(255,255,255,.055);
            background: rgba(255,255,255,.028);
            border-radius: 11px;
            padding: 11px;
            min-width: 0;
        }

        .runtime-control.changed {
            border-color: rgba(241,198,109,.45);
            background: rgba(241,198,109,.045);
        }

        .control-head {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 9px;
            margin-bottom: 9px;
        }

        .control-label {
            font-size: 12px;
            color: #d4dce8;
            line-height: 1.35;
        }

        .applied {
            font-size: 10px;
            color: var(--muted);
            white-space: nowrap;
        }

        .runtime-control input[type="number"],
        .runtime-control input[type="text"],
        .runtime-control input[type="time"],
        .runtime-control select {
            width: 100%;
            border: 1px solid rgba(255,255,255,.11);
            background: rgba(255,255,255,.045);
            color: white;
            border-radius: 8px;
            padding: 8px 9px;
            outline: none;
        }

        .runtime-control input:focus,
        .runtime-control select:focus {
            border-color: rgba(106,167,255,.7);
        }

        .switch {
            position: relative;
            display: inline-block;
            width: 46px;
            height: 26px;
        }

        .switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .slider {
            position:absolute;
            inset:0;
            border-radius:999px;
            background:#5f2f39;
            cursor:pointer;
            transition:.2s;
        }

        .slider:before {
            content:"";
            position:absolute;
            width:20px;
            height:20px;
            left:3px;
            top:3px;
            border-radius:50%;
            background:#fff;
            transition:.2s;
        }

        .switch input:checked + .slider { background:#2c7c56; }
        .switch input:checked + .slider:before { transform:translateX(20px); }

        .control-actions {
            position: sticky;
            bottom: 12px;
            z-index: 8;
            margin-top: 13px;
            padding: 11px 12px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
            flex-wrap:wrap;
            border:1px solid rgba(255,255,255,.1);
            border-radius:13px;
            background:rgba(10,14,23,.94);
            backdrop-filter: blur(12px);
        }

        .action-buttons {
            display:flex;
            gap:9px;
            flex-wrap:wrap;
        }

        .order-grid {
            display:grid;
            grid-template-columns:repeat(7,minmax(0,1fr));
            gap:9px;
        }

        .intelligence-hero {
            display: grid;
            grid-template-columns: 1.15fr .85fr;
            gap: 12px;
        }

        .intelligence-summary {
            border: 1px solid rgba(185,149,255,.22);
            background: linear-gradient(145deg, rgba(185,149,255,.08), rgba(106,167,255,.035));
            border-radius: 15px;
            padding: 16px;
        }

        .intelligence-side {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }

        .intel-list {
            margin: 11px 0 0;
            padding-left: 18px;
            color: #d4dce8;
            font-size: 12px;
            line-height: 1.55;
        }

        .intel-list li + li {
            margin-top: 5px;
        }

        .proposal-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0,1fr));
            gap: 8px;
            margin-top: 11px;
        }

        .proposal-item {
            border: 1px solid rgba(255,255,255,.06);
            background: rgba(255,255,255,.025);
            border-radius: 10px;
            padding: 10px;
        }

        .proposal-item .key {
            color: var(--muted);
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: .06em;
        }

        .proposal-item .val {
            margin-top: 5px;
            font-size: 14px;
            font-weight: 750;
        }

        .observability-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
        }

        .observability-card {
            border: 1px solid rgba(255,255,255,.055);
            background: var(--panel-2);
            border-radius: 13px;
            padding: 13px;
            min-width: 0;
        }

        .observability-card .label {
            color: var(--muted);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: .07em;
        }

        .observability-card .value {
            margin-top: 7px;
            font-size: 18px;
            font-weight: 750;
            overflow-wrap: anywhere;
        }

        .signal-anatomy-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        .signal-anatomy {
            border: 1px solid rgba(255,255,255,.06);
            background: var(--panel-2);
            border-radius: 14px;
            padding: 14px;
        }

        .signal-component-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0,1fr));
            gap: 8px;
            margin-top: 11px;
        }

        .signal-reasoning {
            margin-top: 10px;
            padding: 10px;
            border: 1px solid rgba(255,255,255,.055);
            border-radius: 10px;
            background: rgba(255,255,255,.025);
            color: #cbd5e4;
            font-size: 11px;
            line-height: 1.45;
            overflow-wrap: anywhere;
        }

        .positions-wrapper {
            overflow-x: auto;
        }

        .positions-table {
            width: 100%;
            border-collapse: collapse;
            min-width: 1280px;
            font-size: 11px;
        }

        .positions-table th,
        .positions-table td {
            padding: 9px 10px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,.055);
            white-space: nowrap;
        }

        .positions-table th {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: .06em;
            font-size: 9px;
        }

        .positions-table tr:last-child td {
            border-bottom: 0;
        }

        .risk-meter {
            height: 8px;
            margin-top: 8px;
            background: rgba(255,255,255,.07);
            border-radius: 999px;
            overflow: hidden;
        }

        .risk-meter-fill {
            height: 100%;
            width: 0;
            border-radius: inherit;
            background: linear-gradient(90deg, var(--green), var(--amber), var(--red));
            transition: width .25s ease;
        }

        .verification-wrapper {
            overflow-x: auto;
        }

        .verification-table {
            width: 100%;
            min-width: 760px;
            border-collapse: collapse;
            font-size: 12px;
        }

        .verification-table th,
        .verification-table td {
            padding: 10px 11px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,.06);
        }

        .verification-table th {
            color: var(--muted);
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: .07em;
        }

        .verification-table tr:last-child td {
            border-bottom: 0;
        }

        .match {
            color: var(--green);
            font-weight: 700;
        }

        .mismatch {
            color: var(--amber);
            font-weight: 700;
        }

        .inherited {
            color: var(--blue);
            font-weight: 700;
        }

        .footer {
            margin-top: 17px;
            color:#758196;
            text-align:right;
            font-size:12px;
        }

        .hidden { display:none !important; }

        @media(max-width:1150px) {
            .top-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
            .control-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .order-grid { grid-template-columns:repeat(4,minmax(0,1fr)); }
            .observability-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
        }

        @media(max-width:800px) {
            .header { flex-direction:column; align-items:flex-start; }
            .header-right { justify-content:flex-start; }
            .top-grid,.score-grid,.decision-grid,.master-grid,.control-grid,.order-grid,.gates,
            .observability-grid,.signal-anatomy-grid,.signal-component-grid,
            .intelligence-hero,.intelligence-side,.proposal-grid {
                grid-template-columns:1fr;
            }
            .decision-stats { grid-template-columns:1fr; }
        }
    </style>
</head>

<body>
<div class="container">
    <div class="header">
        <div class="brand">
            <h1>ATLAS</h1>
            <p>Adaptive Trading Learning and Analysis System · Nyao Strategy Control Center</p>
        </div>

        <div class="header-right">
            <div class="pill">
                <span id="connection-dot" class="dot"></span>
                <span id="connection-text">Connecting...</span>
            </div>
            <div class="pill">
                <span>Command</span>
                <strong id="command-version">—</strong>
                <span>→ Applied</span>
                <strong id="applied-version">—</strong>
                <span id="sync-state" class="sync-waiting">Waiting</span>
            </div>
            <div class="pill">
                <span>Runtime</span>
                <strong id="runtime-sync-count">—</strong>
                <span id="runtime-sync-state" class="sync-waiting">Checking</span>
            </div>
            <div class="pill">
                <span>Structural</span>
                <strong id="structural-state">—</strong>
            </div>
        </div>
    </div>

    <div class="top-grid">
        <div class="card">
            <div class="card-label">Balance</div>
            <div id="balance" class="card-value">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Equity</div>
            <div id="equity" class="card-value">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Floating P/L</div>
            <div id="profit" class="card-value">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Realized P/L Baseline</div>
            <div id="realized-profit" class="card-value">$0.00</div>
        </div>
        <div class="card">
            <div class="card-label">Open Positions</div>
            <div id="positions" class="card-value">0</div>
        </div>
    </div>

    <div class="section score-grid">
        <div class="card">
            <div class="card-label">Live Buy Score</div>
            <div id="buy-score" class="score">0.00</div>
            <div class="score-meta">Effective threshold: <strong id="buy-threshold">0.00</strong></div>
            <div class="bar"><div id="buy-bar" class="bar-fill buy-fill"></div></div>
        </div>
        <div class="card">
            <div class="card-label">Live Sell Score</div>
            <div id="sell-score" class="score">0.00</div>
            <div class="score-meta">Effective threshold: <strong id="sell-threshold">0.00</strong></div>
            <div class="bar"><div id="sell-bar" class="bar-fill sell-fill"></div></div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Decision Engine</h2>
                <div class="section-note">
                    Live score is continuously updated. Evaluated score reflects the most recent actual entry evaluation.
                </div>
            </div>
        </div>

        <div class="decision-grid">
            <div class="decision-card buy">
                <div class="decision-top">
                    <div class="decision-side">BUY</div>
                    <span id="buy-state" class="badge blocked">Blocked</span>
                </div>
                <div class="decision-stats">
                    <div class="mini"><div class="label">Live</div><div id="buy-live" class="value">0.00</div></div>
                    <div class="mini"><div class="label">Evaluated</div><div id="buy-adjusted" class="value">0.00</div></div>
                    <div class="mini"><div class="label">Threshold</div><div id="buy-effective" class="value">0.00</div></div>
                </div>
                <div class="reason">
                    <div class="card-label">Current decision state</div>
                    <code id="buy-reason">NOT_EVALUATED</code>
                </div>
            </div>

            <div class="decision-card sell">
                <div class="decision-top">
                    <div class="decision-side">SELL</div>
                    <span id="sell-state" class="badge blocked">Blocked</span>
                </div>
                <div class="decision-stats">
                    <div class="mini"><div class="label">Live</div><div id="sell-live" class="value">0.00</div></div>
                    <div class="mini"><div class="label">Evaluated</div><div id="sell-adjusted" class="value">0.00</div></div>
                    <div class="mini"><div class="label">Threshold</div><div id="sell-effective" class="value">0.00</div></div>
                </div>
                <div class="reason">
                    <div class="card-label">Current decision state</div>
                    <code id="sell-reason">NOT_EVALUATED</code>
                </div>
            </div>
        </div>

        <div class="gates">
            <div class="mini"><div class="label">New-bar mode</div><div id="new-bar-mode" class="value">—</div></div>
            <div class="mini"><div class="label">New bar ready</div><div id="new-bar-ready" class="value">—</div></div>
            <div class="mini"><div class="label">Cooldown</div><div id="cooldown" class="value">—</div></div>
            <div class="mini"><div class="label">Global block</div><div id="global-block" class="value">—</div></div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Atlas Intelligence</h2>
                <div class="section-note">
                    Deterministic v0.1 intelligence using Nyao telemetry only. Advisory mode: Atlas does not auto-write these recommendations to Nyao.
                </div>
            </div>
            <span id="intel-mode" class="badge ready">ADVISORY</span>
        </div>

        <div class="intelligence-hero">
            <div class="intelligence-summary">
                <div class="card-label">Assessment</div>
                <div id="intel-summary" class="card-value" style="font-size:20px;">Waiting for intelligence...</div>

                <div class="observability-grid" style="margin-top:14px;">
                    <div class="observability-card">
                        <div class="label">Market Regime</div>
                        <div id="intel-regime" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Direction</div>
                        <div id="intel-direction" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Volatility</div>
                        <div id="intel-volatility" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Nyao Fit</div>
                        <div id="intel-fit" class="value">—</div>
                    </div>
                </div>

                <div class="subsection-title">History Recorder</div>
                <div class="observability-grid">
                    <div class="observability-card">
                        <div class="label">Stored Snapshots</div>
                        <div id="history-count" class="value">0</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Latest Save Reason</div>
                        <div id="history-reason" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Heartbeat</div>
                        <div id="history-heartbeat" class="value">60s</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Storage</div>
                        <div class="value">JSON</div>
                    </div>
                </div>

                <div class="subsection-title">Recommendations</div>
                <ul id="intel-recommendations" class="intel-list">
                    <li>Waiting for Nyao telemetry.</li>
                </ul>

                <div class="subsection-title">Proposed runtime changes</div>
                <div id="intel-proposals" class="proposal-grid">
                    <div class="proposal-item"><div class="key">State</div><div class="val">Observation only</div></div>
                </div>
            </div>

            <div>
                <div class="intelligence-side">
                    <div class="observability-card">
                        <div class="label">Confidence</div>
                        <div id="intel-confidence" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Risk State</div>
                        <div id="intel-risk-state" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Risk Score</div>
                        <div id="intel-risk-score" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Exposure Bias</div>
                        <div id="intel-exposure-bias" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Risk Governor</div>
                        <div id="intel-veto" class="value">—</div>
                    </div>
                    <div class="observability-card">
                        <div class="label">Execution Environment</div>
                        <div id="intel-execution" class="value">—</div>
                    </div>
                </div>

                <div class="subsection-title">Cautions</div>
                <ul id="intel-cautions" class="intel-list">
                    <li>None reported.</li>
                </ul>

                <div class="subsection-title">Why Atlas classified this regime</div>
                <ul id="intel-reasons" class="intel-list">
                    <li>Waiting for telemetry.</li>
                </ul>
            </div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Exposure & Risk</h2>
                <div class="section-note">Strategy-owned exposure, account drawdown and basket-risk state reported directly by Nyao.</div>
            </div>
        </div>
        <div class="observability-grid">
            <div class="observability-card"><div class="label">Strategy Positions</div><div id="obs-strategy-positions" class="value">0</div></div>
            <div class="observability-card"><div class="label">Total Lots</div><div id="obs-total-lots" class="value">0.00</div></div>
            <div class="observability-card"><div class="label">Strategy Floating P/L</div><div id="obs-strategy-pl" class="value">$0.00</div></div>
            <div class="observability-card"><div class="label">Gross Notional Exposure</div><div id="obs-notional" class="value">$0.00</div></div>
            <div class="observability-card"><div class="label">BUY / SELL Positions</div><div id="obs-side-counts" class="value">0 / 0</div></div>
            <div class="observability-card"><div class="label">BUY / SELL Lots</div><div id="obs-side-lots" class="value">0.00 / 0.00</div></div>
            <div class="observability-card"><div class="label">Winning / Losing</div><div id="obs-win-loss-count" class="value">0 / 0</div></div>
            <div class="observability-card"><div class="label">Working Limit Orders</div><div id="obs-working-limits" class="value">0</div></div>
            <div class="observability-card"><div class="label">Equity Drawdown</div><div id="obs-drawdown" class="value">0.00%</div></div>
            <div class="observability-card"><div class="label">Basket Loss</div><div id="obs-basket-loss" class="value">0.00%</div><div class="risk-meter"><div id="obs-basket-meter" class="risk-meter-fill"></div></div></div>
            <div class="observability-card"><div class="label">Margin / Free Margin</div><div id="obs-margin" class="value">$0 / $0</div></div>
            <div class="observability-card"><div class="label">Margin Level / Leverage</div><div id="obs-margin-level" class="value">—</div></div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Hedge & Recovery State</h2>
                <div class="section-note">Live recovery-chain state, including actual chain exposure and active hedge depth.</div>
            </div>
        </div>
        <div class="observability-grid">
            <div class="observability-card"><div class="label">Active Hedge Chains</div><div id="obs-hedge-chains" class="value">0</div></div>
            <div class="observability-card"><div class="label">Chain Positions</div><div id="obs-hedge-positions" class="value">0</div></div>
            <div class="observability-card"><div class="label">Chain Lots</div><div id="obs-hedge-lots" class="value">0.00</div></div>
            <div class="observability-card"><div class="label">Chain P/L</div><div id="obs-hedge-pl" class="value">$0.00</div></div>
            <div class="observability-card"><div class="label">Chain Loss %</div><div id="obs-hedge-loss" class="value">0.00%</div></div>
            <div class="observability-card"><div class="label">Max Hedge Level</div><div id="obs-hedge-level" class="value">0</div></div>
            <div class="observability-card"><div class="label">Max Hedge Cycle</div><div id="obs-hedge-cycle" class="value">0</div></div>
            <div class="observability-card"><div class="label">Basket Risk Remaining</div><div id="obs-risk-remaining" class="value">0.00%</div></div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Market State & Filters</h2>
                <div class="section-note">Live execution environment used by Nyao to decide whether fresh exposure is acceptable.</div>
            </div>
        </div>
        <div class="observability-grid">
            <div class="observability-card"><div class="label">Bid / Ask</div><div id="obs-bid-ask" class="value">—</div></div>
            <div class="observability-card"><div class="label">Spread / Cap</div><div id="obs-spread" class="value">—</div></div>
            <div class="observability-card"><div class="label">ATR / Average ATR</div><div id="obs-atr" class="value">—</div></div>
            <div class="observability-card"><div class="label">Volatility Ratio</div><div id="obs-volatility-ratio" class="value">0.00</div></div>
            <div class="observability-card"><div class="label">Spread Filter</div><div id="obs-spread-filter" class="value">—</div></div>
            <div class="observability-card"><div class="label">Trading Pause</div><div id="obs-pause" class="value">—</div></div>
            <div class="observability-card"><div class="label">Trading Hours</div><div id="obs-hours" class="value">—</div></div>
            <div class="observability-card"><div class="label">Market Close / Leverage</div><div id="obs-market-filters" class="value">—</div></div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Signal Anatomy</h2>
                <div class="section-note">BUY and SELL component telemetry that Atlas can later interpret by market regime.</div>
            </div>
            <span id="signal-telemetry-state" class="badge blocked">Waiting</span>
        </div>
        <div class="signal-anatomy-grid">
            <div class="signal-anatomy">
                <div class="decision-top"><div class="decision-side">BUY</div><div id="signal-buy-final" class="badge ready">0.00</div></div>
                <div id="signal-buy-components" class="signal-component-grid"></div>
                <div id="signal-buy-reasoning" class="signal-reasoning">No reasoning reported.</div>
            </div>
            <div class="signal-anatomy">
                <div class="decision-top"><div class="decision-side">SELL</div><div id="signal-sell-final" class="badge blocked">0.00</div></div>
                <div id="signal-sell-components" class="signal-component-grid"></div>
                <div id="signal-sell-reasoning" class="signal-reasoning">No reasoning reported.</div>
            </div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Live Nyao Positions</h2>
                <div class="section-note">Strategy-owned positions with management and hedge-chain metadata.</div>
            </div>
        </div>
        <div class="positions-wrapper">
            <table class="positions-table">
                <thead><tr>
                    <th>Ticket</th><th>Side</th><th>Lot</th><th>Entry</th><th>Current</th><th>P/L</th>
                    <th>Distance</th><th>Age</th><th>Entry Score</th><th>SL</th><th>TP</th>
                    <th>BE Lock</th><th>Partial</th><th>Chain</th><th>Level</th><th>Cycle</th>
                </tr></thead>
                <tbody id="positions-body"><tr><td colspan="16">No strategy positions.</td></tr></tbody>
            </table>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Master Controls</h2>
                <div class="section-note">Atlas can stop fresh exposure while Nyao continues managing existing positions.</div>
            </div>
        </div>

        <div class="master-grid">
            <div class="master-item">
                <span>New Trading</span>
                <button id="trading-button" onclick="toggleMaster('enabled')">Loading</button>
            </div>
            <div class="master-item">
                <span>Buy Entries</span>
                <button id="buy-button" onclick="toggleMaster('enable_buy_orders')">Loading</button>
            </div>
            <div class="master-item">
                <span>Sell Entries</span>
                <button id="sell-button" onclick="toggleMaster('enable_sell_orders')">Loading</button>
            </div>
            <div class="master-item">
                <span>Realized P/L Baseline</span>
                <button class="neutral-button" onclick="resetRealizedProfit()">Reset</button>
            </div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Full Nyao Runtime Control</h2>
                <div class="section-note">
                    156 runtime controls. Values shown in each control are the requested Atlas value when set;
                    otherwise the current effective Nyao value. Risk/recovery changes can affect active trade management.
                </div>
            </div>
            <span class="badge danger">Demo / Validation</span>
        </div>

        <div class="control-toolbar">
            <input
                id="control-search"
                class="search"
                placeholder="Search controls, e.g. new bar, hedge, RSI, trailing..."
                oninput="filterControls()"
            >
            <div>
                <button class="neutral-button" onclick="openAllGroups()">Expand all</button>
                <button class="neutral-button" onclick="closeAllGroups()">Collapse all</button>
            </div>
        </div>

        <div id="runtime-groups" class="groups"></div>

        <div class="control-actions">
            <div id="dirty-state" class="clean">No unsaved runtime changes.</div>
            <div class="action-buttons">
                <button class="neutral-button" onclick="discardRuntimeChanges()">Discard edits</button>
                <button id="apply-button" class="primary-button" onclick="applyRuntimeChanges()">Apply changed controls</button>
            </div>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Core Runtime Verification</h2>
                <div class="section-note">
                    Preserves the previous dashboard's requested-vs-applied check for the most important controls.
                    "Inherited" means Atlas has not explicitly overridden that value and Nyao is using its effective runtime value.
                </div>
            </div>
        </div>

        <div class="verification-wrapper">
            <table class="verification-table">
                <thead>
                    <tr>
                        <th>Parameter</th>
                        <th>Requested by Atlas</th>
                        <th>Applied by Nyao</th>
                        <th>State</th>
                    </tr>
                </thead>
                <tbody id="core-verification-body"></tbody>
            </table>
        </div>
    </div>

    <div class="section card">
        <div class="section-heading">
            <div>
                <h2 class="section-title">Last Order Attempt</h2>
                <div class="section-note">Most recent order attempt reported by Nyao.</div>
            </div>
        </div>
        <div class="order-grid">
            <div class="mini"><div class="label">Attempted</div><div id="order-attempted" class="value">—</div></div>
            <div class="mini"><div class="label">Result</div><div id="order-result" class="value">—</div></div>
            <div class="mini"><div class="label">Direction</div><div id="order-direction" class="value">—</div></div>
            <div class="mini"><div class="label">Mode</div><div id="order-mode" class="value">—</div></div>
            <div class="mini"><div class="label">Ticket</div><div id="order-ticket" class="value">—</div></div>
            <div class="mini"><div class="label">Retcode</div><div id="order-retcode" class="value">—</div></div>
            <div class="mini"><div class="label">Time</div><div id="order-time" class="value">—</div></div>
        </div>
    </div>

    <div id="footer" class="footer">Waiting for Nyao status...</div>
</div>

<script>
    const CONTROL_GROUPS = __CONTROL_CONFIG__;

    const CORE_VERIFICATION_FIELDS = [
        "enable_new_bar_entry_only",
        "min_buy_signal_score",
        "min_sell_signal_score",
        "min_vol_ratio_to_trade",
        "base_lot_size",
        "max_open_orders",
        "max_trades_per_candle",
        "enable_hedge_chain",
        "enable_dynamic_lots",
        "enable_virtual_sl_reentry"
    ];

    let currentCommand = {};
    let latestStatus = {};
    let latestIntelligence = {};
    let dirtyFields = new Set();
    let saveInProgress = false;
    let startingBalance = null;

    const storedBalance = localStorage.getItem("atlasStartingBalance");
    if (storedBalance !== null && Number.isFinite(Number(storedBalance))) {
        startingBalance = Number(storedBalance);
    }

    function money(value) {
        return new Intl.NumberFormat("en-SG", {
            style: "currency",
            currency: "USD",
            minimumFractionDigits: 2
        }).format(Number(value || 0));
    }

    function formatEpoch(epoch) {
        const n = Number(epoch || 0);
        return n > 0 ? new Date(n * 1000).toLocaleString() : "—";
    }

    function formatDuration(seconds) {
        let s = Math.max(0, Number(seconds || 0));
        if (s < 60) return `${Math.floor(s)}s`;
        const minutes = Math.floor(s / 60);
        if (minutes < 60) return `${minutes}m`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours}h ${minutes % 60}m`;
        const days = Math.floor(hours / 24);
        return `${days}d ${hours % 24}h`;
    }

    function setSignedMoney(id, value) {
        const el = document.getElementById(id);
        if (!el) return;
        const n = Number(value || 0);
        el.textContent = money(n);
        el.className = `value ${n > 0 ? "positive" : n < 0 ? "negative" : ""}`;
    }

    function humanReason(value) {
        if (!value) return "UNKNOWN";
        return String(value)
            .replaceAll("_", " ")
            .toLowerCase()
            .replace(/\b\w/g, c => c.toUpperCase());
    }

    function getControlDefinition(name) {
        for (const group of CONTROL_GROUPS) {
            const found = group.controls.find(c => c.name === name);
            if (found) return found;
        }
        return null;
    }

    function valuesEqual(a, b) {
        if (typeof a === "boolean" || typeof b === "boolean") {
            return Boolean(a) === Boolean(b);
        }

        const aNumber = Number(a);
        const bNumber = Number(b);

        if (Number.isFinite(aNumber) && Number.isFinite(bNumber)) {
            return Math.abs(aNumber - bNumber) <= 0.0001;
        }

        return String(a) === String(b);
    }

    function formatControlValue(control, value) {
        if (value === undefined || value === null) return "—";
        if (control?.kind === "bool") return value ? "On" : "Off";

        if (control?.kind === "select") {
            const option = control.options?.find(o => Number(o.value) === Number(value));
            return option ? `${option.label} (${value})` : String(value);
        }

        return String(value);
    }

    function effectiveValue(control) {
        if (
            Object.prototype.hasOwnProperty.call(currentCommand, control.name) &&
            currentCommand[control.name] !== null &&
            currentCommand[control.name] !== undefined
        ) {
            return currentCommand[control.name];
        }

        if (
            Object.prototype.hasOwnProperty.call(latestStatus, control.status_key) &&
            latestStatus[control.status_key] !== null &&
            latestStatus[control.status_key] !== undefined
        ) {
            return latestStatus[control.status_key];
        }

        return null;
    }

    function renderRuntimeGroups() {
        const root = document.getElementById("runtime-groups");
        root.innerHTML = "";

        CONTROL_GROUPS.forEach((group, groupIndex) => {
            const details = document.createElement("details");
            details.className = "group";
            details.dataset.groupName = group.name.toLowerCase();
            if (groupIndex === 0) details.open = true;

            const summary = document.createElement("summary");
            const left = document.createElement("div");
            left.className = "group-title";
            left.innerHTML = `
                <span>${group.name}</span>
                <span class="count">${group.controls.length}</span>
                ${group.danger ? '<span class="badge danger">Risk-sensitive</span>' : ''}
            `;

            const arrow = document.createElement("span");
            arrow.textContent = "▾";
            arrow.style.color = "var(--muted)";

            summary.appendChild(left);
            summary.appendChild(arrow);
            details.appendChild(summary);

            const desc = document.createElement("div");
            desc.className = "group-description";
            desc.textContent = group.description || "";
            details.appendChild(desc);

            const grid = document.createElement("div");
            grid.className = "control-grid";

            group.controls.forEach(control => {
                grid.appendChild(buildControl(control));
            });

            details.appendChild(grid);
            root.appendChild(details);
        });

        refreshAllControlValues();
    }

    function buildControl(control) {
        const box = document.createElement("div");
        box.className = "runtime-control";
        box.id = `control-box-${control.name}`;
        box.dataset.search = `${control.label} ${control.name}`.toLowerCase();

        const head = document.createElement("div");
        head.className = "control-head";

        const label = document.createElement("div");
        label.className = "control-label";
        label.textContent = control.label;

        const applied = document.createElement("div");
        applied.className = "applied";
        applied.id = `applied-${control.name}`;
        applied.textContent = "Applied: —";

        head.appendChild(label);
        head.appendChild(applied);
        box.appendChild(head);

        let input;

        if (control.kind === "bool") {
            const wrap = document.createElement("label");
            wrap.className = "switch";

            input = document.createElement("input");
            input.type = "checkbox";
            input.id = `field-${control.name}`;
            input.addEventListener("change", () => markDirty(control.name));

            const slider = document.createElement("span");
            slider.className = "slider";

            wrap.appendChild(input);
            wrap.appendChild(slider);
            box.appendChild(wrap);
        } else if (control.kind === "select") {
            input = document.createElement("select");
            input.id = `field-${control.name}`;

            control.options.forEach(option => {
                const o = document.createElement("option");
                o.value = option.value;
                o.textContent = option.label;
                input.appendChild(o);
            });

            input.addEventListener("change", () => markDirty(control.name));
            box.appendChild(input);
        } else {
            input = document.createElement("input");
            input.id = `field-${control.name}`;
            input.type = control.kind === "time" ? "time" : control.kind === "text" ? "text" : "number";

            if (control.min !== undefined) input.min = control.min;
            if (control.max !== undefined) input.max = control.max;
            if (control.step !== undefined) input.step = control.step;

            input.addEventListener("input", () => markDirty(control.name));
            box.appendChild(input);
        }

        return box;
    }

    function markDirty(name) {
        dirtyFields.add(name);
        document.getElementById(`control-box-${name}`)?.classList.add("changed");
        refreshDirtyState();
    }

    function refreshDirtyState() {
        const el = document.getElementById("dirty-state");
        if (dirtyFields.size === 0) {
            el.className = "clean";
            el.textContent = "No unsaved runtime changes.";
        } else {
            el.className = "dirty";
            el.textContent = `${dirtyFields.size} unsaved runtime change${dirtyFields.size === 1 ? "" : "s"}.`;
        }
    }

    function setControlValue(control, value) {
        const input = document.getElementById(`field-${control.name}`);
        if (!input || dirtyFields.has(control.name) || value === null || value === undefined) return;

        if (control.kind === "bool") {
            input.checked = Boolean(value);
        } else {
            input.value = value;
        }
    }

    function refreshAllControlValues() {
        CONTROL_GROUPS.forEach(group => {
            group.controls.forEach(control => {
                setControlValue(control, effectiveValue(control));

                const applied = latestStatus[control.status_key];
                const appliedEl = document.getElementById(`applied-${control.name}`);

                if (appliedEl) {
                    const hasRequested =
                        Object.prototype.hasOwnProperty.call(currentCommand, control.name) &&
                        currentCommand[control.name] !== null &&
                        currentCommand[control.name] !== undefined;

                    if (applied === undefined || applied === null) {
                        appliedEl.textContent = "Applied: —";
                        appliedEl.className = "applied";
                    } else if (!hasRequested) {
                        appliedEl.textContent = `Applied: ${formatControlValue(control, applied)} · Inherited`;
                        appliedEl.className = "applied inherited";
                    } else {
                        const synced = valuesEqual(currentCommand[control.name], applied);
                        appliedEl.textContent =
                            `Applied: ${formatControlValue(control, applied)} · ${synced ? "Synced" : "Pending"}`;
                        appliedEl.className = `applied ${synced ? "match" : "mismatch"}`;
                    }
                }
            });
        });
    }

    function readControlValue(control) {
        const input = document.getElementById(`field-${control.name}`);
        if (!input) return null;

        if (control.kind === "bool") return input.checked;
        if (control.kind === "select") return Number(input.value);
        if (control.kind === "number") {
            const n = Number(input.value);
            if (!Number.isFinite(n)) throw new Error(`${control.label}: invalid number.`);
            if (control.min !== undefined && n < Number(control.min)) {
                throw new Error(`${control.label}: minimum is ${control.min}.`);
            }
            if (control.max !== undefined && n > Number(control.max)) {
                throw new Error(`${control.label}: maximum is ${control.max}.`);
            }
            return control.mql_type === "int" ? Math.trunc(n) : n;
        }
        return input.value;
    }

    async function sendCommandPatch(patch) {
        if (saveInProgress) return;

        saveInProgress = true;
        document.querySelectorAll("button").forEach(b => b.disabled = true);

        try {
            const response = await fetch("/api/v1/nyao/command", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(patch)
            });

            if (!response.ok) {
                const body = await response.text();
                throw new Error(`Command update failed: ${body}`);
            }

            currentCommand = await response.json();
            updateMasterButtons();
            updateSync();
            refreshAllControlValues();
        } finally {
            saveInProgress = false;
            document.querySelectorAll("button").forEach(b => b.disabled = false);
        }
    }

    async function applyRuntimeChanges() {
        if (dirtyFields.size === 0) return;

        const patch = {};

        try {
            for (const name of dirtyFields) {
                const control = getControlDefinition(name);
                if (!control) continue;
                patch[name] = readControlValue(control);
            }

            await sendCommandPatch(patch);

            for (const name of dirtyFields) {
                document.getElementById(`control-box-${name}`)?.classList.remove("changed");
            }

            dirtyFields.clear();
            refreshDirtyState();
        } catch (error) {
            alert(error.message);
            console.error(error);
        }
    }

    function discardRuntimeChanges() {
        for (const name of dirtyFields) {
            document.getElementById(`control-box-${name}`)?.classList.remove("changed");
        }
        dirtyFields.clear();
        refreshDirtyState();
        refreshAllControlValues();
    }

    async function toggleMaster(field) {
        if (currentCommand[field] === undefined) return;

        try {
            await sendCommandPatch({[field]: !Boolean(currentCommand[field])});
        } catch (error) {
            alert(error.message);
            console.error(error);
        }
    }

    function updateMasterButtons() {
        const map = [
            ["trading-button","enabled"],
            ["buy-button","enable_buy_orders"],
            ["sell-button","enable_sell_orders"],
        ];

        map.forEach(([id, field]) => {
            const button = document.getElementById(id);
            const enabled = Boolean(currentCommand[field]);
            button.textContent = enabled ? "Enabled" : "Disabled";
            button.className = enabled ? "enabled-button" : "disabled-button";
        });
    }

    function updateRuntimeSyncSummary() {
        let telemetryCount = 0;
        let explicitCount = 0;
        let syncedCount = 0;
        let pendingCount = 0;

        CONTROL_GROUPS.forEach(group => {
            group.controls.forEach(control => {
                const applied = latestStatus[control.status_key];

                if (applied !== undefined && applied !== null) {
                    telemetryCount++;
                }

                const hasRequested =
                    Object.prototype.hasOwnProperty.call(currentCommand, control.name) &&
                    currentCommand[control.name] !== null &&
                    currentCommand[control.name] !== undefined;

                if (hasRequested) {
                    explicitCount++;
                    if (applied !== undefined && applied !== null &&
                        valuesEqual(currentCommand[control.name], applied)) {
                        syncedCount++;
                    } else {
                        pendingCount++;
                    }
                }
            });
        });

        const count = document.getElementById("runtime-sync-count");
        const state = document.getElementById("runtime-sync-state");

        count.textContent = `${telemetryCount}/156`;

        if (telemetryCount < 156) {
            state.textContent = "Telemetry incomplete";
            state.className = "sync-waiting";
        } else if (pendingCount > 0) {
            state.textContent = `${pendingCount} pending`;
            state.className = "sync-waiting";
        } else {
            state.textContent = explicitCount > 0 ? `${syncedCount} overrides synced` : "Telemetry complete";
            state.className = "sync-ok";
        }
    }

    function renderCoreVerification() {
        const body = document.getElementById("core-verification-body");
        if (!body) return;

        body.innerHTML = "";

        CORE_VERIFICATION_FIELDS.forEach(name => {
            const control = getControlDefinition(name);
            if (!control) return;

            const applied = latestStatus[control.status_key];

            const hasRequested =
                Object.prototype.hasOwnProperty.call(currentCommand, name) &&
                currentCommand[name] !== null &&
                currentCommand[name] !== undefined;

            const requested = hasRequested ? currentCommand[name] : undefined;
            const row = document.createElement("tr");

            let stateText = "Inherited";
            let stateClass = "inherited";

            if (hasRequested) {
                const synced =
                    applied !== undefined &&
                    applied !== null &&
                    valuesEqual(requested, applied);

                stateText = synced ? "Synced" : "Pending";
                stateClass = synced ? "match" : "mismatch";
            }

            row.innerHTML = `
                <td>${control.label}</td>
                <td>${hasRequested ? formatControlValue(control, requested) : "Profile / current runtime"}</td>
                <td>${formatControlValue(control, applied)}</td>
                <td class="${stateClass}">${stateText}</td>
            `;

            body.appendChild(row);
        });
    }

    function updateSync() {
        const commandVersion = Number(currentCommand.command_version ?? -1);
        const appliedVersion = Number(latestStatus.applied_command_version ?? -2);

        document.getElementById("command-version").textContent =
            commandVersion >= 0 ? commandVersion : "—";
        document.getElementById("applied-version").textContent =
            appliedVersion >= 0 ? appliedVersion : "—";

        const sync = document.getElementById("sync-state");
        const ok = commandVersion >= 0 && commandVersion === appliedVersion;
        sync.textContent = ok ? "Synced" : "Waiting";
        sync.className = ok ? "sync-ok" : "sync-waiting";

        const structural = document.getElementById("structural-state");
        const dirty = Boolean(latestStatus.structural_config_dirty);
        structural.textContent = dirty ? "Rebuilding" : "Stable";
        structural.className = dirty ? "warning" : "positive";

        updateRuntimeSyncSummary();
        renderCoreVerification();
    }

    function updateDecision() {
        const buy = Number(latestStatus.buy_score || 0);
        const sell = Number(latestStatus.sell_score || 0);
        const buyAdj = Number(latestStatus.buy_adjusted_score || 0);
        const sellAdj = Number(latestStatus.sell_adjusted_score || 0);
        const buyTh = Number(latestStatus.buy_effective_threshold || 0);
        const sellTh = Number(latestStatus.sell_effective_threshold || 0);

        document.getElementById("buy-score").textContent = buy.toFixed(2);
        document.getElementById("sell-score").textContent = sell.toFixed(2);
        document.getElementById("buy-threshold").textContent = buyTh.toFixed(2);
        document.getElementById("sell-threshold").textContent = sellTh.toFixed(2);
        document.getElementById("buy-bar").style.width = `${Math.max(0,Math.min(100,buy*10))}%`;
        document.getElementById("sell-bar").style.width = `${Math.max(0,Math.min(100,sell*10))}%`;

        document.getElementById("buy-live").textContent = buy.toFixed(2);
        document.getElementById("sell-live").textContent = sell.toFixed(2);
        document.getElementById("buy-adjusted").textContent = buyAdj.toFixed(2);
        document.getElementById("sell-adjusted").textContent = sellAdj.toFixed(2);
        document.getElementById("buy-effective").textContent = buyTh.toFixed(2);
        document.getElementById("sell-effective").textContent = sellTh.toFixed(2);

        [["buy","buy_entry_eligible","buy_block_reason"],["sell","sell_entry_eligible","sell_block_reason"]]
            .forEach(([side, eligibleKey, reasonKey]) => {
                const badge = document.getElementById(`${side}-state`);
                const eligible = Boolean(latestStatus[eligibleKey]);
                badge.textContent = eligible ? "Ready" : "Blocked";
                badge.className = eligible ? "badge ready" : "badge blocked";
                document.getElementById(`${side}-reason`).textContent =
                    humanReason(latestStatus[reasonKey]);
            });

        document.getElementById("new-bar-mode").textContent =
            latestStatus.new_bar_entry_only ? "ON · New bar only" : "OFF · Intrabar";
        document.getElementById("new-bar-ready").textContent =
            latestStatus.new_bar_ready ? "Ready" : "Waiting";
        document.getElementById("cooldown").textContent =
            latestStatus.cooldown_active
                ? `Active until ${formatEpoch(latestStatus.cooldown_until_epoch)}`
                : "Inactive";
        document.getElementById("global-block").textContent =
            humanReason(latestStatus.last_global_block_reason || "NONE");
    }

    function prettyKey(value) {
        return String(value || "")
            .replaceAll("_", " ")
            .toLowerCase()
            .replace(/\b\w/g, c => c.toUpperCase());
    }

    function renderList(id, items, emptyText) {
        const root = document.getElementById(id);
        const values = Array.isArray(items) ? items : [];
        root.innerHTML = "";

        if (values.length === 0) {
            const li = document.createElement("li");
            li.textContent = emptyText;
            root.appendChild(li);
            return;
        }

        values.forEach(item => {
            const li = document.createElement("li");
            li.textContent = item;
            root.appendChild(li);
        });
    }

    function updateIntelligencePanel() {
        if (!latestIntelligence || !latestIntelligence.regime || !latestIntelligence.risk) {
            return;
        }

        const regime = latestIntelligence.regime;
        const risk = latestIntelligence.risk;

        document.getElementById("intel-mode").textContent = latestIntelligence.mode || "ADVISORY";
        document.getElementById("intel-summary").textContent = latestIntelligence.summary || "—";
        document.getElementById("intel-regime").textContent = prettyKey(regime.regime);
        document.getElementById("intel-direction").textContent = prettyKey(regime.direction);
        document.getElementById("intel-volatility").textContent = prettyKey(regime.volatility);
        document.getElementById("intel-fit").textContent = prettyKey(latestIntelligence.fit);
        document.getElementById("intel-confidence").textContent = `${Number(latestIntelligence.confidence || 0).toFixed(1)}%`;
        document.getElementById("intel-risk-state").textContent = prettyKey(risk.state);
        document.getElementById("intel-risk-score").textContent = `${Number(risk.score || 0)}/100`;
        document.getElementById("intel-exposure-bias").textContent = prettyKey(risk.exposure_bias);
        document.getElementById("intel-execution").textContent = prettyKey(regime.execution_environment);

        const vetoEl = document.getElementById("intel-veto");
        const veto = Boolean(risk.veto_new_risk);
        vetoEl.textContent = veto ? "VETO NEW RISK" : "CLEAR";
        vetoEl.className = `value ${veto ? "negative" : "positive"}`;

        renderList(
            "intel-recommendations",
            latestIntelligence.recommendations,
            "No recommendation."
        );
        renderList(
            "intel-cautions",
            latestIntelligence.cautions,
            "No cautions."
        );
        renderList(
            "intel-reasons",
            regime.reasons,
            "No classification reasons."
        );

        const history = latestIntelligence.history || {};
        document.getElementById("history-count").textContent =
            history.record_count ?? 0;
        document.getElementById("history-reason").textContent =
            prettyKey(history.reason || "—");

        const proposals = latestIntelligence.proposed_changes || {};
        const proposalRoot = document.getElementById("intel-proposals");
        proposalRoot.innerHTML = "";

        const entries = Object.entries(proposals);
        if (entries.length === 0) {
            proposalRoot.innerHTML =
                '<div class="proposal-item"><div class="key">State</div><div class="val">No runtime change proposed</div></div>';
        } else {
            entries.forEach(([key, value]) => {
                const div = document.createElement("div");
                div.className = "proposal-item";
                div.innerHTML = `
                    <div class="key">${prettyKey(key)}</div>
                    <div class="val">${typeof value === "boolean" ? (value ? "On" : "Off") : value}</div>
                `;
                proposalRoot.appendChild(div);
            });
        }
    }

    async function loadIntelligence() {
        try {
            const response = await fetch("/api/v1/atlas/intelligence", {cache:"no-store"});
            if (!response.ok) {
                throw new Error(`Intelligence request failed: ${response.status}`);
            }

            latestIntelligence = await response.json();
            updateIntelligencePanel();
        } catch (error) {
            console.error(error);
        }
    }

    function updateExposureRisk() {
        document.getElementById("obs-strategy-positions").textContent = latestStatus.strategy_open_positions ?? 0;
        document.getElementById("obs-total-lots").textContent = Number(latestStatus.total_lots || 0).toFixed(2);
        setSignedMoney("obs-strategy-pl", latestStatus.strategy_floating_pl);
        document.getElementById("obs-notional").textContent = money(latestStatus.gross_notional_exposure);
        document.getElementById("obs-side-counts").textContent = `${latestStatus.buy_positions ?? 0} / ${latestStatus.sell_positions ?? 0}`;
        document.getElementById("obs-side-lots").textContent = `${Number(latestStatus.buy_lots || 0).toFixed(2)} / ${Number(latestStatus.sell_lots || 0).toFixed(2)}`;
        document.getElementById("obs-win-loss-count").textContent = `${latestStatus.winning_positions ?? 0} / ${latestStatus.losing_positions ?? 0}`;
        document.getElementById("obs-working-limits").textContent = latestStatus.working_limit_orders ?? 0;

        const ddPct = Number(latestStatus.equity_drawdown_pct || 0);
        document.getElementById("obs-drawdown").textContent = `${ddPct.toFixed(2)}% · ${money(latestStatus.equity_drawdown_usd)}`;

        const basketLoss = Number(latestStatus.basket_loss_pct || 0);
        const basketLimit = Number(latestStatus.runtime_max_basket_loss_pct || 0);
        document.getElementById("obs-basket-loss").textContent =
            basketLimit > 0 ? `${basketLoss.toFixed(2)}% / ${basketLimit.toFixed(2)}%` : `${basketLoss.toFixed(2)}% · Stop disabled`;
        const meter = basketLimit > 0 ? Math.max(0, Math.min(100, basketLoss / basketLimit * 100)) : 0;
        document.getElementById("obs-basket-meter").style.width = `${meter}%`;

        document.getElementById("obs-margin").textContent =
            `${money(latestStatus.account_margin)} / ${money(latestStatus.free_margin)}`;
        const marginLevel = Number(latestStatus.margin_level_pct || 0);
        const leverage = Number(latestStatus.account_leverage || 0);
        document.getElementById("obs-margin-level").textContent =
            `${marginLevel > 0 ? marginLevel.toFixed(1) + "%" : "—"} · 1:${leverage || "—"}`;
    }

    function updateHedgeRecovery() {
        document.getElementById("obs-hedge-chains").textContent = latestStatus.active_hedge_chains ?? 0;
        document.getElementById("obs-hedge-positions").textContent = latestStatus.hedge_chain_positions ?? 0;
        document.getElementById("obs-hedge-lots").textContent = Number(latestStatus.hedge_chain_lots || 0).toFixed(2);
        setSignedMoney("obs-hedge-pl", latestStatus.hedge_chain_floating_pl);
        document.getElementById("obs-hedge-loss").textContent = `${Number(latestStatus.hedge_chain_loss_pct || 0).toFixed(2)}%`;
        document.getElementById("obs-hedge-level").textContent = latestStatus.max_active_hedge_level ?? 0;
        document.getElementById("obs-hedge-cycle").textContent = latestStatus.max_active_hedge_cycle ?? 0;
        document.getElementById("obs-risk-remaining").textContent = `${Number(latestStatus.basket_risk_remaining_pct || 0).toFixed(2)}%`;
    }

    function updateMarketState() {
        document.getElementById("obs-bid-ask").textContent = `${Number(latestStatus.bid || 0)} / ${Number(latestStatus.ask || 0)}`;
        const spread = Number(latestStatus.spread_points || 0);
        const cap = Number(latestStatus.effective_spread_cap_points || 0);
        document.getElementById("obs-spread").textContent = `${spread.toFixed(1)} / ${cap > 0 ? cap.toFixed(1) : "No cap"} pts`;
        document.getElementById("obs-atr").textContent = `${Number(latestStatus.current_atr || 0).toFixed(3)} / ${Number(latestStatus.average_atr || 0).toFixed(3)}`;
        document.getElementById("obs-volatility-ratio").textContent = Number(latestStatus.volatility_ratio || 0).toFixed(3);

        const spreadOk = Boolean(latestStatus.spread_within_limit);
        const spreadEl = document.getElementById("obs-spread-filter");
        spreadEl.textContent = spreadOk ? "Within limit" : "Blocked";
        spreadEl.className = `value ${spreadOk ? "positive" : "negative"}`;

        document.getElementById("obs-pause").textContent =
            latestStatus.trading_paused ? `Paused · until ${formatEpoch(latestStatus.pause_until_epoch)}` : "Active";
        document.getElementById("obs-hours").textContent =
            latestStatus.outside_trading_hours ? "Outside hours" : "Allowed";
        document.getElementById("obs-market-filters").textContent =
            `${latestStatus.near_market_close ? "Near close" : "Market OK"} · ${latestStatus.leverage_changed ? "Leverage changed" : "Leverage OK"}`;
    }

    function signalComponentMarkup(prefix) {
        const components = [
            ["Trend", latestStatus[`${prefix}_trend_score`]],
            ["Momentum", latestStatus[`${prefix}_momentum_score`]],
            ["Chop", latestStatus[`${prefix}_chop_score`]],
            ["Peak", latestStatus[`${prefix}_peak_score`]],
            ["Volatility", latestStatus[`${prefix}_volatility_score`]],
            ["Impulse", latestStatus[`${prefix}_impulse_strength`]],
            ["Velocity", latestStatus[`${prefix}_velocity`]],
            ["Norm Velocity", latestStatus[`${prefix}_normalized_velocity`]],
            ["Body Ratio", latestStatus[`${prefix}_body_ratio`]],
            ["Wick Reject", latestStatus[`${prefix}_wick_rejection`]],
            ["Body Penalty", latestStatus[`${prefix}_body_penalty`]],
            ["Wick Penalty", latestStatus[`${prefix}_wick_penalty`]]
        ];

        return components.map(([label, value]) => `
            <div class="mini">
                <div class="label">${label}</div>
                <div class="value">${Number(value || 0).toFixed(3)}</div>
            </div>
        `).join("");
    }

    function updateSignalAnatomy() {
        const ready = Boolean(latestStatus.signal_telemetry_ready);
        const state = document.getElementById("signal-telemetry-state");
        state.textContent = ready ? "Live" : "Waiting";
        state.className = ready ? "badge ready" : "badge blocked";

        document.getElementById("signal-buy-final").textContent = Number(latestStatus.buy_score || 0).toFixed(2);
        document.getElementById("signal-sell-final").textContent = Number(latestStatus.sell_score || 0).toFixed(2);
        document.getElementById("signal-buy-components").innerHTML = signalComponentMarkup("buy");
        document.getElementById("signal-sell-components").innerHTML = signalComponentMarkup("sell");
        document.getElementById("signal-buy-reasoning").textContent = latestStatus.buy_signal_reasoning || "No reasoning reported.";
        document.getElementById("signal-sell-reasoning").textContent = latestStatus.sell_signal_reasoning || "No reasoning reported.";
    }

    function updatePositionsTable() {
        const body = document.getElementById("positions-body");
        const positions = Array.isArray(latestStatus.positions) ? latestStatus.positions : [];

        if (positions.length === 0) {
            body.innerHTML = '<tr><td colspan="16">No strategy positions.</td></tr>';
            return;
        }

        body.innerHTML = positions.map(p => {
            const pl = Number(p.net_pl || 0);
            const chain = Number(p.chain_id || 0);
            return `
                <tr>
                    <td>${p.ticket || "—"}</td>
                    <td>${p.type || "—"}</td>
                    <td>${Number(p.volume || 0).toFixed(2)}</td>
                    <td>${Number(p.entry_price || 0)}</td>
                    <td>${Number(p.current_price || 0)}</td>
                    <td class="${pl > 0 ? "positive" : pl < 0 ? "negative" : ""}">${money(pl)}</td>
                    <td>${Number(p.signed_distance_points || 0).toFixed(1)} pts</td>
                    <td>${formatDuration(p.age_seconds)}</td>
                    <td>${Number(p.entry_signal_score || 0).toFixed(2)}</td>
                    <td>${Number(p.sl || 0)}</td>
                    <td>${Number(p.tp || 0)}</td>
                    <td>${p.break_even_locked ? "Yes" : "No"}</td>
                    <td>${p.partial_close_level || 0}</td>
                    <td>${chain > 0 ? chain : "—"}</td>
                    <td>${p.hedge_level || 0}</td>
                    <td>${p.cycle_num || 0}</td>
                </tr>
            `;
        }).join("");
    }

    function updateObservability() {
        updateExposureRisk();
        updateHedgeRecovery();
        updateMarketState();
        updateSignalAnatomy();
        updatePositionsTable();
    }

    function updateLastOrder() {
        const attempted = Boolean(latestStatus.last_order_attempted);
        const success = Boolean(latestStatus.last_order_success);

        document.getElementById("order-attempted").textContent = attempted ? "Yes" : "No";

        const result = document.getElementById("order-result");
        result.textContent = !attempted ? "No attempt" : success ? "Success" : "Failed";
        result.className = `value ${attempted ? (success ? "positive" : "negative") : ""}`;

        document.getElementById("order-direction").textContent = latestStatus.last_order_direction || "—";
        document.getElementById("order-mode").textContent = latestStatus.last_order_mode || "—";
        document.getElementById("order-ticket").textContent =
            Number(latestStatus.last_order_ticket || 0) > 0 ? latestStatus.last_order_ticket : "—";
        document.getElementById("order-retcode").textContent =
            Number(latestStatus.last_order_retcode || 0) > 0 ? latestStatus.last_order_retcode : "—";
        document.getElementById("order-time").textContent = formatEpoch(latestStatus.last_order_time_epoch);
    }

    async function loadStatus() {
        try {
            const response = await fetch("/api/v1/nyao/status", {cache:"no-store"});
            if (!response.ok) throw new Error(`Status request failed: ${response.status}`);

            latestStatus = await response.json();

            const balance = Number(latestStatus.balance || 0);
            document.getElementById("balance").textContent = money(balance);
            document.getElementById("equity").textContent = money(latestStatus.equity);
            document.getElementById("positions").textContent = latestStatus.open_positions ?? 0;

            const pnl = Number(latestStatus.floating_profit || 0);
            const pnlEl = document.getElementById("profit");
            pnlEl.textContent = money(pnl);
            pnlEl.className = `card-value ${pnl > 0 ? "positive" : pnl < 0 ? "negative" : ""}`;

            if (startingBalance === null && balance > 0) {
                startingBalance = balance;
                localStorage.setItem("atlasStartingBalance", String(balance));
            }

            const realized = startingBalance === null ? 0 : balance - startingBalance;
            const realizedEl = document.getElementById("realized-profit");
            realizedEl.textContent = money(realized);
            realizedEl.className = `card-value ${realized > 0 ? "positive" : realized < 0 ? "negative" : ""}`;

            const connected = Boolean(latestStatus.connected);
            document.getElementById("connection-dot").className = connected ? "dot connected" : "dot";
            document.getElementById("connection-text").textContent =
                connected ? `Nyao connected · ${latestStatus.symbol}` : "Nyao disconnected";

            document.getElementById("footer").textContent =
                `Last Nyao status: ${latestStatus.timestamp}`;

            updateSync();
            updateDecision();
            updateObservability();
            updateLastOrder();
            refreshAllControlValues();
            renderCoreVerification();
        } catch (error) {
            document.getElementById("connection-dot").className = "dot";
            document.getElementById("connection-text").textContent = "Unable to reach Nyao";
            console.error(error);
        }
    }

    async function loadCommand() {
        try {
            const response = await fetch("/api/v1/nyao/command", {cache:"no-store"});
            if (!response.ok) throw new Error(`Command request failed: ${response.status}`);

            currentCommand = await response.json();
            updateMasterButtons();
            updateSync();
            refreshAllControlValues();
        } catch (error) {
            console.error(error);
        }
    }

    async function resetRealizedProfit() {
        try {
            const response = await fetch("/api/v1/nyao/status", {cache:"no-store"});
            if (!response.ok) {
                throw new Error(`Unable to read current balance: ${response.status}`);
            }

            const status = await response.json();
            const balance = Number(status.balance || 0);

            if (!Number.isFinite(balance) || balance <= 0) {
                throw new Error("Current balance is not available.");
            }

            startingBalance = balance;
            localStorage.setItem("atlasStartingBalance", String(balance));
            await loadStatus();
        } catch (error) {
            alert(error.message);
            console.error(error);
        }
    }

    function filterControls() {
        const q = document.getElementById("control-search").value.trim().toLowerCase();

        document.querySelectorAll("details.group").forEach(group => {
            let visible = 0;
            group.querySelectorAll(".runtime-control").forEach(box => {
                const match = !q || box.dataset.search.includes(q);
                box.classList.toggle("hidden", !match);
                if (match) visible++;
            });

            group.classList.toggle("hidden", visible === 0);
            if (q && visible > 0) group.open = true;
        });
    }

    function openAllGroups() {
        document.querySelectorAll("details.group:not(.hidden)").forEach(d => d.open = true);
    }

    function closeAllGroups() {
        document.querySelectorAll("details.group").forEach(d => d.open = false);
    }

    renderRuntimeGroups();

    Promise.all([loadCommand(), loadStatus(), loadIntelligence()]);

    setInterval(loadStatus, 1000);
    setInterval(loadIntelligence, 2000);
    setInterval(loadCommand, 3000);
</script>
</body>
</html>
"""


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    controls_json = json.dumps(RUNTIME_CONTROL_GROUPS, separators=(",", ":"))
    return DASHBOARD_TEMPLATE.replace("__CONTROL_CONFIG__", controls_json)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )