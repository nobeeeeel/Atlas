from datetime import datetime, timezone
import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from backend.app.bridge.protocol import COMMANDS_FILE, STATUS_FILE
from backend.app.bridge.reader import read_json
from backend.app.bridge.schemas import Command, Status
from backend.app.bridge.writer import write_json
from backend.app.intelligence.symbol_namespace import (
    discover_bridge_symbols,
    resolve_default_symbol,
    safe_symbol,
    scoped_symbol_storage,
    symbol_bridge_paths,
)
from backend.app.intelligence.account_identity import (
    account_identity,
    scoped_account_performance,
)
from backend.app.intelligence.advisor import generate_advice
from backend.app.intelligence.analytics import analyze_history
from backend.app.intelligence.outcome_analytics import (
    analyze_trade_outcomes,
    evaluate_policy_performance,
)
from backend.app.intelligence.recovery_attribution import analyze_recovery_chains
from backend.app.intelligence.risk_units import build_risk_units
from backend.app.intelligence.recovery_risk import build_recovery_risk_ledger
from backend.app.intelligence.shadow_policy import (
    build_shadow_policy,
    get_shadow_history,
    record_shadow_policy,
)
from backend.app.intelligence.shadow_evaluation import evaluate_shadow_policies
from backend.app.intelligence.shadow_replay import run_shadow_replay
from backend.app.intelligence.policy_epoch import get_policy_epoch_registry
from backend.app.intelligence.position_policy_resolver import build_position_management_policy_diagnostics
from backend.app.intelligence.shadow_epoch_divergence import (
    build_shadow_epoch_divergence,
    coerce_shadow_test_value,
)
from backend.app.intelligence.policy_decision_engine import (
    build_policy_decision,
    get_policy_decision_history,
    get_policy_decision_stability,
    record_policy_decision,
)
from backend.app.intelligence.advisory_policy_proposal import (
    build_advisory_policy_proposal,
    build_llm_policy_advisory_proposal,
    get_all_advisory_policy_proposals,
    get_advisory_policy_proposal,
    get_advisory_policy_proposals,
    llm_advisory_context_status,
    persist_advisory_policy_proposal,
)
from backend.app.intelligence.advisory_review_workflow import (
    ReviewWorkflowError,
    approve_proposal,
    get_proposal_review_status,
    get_review_events,
    reconcile_advisory_review_state,
    reject_proposal,
    request_human_review,
    verify_review_event_chain,
)
from backend.app.intelligence.supervised_command_proposal import (
    SupervisedCommandBuildError,
    build_supervised_command_proposal,
    get_supervised_command_proposal,
    get_supervised_command_proposals,
)
from backend.app.intelligence.supervised_execution_gate import (
    SupervisedExecutionError,
    execute_supervised_command,
    get_execution_events,
    preflight_supervised_execution,
    verify_execution_event_chain,
    get_execution_arm_state,
    arm_supervised_execution,
    disarm_supervised_execution,
)
from backend.app.intelligence.nyao_execution_confirmation import (
    NyaoAckError,
    evaluate_nyao_ack,
    find_latest_execution_id,
)
from backend.app.intelligence.execution_recovery_diagnostics import (
    build_execution_recovery_diagnostics,
)
from backend.app.intelligence.outcomes import (
    get_outcome_summary,
    get_trade_outcomes,
    track_trade_outcomes,
)
from backend.app.intelligence.history import (
    get_history,
    get_history_summary,
    record_intelligence_snapshot,
)
from backend.app.intelligence.parameter_registry import (
    all_parameters,
    get_parameter,
    registry_summary,
)
from backend.app.intelligence.parameter_intelligence import (
    build_parameter_intelligence,
)
from backend.app.intelligence.parameter_evidence import (
    build_parameter_evidence,
)
from backend.app.intelligence.scalping_responsiveness import (
    analyze_scalping_responsiveness,
)
from backend.app.intelligence.market_candles import (
    build_market_candle_report,
    load_market_candle_export,
)
from backend.app.intelligence.zone_engine import build_zone_map
from backend.app.intelligence.zone_execution_plan import (
    build_zone_execution_plan,
    persist_zone_execution_directive,
)
from backend.app.intelligence.zone_policy import (
    ZonePolicy,
    apply_zone_policy,
    get_zone_policy,
)
from backend.app.intelligence.capital_sizing import build_capital_sizing_plan
from backend.app.intelligence.risk_appetite import get_risk_appetite, update_risk_appetite
from backend.app.intelligence.autonomous_policy import (
    apply_autonomous_llm_policy,
    apply_pending_autonomous_policy,
    apply_ready_loss_protection_consensus,
    get_autonomous_policy_events,
    get_pending_autonomous_policy,
    get_autonomous_policy_consensus,
    get_autonomous_policy_observations,
)
from backend.app.intelligence.llm_cycle_scheduler import (
    claim_llm_cycle,
    complete_llm_cycle,
    get_llm_cycle_schedule,
    recover_interrupted_llm_cycle,
    update_llm_cycle_schedule,
)
from backend.app.agents.llm_provider import (
    build_configured_provider,
    configured_llm_status,
    LlmProviderError,
)
from backend.app.agents.llm_review import run_analyst_critic_review
from backend.app.agents.policy_proposal import (
    build_atlas_prior_analysis,
    build_policy_input,
    run_policy_proposal,
)


app = FastAPI(
    title="Atlas",
    version="1.30.43",
)


class AdvisoryReviewActionRequest(BaseModel):
    reviewer: str = Field(default="human_operator", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    expected_runtime_fingerprint: str = Field(min_length=1, max_length=128)
    expected_proposed_policy_epoch: int = Field(ge=0)


class SupervisedCommandBuildRequest(BaseModel):
    reviewer: str = Field(default="human_operator", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    expected_runtime_fingerprint: str = Field(min_length=1, max_length=128)
    expected_proposed_policy_epoch: int = Field(ge=0)
    expected_review_snapshot_hash: str = Field(min_length=1, max_length=128)


class SupervisedExecutionArmRequest(BaseModel):
    actor: str = Field(default="human_operator", min_length=1, max_length=120)
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    minutes: int = Field(default=30, ge=1, le=120)


class SupervisedExecutionDisarmRequest(BaseModel):
    actor: str = Field(default="human_operator", min_length=1, max_length=120)


class SupervisedExecutionRequest(BaseModel):
    actor: str = Field(default="human_operator", min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    confirmation_phrase: str = Field(min_length=1, max_length=128)
    allow_test_override_execution: bool = False
    expected_source_proposal_id: str = Field(min_length=1, max_length=128)
    expected_runtime_fingerprint: str = Field(min_length=1, max_length=128)
    expected_target_policy_epoch: int = Field(ge=0)
    expected_review_snapshot_hash: str = Field(min_length=1, max_length=128)
    expected_baseline_command_version: int = Field(ge=0)
    expected_baseline_policy_epoch: int = Field(ge=0)


class LlmReviewRequest(BaseModel):
    run_critic: bool = True


class LlmCycleScheduleRequest(BaseModel):
    enabled: bool
    interval_minutes: int = Field(default=240, ge=15, le=1440)
    execution_mode: str = Field(default="SUPERVISED", pattern="^(SUPERVISED|AUTONOMOUS)$")
    minimum_dwell_minutes: int = Field(default=240, ge=30, le=1440)
    minimum_confidence: float = Field(default=70.0, ge=0.0, le=100.0)


class ZonePolicyUpdateRequest(BaseModel):
    policy: ZonePolicy
    expected_current_epoch: int = Field(ge=1)
    source: str = Field(default="ATLAS_OPERATOR", min_length=1, max_length=120)


class RiskAppetiteUpdateRequest(BaseModel):
    portfolio_hard_risk_pct: float = Field(ge=1.0, le=20.0)
    actor: str = Field(default="human_operator", min_length=1, max_length=120)


def _raise_review_workflow_error(exc: ReviewWorkflowError) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail=exc.as_detail(),
    ) from exc


def _raise_supervised_command_build_error(
    exc: SupervisedCommandBuildError,
) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail=exc.as_detail(),
    ) from exc


def _raise_supervised_execution_error(
    exc: SupervisedExecutionError,
) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail=exc.as_detail(),
    ) from exc


def _raise_nyao_ack_error(exc: NyaoAckError) -> None:
    raise HTTPException(
        status_code=exc.http_status,
        detail=exc.as_detail(),
    ) from exc

RUNTIME_CONTROL_GROUPS = json.loads(
    r'''[{"name":"Entry / execution","controls":[{"name":"enable_buy_orders","mql_type":"bool","default":"true","status_key":"runtime_enable_buy_orders","label":"Enable Buy Orders","kind":"bool"},{"name":"enable_sell_orders","mql_type":"bool","default":"true","status_key":"runtime_enable_sell_orders","label":"Enable Sell Orders","kind":"bool"},{"name":"enable_new_bar_entry_only","mql_type":"bool","default":"true","status_key":"runtime_enable_new_bar_entry_only","label":"Enable New Bar Entry Only","kind":"bool"},{"name":"enable_max_spread_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_max_spread_filter","label":"Enable Max Spread Filter","kind":"bool"},{"name":"max_spread_points","mql_type":"double","default":"0","status_key":"runtime_max_spread_points","label":"Max Spread Points","kind":"number","min":0,"max":100000,"step":1},{"name":"max_spread_atr_ratio","mql_type":"double","default":"0.25","status_key":"runtime_max_spread_atr_ratio","label":"Max Spread ATR Ratio","kind":"number","min":0,"max":10,"step":0.01},{"name":"base_lot_size","mql_type":"double","default":"0.01","status_key":"runtime_base_lot_size","label":"Base Lot Size","kind":"number","min":0.01,"max":5,"step":0.01},{"name":"max_open_orders","mql_type":"int","default":"8","status_key":"runtime_max_open_orders","label":"Max Open Orders","kind":"number","min":1,"max":50,"step":1},{"name":"max_trades_per_candle","mql_type":"int","default":"1","status_key":"runtime_max_trades_per_candle","label":"Max Trades Per Candle","kind":"number","min":0,"max":20,"step":1},{"name":"consecutive_candle_threshold_boost","mql_type":"double","default":"1.0","status_key":"runtime_consecutive_candle_threshold_boost","label":"Consecutive Candle Threshold Boost","kind":"number","min":0,"max":10,"step":0.1},{"name":"max_consecutive_candle_boosts","mql_type":"int","default":"3","status_key":"runtime_max_consecutive_candle_boosts","label":"Max Consecutive Candle Boosts","kind":"number","min":0,"max":100,"step":1},{"name":"enable_duplicate_distance_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_duplicate_distance_filter","label":"Enable Duplicate Distance Filter","kind":"bool"},{"name":"zone_points","mql_type":"double","default":"500","status_key":"runtime_zone_points","label":"Zone Points","kind":"number","min":0,"max":1000000,"step":1},{"name":"buy_duplicate_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_buy_duplicate_multiplier","label":"Buy Duplicate Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"sell_duplicate_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_sell_duplicate_multiplier","label":"Sell Duplicate Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"min_break_even_profit","mql_type":"double","default":"0.5","status_key":"runtime_min_break_even_profit","label":"Min Break Even Profit","kind":"number","min":0,"max":1000000,"step":0.1},{"name":"profit_threshold_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_profit_threshold_multiplier","label":"Profit Threshold Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"loss_threshold_multiplier","mql_type":"double","default":"2.0","status_key":"runtime_loss_threshold_multiplier","label":"Loss Threshold Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"min_buy_signal_score","mql_type":"double","default":"4.5","status_key":"runtime_min_buy_signal_score","label":"Min Buy Signal Score","kind":"number","min":0,"max":10,"step":0.1},{"name":"min_sell_signal_score","mql_type":"double","default":"4.5","status_key":"runtime_min_sell_signal_score","label":"Min Sell Signal Score","kind":"number","min":0,"max":10,"step":0.1}],"description":"Controls when fresh positions may open, order frequency, spread gating, lot size and duplicate-entry protection.","danger":false},{"name":"Signal / indicator behavior","controls":[{"name":"directional_body_lookback","mql_type":"int","default":"10","status_key":"runtime_directional_body_lookback","label":"Directional Body Lookback","kind":"number","min":1,"max":500,"step":1},{"name":"ema_fast_period","mql_type":"int","default":"5","status_key":"runtime_ema_fast_period","label":"EMA Fast Period","kind":"number","min":1,"max":500,"step":1},{"name":"ema_slow_period","mql_type":"int","default":"12","status_key":"runtime_ema_slow_period","label":"EMA Slow Period","kind":"number","min":1,"max":500,"step":1},{"name":"slope_lookback","mql_type":"int","default":"3","status_key":"runtime_slope_lookback","label":"Slope Lookback","kind":"number","min":1,"max":100,"step":1},{"name":"rsi_period","mql_type":"int","default":"8","status_key":"runtime_rsi_period","label":"RSI Period","kind":"number","min":2,"max":500,"step":1},{"name":"atr_period","mql_type":"int","default":"8","status_key":"runtime_atr_period","label":"ATR Period","kind":"number","min":1,"max":500,"step":1},{"name":"atr_avg_lookback","mql_type":"int","default":"10","status_key":"runtime_atr_avg_lookback","label":"ATR Avg Lookback","kind":"number","min":1,"max":500,"step":1},{"name":"min_vol_ratio_to_trade","mql_type":"double","default":"0.6","status_key":"runtime_min_vol_ratio_to_trade","label":"Min Vol Ratio To Trade","kind":"number","min":0,"max":10,"step":0.01},{"name":"impulse_lookback","mql_type":"int","default":"3","status_key":"runtime_impulse_lookback","label":"Impulse Lookback","kind":"number","min":1,"max":100,"step":1},{"name":"impulse_boost_weight","mql_type":"double","default":"1.0","status_key":"runtime_impulse_boost_weight","label":"Impulse Boost Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"signal_smoothing_candles","mql_type":"int","default":"2","status_key":"runtime_signal_smoothing_candles","label":"Signal Smoothing Candles","kind":"number","min":1,"max":10,"step":1},{"name":"current_candle_blend","mql_type":"double","default":"0.40","status_key":"runtime_current_candle_blend","label":"Current Candle Blend","kind":"number","min":0,"max":1,"step":0.01},{"name":"velocity_window","mql_type":"double","default":"2.0","status_key":"runtime_velocity_window","label":"Velocity Window","kind":"number","min":0.0001,"max":100,"step":0.1},{"name":"rsi_overbought","mql_type":"int","default":"80","status_key":"runtime_rsi_overbought","label":"RSI Overbought","kind":"number","min":0,"max":100,"step":1},{"name":"rsi_oversold","mql_type":"int","default":"20","status_key":"runtime_rsi_oversold","label":"RSI Oversold","kind":"number","min":0,"max":100,"step":1},{"name":"rsi_momentum_buy","mql_type":"int","default":"60","status_key":"runtime_rsi_momentum_buy","label":"RSI Momentum Buy","kind":"number","min":0,"max":100,"step":1},{"name":"rsi_momentum_sell","mql_type":"int","default":"40","status_key":"runtime_rsi_momentum_sell","label":"RSI Momentum Sell","kind":"number","min":0,"max":100,"step":1}],"description":"Controls indicator periods, smoothing, volatility gating and RSI behavior. EMA/RSI/ATR period changes trigger controlled indicator-handle rebuilds in Nyao.","danger":false},{"name":"Score weights","controls":[{"name":"trend_weight","mql_type":"double","default":"1.5","status_key":"runtime_trend_weight","label":"Trend Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"slope_weight","mql_type":"double","default":"1.5","status_key":"runtime_slope_weight","label":"Slope Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"momentum_base_weight","mql_type":"double","default":"1.0","status_key":"runtime_momentum_base_weight","label":"Momentum Base Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"momentum_trigger_weight","mql_type":"double","default":"0.5","status_key":"runtime_momentum_trigger_weight","label":"Momentum Trigger Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"body_momentum_weight","mql_type":"double","default":"1.5","status_key":"runtime_body_momentum_weight","label":"Body Momentum Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"chop_score_high","mql_type":"double","default":"2.0","status_key":"runtime_chop_score_high","label":"Chop Score High","kind":"number","min":0,"max":10,"step":0.1},{"name":"chop_score_med","mql_type":"double","default":"1.0","status_key":"runtime_chop_score_med","label":"Chop Score Med","kind":"number","min":0,"max":10,"step":0.1},{"name":"chop_score_low","mql_type":"double","default":"0.0","status_key":"runtime_chop_score_low","label":"Chop Score Low","kind":"number","min":0,"max":10,"step":0.1},{"name":"volatility_score_high","mql_type":"double","default":"1.0","status_key":"runtime_volatility_score_high","label":"Volatility Score High","kind":"number","min":0,"max":10,"step":0.1},{"name":"volatility_score_low","mql_type":"double","default":"0.0","status_key":"runtime_volatility_score_low","label":"Volatility Score Low","kind":"number","min":0,"max":10,"step":0.1},{"name":"peak_score_weight","mql_type":"double","default":"1.0","status_key":"runtime_peak_score_weight","label":"Peak Score Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"wick_rejection_weight","mql_type":"double","default":"1.0","status_key":"runtime_wick_rejection_weight","label":"Wick Rejection Weight","kind":"number","min":0,"max":10,"step":0.1},{"name":"min_body_ratio","mql_type":"double","default":"1.5","status_key":"runtime_min_body_ratio","label":"Min Body Ratio","kind":"number","min":0,"max":100,"step":0.1}],"description":"Changes how Nyao composes its signal score. Use carefully: these directly change what qualifies as a strong signal.","danger":false},{"name":"Limit entry","controls":[{"name":"enable_limit_entry","mql_type":"bool","default":"false","status_key":"runtime_enable_limit_entry","label":"Enable Limit Entry","kind":"bool"},{"name":"limit_entry_anchor","mql_type":"ENUM_LIMIT_ANCHOR","default":"LIMIT_ANCHOR_FIXED_ATR","status_key":"runtime_limit_entry_anchor","label":"Limit Entry Anchor","kind":"select","options":[{"value":0,"label":"Fixed ATR"},{"value":1,"label":"EMA"},{"value":2,"label":"Swing"},{"value":3,"label":"Smart"}]},{"name":"limit_entry_atr_fraction","mql_type":"double","default":"0.25","status_key":"runtime_limit_entry_atr_fraction","label":"Limit Entry ATR Fraction","kind":"number","min":0,"max":10,"step":0.01},{"name":"limit_entry_expiry_bars","mql_type":"int","default":"1","status_key":"runtime_limit_entry_expiry_bars","label":"Limit Entry Expiry Bars","kind":"number","min":0,"max":1000,"step":1},{"name":"limit_entry_cancel_on_flip","mql_type":"bool","default":"true","status_key":"runtime_limit_entry_cancel_on_flip","label":"Limit Entry Cancel On Flip","kind":"bool"}],"description":"Controls whether fresh entries use pending pullback orders instead of immediate market orders.","danger":false},{"name":"Signal dampening","controls":[{"name":"enable_signal_dampening","mql_type":"bool","default":"true","status_key":"runtime_enable_signal_dampening","label":"Enable Signal Dampening","kind":"bool"},{"name":"max_losing_positions_same_dir","mql_type":"int","default":"2","status_key":"runtime_max_losing_positions_same_dir","label":"Max Losing Positions Same Dir","kind":"number","min":0,"max":50,"step":1},{"name":"losing_pos_score_penalty","mql_type":"double","default":"1.5","status_key":"runtime_losing_pos_score_penalty","label":"Losing Pos Score Penalty","kind":"number","min":0,"max":10,"step":0.1},{"name":"drawdown_threshold_pct","mql_type":"double","default":"3.0","status_key":"runtime_drawdown_threshold_pct","label":"Drawdown Threshold %","kind":"number","min":0,"max":100,"step":0.1},{"name":"drawdown_score_boost","mql_type":"double","default":"2.0","status_key":"runtime_drawdown_score_boost","label":"Drawdown Score Boost","kind":"number","min":0,"max":10,"step":0.1},{"name":"consecutive_losses_before_cooldown","mql_type":"int","default":"3","status_key":"runtime_consecutive_losses_before_cooldown","label":"Consecutive Losses Before Cooldown","kind":"number","min":0,"max":100,"step":1},{"name":"consecutive_loss_cooldown_bars","mql_type":"int","default":"3","status_key":"runtime_consecutive_loss_cooldown_bars","label":"Consecutive Loss Cooldown Bars","kind":"number","min":0,"max":1000,"step":1}],"description":"Reduces repeated entries during drawdown, losing-position clusters and consecutive-loss periods.","danger":false},{"name":"Loss / health management","controls":[{"name":"enable_loss_management","mql_type":"bool","default":"true","status_key":"runtime_enable_loss_management","label":"Enable Loss Management","kind":"bool"},{"name":"max_holding_loss_positions","mql_type":"int","default":"2","status_key":"runtime_max_holding_loss_positions","label":"Max Holding Loss Positions","kind":"number","min":0,"max":50,"step":1},{"name":"min_health_score","mql_type":"double","default":"0.40","status_key":"runtime_min_health_score","label":"Min Health Score","kind":"number","min":0,"max":1,"step":0.01},{"name":"max_adverse_atr","mql_type":"double","default":"1.5","status_key":"runtime_max_adverse_atr","label":"Max Adverse ATR","kind":"number","min":0,"max":100,"step":0.1},{"name":"health_trend_weight","mql_type":"double","default":"0.40","status_key":"runtime_health_trend_weight","label":"Health Trend Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_rsi_weight","mql_type":"double","default":"0.25","status_key":"runtime_health_rsi_weight","label":"Health RSI Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_atr_weight","mql_type":"double","default":"0.25","status_key":"runtime_health_atr_weight","label":"Health ATR Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_swing_weight","mql_type":"double","default":"0.10","status_key":"runtime_health_swing_weight","label":"Health Swing Weight","kind":"number","min":0,"max":100,"step":0.01},{"name":"health_rsi_buy_min","mql_type":"double","default":"40.0","status_key":"runtime_health_rsi_buy_min","label":"Health RSI Buy Min","kind":"number","min":0,"max":100,"step":0.1},{"name":"health_rsi_sell_max","mql_type":"double","default":"60.0","status_key":"runtime_health_rsi_sell_max","label":"Health RSI Sell Max","kind":"number","min":0,"max":100,"step":0.1},{"name":"health_swing_lookback","mql_type":"int","default":"20","status_key":"runtime_health_swing_lookback","label":"Health Swing Lookback","kind":"number","min":1,"max":1000,"step":1},{"name":"health_grace_bars","mql_type":"int","default":"2","status_key":"runtime_health_grace_bars","label":"Health Grace Bars","kind":"number","min":0,"max":1000,"step":1},{"name":"enable_partial_close","mql_type":"bool","default":"true","status_key":"runtime_enable_partial_close","label":"Enable Partial Close","kind":"bool"},{"name":"partial_close75_pct","mql_type":"double","default":"0.25","status_key":"runtime_partial_close75_pct","label":"Partial Close 75 %","kind":"number","min":0,"max":1,"step":0.01},{"name":"partial_close50_pct","mql_type":"double","default":"0.50","status_key":"runtime_partial_close50_pct","label":"Partial Close 50 %","kind":"number","min":0,"max":1,"step":0.01},{"name":"partial_close25_pct","mql_type":"double","default":"1.00","status_key":"runtime_partial_close25_pct","label":"Partial Close 25 %","kind":"number","min":0,"max":1,"step":0.01},{"name":"enable_health_sl_tightening","mql_type":"bool","default":"true","status_key":"runtime_enable_health_sl_tightening","label":"Enable Health SL Tightening","kind":"bool"},{"name":"sl_tighten_atr_multiplier","mql_type":"double","default":"2.0","status_key":"runtime_sl_tighten_atr_multiplier","label":"SL Tighten ATR Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"sl_tighten_min_health_pct","mql_type":"double","default":"0.50","status_key":"runtime_sl_tighten_min_health_pct","label":"SL Tighten Min Health %","kind":"number","min":0,"max":1,"step":0.01},{"name":"enable_break_even_on_spread","mql_type":"bool","default":"true","status_key":"runtime_enable_break_even_on_spread","label":"Enable Break Even On Spread","kind":"bool"},{"name":"break_even_spread_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_break_even_spread_multiplier","label":"Break Even Spread Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"enable_virtual_sl_reentry","mql_type":"bool","default":"true","status_key":"runtime_enable_virtual_sl_reentry","label":"Enable Virtual SL Reentry","kind":"bool"},{"name":"reentry_respects_new_bar_gate","mql_type":"bool","default":"false","status_key":"runtime_reentry_respects_new_bar_gate","label":"Reentry Respects New Bar Gate","kind":"bool"},{"name":"reentry_min_signal_pct","mql_type":"double","default":"0.75","status_key":"runtime_reentry_min_signal_pct","label":"Reentry Min Signal %","kind":"number","min":0,"max":2,"step":0.01},{"name":"enable_profit_offset_sl","mql_type":"bool","default":"true","status_key":"runtime_enable_profit_offset_sl","label":"Enable Profit Offset SL","kind":"bool"},{"name":"consecutive_wins_required","mql_type":"int","default":"3","status_key":"runtime_consecutive_wins_required","label":"Consecutive Wins Required","kind":"number","min":0,"max":100,"step":1},{"name":"min_offset_profit","mql_type":"double","default":"1.0","status_key":"runtime_min_offset_profit","label":"Min Offset Profit","kind":"number","min":0,"max":1000000,"step":0.1}],"description":"Controls position health scoring, partial closes, break-even behavior, SL tightening and virtual-SL re-entry.","danger":true},{"name":"Hedge chain","controls":[{"name":"enable_hedge_chain","mql_type":"bool","default":"true","status_key":"runtime_enable_hedge_chain","label":"Enable Hedge Chain","kind":"bool"},{"name":"hedge_trigger_atr","mql_type":"double","default":"1.5","status_key":"runtime_hedge_trigger_atr","label":"Hedge Trigger ATR","kind":"number","min":0,"max":100,"step":0.1},{"name":"hedge_require_signal","mql_type":"bool","default":"true","status_key":"runtime_hedge_require_signal","label":"Hedge Require Signal","kind":"bool"},{"name":"hedge_min_signal_score","mql_type":"double","default":"4.5","status_key":"runtime_hedge_min_signal_score","label":"Hedge Min Signal Score","kind":"number","min":0,"max":10,"step":0.1},{"name":"hedge_auto_lot","mql_type":"bool","default":"true","status_key":"runtime_hedge_auto_lot","label":"Hedge Auto Lot","kind":"bool"},{"name":"hedge_recovery_atr","mql_type":"double","default":"1.0","status_key":"runtime_hedge_recovery_atr","label":"Hedge Recovery ATR","kind":"number","min":0,"max":100,"step":0.1},{"name":"hedge_lot_multiplier","mql_type":"double","default":"2.0","status_key":"runtime_hedge_lot_multiplier","label":"Hedge Lot Multiplier","kind":"number","min":0,"max":20,"step":0.1},{"name":"hedge_max_lot","mql_type":"double","default":"0.10","status_key":"runtime_hedge_max_lot","label":"Hedge Max Lot","kind":"number","min":0.01,"max":5,"step":0.01},{"name":"hedge_recovery_pct","mql_type":"double","default":"110.0","status_key":"runtime_hedge_recovery_pct","label":"Hedge Recovery %","kind":"number","min":0,"max":1000,"step":1},{"name":"hedge_roll_min_profit","mql_type":"double","default":"0.5","status_key":"runtime_hedge_roll_min_profit","label":"Hedge Roll Min Profit","kind":"number","min":0,"max":1000000,"step":0.1},{"name":"hedge_cycle_levels","mql_type":"int","default":"2","status_key":"runtime_hedge_cycle_levels","label":"Hedge Cycle Levels","kind":"number","min":1,"max":20,"step":1},{"name":"enable_hedge_cycle_reset","mql_type":"bool","default":"false","status_key":"runtime_enable_hedge_cycle_reset","label":"Enable Hedge Cycle Reset","kind":"bool"},{"name":"hedge_cycle_partial_pct","mql_type":"double","default":"50.0","status_key":"runtime_hedge_cycle_partial_pct","label":"Hedge Cycle Partial %","kind":"number","min":0,"max":100,"step":1},{"name":"hedge_max_cycles","mql_type":"int","default":"3","status_key":"runtime_hedge_max_cycles","label":"Hedge Max Cycles","kind":"number","min":0,"max":100,"step":1},{"name":"hedge_max_chain_loss_usd","mql_type":"double","default":"0.0","status_key":"runtime_hedge_max_chain_loss_usd","label":"Hedge Max Chain Loss USD","kind":"number","min":0,"max":100000000,"step":1},{"name":"hedge_max_chain_loss_pct","mql_type":"double","default":"0.0","status_key":"runtime_hedge_max_chain_loss_pct","label":"Hedge Max Chain Loss %","kind":"number","min":0,"max":100,"step":0.1},{"name":"hedge_clear_root_sl","mql_type":"bool","default":"true","status_key":"runtime_hedge_clear_root_sl","label":"Hedge Clear Root SL","kind":"bool"},{"name":"hedge_trail_atr","mql_type":"double","default":"0.5","status_key":"runtime_hedge_trail_atr","label":"Hedge Trail ATR","kind":"number","min":0,"max":100,"step":0.1}],"description":"High-risk recovery subsystem. Changes can affect existing recovery chains and exposure.","danger":true},{"name":"Dynamic sizing","controls":[{"name":"enable_dynamic_lots","mql_type":"bool","default":"true","status_key":"runtime_enable_dynamic_lots","label":"Enable Dynamic Lots","kind":"bool"},{"name":"equity_drop_percent","mql_type":"double","default":"5.0","status_key":"runtime_equity_drop_percent","label":"Equity Drop Percent","kind":"number","min":0,"max":100,"step":0.1},{"name":"max_equity_drop_lot_steps","mql_type":"int","default":"2","status_key":"runtime_max_equity_drop_lot_steps","label":"Max Equity Drop Lot Steps","kind":"number","min":0,"max":100,"step":1},{"name":"min_signal_strength_for_lot","mql_type":"double","default":"8.0","status_key":"runtime_min_signal_strength_for_lot","label":"Min Signal Strength For Lot","kind":"number","min":0,"max":10,"step":0.1},{"name":"lot_step_size","mql_type":"double","default":"0.01","status_key":"runtime_lot_step_size","label":"Lot Step Size","kind":"number","min":0,"max":5,"step":0.01},{"name":"max_lot_size","mql_type":"double","default":"0.05","status_key":"runtime_max_lot_size","label":"Max Lot Size","kind":"number","min":0.01,"max":5,"step":0.01}],"description":"Controls drawdown/signal-based lot increases. Changes can alter future position size.","danger":true},{"name":"Equity protection","controls":[{"name":"enable_basket_stop","mql_type":"bool","default":"true","status_key":"runtime_enable_basket_stop","label":"Enable Basket Stop","kind":"bool"},{"name":"max_basket_loss_pct","mql_type":"double","default":"8.0","status_key":"runtime_max_basket_loss_pct","label":"Max Basket Loss %","kind":"number","min":0,"max":100,"step":0.1},{"name":"min_equity_percent","mql_type":"double","default":"70.0","status_key":"runtime_min_equity_percent","label":"Min Equity Percent","kind":"number","min":0,"max":1000,"step":0.1},{"name":"max_drawdown_from_peak","mql_type":"double","default":"0","status_key":"runtime_max_drawdown_from_peak","label":"Max Drawdown From Peak","kind":"number","min":0,"max":100000000,"step":1},{"name":"pause_minutes","mql_type":"int","default":"5","status_key":"runtime_pause_minutes","label":"Pause Minutes","kind":"number","min":0,"max":1440,"step":1},{"name":"pause_minutes_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_pause_minutes_multiplier","label":"Pause Minutes Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"max_pause_minutes","mql_type":"int","default":"120","status_key":"runtime_max_pause_minutes","label":"Max Pause Minutes","kind":"number","min":0,"max":10080,"step":1},{"name":"max_min_equity_triggers","mql_type":"int","default":"0","status_key":"runtime_max_min_equity_triggers","label":"Max Min Equity Triggers","kind":"number","min":0,"max":1000,"step":1},{"name":"reset_on_new_peak","mql_type":"bool","default":"true","status_key":"runtime_reset_on_new_peak","label":"Reset On New Peak","kind":"bool"},{"name":"target_equity","mql_type":"double","default":"0","status_key":"runtime_target_equity","label":"Target Equity","kind":"number","min":0,"max":1000000000,"step":1},{"name":"minimum_equity","mql_type":"double","default":"20","status_key":"runtime_minimum_equity","label":"Minimum Equity","kind":"number","min":0,"max":1000000000,"step":1}],"description":"Account-level circuit breakers, basket loss limits, trading pauses and equity targets.","danger":true},{"name":"TP / SL / risk reward","controls":[{"name":"enable_take_profit","mql_type":"bool","default":"false","status_key":"runtime_enable_take_profit","label":"Enable Take Profit","kind":"bool"},{"name":"tp_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_DOLLAR","status_key":"runtime_tp_input_type","label":"TP Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"tp_value","mql_type":"double","default":"10.0","status_key":"runtime_tp_value","label":"TP Value","kind":"number","min":0,"max":100000000,"step":0.1},{"name":"enable_stop_loss","mql_type":"bool","default":"true","status_key":"runtime_enable_stop_loss","label":"Enable Stop Loss","kind":"bool"},{"name":"sl_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_PERCENT","status_key":"runtime_sl_input_type","label":"SL Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"sl_value","mql_type":"double","default":"10.0","status_key":"runtime_sl_value","label":"SL Value","kind":"number","min":0,"max":100000000,"step":0.1},{"name":"enable_risk_reward","mql_type":"bool","default":"false","status_key":"runtime_enable_risk_reward","label":"Enable Risk Reward","kind":"bool"},{"name":"rr_risk_mode","mql_type":"ENUM_RR_RISK_MODE","default":"RR_RISK_ATR","status_key":"runtime_rr_risk_mode","label":"R:R Risk Mode","kind":"select","options":[{"value":0,"label":"Manual"},{"value":1,"label":"ATR"}]},{"name":"rr_risk_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_POINTS","status_key":"runtime_rr_risk_input_type","label":"R:R Risk Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"rr_risk_value","mql_type":"double","default":"200.0","status_key":"runtime_rr_risk_value","label":"R:R Risk Value","kind":"number","min":0,"max":100000000,"step":0.1},{"name":"rr_atr_multiplier","mql_type":"double","default":"1.5","status_key":"runtime_rr_atr_multiplier","label":"R:R ATR Multiplier","kind":"number","min":0,"max":100,"step":0.1},{"name":"risk_reward_ratio","mql_type":"double","default":"1.5","status_key":"runtime_risk_reward_ratio","label":"Risk Reward Ratio","kind":"number","min":0,"max":100,"step":0.1}],"description":"Controls initial take-profit, stop-loss and independent risk:reward placement.","danger":true},{"name":"Trailing","controls":[{"name":"enable_trailing","mql_type":"bool","default":"true","status_key":"runtime_enable_trailing","label":"Enable Trailing","kind":"bool"},{"name":"trailing_enable_break_even_lock","mql_type":"bool","default":"true","status_key":"runtime_trailing_enable_break_even_lock","label":"Trailing Enable Break Even Lock","kind":"bool"},{"name":"trailing_sl_on_profitable_only","mql_type":"bool","default":"true","status_key":"runtime_trailing_sl_on_profitable_only","label":"Trailing SL On Profitable Only","kind":"bool"},{"name":"enable_adaptive_tp","mql_type":"bool","default":"true","status_key":"runtime_enable_adaptive_tp","label":"Enable Adaptive TP","kind":"bool"},{"name":"enable_adaptive_sl","mql_type":"bool","default":"true","status_key":"runtime_enable_adaptive_sl","label":"Enable Adaptive SL","kind":"bool"},{"name":"ts_input_type","mql_type":"ENUM_INPUT_TYPE","default":"INPUT_DOLLAR","status_key":"runtime_ts_input_type","label":"Ts Input Type","kind":"select","options":[{"value":0,"label":"Dollar"},{"value":1,"label":"Percent"},{"value":2,"label":"Points"}]},{"name":"trailing_distance_value","mql_type":"double","default":"0.2","status_key":"runtime_trailing_distance_value","label":"Trailing Distance Value","kind":"number","min":0,"max":100000000,"step":0.01},{"name":"trailing_value_multiplier","mql_type":"double","default":"0.2","status_key":"runtime_trailing_value_multiplier","label":"Trailing Value Multiplier","kind":"number","min":0,"max":100,"step":0.01}],"description":"Controls trailing, break-even locks and adaptive exit behavior.","danger":true},{"name":"Operational filters / diagnostics","controls":[{"name":"enable_discord_alerts","mql_type":"bool","default":"false","status_key":"runtime_enable_discord_alerts","label":"Enable Discord Alerts","kind":"bool"},{"name":"enable_trading_hours","mql_type":"bool","default":"false","status_key":"runtime_enable_trading_hours","label":"Enable Trading Hours","kind":"bool"},{"name":"trading_start_time","mql_type":"string","default":"\"00:00\"","status_key":"runtime_trading_start_time","label":"Trading Start Time","kind":"time"},{"name":"trading_end_time","mql_type":"string","default":"\"23:59\"","status_key":"runtime_trading_end_time","label":"Trading End Time","kind":"time"},{"name":"enable_reports","mql_type":"bool","default":"true","status_key":"runtime_enable_reports","label":"Enable Reports","kind":"bool"},{"name":"send_report_every_hour","mql_type":"int","default":"1","status_key":"runtime_send_report_every_hour","label":"Send Report Every Hour","kind":"number","min":1,"max":168,"step":1},{"name":"enable_market_close_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_market_close_filter","label":"Enable Market Close Filter","kind":"bool"},{"name":"minutes_before_close","mql_type":"int","default":"30","status_key":"runtime_minutes_before_close","label":"Minutes Before Close","kind":"number","min":0,"max":1440,"step":1},{"name":"enable_news_filter","mql_type":"bool","default":"true","status_key":"runtime_enable_news_filter","label":"Enable News Filter","kind":"bool"},{"name":"news_minutes_before","mql_type":"int","default":"30","status_key":"runtime_news_minutes_before","label":"News Minutes Before","kind":"number","min":0,"max":1440,"step":1},{"name":"news_minutes_after","mql_type":"int","default":"30","status_key":"runtime_news_minutes_after","label":"News Minutes After","kind":"number","min":0,"max":1440,"step":1},{"name":"enable_leverage_pause","mql_type":"bool","default":"true","status_key":"runtime_enable_leverage_pause","label":"Enable Leverage Pause","kind":"bool"},{"name":"enable_logging","mql_type":"bool","default":"false","status_key":"runtime_enable_logging","label":"Enable Logging","kind":"bool"}],"description":"Trading hours, market-close/news/leverage filters plus reports, alerts and logging.","danger":false}]'''
)


def _model_dump(model: Any, *, exclude_none: bool = False, exclude_unset: bool = False) -> dict:
    return model.model_dump(
        mode="json",
        exclude_none=exclude_none,
        exclude_unset=exclude_unset,
    )



# ---------------------------------------------------------------------
# Atlas v1.1 multi-symbol compatibility layer.
#
# Nyao instances now use:
#   MQL5/Files/Atlas/<SYMBOL>/commands.json
#   MQL5/Files/Atlas/<SYMBOL>/status.json
#
# The existing Atlas intelligence code is reused unchanged, while its
# persisted state is redirected into data/symbols/<SYMBOL>/ per request.
# ---------------------------------------------------------------------
_LEGACY_COMMANDS_FILE = COMMANDS_FILE
_LEGACY_STATUS_FILE = STATUS_FILE
_ATLAS_BRIDGE_DIR = STATUS_FILE.parent
_SYMBOL_REQUEST_LOCK = asyncio.Lock()


def _requested_symbol(request: Request) -> str | None:
    explicit = request.query_params.get("symbol")
    if explicit:
        return explicit

    return resolve_default_symbol(
        _ATLAS_BRIDGE_DIR,
        legacy_status_file=_LEGACY_STATUS_FILE,
    )


@app.middleware("http")
async def atlas_symbol_namespace_middleware(
    request: Request,
    call_next,
):
    global COMMANDS_FILE, STATUS_FILE

    # Dashboard HTML, health, and symbol discovery are not symbol-scoped.
    if (
        not request.url.path.startswith("/api/v1/")
        or request.url.path == "/api/v1/atlas/symbols"
    ):
        return await call_next(request)

    symbol = _requested_symbol(request)
    if not symbol:
        return await call_next(request)

    async with _SYMBOL_REQUEST_LOCK:
        previous_command_file = COMMANDS_FILE
        previous_status_file = STATUS_FILE

        command_file, status_file, _runtime_file = symbol_bridge_paths(
            _ATLAS_BRIDGE_DIR,
            symbol,
        )
        command_file.parent.mkdir(parents=True, exist_ok=True)

        COMMANDS_FILE = command_file
        STATUS_FILE = status_file

        try:
            with scoped_symbol_storage(symbol):
                with scoped_account_performance(read_json(status_file) or {}):
                    response = await call_next(request)
                    response.headers["X-Atlas-Symbol"] = str(symbol)
                    return response
        finally:
            COMMANDS_FILE = previous_command_file
            STATUS_FILE = previous_status_file


@app.get("/api/v1/atlas/symbols")
def get_atlas_symbols() -> dict[str, Any]:
    symbols = discover_bridge_symbols(_ATLAS_BRIDGE_DIR)
    default_symbol = resolve_default_symbol(
        _ATLAS_BRIDGE_DIR,
        legacy_status_file=_LEGACY_STATUS_FILE,
    )
    return {
        "multi_symbol_version": "1.1",
        "symbols": symbols,
        "symbol_count": len(symbols),
        "default_symbol": default_symbol,
        "bridge_root": str(_ATLAS_BRIDGE_DIR),
        "storage_model": "ONE_BRAIN_SEPARATE_SYMBOL_STATE",
    }


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Welcome to Atlas"}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "running",
        "version": "1.30.43",
        "strategy": "nyao",
        "execution_model": "account_environment_agnostic",
    }


@app.get("/api/v1/nyao/command")
def get_nyao_command() -> dict:
    command_data = read_json(COMMANDS_FILE)

    if not command_data:
        status_data = read_json(STATUS_FILE) or {}
        runtime = {
            key.removeprefix("runtime_"): value
            for key, value in status_data.items()
            if key.startswith("runtime_")
        }

        seed: dict[str, Any] = {
            **runtime,
            "command_version": int(
                status_data.get("applied_command_version") or 0
            ),
            "policy_epoch": int(
                status_data.get("policy_epoch") or 1
            ),
            "updated_at": datetime.now(timezone.utc),
        }

        # Preserve current bridge enable flags if Nyao reports them.
        for source_key, target_key in (
            ("atlas_enabled", "enabled"),
            ("atlas_buy_enabled", "buy_enabled"),
            ("atlas_sell_enabled", "sell_enabled"),
        ):
            if source_key in status_data:
                seed[target_key] = status_data[source_key]

        try:
            command = Command.model_validate(seed)
        except Exception:
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

    # Atlas owns command/policy metadata.
    incoming.pop("command_version", None)
    incoming.pop("policy_epoch", None)
    incoming.pop("updated_at", None)

    merged = {**existing, **incoming}
    previous_version = int(existing.get("command_version", 0))
    previous_policy_epoch = int(existing.get("policy_epoch", 1) or 1)

    metadata_keys = {"command_version", "policy_epoch", "updated_at"}
    before_material = {k: v for k, v in existing.items() if k not in metadata_keys}
    after_material = {k: v for k, v in merged.items() if k not in metadata_keys}
    material_change = before_material != after_material

    merged["command_version"] = previous_version + 1
    merged["policy_epoch"] = previous_policy_epoch + (1 if material_change else 0)
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


@app.get("/api/v1/atlas/market-candles")
def get_market_candles(include_bars: bool = False) -> dict[str, Any]:
    """Validate Nyao's symbol-scoped, closed-bar M30/H1/H4 export."""
    status_data = read_json(STATUS_FILE) or {}
    expected_symbol = str(status_data.get("symbol") or "").strip() or None
    candle_file = STATUS_FILE.parent / "candles.json"
    payload, read_error = load_market_candle_export(candle_file)
    return build_market_candle_report(
        payload,
        source_path=candle_file,
        expected_symbol=expected_symbol,
        include_bars=include_bars,
        read_error=read_error,
    )


@app.get("/api/v1/atlas/zone-map")
def get_zone_map() -> dict[str, Any]:
    """Build an analysis-only deterministic zone map from validated candles."""
    status_data = read_json(STATUS_FILE) or {}
    expected_symbol = str(status_data.get("symbol") or "").strip() or None
    candle_file = STATUS_FILE.parent / "candles.json"
    payload, read_error = load_market_candle_export(candle_file)
    candle_report = build_market_candle_report(
        payload,
        source_path=candle_file,
        expected_symbol=expected_symbol,
        include_bars=True,
        read_error=read_error,
    )
    return build_zone_map(candle_report)


def _persist_zone_campaign(
    plan: dict[str, Any],
    status_data: dict[str, Any],
    directive_path: Path,
) -> dict[str, Any]:
    """Persist one immutable broker campaign and align the API snapshot to it."""
    directive = persist_zone_execution_directive(
        plan,
        directive_path,
        status_data=status_data,
    )
    if directive.get("campaign_locked"):
        snapshot = directive.get("plan_snapshot")
        if isinstance(snapshot, dict) and snapshot:
            plan.clear()
            plan.update(snapshot)
        else:
            active_plan = dict(plan.get("zone_plan") or {})
            active_plan.update({
                "plan_id": directive.get("plan_id"),
                "side": directive.get("side"),
                "stop_loss": directive.get("stop_loss"),
                "entries": [
                    {
                        "leg": leg,
                        "entry_price": directive.get(f"entry_{leg}_price"),
                        "risk_allocation_pct": directive.get(f"entry_{leg}_risk_pct"),
                        "order_type": (
                            "MARKET_ON_CONFIRMATION"
                            if leg == 1
                            else "VIRTUAL_MARKET_ON_TOUCH"
                        ),
                    }
                    for leg in range(1, 4)
                ],
                "take_profits": [
                    {
                        "target": leg,
                        "price": directive.get(f"tp_{leg}_price"),
                        "close_allocation_pct": directive.get(f"tp_{leg}_close_pct"),
                    }
                    for leg in range(1, 4)
                ],
            })
            risk = dict(active_plan.get("risk") or {})
            campaign_risk_pct = float(directive.get("account_risk_pct") or 0.0)
            risk["account_risk_pct"] = campaign_risk_pct
            campaign_equity = float(
                status_data.get("equity") or status_data.get("balance") or 0.0
            )
            risk["maximum_loss_account_currency"] = round(
                campaign_equity * campaign_risk_pct / 100.0,
                2,
            )
            active_plan["risk"] = risk
            plan["zone_plan"] = active_plan
            plan["zone_map_id"] = directive.get("zone_map_id")
        source_zone_invalidated = bool(directive.get("source_zone_invalidated", False))
        plan["state"] = (
            "ZONE_CAMPAIGN_INVALIDATED_MANAGEMENT"
            if source_zone_invalidated
            else "ZONE_CAMPAIGN_ACTIVE"
        )
        plan["source_zone_invalidated"] = source_zone_invalidated
        plan["source_zone_invalidation_reason"] = directive.get("source_zone_invalidation_reason") or ""
        plan["source_zone_invalidated_at_epoch"] = directive.get("source_zone_invalidated_at_epoch") or 0
        plan["source_zone_invalidating_close"] = directive.get("source_zone_invalidating_close") or 0.0
        plan["mode"] = "ZONE_MODE"
        plan["ordinary_scalping_allowed"] = False
        preview = dict(plan.get("directive_preview") or {})
        preview.update({
            "suspend_ordinary_scalp_entries": True,
            "zone_entry_allowed": not source_zone_invalidated,
            "plan_id": directive.get("plan_id"),
            "source_zone_invalidated": source_zone_invalidated,
        })
        plan["directive_preview"] = preview
        spread_assessment = (
            ((plan.get("zone_plan") or {}).get("confirmation") or {}).get(
                "spread_assessment"
            )
            or {}
        )
        if source_zone_invalidated:
            plan["blockers"] = [
                "SOURCE ZONE INVALIDATED: no new campaign layers may open. "
                "Existing exposure remains under locked position/recovery management until flat."
            ]
        else:
            plan["blockers"] = (
                [
                    "Active position management continues; new virtual zone layers "
                    "wait until the dedicated zone spread gate is clear."
                ]
                if spread_assessment.get("zone_spread_within_limit") is False
                else []
            )
        plan["campaign_lock"] = {
            "active": True,
            "plan_id": directive.get("plan_id"),
            "reason": directive.get("campaign_lock_reason"),
            "source_zone_invalidated": source_zone_invalidated,
        }
    else:
        plan["campaign_lock"] = {"active": False}
    return directive


@app.get("/api/v1/atlas/zone-execution-plan")
def get_zone_execution_plan() -> dict[str, Any]:
    """Build a non-executing scalp/zone mode directive from live Nyao state."""
    status_data = read_json(STATUS_FILE) or {}
    expected_symbol = str(status_data.get("symbol") or "").strip() or None
    candle_file = STATUS_FILE.parent / "candles.json"
    payload, read_error = load_market_candle_export(candle_file)
    candle_report = build_market_candle_report(
        payload,
        source_path=candle_file,
        expected_symbol=expected_symbol,
        include_bars=True,
        read_error=read_error,
    )
    capital_sizing = build_capital_sizing_plan(
        status_data,
        get_trade_outcomes(closed_limit=50, include_active=False),
    )
    plan = build_zone_execution_plan(
        build_zone_map(candle_report), status_data, capital_sizing
    )
    directive_path = STATUS_FILE.parent / "zone_directive.json"
    _persist_zone_campaign(
        plan,
        status_data,
        directive_path,
    )
    return plan


@app.get("/api/v1/atlas/zone-policy")
def get_atlas_zone_policy() -> dict[str, Any]:
    return get_zone_policy()


@app.put("/api/v1/atlas/zone-policy")
def update_atlas_zone_policy(request: ZonePolicyUpdateRequest) -> dict[str, Any]:
    try:
        return apply_zone_policy(
            request.policy.model_dump(mode="json"),
            source=request.source,
            expected_current_epoch=request.expected_current_epoch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    outcome_result = track_trade_outcomes(
        status_payload,
        intelligence,
    )
    shadow_policy = build_shadow_policy(
        status_payload,
        intelligence,
    )
    shadow_history = record_shadow_policy(
        shadow_policy,
    )
    management_policy_diagnostics = build_position_management_policy_diagnostics(
        status_payload,
    )
    shadow_epoch_divergence = build_shadow_epoch_divergence(
        status_payload,
        shadow_policy,
    )
    shadow_evaluation = evaluate_shadow_policies(
        recent_limit=50,
    )
    shadow_replay = run_shadow_replay(
        recent_limit=100,
    )
    policy_decision = build_policy_decision(
        status_payload,
        intelligence,
        shadow_policy,
        shadow_evaluation=shadow_evaluation,
        shadow_replay=shadow_replay,
    )
    policy_decision_history = record_policy_decision(
        policy_decision,
    )
    advisory_proposal = build_advisory_policy_proposal(
        policy_decision,
    )
    advisory_proposal_persistence = persist_advisory_policy_proposal(
        advisory_proposal,
    )

    intelligence["history"] = history_result
    intelligence["outcomes"] = outcome_result
    intelligence["shadow_policy"] = shadow_policy
    intelligence["shadow_history"] = shadow_history
    intelligence["management_policy_diagnostics"] = management_policy_diagnostics
    intelligence["shadow_epoch_divergence"] = shadow_epoch_divergence
    intelligence["policy_decision"] = policy_decision
    intelligence["policy_decision_history"] = policy_decision_history
    intelligence["advisory_proposal"] = advisory_proposal
    intelligence["advisory_proposal_persistence"] = (
        advisory_proposal_persistence
    )
    return intelligence


@app.get("/api/v1/atlas/management-policy-diagnostics")
def get_management_policy_diagnostics() -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )
    status = Status.model_validate(status_data)
    return build_position_management_policy_diagnostics(
        status.model_dump(mode="json"),
    )


@app.get("/api/v1/atlas/shadow-epoch-divergence")
def get_shadow_epoch_divergence(
    test_control: str | None = None,
    test_value: str | None = None,
) -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)
    shadow_policy = build_shadow_policy(
        status_payload,
        intelligence,
    )

    coerced_value = None
    if test_control is not None:
        if test_value is None:
            raise HTTPException(
                status_code=422,
                detail="test_value is required when test_control is supplied.",
            )
        current_runtime_value = status_payload.get(f"runtime_{test_control}")
        if current_runtime_value is None:
            raise HTTPException(
                status_code=422,
                detail=f"{test_control!r} is not present in the current Nyao runtime.",
            )
        try:
            coerced_value = coerce_shadow_test_value(
                test_value,
                current_runtime_value,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return build_shadow_epoch_divergence(
            status_payload,
            shadow_policy,
            test_control=test_control,
            test_value=coerced_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/atlas/policy-decision")
def get_atlas_policy_decision() -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)
    shadow_policy = build_shadow_policy(
        status_payload,
        intelligence,
    )
    shadow_evaluation = evaluate_shadow_policies(
        recent_limit=50,
    )
    shadow_replay = run_shadow_replay(
        recent_limit=100,
    )

    decision = build_policy_decision(
        status_payload,
        intelligence,
        shadow_policy,
        shadow_evaluation=shadow_evaluation,
        shadow_replay=shadow_replay,
    )
    history = record_policy_decision(decision)
    proposal = build_advisory_policy_proposal(decision)
    proposal_persistence = persist_advisory_policy_proposal(
        proposal,
    )
    active_llm = _find_current_llm_advisory_proposal(
        status_payload,
        read_json(COMMANDS_FILE) or {},
    )
    active_proposal = active_llm["proposal"] if active_llm else proposal
    review_reconciliation = reconcile_advisory_review_state(
        active_proposal,
    )

    return {
        "decision": decision,
        "history": history,
        "advisory_proposal": active_proposal,
        "deterministic_advisory_proposal": proposal,
        "active_llm_context": active_llm,
        "advisory_proposal_persistence": proposal_persistence,
        "advisory_review_reconciliation": review_reconciliation,
    }


def _find_current_llm_advisory_proposal(
    status_payload: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any] | None:
    pending = get_pending_autonomous_policy()
    pending_proposal = pending.get("advisory") or {}
    pending_account = str(pending_proposal.get("account_fingerprint") or "")
    live_account = str(account_identity(status_payload).get("fingerprint") or "")
    pending_baseline_epoch = int(
        pending_proposal.get("current_policy_epoch") or 0
    )
    command_epoch = int(current_command.get("policy_epoch") or 0)
    if (
        pending.get("status") == "PENDING_MODE_BOUNDARY"
        and pending_proposal.get("mode") == "LLM_POLICY_PROPOSAL"
        and pending_account
        and pending_account == live_account
        and pending_baseline_epoch == command_epoch
    ):
        return {
            "proposal": pending_proposal,
            "context_status": {
                "current": True,
                "phase": "PRE_APPLY",
                "reason": "PENDING_MODE_BOUNDARY",
                "command_policy_epoch": command_epoch,
                "pending_since": pending.get("queued_at"),
            },
        }
    llm_candidates = [
        proposal
        for proposal in reversed(get_all_advisory_policy_proposals())
        if proposal.get("mode") == "LLM_POLICY_PROPOSAL"
    ]
    for proposal in llm_candidates:
        context_status = llm_advisory_context_status(
            proposal,
            current_status=status_payload,
            current_command=current_command,
        )
        approval_status = (proposal.get("approval") or {}).get("status")
        active_pre_apply = (
            context_status.get("phase") == "PRE_APPLY"
            and approval_status in {"NOT_REQUESTED", "PENDING_APPROVAL", "APPROVED"}
        )
        # Applied proposals remain the current policy record even after their
        # one-time approval expires; hiding them caused the dashboard to fall
        # back to a fresh "ready for human" deterministic proposal.
        applied = context_status.get("phase") == "APPLYING_OR_APPLIED"
        if context_status.get("current") and (active_pre_apply or applied):
            return {"proposal": proposal, "context_status": context_status}
    return None


def _build_current_advisory_context() -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    current_command = read_json(COMMANDS_FILE) or {}

    active_llm = _find_current_llm_advisory_proposal(
        status_payload,
        current_command,
    )
    if active_llm:
        proposal = active_llm["proposal"]
        reconciliation = reconcile_advisory_review_state(proposal)
        return {
            "status_payload": status_payload,
            "proposal": proposal,
            "persistence": {
                "persisted": True,
                "action": "REUSED_CURRENT_LLM_POLICY",
                "proposal_id": proposal.get("proposal_id"),
            },
            "reconciliation": reconciliation,
            "llm_context_status": active_llm["context_status"],
        }

    intelligence = generate_advice(status_payload)
    shadow_policy = build_shadow_policy(status_payload, intelligence)
    shadow_evaluation = evaluate_shadow_policies(recent_limit=50)
    shadow_replay = run_shadow_replay(recent_limit=100)
    decision = build_policy_decision(
        status_payload,
        intelligence,
        shadow_policy,
        shadow_evaluation=shadow_evaluation,
        shadow_replay=shadow_replay,
    )
    record_policy_decision(decision)
    proposal = build_advisory_policy_proposal(decision)
    persistence = persist_advisory_policy_proposal(proposal)
    reconciliation = reconcile_advisory_review_state(proposal)
    return {
        "status_payload": status_payload,
        "proposal": proposal,
        "persistence": persistence,
        "reconciliation": reconciliation,
    }


def _advisory_lifecycle(
    proposal: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Expose post-execution state without rewriting the immutable proposal."""
    context_status = context.get("llm_context_status") or {}
    if context_status.get("phase") == "APPLYING_OR_APPLIED":
        target = int(proposal.get("proposed_policy_epoch") or 0)
        applied_epoch = int(context_status.get("status_policy_epoch") or 0)
        state = "APPLIED" if target and applied_epoch == target else "AWAITING_NYAO_ACK"
        return {
            "state": state,
            "phase": context_status.get("phase"),
            "manual_action_complete": True,
            "target_policy_epoch": target,
            "applied_policy_epoch": applied_epoch,
        }
    schedule = get_llm_cycle_schedule()
    if (
        schedule.get("execution_mode") == "AUTONOMOUS"
        and proposal.get("review_state") == "READY_FOR_AUTONOMOUS_APPLY"
    ):
        latest_matches = (
            schedule.get("last_advisory_proposal_id") == proposal.get("proposal_id")
        )
        auto_status = (
            str(schedule.get("last_auto_apply_status") or "EVALUATING")
            if latest_matches else "EVALUATING"
        )
        state = {
            "MINIMUM_DWELL_ACTIVE": "AUTO_APPLY_DEFERRED_DWELL",
            "CONSENSUS_NOT_READY": "AUTO_APPLY_DEFERRED_CONSENSUS",
            "DEFERRED_ACTIVE_ZONE_PLAN": "AUTO_APPLY_DEFERRED_ZONE",
            "RISK_GOVERNOR_VETO": "AUTO_APPLY_BLOCKED_RISK",
            "CONFIDENCE_BELOW_70": "AUTO_APPLY_BLOCKED_CONFIDENCE",
        }.get(auto_status, f"AUTO_{auto_status}")
        return {
            "state": state,
            "phase": context_status.get("phase") or "PRE_APPLY",
            "manual_action_complete": False,
            "autonomous": True,
            "auto_apply_status": auto_status,
            "seconds_until_auto_apply_eligible": schedule.get(
                "seconds_until_auto_apply_eligible"
            ),
        }
    return {
        "state": proposal.get("review_state") or "UNKNOWN",
        "phase": context_status.get("phase") or "PRE_APPLY",
        "manual_action_complete": False,
    }


@app.get("/api/v1/atlas/advisory-proposal")
def get_atlas_advisory_proposal() -> dict:
    context = _build_current_advisory_context()
    proposal = dict(context["proposal"])
    proposal["lifecycle"] = _advisory_lifecycle(proposal, context)
    return {
        "proposal": proposal,
        "persistence": context["persistence"],
        "review_reconciliation": context["reconciliation"],
        "llm_context_status": context.get("llm_context_status"),
    }


@app.get("/api/v1/atlas/advisory-proposals")
def get_atlas_advisory_proposals(
    limit: int = 100,
) -> dict:
    return get_advisory_policy_proposals(limit=limit)


@app.get("/api/v1/atlas/advisory-proposals/{proposal_id}")
def get_atlas_advisory_proposal_by_id(
    proposal_id: str,
) -> dict:
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Advisory proposal not found.",
        )
    return proposal


@app.post("/api/v1/atlas/advisory-proposals/{proposal_id}/request-review")
def request_atlas_advisory_proposal_review(
    proposal_id: str,
    request: AdvisoryReviewActionRequest,
) -> dict:
    try:
        return request_human_review(
            proposal_id,
            reviewer=request.reviewer,
            note=request.note,
            expected_runtime_fingerprint=request.expected_runtime_fingerprint,
            expected_proposed_policy_epoch=request.expected_proposed_policy_epoch,
        )
    except ReviewWorkflowError as exc:
        _raise_review_workflow_error(exc)


@app.post("/api/v1/atlas/advisory-proposals/{proposal_id}/approve")
def approve_atlas_advisory_proposal(
    proposal_id: str,
    request: AdvisoryReviewActionRequest,
) -> dict:
    try:
        return approve_proposal(
            proposal_id,
            reviewer=request.reviewer,
            note=request.note,
            expected_runtime_fingerprint=request.expected_runtime_fingerprint,
            expected_proposed_policy_epoch=request.expected_proposed_policy_epoch,
        )
    except ReviewWorkflowError as exc:
        _raise_review_workflow_error(exc)


@app.post("/api/v1/atlas/advisory-proposals/{proposal_id}/reject")
def reject_atlas_advisory_proposal(
    proposal_id: str,
    request: AdvisoryReviewActionRequest,
) -> dict:
    try:
        return reject_proposal(
            proposal_id,
            reviewer=request.reviewer,
            note=request.note,
            expected_runtime_fingerprint=request.expected_runtime_fingerprint,
            expected_proposed_policy_epoch=request.expected_proposed_policy_epoch,
        )
    except ReviewWorkflowError as exc:
        _raise_review_workflow_error(exc)


@app.get("/api/v1/atlas/advisory-proposals/{proposal_id}/review")
def get_atlas_advisory_proposal_review(
    proposal_id: str,
) -> dict:
    try:
        return get_proposal_review_status(proposal_id)
    except ReviewWorkflowError as exc:
        _raise_review_workflow_error(exc)


@app.get("/api/v1/atlas/advisory-review-events")
def get_atlas_advisory_review_events(
    limit: int = 100,
    proposal_id: str | None = None,
) -> dict:
    return get_review_events(
        limit=limit,
        proposal_id=proposal_id,
    )


@app.get("/api/v1/atlas/advisory-review-events/verify")
def verify_atlas_advisory_review_event_chain() -> dict:
    return verify_review_event_chain()


@app.post(
    "/api/v1/atlas/advisory-proposals/{proposal_id}/supervised-command-proposal"
)
def build_atlas_supervised_command_proposal(
    proposal_id: str,
    request: SupervisedCommandBuildRequest,
) -> dict:
    current = _build_current_advisory_context()
    current_command = read_json(COMMANDS_FILE) or {}
    try:
        result = build_supervised_command_proposal(
            proposal_id,
            current_proposal=current["proposal"],
            current_status=current["status_payload"],
            current_command=current_command,
            reviewer=request.reviewer,
            note=request.note,
            expected_runtime_fingerprint=request.expected_runtime_fingerprint,
            expected_proposed_policy_epoch=request.expected_proposed_policy_epoch,
            expected_review_snapshot_hash=request.expected_review_snapshot_hash,
        )
    except SupervisedCommandBuildError as exc:
        _raise_supervised_command_build_error(exc)

    result["current_advisory_reconciliation"] = current["reconciliation"]
    return result


@app.get("/api/v1/atlas/supervised-execution-arm")
def get_atlas_supervised_execution_arm() -> dict:
    return get_execution_arm_state()


@app.post("/api/v1/atlas/supervised-execution-arm")
def arm_atlas_supervised_execution(
    request: SupervisedExecutionArmRequest,
) -> dict:
    try:
        return arm_supervised_execution(
            actor=request.actor,
            confirmation_phrase=request.confirmation_phrase,
            minutes=request.minutes,
        )
    except SupervisedExecutionError as exc:
        _raise_supervised_execution_error(exc)


@app.post("/api/v1/atlas/supervised-execution-arm/disarm")
def disarm_atlas_supervised_execution(
    request: SupervisedExecutionDisarmRequest,
) -> dict:
    return disarm_supervised_execution(actor=request.actor)


@app.get("/api/v1/atlas/supervised-command-proposals")
def get_atlas_supervised_command_proposals(limit: int = 100) -> dict:
    return get_supervised_command_proposals(limit=limit)


@app.get("/api/v1/atlas/supervised-command-proposals/{supervised_command_id}")
def get_atlas_supervised_command_proposal(
    supervised_command_id: str,
) -> dict:
    proposal = get_supervised_command_proposal(supervised_command_id)
    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Supervised command proposal not found.",
        )
    return proposal


@app.get(
    "/api/v1/atlas/supervised-command-proposals/{supervised_command_id}/execution-preflight"
)
def get_atlas_supervised_execution_preflight(
    supervised_command_id: str,
) -> dict:
    current = _build_current_advisory_context()
    current_command = read_json(COMMANDS_FILE) or {}
    try:
        return preflight_supervised_execution(
            supervised_command_id,
            current_proposal=current["proposal"],
            current_status=current["status_payload"],
            current_command=current_command,
        )
    except SupervisedExecutionError as exc:
        _raise_supervised_execution_error(exc)


@app.post(
    "/api/v1/atlas/supervised-command-proposals/{supervised_command_id}/execute"
)
def execute_atlas_supervised_command(
    supervised_command_id: str,
    request: SupervisedExecutionRequest,
) -> dict:
    # Rebuild/reconcile Atlas context immediately before the one narrow write.
    current = _build_current_advisory_context()
    current_command = read_json(COMMANDS_FILE) or {}

    try:
        return execute_supervised_command(
            supervised_command_id,
            command_file=COMMANDS_FILE,
            current_proposal=current["proposal"],
            current_status=current["status_payload"],
            current_command=current_command,
            actor=request.actor,
            note=request.note,
            confirmation_phrase=request.confirmation_phrase,
            allow_test_override_execution=request.allow_test_override_execution,
            expected_source_proposal_id=request.expected_source_proposal_id,
            expected_runtime_fingerprint=request.expected_runtime_fingerprint,
            expected_target_policy_epoch=request.expected_target_policy_epoch,
            expected_review_snapshot_hash=request.expected_review_snapshot_hash,
            expected_baseline_command_version=request.expected_baseline_command_version,
            expected_baseline_policy_epoch=request.expected_baseline_policy_epoch,
        )
    except SupervisedExecutionError as exc:
        _raise_supervised_execution_error(exc)


@app.get("/api/v1/atlas/supervised-execution-events")
def get_atlas_supervised_execution_events(
    limit: int = 200,
    supervised_command_id: str | None = None,
) -> dict:
    return get_execution_events(
        limit=limit,
        supervised_command_id=supervised_command_id,
    )


@app.get("/api/v1/atlas/supervised-execution-events/verify")
def verify_atlas_supervised_execution_event_chain() -> dict:
    return verify_execution_event_chain()


@app.get("/api/v1/atlas/supervised-executions/{execution_id}/nyao-ack")
def get_atlas_nyao_execution_ack(execution_id: str) -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )
    try:
        return evaluate_nyao_ack(
            execution_id,
            current_status=status_data,
            record_transition=False,
        )
    except NyaoAckError as exc:
        _raise_nyao_ack_error(exc)


@app.post("/api/v1/atlas/supervised-executions/{execution_id}/nyao-ack/refresh")
def refresh_atlas_nyao_execution_ack(execution_id: str) -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )
    try:
        return evaluate_nyao_ack(
            execution_id,
            current_status=status_data,
            record_transition=True,
        )
    except NyaoAckError as exc:
        _raise_nyao_ack_error(exc)


@app.get("/api/v1/atlas/supervised-command-proposals/{supervised_command_id}/latest-nyao-ack")
def get_latest_atlas_nyao_ack_for_command(
    supervised_command_id: str,
) -> dict:
    execution_id = find_latest_execution_id(
        supervised_command_id=supervised_command_id,
    )
    if not execution_id:
        raise HTTPException(
            status_code=404,
            detail="No completed supervised execution exists for this supervised command.",
        )
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )
    try:
        return evaluate_nyao_ack(
            execution_id,
            current_status=status_data,
            record_transition=False,
        )
    except NyaoAckError as exc:
        _raise_nyao_ack_error(exc)


@app.get("/api/v1/atlas/execution-recovery-diagnostics")
def get_atlas_execution_recovery_diagnostics(
    supervised_command_id: str | None = None,
) -> dict:
    return build_execution_recovery_diagnostics(
        supervised_command_id=supervised_command_id,
    )


@app.get("/api/v1/atlas/policy-decision-stability")
def get_atlas_policy_decision_stability() -> dict:
    return get_policy_decision_stability()


@app.get("/api/v1/atlas/policy-decision-history")
def get_atlas_policy_decision_history(
    limit: int = 200,
) -> dict:
    return get_policy_decision_history(limit=limit)


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


@app.get("/api/v1/atlas/analytics")
def get_atlas_analytics() -> dict:
    return analyze_history()


@app.get("/api/v1/atlas/outcome-analytics")
def get_atlas_outcome_analytics() -> dict:
    return analyze_trade_outcomes()


@app.get("/api/v1/atlas/policy-performance")
def get_atlas_policy_performance() -> dict:
    return evaluate_policy_performance()


@app.get("/api/v1/atlas/recovery-attribution")
def get_atlas_recovery_attribution() -> dict:
    return analyze_recovery_chains()


@app.get("/api/v1/atlas/risk-units")
def get_atlas_risk_units() -> dict:
    outcomes = get_trade_outcomes(closed_limit=2_000, include_active=True)
    return build_risk_units(outcomes)


@app.get("/api/v1/atlas/risk-appetite")
def get_atlas_risk_appetite() -> dict:
    return get_risk_appetite()


@app.put("/api/v1/atlas/risk-appetite")
def put_atlas_risk_appetite(request: RiskAppetiteUpdateRequest) -> dict:
    try:
        return update_risk_appetite(
            request.portfolio_hard_risk_pct,
            actor=request.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/atlas/capital-sizing")
def get_atlas_capital_sizing() -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")
    status = Status.model_validate(status_data).model_dump(mode="json")
    outcomes = get_trade_outcomes(closed_limit=2_000, include_active=True)
    return build_capital_sizing_plan(status, outcomes)


@app.get("/api/v1/atlas/recovery-risk")
def get_atlas_recovery_risk() -> dict:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")
    status = Status.model_validate(status_data).model_dump(mode="json")
    outcomes = get_trade_outcomes(closed_limit=2_000, include_active=True)
    return build_recovery_risk_ledger(status, outcomes)


@app.get("/api/v1/atlas/shadow-policy")
def get_atlas_shadow_policy() -> dict:
    status_data = read_json(STATUS_FILE)

    if not status_data:
        raise HTTPException(
            status_code=503,
            detail="Nyao status is not available yet.",
        )

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)
    policy = build_shadow_policy(
        status_payload,
        intelligence,
    )
    history = record_shadow_policy(policy)

    return {
        "policy": policy,
        "history": history,
    }


@app.get("/api/v1/atlas/shadow-history")
def get_atlas_shadow_history(
    limit: int = 200,
) -> dict:
    return get_shadow_history(limit=limit)


@app.get("/api/v1/atlas/shadow-evaluation")
def get_atlas_shadow_evaluation(
    recent_limit: int = 50,
) -> dict:
    return evaluate_shadow_policies(
        recent_limit=recent_limit,
    )


@app.get("/api/v1/atlas/shadow-replay")
def get_atlas_shadow_replay(
    recent_limit: int = 100,
) -> dict:
    return run_shadow_replay(
        recent_limit=recent_limit,
    )


@app.get("/api/v1/atlas/policy-epochs")
def get_atlas_policy_epochs(limit: int = 200) -> dict:
    return get_policy_epoch_registry(limit=limit)


@app.get("/api/v1/atlas/outcomes")
def get_atlas_outcomes(
    closed_limit: int = 200,
    include_active: bool = True,
) -> dict:
    return get_trade_outcomes(
        closed_limit=closed_limit,
        include_active=include_active,
    )


@app.get("/api/v1/atlas/outcomes/summary")
def get_atlas_outcomes_summary() -> dict:
    return get_outcome_summary()


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


@app.get("/api/v1/atlas/parameter-registry")
def get_atlas_parameter_registry(name: str | None = None) -> dict[str, Any]:
    if name:
        parameter = get_parameter(name)
        if parameter is None:
            raise HTTPException(status_code=404, detail="Parameter not found.")
        return {"summary": registry_summary(), "parameter": parameter}
    return {"summary": registry_summary(), "parameters": all_parameters()}


@app.get("/api/v1/atlas/parameter-intelligence")
def get_atlas_parameter_intelligence() -> dict[str, Any]:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")
    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)
    current_command = read_json(COMMANDS_FILE) or {}
    return build_parameter_intelligence(
        status_payload,
        intelligence,
        current_command=current_command,
    )


@app.get("/api/v1/atlas/parameter-evidence")
def get_atlas_parameter_evidence(name: str | None = None) -> dict[str, Any]:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")
    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    evidence = build_parameter_evidence(status_payload)
    if name:
        item = evidence.get(name)
        if item is None:
            raise HTTPException(status_code=404, detail="Parameter evidence not found.")
        return {"symbol": status_payload.get("symbol"), "evidence": item}
    return {
        "symbol": status_payload.get("symbol"),
        "parameter_count": len(evidence),
        "evidence": evidence,
    }


@app.get("/api/v1/atlas/llm-evidence-packet")
def get_atlas_llm_evidence_packet() -> dict[str, Any]:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")
    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)
    current_command = read_json(COMMANDS_FILE) or {}
    result = build_parameter_intelligence(
        status_payload,
        intelligence,
        current_command=current_command,
    )
    return result["llm_evidence_packet"]


@app.get("/api/v1/atlas/scalping-responsiveness")
def get_atlas_scalping_responsiveness() -> dict[str, Any]:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")
    status_payload = Status.model_validate(status_data).model_dump(mode="json")
    return analyze_scalping_responsiveness(
        status_payload,
        read_json(COMMANDS_FILE) or {},
        history=get_history(limit=720),
        trade_outcomes=get_trade_outcomes(closed_limit=2_000, include_active=False),
    )


@app.get("/api/v1/atlas/llm/status")
def get_atlas_llm_status() -> dict[str, Any]:
    status = configured_llm_status()
    return {
        "foundation_version": "3.6",
        **status,
        "analyst_enabled": bool(status.get("enabled")) and bool(status.get("model")),
        "critic_enabled": bool(status.get("enabled")) and bool(status.get("model")),
        "human_review_required": True,
        "eligible_for_execution": False,
    }


def _build_full_llm_policy_input(
    status_payload: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any]:
    """Build the same complete Atlas evidence packet for manual and timed runs."""
    identity = account_identity(status_payload)
    if not identity["ready"]:
        raise ValueError(
            "Nyao has not exported MT5 account identity yet. Refresh the updated EA "
            "before running Gemini so performance cannot cross account boundaries."
        )
    with scoped_account_performance(status_payload):
        return _build_scoped_llm_policy_input(status_payload, current_command, identity)


def _build_gemini_scalp_zone_context(
    zone_map: dict[str, Any],
    zone_plan: dict[str, Any],
    status_payload: dict[str, Any],
) -> dict[str, Any]:
    active_plan = dict(zone_plan.get("zone_plan") or {})
    source_zone = dict(active_plan.get("source_zone") or {})
    zone_aware = bool(zone_plan.get("zone_aware_scalping_active"))
    ordinary_allowed = bool(zone_plan.get("ordinary_scalping_allowed", True))
    live_zone_campaign = bool(status_payload.get("zone_mode_active"))

    if zone_aware:
        execution_lane = "ZONE_AWARE_SCALP"
    elif live_zone_campaign or (zone_plan.get("mode") == "ZONE_MODE" and not ordinary_allowed):
        execution_lane = "ZONE_CAMPAIGN"
    else:
        execution_lane = "NORMAL_SCALP"

    side = str(active_plan.get("side") or zone_plan.get("zone_aware_scalping_side") or "NONE")
    broker = dict(active_plan.get("broker_feasibility") or {})
    return {
        "version": "atlas-gemini-scalp-zone-context-v1",
        "execution_lane": execution_lane,
        "zone_context_active": bool(source_zone),
        "zone_aware_scalping_active": zone_aware,
        "ordinary_scalping_allowed": ordinary_allowed,
        "zone_side": side,
        "aligned_scalp_direction": side if zone_aware else "BOTH_OR_NORMAL_POLICY",
        "counter_direction_rule": (
            "CONDITIONAL_STRONGER_EVIDENCE_REDUCED_RISK" if zone_aware else "NORMAL_SCALP_RULES"
        ),
        "active_zone": {
            key: source_zone.get(key)
            for key in ("zone_id", "side", "timeframe", "kind", "low", "high", "score", "status", "confluence")
        } if source_zone else None,
        "zone_plan_state": zone_plan.get("state"),
        "campaign_commit_state": (
            "COMMITTED" if execution_lane == "ZONE_CAMPAIGN"
            else "WATCHING" if execution_lane == "ZONE_AWARE_SCALP"
            else "NONE"
        ),
        "scalp_policy_update_rule": (
            "CONTINUE_WITH_ZONE_CONTEXT" if execution_lane == "ZONE_AWARE_SCALP"
            else "DEFER_NEW_ACTIVATION_AT_CAMPAIGN_BOUNDARY" if execution_lane == "ZONE_CAMPAIGN"
            else "NORMAL"
        ),
        "selected_zone_structure": active_plan.get("selected_structure") or broker.get("selected_structure"),
        "broker_campaign_feasible": broker.get("campaign_feasible"),
        "composite_bias": zone_map.get("composite_bias"),
        "nearest_demand": zone_map.get("nearest_demand"),
        "nearest_supply": zone_map.get("nearest_supply"),
        "instruction": (
            "Use deterministic zone analysis as contextual evidence for SCALP policy only. "
            "Do not alter zone policy or turn a zone into a direct trade instruction. "
            "When execution_lane is ZONE_AWARE_SCALP, classify fresh scalps as zone-aligned "
            "or counter-zone. Counter-zone entries remain deterministic Nyao decisions with "
            "a stronger evidence requirement, reduced risk authority, and campaign-proximity "
            "blocking; optimize scalp policy around that context without mutating the zone system. Autonomous Nyao scalp-policy updates "
            "may continue in this WATCHING state. When execution_lane becomes ZONE_CAMPAIGN, "
            "the campaign has crossed the deterministic commit boundary; new scalp-policy "
            "activation is deferred until the campaign releases execution authority."
        ),
    }


def _build_scoped_llm_policy_input(
    status_payload: dict[str, Any],
    current_command: dict[str, Any],
    identity: dict[str, Any],
) -> dict[str, Any]:
    intelligence = generate_advice(status_payload)
    parameter_result = build_parameter_intelligence(
        status_payload,
        intelligence,
        current_command=current_command,
    )
    shadow_policy = build_shadow_policy(status_payload, intelligence)
    shadow_evaluation = evaluate_shadow_policies(recent_limit=50)
    shadow_replay = run_shadow_replay(recent_limit=100)
    policy_decision = build_policy_decision(
        status_payload,
        intelligence,
        shadow_policy,
        shadow_evaluation=shadow_evaluation,
        shadow_replay=shadow_replay,
    )
    atlas_prior_analysis = build_atlas_prior_analysis(
        shadow_policy=shadow_policy,
        shadow_evaluation=shadow_evaluation,
        shadow_replay=shadow_replay,
        policy_decision=policy_decision,
        decision_stability=get_policy_decision_stability(),
        policy_epochs=get_policy_epoch_registry(limit=20),
    )
    trade_outcomes = get_trade_outcomes(closed_limit=2_000, include_active=False)
    responsiveness = analyze_scalping_responsiveness(
        status_payload,
        current_command,
        history=get_history(limit=720),
        trade_outcomes=trade_outcomes,
    )
    policy_input = build_policy_input(
        status_payload,
        parameter_result,
        performance_analytics=analyze_trade_outcomes(),
        outcome_summary=get_outcome_summary(),
        trade_outcomes=trade_outcomes,
        atlas_prior_analysis=atlas_prior_analysis,
        responsiveness_analysis=responsiveness,
    )
    policy_input["account_identity"] = {
        "ready": identity["ready"],
        "fingerprint": identity["fingerprint"],
        "currency": identity["currency"],
        "trade_mode": identity["trade_mode"],
        "performance_scope": identity["performance_scope"],
    }
    policy_input["performance_context"]["account_fingerprint"] = identity[
        "fingerprint"
    ]
    policy_input["performance_context"]["performance_scope"] = (
        "CURRENT_MT5_ACCOUNT_ONLY"
    )
    policy_input["cross_account_learning"] = {
        "scope": "GENERALIZED_KNOWLEDGE_ONLY",
        "retained": [
            "Nyao control meanings, constraints, and interaction rules",
            "current applied runtime policy and policy epochs",
            "symbol market history, regimes, candles, and zone methodology",
            "non-account-specific execution and risk-management lessons",
        ],
        "quarantined_from_current_performance": [
            "prior-account trades and P/L",
            "prior-account win/loss streaks",
            "prior-account balance, equity, and drawdown",
        ],
        "instruction": (
            "Use retained knowledge as hypotheses and operating knowledge only. "
            "Never describe prior-account trade statistics as this account's results."
        ),
    }
    policy_input["application_mode"] = get_llm_cycle_schedule().get(
        "execution_mode", "SUPERVISED"
    )
    candle_file = STATUS_FILE.parent / "candles.json"
    candle_payload, candle_error = load_market_candle_export(candle_file)
    candle_report = build_market_candle_report(
        candle_payload,
        source_path=candle_file,
        expected_symbol=str(status_payload.get("symbol") or "") or None,
        include_bars=True,
        read_error=candle_error,
    )
    zone_map = build_zone_map(candle_report)
    capital_sizing = build_capital_sizing_plan(
        status_payload,
        get_trade_outcomes(closed_limit=50, include_active=False),
    )
    zone_execution_plan = build_zone_execution_plan(
        zone_map,
        status_payload,
        capital_sizing,
    )
    policy_input["zone_trading"] = {
        "authority": "DETERMINISTIC_READ_ONLY",
        "current_zone_policy": get_zone_policy(),
        "current_zone_map": zone_map,
        "current_zone_execution_plan": zone_execution_plan,
        "capital_sizing": capital_sizing,
        "instruction": (
            "Zone analysis is read-only context for Gemini. Gemini may use zone side, "
            "quality, timeframe, freshness, structure and feasibility to reason about "
            "the full Nyao scalp lifecycle, including entry, management, exits, sizing "
            "preferences and recovery. Gemini may not change zone policy, geometry, "
            "confirmation, zone risk allocation, Atlas capital sizing, broker feasibility, "
            "or the Atlas risk governor."
        ),
    }
    policy_input["scalp_zone_context"] = _build_gemini_scalp_zone_context(
        zone_map,
        zone_execution_plan,
        status_payload,
    )
    return policy_input


def _persist_accepted_llm_policy(
    result: dict[str, Any],
    policy_input: dict[str, Any],
    *,
    status_payload: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any] | None:
    if not result.get("eligible_for_rapid_supervised_review"):
        return None
    advisory = build_llm_policy_advisory_proposal(
        result,
        policy_input,
        current_status=status_payload,
        current_command=current_command,
    )
    persistence = persist_advisory_policy_proposal(advisory)
    reconciliation = reconcile_advisory_review_state(advisory)
    workflow = {
        "proposal": advisory,
        "persistence": persistence,
        "review_reconciliation": reconciliation,
        "next_action": "REQUEST_HUMAN_REVIEW",
    }
    result["advisory_workflow"] = workflow
    return workflow


@app.post("/api/v1/atlas/llm/review")
async def run_atlas_llm_review(
    request: LlmReviewRequest,
) -> dict[str, Any]:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    intelligence = generate_advice(status_payload)
    current_command = read_json(COMMANDS_FILE) or {}
    parameter_result = build_parameter_intelligence(
        status_payload,
        intelligence,
        current_command=current_command,
    )

    try:
        provider = build_configured_provider()
        return await asyncio.to_thread(
            run_analyst_critic_review,
            parameter_result["llm_evidence_packet"],
            provider,
            provider if request.run_critic else None,
        )
    except (
        LlmProviderError,
        ValidationError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/atlas/llm/policy-proposal")
async def run_atlas_llm_policy_proposal() -> dict[str, Any]:
    status_data = read_json(STATUS_FILE)
    if not status_data:
        raise HTTPException(status_code=503, detail="Nyao status is not available yet.")

    status = Status.model_validate(status_data)
    status_payload = status.model_dump(mode="json")
    current_command = read_json(COMMANDS_FILE) or {}
    policy_input = _build_full_llm_policy_input(status_payload, current_command)

    try:
        provider = build_configured_provider()
        result = await asyncio.to_thread(
            run_policy_proposal,
            policy_input,
            provider,
            provider,
        )
        _persist_accepted_llm_policy(
            result,
            policy_input,
            status_payload=status_payload,
            current_command=current_command,
        )
        return result
    except (
        LlmProviderError,
        ValidationError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


_LLM_CYCLE_TASKS: dict[str, asyncio.Task[Any]] = {}
_LLM_SCHEDULE_LOOP_TASK: asyncio.Task[Any] | None = None
_ZONE_DIRECTIVE_LOOP_TASK: asyncio.Task[Any] | None = None


def _gemini_cycle_run_record(
    *,
    result: dict[str, Any] | None,
    advisory: dict[str, Any] | None,
    autonomous: dict[str, Any] | None,
    baseline_policy_epoch: int | None,
) -> dict[str, Any]:
    """Persist every Gemini cycle separately from accepted consensus observations."""
    result = dict(result or {})
    advisory = dict(advisory or {})
    autonomous = dict(autonomous or {})
    bundle = dict(result.get("bundle") or {})
    critic = dict(result.get("critic") or {})
    changes = {}
    for name, row in dict(advisory.get("changed_controls") or {}).items():
        if not isinstance(row, dict):
            continue
        changes[str(name)] = {
            "current": row.get("current"),
            "proposed": row.get("shadow"),
            "confidence": row.get("confidence"),
            "rationale": row.get("rationale"),
        }
    deferred = list(result.get("deferred_locked_changes") or [])
    consensus = dict(autonomous.get("consensus") or {})
    auto_status = str(autonomous.get("status") or "")
    if autonomous.get("applied"):
        outcome = "APPLIED"
    elif deferred:
        outcome = "DEFERRED"
    elif auto_status in {"CONSENSUS_NOT_READY", "MINIMUM_DWELL_ACTIVE", "DEFERRED_ACTIVE_ZONE_PLAN"}:
        outcome = "OBSERVED"
    elif not changes:
        outcome = "NO_CHANGE"
    elif critic.get("verdict") and "ACCEPT" not in str(critic.get("verdict")).upper():
        outcome = "REJECTED"
    else:
        outcome = "GENERATED"
    return {
        "baseline_policy_epoch": int(advisory.get("current_policy_epoch") or baseline_policy_epoch or 0),
        "overall_confidence": float(bundle.get("overall_confidence") or 0.0),
        "critic_summary": critic.get("summary"),
        "proposal_state": result.get("state"),
        "outcome": outcome,
        "changes": changes,
        "deferred_locked_changes": deferred,
        "consensus_observation_recorded": bool(consensus),
        "consensus_observation_count_after_run": consensus.get("observation_count") if consensus else None,
        "consensus_minimum_observations": consensus.get("minimum_observations") if consensus else None,
        "consensus_control_count_after_run": consensus.get("consensus_control_count") if consensus else None,
        "autonomous_status": auto_status or None,
        "analysis": {
            "performance_diagnosis": list(bundle.get("performance_diagnosis") or []),
            "responsiveness_profile": bundle.get("responsiveness_profile"),
            "responsiveness_diagnosis": list(bundle.get("responsiveness_diagnosis") or []),
            "weaknesses_targeted": list(bundle.get("weaknesses_targeted") or []),
        },
    }


async def _execute_claimed_llm_cycle(symbol: str) -> None:
    """Run Gemini outside the namespace lock, then atomically persist its result."""
    command_file, status_file, _runtime_file = symbol_bridge_paths(
        _ATLAS_BRIDGE_DIR,
        symbol,
    )
    try:
        async with _SYMBOL_REQUEST_LOCK:
            with scoped_symbol_storage(symbol):
                status_data = read_json(status_file)
                if not status_data:
                    raise ValueError(f"Nyao status is not available for {symbol}.")
                status_payload = Status.model_validate(status_data).model_dump(
                    mode="json"
                )
                current_command = read_json(command_file) or {}
                policy_input = _build_full_llm_policy_input(
                    status_payload,
                    current_command,
                )

        provider = build_configured_provider()
        result = await asyncio.to_thread(
            run_policy_proposal,
            policy_input,
            provider,
            provider,
        )

        advisory_id = None
        advisory: dict[str, Any] | None = None
        autonomous: dict[str, Any] | None = None
        cycle_status = str(result.get("state") or "COMPLETED")
        critic = result.get("critic") or {}
        critic_verdict = critic.get("verdict")
        if result.get("eligible_for_rapid_supervised_review"):
            advisory = build_llm_policy_advisory_proposal(
                result,
                policy_input,
                current_status=status_payload,
                current_command=current_command,
            )
            async with _SYMBOL_REQUEST_LOCK:
                with scoped_symbol_storage(symbol):
                    live_status_data = read_json(status_file) or {}
                    live_command = read_json(command_file) or {}
                    live_status = Status.model_validate(live_status_data).model_dump(
                        mode="json"
                    )
                    live_capital = build_capital_sizing_plan(
                        live_status,
                        get_trade_outcomes(closed_limit=200, include_active=False),
                    )
                    live_status["_atlas_capital_protection"] = dict(
                        live_capital.get("loss_protection") or {}
                    )
                    context = llm_advisory_context_status(
                        advisory,
                        current_status=live_status,
                        current_command=live_command,
                    )
                    if context.get("phase") != "PRE_APPLY":
                        cycle_status = "STALE_NOT_PERSISTED"
                    else:
                        persist_advisory_policy_proposal(advisory)
                        reconcile_advisory_review_state(advisory)
                        advisory_id = advisory.get("proposal_id")
                        autonomous = apply_autonomous_llm_policy(
                            llm_result=result,
                            advisory=advisory,
                            current_status=live_status,
                            current_command=live_command,
                            command_file=command_file,
                        )
                        if autonomous.get("active_proposal_id"):
                            advisory_id = str(autonomous["active_proposal_id"])
                        result["autonomous_application"] = autonomous
                        cycle_status = (
                            "AUTONOMOUS_POLICY_APPLIED"
                            if autonomous.get("applied")
                            else str(autonomous.get("status") or "READY_FOR_HUMAN_REVIEW")
                        )

        async with _SYMBOL_REQUEST_LOCK:
            with scoped_symbol_storage(symbol):
                complete_llm_cycle(
                    status=cycle_status,
                    llm_proposal_id=result.get("proposal_id"),
                    advisory_proposal_id=advisory_id,
                    critic_verdict=critic_verdict,
                    run_record=_gemini_cycle_run_record(
                        result=result,
                        advisory=advisory,
                        autonomous=autonomous,
                        baseline_policy_epoch=int(current_command.get("policy_epoch") or 0),
                    ),
                )
    except asyncio.CancelledError:
        async with _SYMBOL_REQUEST_LOCK:
            with scoped_symbol_storage(symbol):
                complete_llm_cycle(
                    status="CANCELLED",
                    error="Atlas stopped while the policy cycle was running.",
                    run_record={
                        "baseline_policy_epoch": int((locals().get("current_command") or {}).get("policy_epoch") or 0),
                        "outcome": "CANCELLED",
                        "changes": {},
                        "deferred_locked_changes": [],
                        "consensus_observation_recorded": False,
                    },
                )
        raise
    except Exception as exc:
        async with _SYMBOL_REQUEST_LOCK:
            with scoped_symbol_storage(symbol):
                complete_llm_cycle(
                    status="FAILED",
                    error=str(exc)[:2000],
                    run_record={
                        "baseline_policy_epoch": int((locals().get("current_command") or {}).get("policy_epoch") or 0),
                        "outcome": "FAILED",
                        "changes": {},
                        "deferred_locked_changes": [],
                        "consensus_observation_recorded": False,
                    },
                )


def _start_claimed_llm_cycle(symbol: str) -> None:
    task = asyncio.create_task(
        _execute_claimed_llm_cycle(symbol),
        name=f"atlas-llm-cycle-{safe_symbol(symbol)}",
    )
    _LLM_CYCLE_TASKS[symbol] = task

    def _remove(completed: asyncio.Task[Any]) -> None:
        if _LLM_CYCLE_TASKS.get(symbol) is completed:
            _LLM_CYCLE_TASKS.pop(symbol, None)

    task.add_done_callback(_remove)


@app.get("/api/v1/atlas/llm/cycle-schedule")
def get_atlas_llm_cycle_schedule() -> dict[str, Any]:
    return get_llm_cycle_schedule()


@app.put("/api/v1/atlas/llm/cycle-schedule")
def update_atlas_llm_cycle_schedule(
    request: LlmCycleScheduleRequest,
) -> dict[str, Any]:
    return update_llm_cycle_schedule(
        enabled=request.enabled,
        interval_minutes=request.interval_minutes,
        execution_mode=request.execution_mode,
        minimum_dwell_minutes=request.minimum_dwell_minutes,
        minimum_confidence=request.minimum_confidence,
    )


@app.get("/api/v1/atlas/autonomous-policy-events")
def get_atlas_autonomous_policy_events(limit: int = 100) -> dict[str, Any]:
    return get_autonomous_policy_events(limit=limit)


@app.get("/api/v1/atlas/autonomous-policy-consensus")
def get_atlas_autonomous_policy_consensus() -> dict[str, Any]:
    return get_autonomous_policy_consensus(read_json(COMMANDS_FILE) or {})




@app.get("/api/v1/atlas/autonomous-policy-observations")
def get_atlas_autonomous_policy_observations(limit: int = 200) -> dict[str, Any]:
    return get_autonomous_policy_observations(limit=limit)


@app.get("/api/v1/atlas/autonomous-policy-applications")
def get_atlas_autonomous_policy_applications(limit: int = 50) -> dict[str, Any]:
    """Reconcile autonomous intent with registered and live Nyao runtime state."""
    limit = max(1, min(int(limit), 200))
    event_store = get_autonomous_policy_events(limit=1000)
    events = [
        row for row in list(event_store.get("events") or [])
        if isinstance(row, dict) and row.get("action") == "AUTO_POLICY_APPLIED"
    ]
    registry = get_policy_epoch_registry(limit=1000)
    epochs = list(registry.get("epochs") or registry.get("policy_epochs") or [])
    by_epoch = {
        int(row.get("policy_epoch") or row.get("epoch") or 0): row
        for row in epochs if isinstance(row, dict)
    }
    command = read_json(COMMANDS_FILE) or {}
    status = read_json(STATUS_FILE) or {}
    current_command_epoch = int(command.get("policy_epoch") or 0)
    current_status_epoch = int(status.get("policy_epoch") or 0)

    rows: list[dict[str, Any]] = []
    for event in events[:limit]:
        epoch = int(event.get("policy_epoch") or 0)
        patch = dict(event.get("consensus_patch") or {})
        epoch_row = by_epoch.get(epoch) or {}
        runtime = dict(epoch_row.get("runtime") or {})
        previous_runtime = dict((by_epoch.get(epoch - 1) or {}).get("runtime") or {})
        registered_values = {name: runtime.get(name) for name in patch}
        before_values = {name: previous_runtime.get(name) for name in patch}
        registry_available = bool(runtime)
        registry_matches = bool(patch) and registry_available and all(
            runtime.get(name) == value for name, value in patch.items()
        )

        live_values = {
            name: status.get(f"runtime_{name}")
            for name in patch
        }
        live_comparable = epoch == current_status_epoch and bool(patch)
        live_matches = live_comparable and all(
            live_values.get(name) == value for name, value in patch.items()
        )

        if live_comparable:
            reconciliation = "RUNTIME_CONFIRMED" if live_matches else "RUNTIME_MISMATCH"
        elif registry_available:
            reconciliation = "SUPERSEDED_CONFIRMED" if registry_matches else "REGISTRY_MISMATCH"
        else:
            reconciliation = "COMMAND_WRITTEN_AWAITING_REGISTRY"

        changes = {
            name: {
                "before": before_values.get(name),
                "intended": value,
                "registered": registered_values.get(name),
                "live": live_values.get(name) if live_comparable else None,
                "confirmed": (live_matches if live_comparable else registry_matches),
            }
            for name, value in patch.items()
        }
        consensus_obs = int(event.get("consensus_observation_count") or 0)
        consensus_minimum = 3
        baseline_epoch = int(event.get("baseline_policy_epoch") or max(0, epoch - 1))
        consensus_gate_integrity = (
            "LEGACY_BYPASS"
            if baseline_epoch > 1 and consensus_obs < consensus_minimum and not bool(event.get("minimum_dwell_overridden"))
            else "VERIFIED"
        )
        rows.append({
            **event,
            "reconciliation": reconciliation,
            "consensus_gate_integrity": consensus_gate_integrity,
            "consensus_minimum_observations": consensus_minimum,
            "registry_available": registry_available,
            "registry_matches_intent": registry_matches,
            "live_comparable": live_comparable,
            "live_matches_intent": live_matches if live_comparable else None,
            "current_command_epoch": current_command_epoch,
            "current_status_epoch": current_status_epoch,
            "changes": changes,
            "runtime": runtime,
            "previous_runtime": previous_runtime,
        })

    current_active = next(
        (row for row in rows if int(row.get("policy_epoch") or 0) == current_command_epoch),
        None,
    )
    return {
        "version": "atlas-autonomous-application-history-v1",
        "application_count": len(rows),
        "current_command_epoch": current_command_epoch,
        "current_status_epoch": current_status_epoch,
        "current_active": current_active,
        "current_command_runtime": {k: v for k, v in command.items() if k not in {"command_version", "policy_epoch", "updated_at"}},
        "current_status_runtime": {k.removeprefix("runtime_"): v for k, v in status.items() if k.startswith("runtime_")},
        "applications": rows,
    }


@app.post("/api/v1/atlas/llm/cycle-schedule/run-now")
async def run_atlas_llm_cycle_now() -> dict[str, Any]:
    status_data = read_json(STATUS_FILE) or {}
    symbol = str(status_data.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=503, detail="Nyao symbol is not available.")
    claim = claim_llm_cycle(trigger="HUMAN_RUN_NOW", force=True)
    if claim.get("claimed"):
        _start_claimed_llm_cycle(symbol)
    return claim


async def _llm_schedule_loop() -> None:
    while True:
        try:
            for item in discover_bridge_symbols(_ATLAS_BRIDGE_DIR):
                symbol = str(item.get("symbol") or "").strip()
                if not symbol or symbol in _LLM_CYCLE_TASKS:
                    continue
                async with _SYMBOL_REQUEST_LOCK:
                    with scoped_symbol_storage(symbol):
                        claim = claim_llm_cycle(
                            trigger="SCHEDULED_INTERVAL",
                            force=False,
                        )
                if claim.get("claimed"):
                    _start_claimed_llm_cycle(symbol)
        except asyncio.CancelledError:
            raise
        except Exception:
            # One malformed/offline symbol must not stop schedules for all symbols.
            pass
        await asyncio.sleep(15)


def _refresh_zone_directive_for_symbol(symbol: str) -> None:
    command_file, status_file, _runtime_file = symbol_bridge_paths(
        _ATLAS_BRIDGE_DIR,
        symbol,
    )
    status_data = read_json(status_file) or {}
    candle_file = status_file.parent / "candles.json"
    payload, read_error = load_market_candle_export(candle_file)
    candle_report = build_market_candle_report(
        payload,
        source_path=candle_file,
        expected_symbol=symbol,
        include_bars=True,
        read_error=read_error,
    )
    zone_map = build_zone_map(candle_report)
    # Background directive publication does not pass through FastAPI middleware.
    # Scope outcome evidence explicitly to the live MT5 account so loss streaks
    # and capital budgets cannot oscillate between CURRENT_ACCOUNT and
    # UNIDENTIFIED_ACCOUNT data every two seconds.
    with scoped_account_performance(status_data):
        capital_sizing = build_capital_sizing_plan(
            status_data,
            get_trade_outcomes(closed_limit=200, include_active=False),
        )

    # Loss-protection windows actively inspect the already accumulated Gemini
    # consensus. A qualified candidate may bypass normal dwell immediately
    # without waiting for the next scheduled Gemini cycle.
    protection_status = {
        **status_data,
        "_atlas_capital_protection": dict(capital_sizing.get("loss_protection") or {}),
    }
    protection_apply = apply_ready_loss_protection_consensus(
        current_status=protection_status,
        current_command=read_json(command_file) or {},
        command_file=command_file,
    )
    if protection_apply.get("applied"):
        # The policy changed, but capital authority remains deterministic and
        # independent. Rebuilding the plan below uses the same capital snapshot.
        pass

    plan = build_zone_execution_plan(zone_map, status_data, capital_sizing)
    campaign_exposure_active = bool(
        int(status_data.get("strategy_open_positions") or 0) > 0
        or int(status_data.get("working_limit_orders") or 0) > 0
    )
    if plan.get("mode") != "ZONE_MODE" and not campaign_exposure_active:
        # The live market plan is the mode authority here. Nyao's status can
        # briefly retain zone_mode_active after price has already left a zone.
        # Broker exposure remains a stronger boundary: never activate a queued
        # scalp policy while a locked zone position or limit is still live.
        clean_boundary_status = {**status_data, "zone_mode_active": False}
        pending_result = apply_pending_autonomous_policy(
            current_status=clean_boundary_status,
            current_command=read_json(command_file) or {},
            command_file=command_file,
        )
        if pending_result.get("applied"):
            plan = build_zone_execution_plan(zone_map, status_data, capital_sizing)

    # Once Nyao has submitted a zone campaign, keep the complete directive
    # immutable until all campaign positions and pending limits are gone.
    _persist_zone_campaign(
        plan,
        status_data,
        status_file.parent / "zone_directive.json",
    )


async def _zone_directive_loop() -> None:
    while True:
        try:
            for item in discover_bridge_symbols(_ATLAS_BRIDGE_DIR):
                symbol = str(item.get("symbol") or "").strip()
                if not symbol:
                    continue
                async with _SYMBOL_REQUEST_LOCK:
                    with scoped_symbol_storage(symbol):
                        _status_for_account_scope = read_json(
                            symbol_bridge_paths(_ATLAS_BRIDGE_DIR, symbol)[1]
                        ) or {}
                        with scoped_account_performance(_status_for_account_scope):
                            await asyncio.to_thread(
                                _refresh_zone_directive_for_symbol,
                                symbol,
                            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Invalid or mid-write market files must not stop future refreshes.
            pass
        await asyncio.sleep(2)


@app.on_event("startup")
async def start_llm_cycle_scheduler() -> None:
    global _LLM_SCHEDULE_LOOP_TASK, _ZONE_DIRECTIVE_LOOP_TASK
    for item in discover_bridge_symbols(_ATLAS_BRIDGE_DIR):
        symbol = str(item.get("symbol") or "").strip()
        if symbol:
            with scoped_symbol_storage(symbol):
                recover_interrupted_llm_cycle()
    _LLM_SCHEDULE_LOOP_TASK = asyncio.create_task(
        _llm_schedule_loop(),
        name="atlas-llm-cycle-scheduler",
    )
    _ZONE_DIRECTIVE_LOOP_TASK = asyncio.create_task(
        _zone_directive_loop(),
        name="atlas-zone-directive-publisher",
    )


@app.on_event("shutdown")
async def stop_llm_cycle_scheduler() -> None:
    tasks = [task for task in _LLM_CYCLE_TASKS.values() if not task.done()]
    if _LLM_SCHEDULE_LOOP_TASK and not _LLM_SCHEDULE_LOOP_TASK.done():
        _LLM_SCHEDULE_LOOP_TASK.cancel()
        tasks.append(_LLM_SCHEDULE_LOOP_TASK)
    if _ZONE_DIRECTIVE_LOOP_TASK and not _ZONE_DIRECTIVE_LOOP_TASK.done():
        _ZONE_DIRECTIVE_LOOP_TASK.cancel()
        tasks.append(_ZONE_DIRECTIVE_LOOP_TASK)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@app.get("/api/v1/nyao/control-schema")
def get_nyao_control_schema() -> list[dict]:
    return RUNTIME_CONTROL_GROUPS



DASHBOARD_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Atlas Operator Control Center</title>
<link rel="icon" type="image/png" sizes="64x64" href="/assets/atlas-favicon.png">
<link rel="apple-touch-icon" href="/assets/atlas-app-icon.png">
<style>
:root{
  color-scheme:dark;
  --bg:#080b11; --panel:#10151f; --panel2:#151c28; --panel3:#0c1119;
  --border:#252e3d; --text:#eef2f7; --muted:#8e9aad; --soft:#b9c2cf;
  --green:#48d597; --red:#ff6f7d; --amber:#f2c66d; --blue:#73a9ff;
  --purple:#b99aff; --shadow:0 18px 60px rgba(0,0,0,.28);
  --radius:18px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
button,input,select,textarea{font:inherit}
button{cursor:pointer}
.shell{display:grid;grid-template-columns:238px 1fr;min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;border-right:1px solid var(--border);padding:24px 18px;background:#0b0f16}
.brand{display:flex;gap:12px;align-items:center;margin-bottom:28px;padding:0 8px}
.logo{width:42px;height:42px;border-radius:12px;display:block;object-fit:cover;background:#0b1119;box-shadow:0 0 0 1px rgba(126,174,255,.18) inset}
.brand h1{font-size:16px;margin:0}.brand small{display:block;color:var(--muted);margin-top:2px}
.nav{display:grid;gap:6px}
.nav button{border:0;background:transparent;color:var(--muted);padding:11px 12px;border-radius:11px;text-align:left;font-weight:650}
.nav button:hover,.nav button.active{background:#151d29;color:var(--text)}
.sidebar-bottom{position:absolute;bottom:22px;left:18px;right:18px}
.connection{padding:12px;border:1px solid var(--border);background:var(--panel3);border-radius:12px}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);display:inline-block}.dot.ok{background:var(--green)}.dot.bad{background:var(--red)}
.main{min-width:0}
.topbar{height:74px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);padding:0 30px;position:sticky;top:0;background:rgba(8,11,17,.93);backdrop-filter:blur(15px);z-index:20}
.title{font-size:18px;font-weight:750}.subtitle{color:var(--muted);font-size:12px;margin-top:2px}
.top-meta{display:flex;gap:10px;align-items:center}
.pill{border:1px solid var(--border);background:var(--panel);padding:7px 10px;border-radius:999px;color:var(--soft);font-size:12px}
.symbol-select{border:1px solid rgba(115,169,255,.35);background:var(--panel);color:var(--blue);padding:7px 30px 7px 10px;border-radius:999px;font-size:12px;font-weight:750;outline:none}
.pill.ok{color:var(--green);border-color:rgba(72,213,151,.25)}.pill.warn{color:var(--amber)}.pill.bad{color:var(--red)}
.content{padding:28px 30px 60px;max-width:1540px;margin:0 auto}
.view{display:none}.view.active{display:block}
.page-head{margin-bottom:22px}.page-head h2{margin:0;font-size:25px}.page-head p{margin:6px 0 0;color:var(--muted)}
.grid{display:grid;gap:16px}.g4{grid-template-columns:repeat(4,minmax(0,1fr))}.g3{grid-template-columns:repeat(3,minmax(0,1fr))}.g2{grid-template-columns:repeat(2,minmax(0,1fr))}
.card{background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:18px}
.card h3{margin:0 0 14px;font-size:14px}.label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.value{font-size:25px;font-weight:760;margin-top:5px}.value.small{font-size:16px}.muted{color:var(--muted)}
.hero{padding:22px;display:grid;grid-template-columns:1.5fr 1fr;gap:18px}
.hero-status{font-size:30px;font-weight:800;margin:9px 0}.hero-copy{max-width:700px;color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.kpi{padding:13px;background:var(--panel3);border:1px solid var(--border);border-radius:12px}
.section{margin-top:18px}.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:12px}.section-head h3{margin:0;font-size:16px}.section-head p{margin:4px 0 0;color:var(--muted);font-size:12px}
.badge{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;border:1px solid var(--border);font-size:11px;font-weight:750}.badge.ok{color:var(--green)}.badge.warn{color:var(--amber)}.badge.bad{color:var(--red)}.badge.info{color:var(--blue)}
.signal-grid{display:grid;grid-template-columns:1.05fr 1fr 1fr;gap:14px}
.signal-score{font-size:34px;font-weight:800;letter-spacing:-.03em;margin:8px 0 2px}
.signal-meta{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
.signal-meta .kpi{padding:10px}
.signal-track{height:7px;background:rgba(255,255,255,.06);border-radius:999px;overflow:hidden;margin-top:12px}
.signal-fill{height:100%;width:0;border-radius:999px;background:currentColor;transition:width .2s ease}
.signal-buy{color:var(--green)} .signal-sell{color:var(--red)}
.bias-value{font-size:28px;font-weight:850;margin:7px 0 3px}
.bias-bull{color:var(--green)} .bias-bear{color:var(--red)} .bias-neutral{color:var(--amber)}
.signal-reason{margin-top:10px;min-height:34px;font-size:12px;color:var(--soft);line-height:1.45}
.analysis-thesis{font-size:18px;font-weight:720;line-height:1.45;margin:8px 0;color:var(--text)}
.zone-empty{min-height:220px;display:grid;place-items:center;text-align:center;padding:28px;border:1px dashed rgba(115,169,255,.35);border-radius:14px;background:linear-gradient(145deg,rgba(115,169,255,.05),rgba(185,154,255,.025))}
.zone-empty strong{display:block;font-size:17px;margin-bottom:7px}.zone-empty p{max-width:650px;margin:0;color:var(--muted)}
.zone-chart-shell{border:1px solid rgba(115,169,255,.28);border-radius:14px;overflow:hidden;background:linear-gradient(145deg,rgba(115,169,255,.045),rgba(5,9,16,.25))}.zone-chart-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;padding:15px 17px;border-bottom:1px solid var(--border)}.zone-chart-head strong{display:block;font-size:17px}.zone-chart-head p{margin:5px 0 0;color:var(--muted);max-width:850px}.zone-chart-frame{display:block;width:100%;height:auto;min-height:330px}.zone-chart-legend{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:11px;color:var(--muted)}.zone-chart-key{display:inline-flex;gap:5px;align-items:center}.zone-chart-swatch{width:12px;height:8px;border-radius:2px}.zone-chart-swatch.demand{background:rgba(74,222,128,.35);border:1px solid var(--green)}.zone-chart-swatch.supply{background:rgba(251,113,133,.30);border:1px solid var(--red)}@media(max-width:760px){.zone-chart-head{display:block}.zone-chart-legend{margin-top:10px}.zone-chart-frame{min-height:270px}}
.zone-map-list{display:grid;gap:9px;margin-top:12px}.zone-card{display:grid;grid-template-columns:115px minmax(160px,1fr) 110px 90px;gap:14px;align-items:center;padding:13px;border:1px solid var(--border);background:var(--panel3);border-radius:12px}.zone-card.demand{border-left:4px solid var(--green)}.zone-card.supply{border-left:4px solid var(--red)}.zone-price{font-size:17px;font-weight:760}.zone-evidence{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.zone-score{text-align:right}.zone-score strong{font-size:17px}.zone-plan{margin-top:12px;padding:15px;border:1px solid rgba(115,169,255,.3);border-radius:13px;background:rgba(37,99,235,.055)}.zone-plan-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}.zone-plan-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:12px}.zone-plan-leg{padding:11px;border:1px solid var(--border);border-radius:10px;background:var(--panel3)}@media(max-width:760px){.zone-card{grid-template-columns:1fr auto}.zone-evidence{grid-column:1/-1}.zone-score{text-align:left}.zone-plan-head{display:block}.zone-plan-head .badge{margin-top:8px}.zone-plan-grid{grid-template-columns:1fr}}
.analysis-list{display:grid;gap:8px}.analysis-item{padding:11px 12px;border-left:3px solid var(--border);background:var(--panel3);border-radius:0 11px 11px 0}.analysis-item.buy{border-left-color:var(--green)}.analysis-item.sell{border-left-color:var(--red)}.analysis-item.info{border-left-color:var(--blue)}
@media(max-width:900px){.signal-grid{grid-template-columns:1fr}}


.strategy-authority-grid{display:grid;grid-template-columns:1.15fr 1fr 1fr 1.15fr;gap:14px;margin-top:18px}
.authority-card{position:relative;overflow:hidden}
.authority-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--border)}
.authority-card.active:before{background:var(--blue)}
.authority-card.context:before{background:var(--purple)}
.authority-card.capital:before{background:var(--green)}
.authority-card.brain:before{background:var(--amber)}
.authority-main{font-size:18px;font-weight:800;margin-top:6px}
.authority-sub{color:var(--muted);font-size:12px;margin-top:6px;min-height:34px}
.authority-mini{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:12px}
.authority-mini>div{padding:8px 9px;border:1px solid var(--border);border-radius:9px;background:var(--panel3)}
.authority-mini strong{display:block;font-size:13px;margin-top:2px}
.lane-normal{color:var(--green)}.lane-zone-aware{color:var(--purple)}.lane-zone{color:var(--blue)}
@media(max-width:1180px){.strategy-authority-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.strategy-authority-grid{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse}th{text-align:left;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:650;padding:10px 10px;border-bottom:1px solid var(--border)}td{padding:12px 10px;border-bottom:1px solid rgba(37,46,61,.7);white-space:nowrap}tr:last-child td{border-bottom:0}.table-wrap{overflow:auto}
.pos{color:var(--green)}.neg{color:var(--red)}
.btn{border:1px solid var(--border);background:#161f2c;color:var(--text);padding:9px 12px;border-radius:10px;font-weight:700}.btn:hover{filter:brightness(1.12)}.btn.primary{background:#edf3ff;color:#0b111a;border-color:#edf3ff}.btn.danger{color:#ffd6da;border-color:rgba(255,111,125,.35);background:rgba(255,111,125,.08)}.btn:disabled{opacity:.42;cursor:not-allowed}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.changes{display:grid;gap:8px}.change{display:grid;grid-template-columns:1fr auto auto;gap:16px;align-items:center;padding:11px 12px;border:1px solid var(--border);background:var(--panel3);border-radius:11px}.arrow{color:var(--muted)}

.policy-hero{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(300px,.7fr);gap:14px}
.policy-runtime-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:12px}.policy-runtime-item{border:1px solid var(--border);border-radius:11px;padding:10px;background:var(--panel3)}
.policy-runtime-item .label{margin-bottom:4px}.policy-runtime-item strong{font-size:13px}.policy-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.policy-timeline{display:grid;gap:9px}.policy-record{border:1px solid var(--border);border-radius:12px;background:var(--panel3);padding:12px;cursor:pointer}.policy-record:hover{border-color:#355074}.policy-record.active{border-color:rgba(72,221,164,.32);background:linear-gradient(90deg,rgba(72,221,164,.05),var(--panel3) 35%)}
.policy-record-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.policy-record-meta{display:flex;gap:10px;flex-wrap:wrap;margin-top:5px;color:var(--muted);font-size:10px}.policy-record-changes{margin-top:7px;color:var(--soft);font-size:11px;line-height:1.45}
.brain-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}.brain-tab{border:1px solid var(--border);background:var(--panel3);color:var(--muted);padding:7px 10px;border-radius:9px;cursor:pointer;font:inherit;font-size:10px}.brain-tab.active{color:var(--text);border-color:#41628a;background:#111d2c}.brain-tab-panel{display:none;margin-top:12px}.brain-tab-panel.active{display:block}
.observation-list{display:grid;gap:8px;max-height:460px;overflow:auto}.observation-row{border:1px solid var(--border);border-radius:11px;background:var(--panel3);padding:11px;cursor:pointer}.observation-row:hover{border-color:#355074}.observation-changes{display:flex;gap:6px;flex-wrap:wrap;margin-top:7px}.observation-chip{font-size:9px;border:1px solid var(--border);border-radius:999px;padding:3px 7px;color:var(--soft)}
.policy-modal{position:fixed;inset:0;z-index:90;background:rgba(0,0,0,.62);display:none;align-items:center;justify-content:center;padding:24px}.policy-modal.open{display:flex}.policy-modal-card{width:min(980px,96vw);max-height:88vh;overflow:auto;border:1px solid var(--border);border-radius:18px;background:#0c131e;box-shadow:0 24px 80px rgba(0,0,0,.55);padding:20px}.policy-modal-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;position:sticky;top:-20px;background:#0c131e;padding:4px 0 12px;z-index:2}.policy-control-table{display:grid;gap:5px;margin-top:12px}.policy-control-row{display:grid;grid-template-columns:minmax(220px,1fr) minmax(140px,.45fr) minmax(140px,.45fr);gap:10px;padding:8px 10px;border:1px solid var(--border);border-radius:8px;font-size:10px}.policy-control-row.changed{border-color:rgba(126,174,255,.35);background:rgba(126,174,255,.035)}
@media(max-width:900px){.policy-hero{grid-template-columns:1fr}.policy-runtime-grid{grid-template-columns:1fr 1fr}.policy-control-row{grid-template-columns:1fr}}

.consensus-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:12px}
.consensus-table{display:grid;gap:8px;margin-top:12px;max-height:520px;overflow:auto;padding-right:2px}
.consensus-row{display:grid;grid-template-columns:minmax(190px,1.3fr) minmax(155px,.8fr) minmax(150px,.9fr) minmax(190px,1.2fr) auto;gap:12px;align-items:center;padding:12px 13px;border:1px solid var(--border);background:var(--panel3);border-radius:11px}
.consensus-row.ready{border-color:rgba(72,221,164,.34);background:linear-gradient(90deg,rgba(72,221,164,.055),var(--panel3) 34%)}
.consensus-name strong{display:block}.consensus-name .muted{margin-top:3px;font-size:11px}
.consensus-values{font-size:12px}.consensus-values strong{font-size:13px;color:var(--text)}
.consensus-support{display:grid;gap:5px}.consensus-support-line{display:flex;justify-content:space-between;gap:10px;font-size:11px;color:var(--soft)}
.consensus-meter{height:7px;background:#091018;border:1px solid rgba(255,255,255,.045);border-radius:999px;overflow:hidden}.consensus-meter>span{display:block;height:100%;background:var(--blue);border-radius:999px}.consensus-row.ready .consensus-meter>span{background:var(--green)}
.consensus-gate{font-size:11px;color:var(--muted);line-height:1.4}
.consensus-empty{padding:16px;border:1px dashed var(--border);border-radius:11px;color:var(--muted)}
@media(max-width:1180px){.consensus-row{grid-template-columns:1fr 1fr}.consensus-row>*:nth-child(3),.consensus-row>*:nth-child(4){grid-column:auto}.consensus-summary{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.consensus-summary{grid-template-columns:1fr}.consensus-row{grid-template-columns:1fr}}

.callout{padding:13px;border:1px solid var(--border);background:var(--panel3);border-radius:12px;color:var(--soft)}
.workflow{display:grid;gap:10px}.step{display:grid;grid-template-columns:28px 1fr auto;gap:10px;align-items:center;padding:11px;border:1px solid var(--border);border-radius:11px}.step-num{width:28px;height:28px;border-radius:9px;background:#1c2635;display:grid;place-items:center;font-weight:800}.step.done .step-num{color:var(--green)}.step.active{border-color:rgba(115,169,255,.4)}
.search{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:#0b111a;color:var(--text);outline:none}
.controls{display:grid;gap:10px}.control-group{border:1px solid var(--border);border-radius:13px;overflow:hidden}.control-group summary{list-style:none;padding:13px 14px;background:var(--panel3);font-weight:750;cursor:pointer}.control-group summary::-webkit-details-marker{display:none}.control-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding:12px}.control{padding:10px;border:1px solid var(--border);border-radius:10px}.control label{display:block;font-size:11px;color:var(--muted);margin-bottom:7px}.control input,.control select{width:100%;padding:8px 9px;border-radius:8px;border:1px solid var(--border);background:#090e15;color:var(--text)}.control.dirty{border-color:rgba(242,198,109,.5)}
.sticky-actions{position:sticky;bottom:12px;margin-top:12px;padding:11px 12px;border:1px solid var(--border);background:rgba(15,21,31,.96);backdrop-filter:blur(10px);border-radius:13px;display:flex;justify-content:space-between;align-items:center}
.timeline{display:grid;gap:8px}.event{display:grid;grid-template-columns:145px 1fr auto;gap:12px;padding:11px;border-bottom:1px solid var(--border)}.event:last-child{border-bottom:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
details.raw summary{cursor:pointer;color:var(--muted);font-weight:650}pre{white-space:pre-wrap;word-break:break-word;background:#090d13;border:1px solid var(--border);padding:12px;border-radius:11px;max-height:430px;overflow:auto}
.toast{position:fixed;right:22px;bottom:22px;max-width:430px;padding:12px 14px;border-radius:12px;background:#151e2a;border:1px solid var(--border);box-shadow:var(--shadow);display:none;z-index:60}.toast.show{display:block}.toast.bad{border-color:rgba(255,111,125,.45)}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.68);display:none;align-items:center;justify-content:center;padding:20px;z-index:50}.modal.show{display:flex}.modal-card{width:min(640px,100%);max-height:88vh;overflow:auto;background:#101722;border:1px solid var(--border);border-radius:18px;padding:20px}.modal-card h3{margin-top:0}.modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}
@media(max-width:1050px){.g4,.g3{grid-template-columns:repeat(2,1fr)}.control-grid{grid-template-columns:repeat(2,1fr)}.hero{grid-template-columns:1fr}}
@media(max-width:760px){.shell{grid-template-columns:1fr}.sidebar{height:auto;position:static;border-right:0;border-bottom:1px solid var(--border)}.sidebar-bottom{position:static;margin-top:14px}.nav{grid-template-columns:repeat(3,1fr)}.nav button{text-align:center;font-size:11px;padding:9px 4px}.topbar{padding:0 16px}.content{padding:20px 14px 50px}.g4,.g3,.g2{grid-template-columns:1fr}.control-grid{grid-template-columns:1fr}.top-meta{display:none}.event{grid-template-columns:1fr}}

/* Atlas operator experience v2 */
:root{
  --bg:#070a0f;--panel:#101721;--panel2:#151e2a;--panel3:#0b1119;
  --border:#202c3a;--muted:#8290a3;--soft:#c0cad7;--text:#f4f7fb;
  --green:#48dda4;--red:#ff7185;--amber:#f5c86b;--blue:#6ea8ff;
  --radius:16px;--shadow:0 14px 45px rgba(0,0,0,.22)
}
body{background:radial-gradient(circle at 80% -10%,rgba(45,105,170,.10),transparent 32%),var(--bg)}
.shell{grid-template-columns:214px 1fr}.sidebar{padding:22px 14px;background:#090d13}.brand{margin-bottom:34px}.logo{box-shadow:0 0 0 1px rgba(126,174,255,.18) inset,0 8px 24px rgba(0,0,0,.24)}.brand small{font-size:10px;letter-spacing:.04em}
.nav{gap:4px}.nav button{position:relative;padding:10px 12px 10px 38px;font-size:13px}.nav button:before{position:absolute;left:13px;top:50%;transform:translateY(-50%);width:16px;text-align:center;color:#627188;font-size:11px}.nav button[data-view="overview"]:before{content:"●"}.nav button[data-view="market"]:before{content:"∿"}.nav button[data-view="analysis"]:before{content:"◇"}.nav button[data-view="positions"]:before{content:"▤"}.nav button[data-view="performance"]:before{content:"▥"}.nav button[data-view="atlas"]:before{content:"✦"}.nav button[data-view="control"]:before{content:"⌁"}.nav button[data-view="history"]:before{content:"◷"}.nav button.active:after{content:"";position:absolute;left:0;top:9px;bottom:9px;width:2px;border-radius:2px;background:var(--blue)}
.connection{background:linear-gradient(145deg,#0e1721,#0a1017)}.topbar{height:64px;padding:0 28px}.top-meta #epoch-pill,.top-meta #command-pill{display:none}.content{padding:24px 28px 60px;max-width:1480px}.page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;margin-bottom:18px}.page-head h2{font-size:22px;letter-spacing:-.02em}.page-head p{font-size:12px}.card{box-shadow:none;background:linear-gradient(145deg,rgba(17,24,35,.98),rgba(13,19,28,.98))}.section{margin-top:14px}
.hero{display:block;padding:0;overflow:hidden;border-color:#2b4260;background:linear-gradient(120deg,rgba(31,63,99,.32),rgba(14,21,31,.98) 52%)}
.command-hero{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(330px,.8fr);min-height:210px}.command-primary{padding:24px 26px;display:flex;flex-direction:column;justify-content:space-between}.command-side{padding:18px;border-left:1px solid rgba(110,168,255,.16);background:rgba(5,10,16,.28)}.mode-line{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.mode-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 5px rgba(72,221,164,.09)}.hero-status{font-size:31px;letter-spacing:-.035em;margin:13px 0 7px}.hero-copy{font-size:13px;max-width:760px}.hero-foot{display:flex;gap:18px;align-items:center;flex-wrap:wrap;margin-top:20px;color:var(--soft);font-size:12px}.hero-foot strong{color:var(--text)}
.command-side .kpis{grid-template-columns:1fr 1fr;height:100%}.command-side .kpi{display:flex;flex-direction:column;justify-content:center;background:rgba(7,12,18,.55);border-color:rgba(110,168,255,.13)}
.account-strip{grid-template-columns:1.1fr 1.1fr 1.4fr .9fr}.account-strip .card{min-height:108px;padding:16px 18px}.account-strip .value{font-size:23px}.account-strip .value.small{font-size:18px}
.operator-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(310px,.75fr);gap:14px}.campaign-card{border-color:rgba(110,168,255,.28);background:linear-gradient(145deg,rgba(18,31,48,.98),rgba(12,19,28,.98))}.campaign-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.campaign-title{font-size:20px;font-weight:800;letter-spacing:-.025em;margin:5px 0}.campaign-ladder{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px}.campaign-leg{position:relative;padding:12px 12px 11px 15px;background:rgba(5,10,16,.48);border:1px solid var(--border);border-radius:11px}.campaign-leg:before{content:"";position:absolute;left:-1px;top:10px;bottom:10px;width:3px;border-radius:3px;background:var(--blue)}.campaign-leg.live:before{background:var(--green)}.campaign-price{font-size:17px;font-weight:780;margin:4px 0}.decision-card{display:flex;flex-direction:column;justify-content:space-between}.decision-state{font-size:20px;font-weight:800;letter-spacing:-.02em;margin:7px 0}.decision-list{display:grid;gap:9px;margin-top:14px}.decision-item{display:grid;grid-template-columns:10px 1fr;gap:9px;color:var(--soft);font-size:12px}.decision-item:before{content:"";width:6px;height:6px;border-radius:50%;background:var(--green);margin-top:5px}.quiet-card{background:#0c121a}.overview-support .card{min-height:180px}.overview-support .changes{max-height:180px;overflow:auto}
.workspace-intro{padding:14px 16px;border:1px solid rgba(110,168,255,.18);border-radius:13px;background:rgba(110,168,255,.045);margin-bottom:14px;color:var(--soft);font-size:12px}.workspace-intro strong{color:var(--text)}
.signal-grid .card{min-height:210px}
.table-wrap table th:nth-child(n+6),.table-wrap table td:nth-child(n+6){font-size:11px;color:var(--muted)}

/* Atlas notification center */
.notify-wrap{position:relative}.notify-bell{position:relative;width:36px;height:36px;border:1px solid var(--border);border-radius:10px;background:#0d141e;color:var(--text);cursor:pointer;font-size:17px}.notify-bell:hover{border-color:rgba(110,168,255,.45)}.notify-count{position:absolute;right:-5px;top:-5px;min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:#ff5c6c;color:white;font-size:10px;font-weight:800;display:none;align-items:center;justify-content:center}.notify-count.show{display:flex}.notify-drawer{position:fixed;z-index:90;right:18px;top:68px;width:min(430px,calc(100vw - 28px));max-height:72vh;background:#0b1119;border:1px solid rgba(110,168,255,.25);border-radius:15px;box-shadow:0 22px 70px rgba(0,0,0,.48);display:none;overflow:hidden}.notify-drawer.open{display:block}.notify-head{display:flex;justify-content:space-between;align-items:center;padding:15px 16px;border-bottom:1px solid var(--border)}.notify-list{max-height:60vh;overflow:auto}.notify-item{padding:13px 16px;border-bottom:1px solid var(--border);cursor:pointer}.notify-item:hover{background:rgba(110,168,255,.045)}.notify-item.unread{background:rgba(110,168,255,.07)}.notify-row{display:flex;justify-content:space-between;gap:12px}.notify-title{font-weight:760;font-size:13px}.notify-time{color:var(--muted);font-size:10px;white-space:nowrap}.notify-body{color:var(--soft);font-size:11px;margin-top:4px;line-height:1.45}.notify-sev{font-size:9px;font-weight:800;letter-spacing:.08em;margin-right:6px}.notify-sev.INFO{color:var(--blue)}.notify-sev.IMPORTANT{color:var(--green)}.notify-sev.WARNING{color:#ffbf69}.notify-sev.CRITICAL{color:#ff6b78}.notify-empty{padding:28px 16px;text-align:center;color:var(--muted);font-size:12px}.notification-settings{display:grid;gap:10px}.notification-setting{display:flex;justify-content:space-between;gap:16px;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)}.notification-setting:last-child{border-bottom:0}.switch{width:42px;height:24px;accent-color:#6ea8ff}.volume{width:150px}
/* Atlas opportunity observability */
.observability-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:14px;margin-top:14px}.observability-card{min-height:360px}.observable-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:12px}.observable-head h3{margin:0;font-size:16px}.observable-head p{margin:4px 0 0;color:var(--muted);font-size:11px;line-height:1.45}.opportunity-list{display:grid;gap:9px}.opportunity-item{display:grid;grid-template-columns:minmax(145px,.85fr) minmax(210px,1.45fr) auto;gap:12px;align-items:center;padding:12px 13px;border:1px solid var(--border);background:rgba(7,12,18,.46);border-radius:12px;cursor:pointer}.opportunity-item:hover{border-color:rgba(110,168,255,.32);background:rgba(110,168,255,.035)}.opportunity-item.ready{border-color:rgba(72,221,164,.32)}.opportunity-item.active{border-color:rgba(110,168,255,.34)}.opportunity-item.blocked{opacity:.9}.opportunity-name{font-size:12px;font-weight:800}.opportunity-value{font-size:17px;font-weight:830;margin-top:3px;letter-spacing:-.02em}.opportunity-next{font-size:11px;color:var(--soft);line-height:1.45}.opportunity-next strong{color:var(--text)}.opportunity-meta{font-size:10px;color:var(--muted);margin-top:4px}.opportunity-status{white-space:nowrap}.decision-timeline{display:grid;max-height:420px;overflow:auto;padding-right:2px}.decision-event{display:grid;grid-template-columns:9px 1fr auto;gap:10px;padding:11px 3px;border-bottom:1px solid var(--border);cursor:pointer}.decision-event:last-child{border-bottom:0}.decision-event:hover{background:rgba(110,168,255,.025)}.decision-dot{width:8px;height:8px;border-radius:50%;margin-top:5px;background:var(--blue)}.decision-dot.TRADE,.decision-dot.READY{background:var(--green)}.decision-dot.RISK,.decision-dot.BLOCK{background:var(--amber)}.decision-dot.CRITICAL{background:var(--red)}.decision-title{font-size:12px;font-weight:760}.decision-body{font-size:10.5px;color:var(--muted);line-height:1.45;margin-top:3px}.decision-time{font-size:9.5px;color:var(--muted);white-space:nowrap}.observability-empty{padding:24px 10px;text-align:center;color:var(--muted);font-size:11px}.queue-summary{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;color:var(--muted);font-size:10px}.queue-summary strong{color:var(--soft)}
@media(max-width:1050px){.observability-grid{grid-template-columns:1fr}}@media(max-width:760px){.opportunity-item{grid-template-columns:1fr}.opportunity-status{justify-self:start}}


/* Atlas command-center hierarchy v2 */
.command-focus{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:center;margin-top:14px;padding:12px 15px;border:1px solid rgba(110,168,255,.18);border-radius:13px;background:linear-gradient(90deg,rgba(110,168,255,.055),rgba(8,13,20,.55))}
.command-focus-main{min-width:0}.command-focus .decision-state{font-size:15px;margin:3px 0}.command-focus .decision-list{display:flex;gap:12px;flex-wrap:wrap;margin-top:7px}.command-focus .decision-item{display:flex;grid-template-columns:none;gap:6px;font-size:10.5px}.command-focus .actions{white-space:nowrap}
.command-details{margin-top:12px;border:1px solid var(--border);border-radius:14px;background:rgba(8,13,20,.44);overflow:hidden}.command-details>summary{list-style:none;cursor:pointer;padding:13px 15px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;font-weight:780;color:var(--soft);user-select:none}.command-details>summary::-webkit-details-marker{display:none}.command-details>summary:after{content:"＋";font-size:16px;color:var(--muted)}.command-details[open]>summary:after{content:"−"}.command-details[open]>summary{border-bottom:1px solid var(--border);color:var(--text)}.command-details-body{padding:14px}.command-details .strategy-authority-grid,.command-details .operator-grid,.command-details .section,.command-details .overview-support{margin-top:0}.command-details .overview-support{margin-top:14px}
.command-center-primary .observability-grid{margin-top:14px}.command-center-primary .observability-card{min-height:330px}.command-center-primary .decision-timeline{max-height:360px}.command-center-primary .opportunity-list{gap:7px}.command-center-primary .opportunity-item{padding:10px 12px}
.secondary-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.secondary-grid .card{min-height:0}
@media(max-width:900px){.command-focus{grid-template-columns:1fr}.secondary-grid{grid-template-columns:1fr}.command-focus .actions{white-space:normal}}



/* Atlas Brain information architecture — 1.30.43 */
.brain-section-label{display:flex;align-items:flex-start;gap:12px;margin:24px 0 10px;padding-top:4px}
.brain-section-label>span{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;background:#111c2a;border:1px solid #2c4058;color:#8bb8ef;font-size:9px;font-weight:800}
.brain-section-label strong{display:block;font-size:13px}.brain-section-label p{margin:3px 0 0;color:var(--muted);font-size:10px}
.brain-policy-control-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(420px,.92fr);gap:14px;align-items:start}
.brain-learning-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;align-items:start}
.brain-policy-control-grid>.card,.brain-learning-grid>.card{margin:0}
.consensus-full{max-height:none!important;overflow:visible!important;padding-right:0!important}
.consensus-overview{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.consensus-overview>div{padding:9px 10px;border:1px solid var(--border);border-radius:9px;background:#0a111a}
.consensus-overview strong{display:block;margin-top:3px;font-size:13px}
.consensus-card{border:1px solid var(--border);border-radius:13px;background:var(--panel3);padding:13px;display:grid;gap:12px}
.consensus-card.ready{border-color:rgba(72,221,164,.34);background:linear-gradient(90deg,rgba(72,221,164,.045),var(--panel3) 32%)}
.consensus-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.consensus-card-head strong{display:block;font-size:13px;margin:3px 0}
.consensus-value-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.consensus-value-grid>div{padding:9px 10px;border:1px solid rgba(255,255,255,.055);border-radius:9px;background:#091018}
.consensus-value-grid strong{display:block;margin-top:4px;font-size:13px;word-break:break-word}
.consensus-support-block{display:grid;gap:6px}
.consensus-gate{display:grid;grid-template-columns:auto 1fr;gap:9px;align-items:start;padding-top:9px;border-top:1px solid rgba(255,255,255,.055);font-size:10px;line-height:1.45}
.consensus-gate strong{color:var(--soft)}.consensus-gate span{color:var(--muted)}
@media(max-width:1180px){.brain-policy-control-grid,.brain-learning-grid{grid-template-columns:1fr}.consensus-overview{grid-template-columns:repeat(2,1fr)}}
@media(max-width:700px){.consensus-overview,.consensus-value-grid{grid-template-columns:1fr}.consensus-card-head{flex-direction:column}.consensus-gate{grid-template-columns:1fr}}

/* Information architecture refresh — Atlas 1.30.44 */
.global-status-strip{position:sticky;top:64px;z-index:19;display:flex;align-items:stretch;padding:0 26px;background:rgba(7,11,17,.96);border-bottom:1px solid var(--border);backdrop-filter:blur(14px);overflow-x:auto}
.global-status-strip button{appearance:none;background:transparent;border:0;border-right:1px solid var(--border);padding:10px 15px;color:var(--text);font:inherit;display:flex;align-items:center;gap:8px;white-space:nowrap;cursor:pointer}
.global-status-strip button:first-child{border-left:1px solid var(--border)}.global-status-strip button:hover{background:rgba(84,140,220,.08)}
.global-status-strip strong{font-size:11px}.global-label{font-size:8px;letter-spacing:.11em;color:var(--muted)}
.global-status-strip .dot{width:7px;height:7px}
.command-workspaces{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.workspace-card{appearance:none;width:100%;display:grid;grid-template-columns:52px 1fr 24px;align-items:center;gap:14px;text-align:left;border:1px solid var(--border);border-radius:16px;background:linear-gradient(145deg,rgba(15,22,33,.94),rgba(9,14,22,.94));color:var(--text);padding:17px 18px;cursor:pointer;transition:.15s ease}
.workspace-card:hover{transform:translateY(-1px);border-color:#38577b;background:linear-gradient(145deg,rgba(18,29,43,.98),rgba(10,17,27,.98))}
.workspace-card .workspace-icon{height:44px;border:1px solid #26384e;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;letter-spacing:.08em;background:#0c1521;color:#91b8ea}
.workspace-card strong{display:block;font-size:14px;margin:3px 0 4px}.workspace-card p{margin:0;color:var(--muted);font-size:11px;line-height:1.45}.workspace-arrow{font-size:19px;color:#7897ba}
.workspace-card.brain .workspace-icon{color:#bd9cff}.workspace-card.performance .workspace-icon{color:#8fd8aa}.workspace-card.portfolio .workspace-icon{color:#f0c77d}
.command-footer-note{margin-top:12px;padding:10px 12px;border:1px solid var(--border);border-radius:12px;color:var(--muted);font-size:10px;display:flex;align-items:center;gap:8px;background:rgba(8,13,20,.55)}
#view-overview .command-details{margin-top:12px}
#view-overview .observability-grid{margin-top:14px}
#view-market #live-execution-panel{margin-top:14px}
@media(max-width:900px){.command-workspaces{grid-template-columns:1fr}}
@media(max-width:760px){.global-status-strip{position:static;padding:0 12px}}

/* Performance Intelligence */
.performance-hero{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(420px,1fr);gap:14px}.performance-primary{min-height:310px;display:flex;flex-direction:column}.performance-net{font-size:38px;font-weight:850;letter-spacing:-.04em;margin-top:5px}.performance-sub{color:var(--soft);font-size:12px;margin-top:7px}.performance-kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.performance-kpis .card{min-height:92px;padding:16px}.performance-curve{flex:1;min-height:160px;margin-top:18px;border:1px solid var(--border);border-radius:12px;background:rgba(5,10,16,.42);overflow:hidden}.performance-curve svg{display:block;width:100%;height:100%}.performance-unit-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin-top:12px}.performance-unit-summary .mini{padding:10px 11px;border:1px solid var(--border);border-radius:10px;background:rgba(5,10,16,.38)}.performance-unit-summary .mini strong{display:block;font-size:16px;margin-top:3px}.performance-results{display:grid;gap:8px}.performance-result{display:grid;grid-template-columns:minmax(0,1.2fr) .8fr .7fr;gap:10px;align-items:center;padding:11px 12px;border:1px solid var(--border);border-radius:10px;background:rgba(5,10,16,.38)}.performance-bars{display:grid;gap:9px;margin-top:9px}.performance-bar{display:grid;grid-template-columns:110px 1fr 78px;gap:9px;align-items:center;font-size:11px}.performance-bar-track{height:8px;border-radius:5px;background:#192333;overflow:hidden}.performance-bar-fill{height:100%;border-radius:5px;background:var(--blue)}
@media(max-width:1100px){.performance-hero{grid-template-columns:1fr}.performance-kpis{grid-template-columns:repeat(3,1fr)}}
@media(max-width:760px){.performance-kpis{grid-template-columns:repeat(2,1fr)}.performance-result{grid-template-columns:1fr auto}.performance-result .muted:last-child{grid-column:1/-1}}

@media(max-width:1100px){.command-hero,.operator-grid{grid-template-columns:1fr}.command-side{border-left:0;border-top:1px solid rgba(110,168,255,.16)}.account-strip{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.shell{grid-template-columns:1fr}.sidebar{padding:14px}.brand{margin-bottom:14px}.nav{grid-template-columns:repeat(3,1fr)}.nav button{padding:9px 4px}.nav button:before,.nav button.active:after{display:none}.content{padding:18px 12px 45px}.page-head{display:block}.command-primary{padding:20px}.command-hero{min-height:0}.command-side .kpis,.account-strip,.campaign-ladder{grid-template-columns:1fr}.operator-grid{grid-template-columns:1fr}.hero-status{font-size:26px}.topbar{height:58px}}

/* Atlas 1.30.44 portfolio risk allocation */
.risk-allocation-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin:4px 0 13px}.risk-allocation-total{font-size:26px;font-weight:800;letter-spacing:-.03em;margin:4px 0}.risk-allocation-hard{display:grid;text-align:right;gap:3px}.risk-allocation-hard strong{font-size:18px}.risk-allocation-bar{height:15px;border:1px solid var(--border);border-radius:999px;overflow:hidden;display:flex;background:#081018}.risk-segment{height:100%;transition:width .25s ease}.risk-segment.active{background:rgba(101,161,255,.85)}.risk-segment.zone{background:rgba(241,190,79,.9)}.risk-segment.free{background:rgba(72,221,164,.8)}.risk-allocation-legend{display:flex;flex-wrap:wrap;gap:16px;margin:9px 0 14px;color:var(--muted);font-size:10px}.risk-allocation-legend span{display:flex;align-items:center;gap:6px}.risk-dot{width:8px;height:8px;border-radius:50%;display:inline-block}.risk-dot.active{background:rgba(101,161,255,.9)}.risk-dot.zone{background:rgba(241,190,79,.95)}.risk-dot.free{background:rgba(72,221,164,.9)}.risk-allocation-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.risk-allocation-card{border:1px solid var(--border);border-radius:12px;padding:12px;background:var(--panel3);display:grid;gap:8px;min-width:0}.risk-allocation-card .risk-card-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.risk-allocation-card .risk-card-head strong{font-size:12px}.risk-allocation-card .risk-amount{font-size:19px;font-weight:800}.risk-allocation-card .risk-detail{display:grid;grid-template-columns:1fr auto;gap:7px;border-top:1px solid rgba(255,255,255,.055);padding-top:7px;font-size:10px}.risk-allocation-card .risk-detail span{color:var(--muted)}.opportunity-item.qualifying{border-color:rgba(241,190,79,.32);background:linear-gradient(90deg,rgba(241,190,79,.035),transparent 45%)}@media(max-width:900px){.risk-allocation-cards{grid-template-columns:1fr}.risk-allocation-hero{align-items:flex-start;flex-direction:column}.risk-allocation-hard{text-align:left}}

/* Atlas Brain policy lifecycle — 1.30.43 */
.gemini-run-history,.policy-window-list{display:grid;gap:9px}
.gemini-run-row,.policy-window-row{border:1px solid var(--border);border-radius:12px;background:var(--panel3);padding:12px;cursor:pointer}
.gemini-run-row:hover{border-color:#355272}.gemini-run-head,.policy-window-row{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.gemini-run-meta{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:8px;color:var(--muted);font-size:10px}
.policy-window-history{margin-top:12px}.policy-window-list{margin-top:8px}.policy-window-row.current{border-color:rgba(101,161,255,.35);background:linear-gradient(90deg,rgba(101,161,255,.045),var(--panel3) 32%)}


.zone-card.invalidated{opacity:.82;border-color:rgba(255,91,116,.28);background:linear-gradient(90deg,rgba(255,91,116,.045),var(--panel3) 36%)}
.zone-plan.invalidated{border-color:rgba(255,91,116,.35);background:linear-gradient(90deg,rgba(255,91,116,.05),var(--panel2) 45%)}

/* Atlas Help & Guide — 1.30.44 */
.help-hero{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(280px,.7fr);gap:14px;align-items:stretch}
.help-hero-copy{padding:24px}.help-hero-copy h3{font-size:22px;margin:0 0 8px}.help-hero-copy p{max-width:840px;line-height:1.7}
.help-search-wrap{display:flex;gap:10px;align-items:center;margin-top:16px}.help-search-wrap .search{flex:1;min-width:0}
.help-quick{display:grid;gap:9px;padding:16px}.help-quick button{width:100%;text-align:left}
.help-section{margin-top:16px}.help-section>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:12px;padding:15px 17px;border:1px solid var(--border);border-radius:13px;background:var(--panel2);font-weight:800}
.help-section>summary::-webkit-details-marker{display:none}.help-section>summary:after{content:"＋";color:var(--muted);font-size:17px}.help-section[open]>summary:after{content:"−"}.help-section[open]>summary{border-bottom-left-radius:0;border-bottom-right-radius:0}
.help-section-body{border:1px solid var(--border);border-top:0;border-radius:0 0 13px 13px;padding:16px;background:rgba(8,13,20,.4)}
.help-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.help-grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}
.help-card{border:1px solid var(--border);border-radius:12px;padding:14px;background:var(--panel3);min-width:0}.help-card h4{margin:0 0 8px;font-size:13px}.help-card p{margin:5px 0;color:var(--muted);font-size:11px;line-height:1.55}.help-card strong{color:var(--text)}
.help-definition{display:grid;grid-template-columns:minmax(150px,.32fr) minmax(0,1fr);gap:12px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.055);font-size:11px;line-height:1.5}.help-definition:last-child{border-bottom:0}.help-definition dt{font-weight:800;color:var(--soft)}.help-definition dd{margin:0;color:var(--muted)}
.help-definition code,.help-card code{font-size:10px;color:#a9c8ef;background:#09121d;border:1px solid rgba(255,255,255,.06);padding:2px 5px;border-radius:5px}
.help-callout{padding:12px 14px;border:1px solid rgba(110,168,255,.25);border-radius:11px;background:rgba(72,126,190,.06);font-size:11px;line-height:1.55;color:var(--soft);margin:10px 0}.help-callout.warn{border-color:rgba(241,190,79,.28);background:rgba(241,190,79,.05)}
.help-flow{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:12px 0}.help-flow span{padding:7px 10px;border:1px solid var(--border);border-radius:999px;background:#0a111a;font-size:10px;font-weight:760}.help-flow b{color:var(--muted)}
.help-chip-row{display:flex;flex-wrap:wrap;gap:7px}.help-chip{font-size:9px;padding:5px 8px;border-radius:999px;border:1px solid var(--border);color:var(--soft);background:#0a111a}
.help-hidden{display:none!important}.help-empty{padding:22px;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:12px;margin-top:14px;display:none}
.help-version{font-family:var(--mono);font-size:10px;color:var(--muted)}
@media(max-width:1000px){.help-hero,.help-grid,.help-grid.three{grid-template-columns:1fr}.help-definition{grid-template-columns:1fr;gap:4px}}

</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand"><img class="logo" src="/assets/atlas-sidebar-icon.png" alt="Atlas"><div><h1>Atlas</h1><small>Adaptive Trading Intelligence</small></div></div>
    <nav class="nav">
      <button class="active" data-view="overview">Command Center</button>
      <button data-view="market">Market</button>
      <button data-view="analysis">Zone Analysis</button>
      <button data-view="positions">Portfolio</button>
      <button data-view="performance">Performance</button>
      <button data-view="atlas">Atlas Brain</button>
      <button data-view="control">Settings</button>
      <button data-view="history">System & Audit</button>
      <button data-view="help">Help & Guide</button>
    </nav>
    <div class="sidebar-bottom">
      <div class="connection">
        <div class="row"><span><span id="side-dot" class="dot"></span>&nbsp; Nyao</span><strong id="side-connection">Checking</strong></div>
        <div class="row" style="margin-top:7px"><span class="muted">Instrument</span><strong id="side-symbol">—</strong></div>
        <div class="muted" style="margin-top:6px;font-size:11px">Account type is reported by MT5. Atlas uses the same safety pipeline either way.</div>
      </div>
    </div>
  </aside>



      <section id="view-help" class="view">
        <div class="page-head"><div><h2>Help & Atlas Guide</h2><p>The complete operator handbook for understanding the dashboard, trading states, risk, zones, Nyao execution and Atlas Brain.</p></div><span class="badge info">START HERE</span></div>

        <div class="help-hero">
          <div class="card help-hero-copy">
            <div class="label">Atlas operator handbook</div>
            <h3>Understand what Atlas is telling you — and what it is not.</h3>
            <p>Atlas separates <strong>market interpretation</strong>, <strong>deterministic risk authority</strong>, <strong>Nyao execution</strong>, and <strong>Gemini policy learning</strong>. This guide explains the dashboard in that same order so a new operator can understand why a trade is or is not allowed without reading the source code.</p>
            <div class="help-flow"><span>Market evidence</span><b>→</b><span>Atlas risk & zone authority</span><b>→</b><span>Nyao execution gates</span><b>→</b><span>Position lifecycle</span><b>→</b><span>Performance evidence</span><b>→</b><span>Gemini policy learning</span></div>
            <div class="help-search-wrap"><input id="help-search" class="search" placeholder="Search: spread cap, zone invalidated, lifecycle P/L, consensus, MFE…" oninput="filterHelp(this.value)"><button class="btn" onclick="clearHelpSearch()">Clear</button></div>
            <div class="help-version">Guide aligned to Atlas 1.30.44 · Nyao 44.5.3</div>
          </div>
          <div class="card help-quick">
            <div class="label">Jump to a live workspace</div>
            <button class="btn" onclick="go('overview')">Command Center · What matters now</button>
            <button class="btn" onclick="go('market')">Market · Signals & execution economics</button>
            <button class="btn" onclick="go('analysis')">Zone Analysis · Trade locations & lifecycle</button>
            <button class="btn" onclick="go('positions')">Portfolio · Exposure & risk allocation</button>
            <button class="btn" onclick="go('performance')">Performance · Strategic outcomes</button>
            <button class="btn" onclick="go('atlas')">Atlas Brain · Gemini & policies</button>
            <button class="btn" onclick="go('control')">Settings · Operator controls</button>
            <button class="btn" onclick="go('history')">System & Audit · Authoritative history</button>
          </div>
        </div>

        <div id="help-no-results" class="help-empty">No Help topics match that search.</div>

        <details class="help-section help-searchable" open data-help="start basics architecture atlas nyao gemini authority">
          <summary><span>1 · Start here — how Atlas is structured</span><span class="badge ok">FOUNDATION</span></summary>
          <div class="help-section-body">
            <div class="help-grid three">
              <div class="help-card"><h4>Atlas</h4><p>The orchestration, market-context and deterministic risk layer. Atlas builds zone maps, capital envelopes, risk reservations, policy evidence and instructions for Nyao. It may reduce or veto risk but cannot manufacture broker feasibility.</p></div>
              <div class="help-card"><h4>Nyao</h4><p>The MT5 Expert Advisor and final execution authority. Nyao evaluates live BUY/SELL signals, broker constraints, actual lot sizing, order placement, position management, recovery and telemetry.</p></div>
              <div class="help-card"><h4>Gemini / Atlas Brain</h4><p>The reasoning and policy-learning layer. Gemini can propose changes to the Nyao runtime policy. Deterministic validation, consensus, dwell, position locks and operator mode decide whether those proposals can become active.</p></div>
            </div>
            <div class="help-callout"><strong>Important:</strong> a Gemini opinion is not an order. A zone is not automatically a trade. A high signal score is not enough by itself. New risk is allowed only when every applicable deterministic gate agrees.</div>
            <dl>
              <div class="help-definition"><dt>Policy epoch</dt><dd>A durable version of the Nyao runtime policy. Existing positions keep the management/recovery policy from their entry epoch so later policy changes do not rewrite their lifecycle.</dd></div>
              <div class="help-definition"><dt>Command version</dt><dd>The bridge package version requested by Atlas and acknowledged by Nyao. It is execution synchronization, not the same thing as a policy epoch.</dd></div>
              <div class="help-definition"><dt>Selected symbol</dt><dd>Every workspace is scoped to the currently selected instrument. Account-level cards can still reflect the MT5 account as a whole.</dd></div>
              <div class="help-definition"><dt>Authoritative vs diagnostic</dt><dd>Authoritative values drive execution/risk. Diagnostic values explain behavior and learning but do not independently permit a trade.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="command center overview opportunity queue decision timeline balance equity system health campaign">
          <summary><span>2 · Command Center</span><span class="badge info">DAILY HOME</span></summary>
          <div class="help-section-body">
            <div class="help-callout">Use this page first. It answers: <strong>What mode is Atlas in? Is anything actionable? What is blocking execution? What risk is being used?</strong> Detailed diagnostics live in the specialist workspaces.</div>
            <div class="help-grid">
              <div class="help-card"><h4>Operating mode hero</h4><p><strong>Trading mode</strong> tells you whether normal scalping, zone-aware scalping or zone campaign execution currently owns fresh-entry authority. <strong>Campaign risk</strong> is the current zone campaign risk envelope when applicable. <strong>Live / staged</strong> summarizes campaign layers. <strong>Next Brain review</strong> shows the scheduled Gemini review cadence.</p></div>
              <div class="help-card"><h4>Account strip</h4><p><strong>Balance</strong> is closed-account value. <strong>Equity</strong> includes floating P/L. <strong>Open P/L</strong> is current mark-to-market. <strong>Drawdown</strong> is decline from tracked peak equity. <strong>Live market</strong> shows current price and spread. <strong>System health</strong> reflects bridge/Nyao synchronization.</p></div>
              <div class="help-card"><h4>Opportunity Queue</h4><p>Each row is a possible fresh opportunity. <strong>WATCHING</strong> means a prerequisite such as score is not met. <strong>QUALIFYING</strong> means the base setup passed but an extra contextual gate remains. <strong>READY</strong> means the displayed deterministic opportunity gates pass. <strong>BLOCKED</strong> is reserved for a real veto.</p></div>
              <div class="help-card"><h4>Decision Timeline</h4><p>A compact event log of material state transitions: signal eligibility, cost gates, zone handoffs, risk reservations, policy application and trade lifecycle events. It is intentionally not every polling refresh.</p></div>
              <div class="help-card"><h4>Operator attention</h4><p>A synthesized “what needs attention now” card. It prioritizes synchronization failures, capital vetoes, execution blockers and material lifecycle changes over ordinary monitoring states.</p></div>
              <div class="help-card"><h4>Active trade plan</h4><p>Shows either the current zone campaign ladder, a zone-aware scalp fallback, or ordinary scalp gates. <strong>LIVE</strong> layers are already exposed; <strong>STAGED</strong> layers are admitted but not filled; <strong>PLANNED</strong> layers are geometry only.</p></div>
            </div>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="market signals buy sell score evaluated threshold blocker spread cost atr volatility regime confidence">
          <summary><span>3 · Market — signals, gates and execution economics</span><span class="badge info">LIVE EVIDENCE</span></summary>
          <div class="help-section-body">
            <dl>
              <div class="help-definition"><dt>BUY / SELL score</dt><dd>Nyao's raw directional evidence score built from trend, momentum, chop, peak, volatility, impulse and other configured components.</dd></div>
              <div class="help-definition"><dt>Evaluated / adjusted score</dt><dd>The score after applicable runtime adjustments such as dampening, position pressure or contextual modifiers. This is the value compared with the effective threshold.</dd></div>
              <div class="help-definition"><dt>Threshold</dt><dd>The minimum evaluated score required before the direction can proceed to later gates. Reaching threshold does not bypass cost, capital, duplicate-distance, cooldown, zone or broker checks.</dd></div>
              <div class="help-definition"><dt>BUY / SELL state</dt><dd>Human-readable result of the current gate chain. A low score should normally appear as watching rather than a deterministic block.</dd></div>
              <div class="help-definition"><dt>Global blocker</dt><dd>A market-wide veto affecting both directions, such as trading pause, account safety, committed zone ownership or another global execution condition.</dd></div>
              <div class="help-definition"><dt>New-bar gate</dt><dd>Whether entry is restricted to a new candle. When disabled, qualified intrabar entries may be evaluated.</dd></div>
              <div class="help-definition"><dt>Cooldown</dt><dd>Temporary protection after configured loss sequences or other timing conditions. It prevents repeated immediate re-entry.</dd></div>
              <div class="help-definition"><dt>Spread gate</dt><dd>Whether the current bid/ask cost is acceptable for the active strategy geometry. Scalp and zone campaigns use separate economics.</dd></div>
              <div class="help-definition"><dt>Market bias</dt><dd>Atlas's current directional interpretation. It explains context; it is not execution authority by itself.</dd></div>
              <div class="help-definition"><dt>Volatility / volatility ratio</dt><dd>Current ATR conditions compared with recent average ATR. The ratio helps Atlas scale risk and judge whether current movement is unusual.</dd></div>
              <div class="help-definition"><dt>Execution fit</dt><dd>Whether current market geometry and cost are suitable for the strategy. A strong directional thesis can still have poor execution fit.</dd></div>
              <div class="help-definition"><dt>Risk state</dt><dd>Atlas's deterministic risk classification after drawdown, loss streak, volatility and other safety modifiers.</dd></div>
              <div class="help-definition"><dt>Bid / ask gap</dt><dd>The actual spread expressed in price terms for easier comparison with stop/target geometry.</dd></div>
              <div class="help-definition"><dt>Economic spread cap</dt><dd>The adaptive maximum spread justified by the current strategy geometry. It is not the same as the old static `MaxSpreadPoints` ceiling.</dd></div>
              <div class="help-definition"><dt>Spread / cap</dt><dd>Cost pressure relative to the adaptive cap. Above 1.0 means current cost exceeds the allowed economic envelope.</dd></div>
              <div class="help-definition"><dt>Entry eligible</dt><dd>Final direction-level eligibility after the current chain of Nyao gates. Broker order placement can still fail after this if the broker rejects an order.</dd></div>
            </dl>
            <div class="help-callout warn"><strong>Common cost reasons:</strong> <code>STOP_EXPANSION_EXCESSIVE</code> means spread forces the planned protective structure to expand too far; <code>STOP_AND_TARGET</code> indicates both stop and target economics constrain the setup. These mean the idea may be directionally valid but economically poor to execute.</div>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="zone analysis fvg order block support resistance supply demand fresh mitigated invalidated lifecycle zone aware campaign invalidation spread confirmation">
          <summary><span>4 · Zone Analysis — locations, lifecycle and execution handoff</span><span class="badge info">STRUCTURE</span></summary>
          <div class="help-section-body">
            <div class="help-grid three">
              <div class="help-card"><h4>FVG</h4><p>Fair Value Gap detected from three-candle displacement geometry. Atlas stores side, bounds, age, width in ATR and mitigation/invalidation state.</p></div>
              <div class="help-card"><h4>Order Block</h4><p>Last opposing candle before qualifying displacement. It becomes a demand or supply location depending on displacement direction.</p></div>
              <div class="help-card"><h4>Support / Resistance</h4><p>Repeated closed-candle pivot reactions clustered into a structural zone.</p></div>
            </div>
            <div class="help-flow"><span>FRESH</span><b>→ touch</b><span>MITIGATED</span><b>→ later close beyond boundary</b><span>INVALIDATED</span><b>→</b><span>ARCHIVED</span></div>
            <dl>
              <div class="help-definition"><dt>Demand / BUY zone</dt><dd>A structural area expected to provide buying support. Deterministic invalidation occurs when a later relevant closed candle finishes below the zone low.</dd></div>
              <div class="help-definition"><dt>Supply / SELL zone</dt><dd>A structural area expected to provide selling pressure. Deterministic invalidation occurs when a later relevant closed candle finishes above the zone high.</dd></div>
              <div class="help-definition"><dt>FRESH</dt><dd>Detected and not materially revisited.</dd></div>
              <div class="help-definition"><dt>MITIGATED</dt><dd>Price has interacted with the zone but the structural boundary still holds. A wick beyond the boundary does not invalidate it.</dd></div>
              <div class="help-definition"><dt>INVALIDATED</dt><dd>A later closed candle has closed beyond the technical boundary. The zone is removed from fresh priority selection but retained in invalidated-zone history.</dd></div>
              <div class="help-definition"><dt>Zone score</dt><dd>Relative structural quality using timeframe, age, touches, geometry, confluence and zone-type evidence. It ranks zones; it does not by itself permit entry.</dd></div>
              <div class="help-definition"><dt>Width ATR</dt><dd>Zone width normalized by ATR. Helps Atlas reject zones that are too broad for the current timeframe/structure model.</dd></div>
              <div class="help-definition"><dt>Confluence</dt><dd>Other zones/structures overlapping the location, such as H4 Order Block plus H4 Support/Resistance. Confluence can strengthen location quality.</dd></div>
              <div class="help-definition"><dt>Touch count</dt><dd>Number of historical interactions detected after creation. It is lifecycle evidence, not simply “more is better.”</dd></div>
              <div class="help-definition"><dt>Invalidating close</dt><dd>The closed-candle price that crossed the technical boundary and caused invalidation.</dd></div>
              <div class="help-definition"><dt>Invalidation penetration / ATR</dt><dd>How far the invalidating close finished beyond the boundary, both in price units and ATR-normalized form.</dd></div>
              <div class="help-definition"><dt>Zone-aware scalp</dt><dd>The zone remains context while Nyao retains fresh scalp authority. Aligned scalps use normal gates; counter-zone scalps need stronger evidence and reduced risk.</dd></div>
              <div class="help-definition"><dt>Zone-aligned scalp</dt><dd>A scalp in the same direction as the current source zone, e.g. SELL inside a SELL/supply context.</dd></div>
              <div class="help-definition"><dt>Counter-zone scalp</dt><dd>A scalp against the current zone direction. It is conditionally allowed, not automatically blocked. It receives stricter evidence/risk rules and can be blocked near campaign commitment.</dd></div>
              <div class="help-definition"><dt>ZONE_ENTRY_CONFIRMED</dt><dd>Campaign confirmation gates have passed and fresh scalp authority may be suspended while Atlas attempts to establish the zone campaign.</dd></div>
              <div class="help-definition"><dt>ZONE_CAMPAIGN_ACTIVE</dt><dd>Actual `ATLAS_ZONE` exposure exists for the plan. Campaign lineage is now authoritative and the plan is managed as one composite risk unit.</dd></div>
              <div class="help-definition"><dt>ZONE_CAMPAIGN_INVALIDATED_MANAGEMENT</dt><dd>The source zone failed after campaign exposure already existed. Existing positions remain managed, but no new campaign layers may open.</dd></div>
              <div class="help-definition"><dt>Zone spread cap</dt><dd>Dedicated campaign spread economics computed from campaign stop/target geometry. It is separate from the scalp spread cap.</dd></div>
              <div class="help-definition"><dt>Campaign lock</dt><dd>True only when actual exposure belonging to that exact zone plan exists. Unrelated scalp/recovery positions must not lock a zone campaign.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="portfolio positions volume realized floating lifecycle risk allocation reservation operating ceiling hard ceiling recovery chain">
          <summary><span>5 · Portfolio — exposure, lifecycle P/L and risk allocation</span><span class="badge info">CAPITAL</span></summary>
          <div class="help-section-body">
            <div class="help-grid three">
              <div class="help-card"><h4>Strategy positions</h4><p>Number of Atlas/Nyao-managed open MT5 positions for the selected strategy/symbol.</p></div>
              <div class="help-card"><h4>Total lots remaining</h4><p>Current still-open volume. After partial closes this is lower than the original volume.</p></div>
              <div class="help-card"><h4>Recovery chains</h4><p>Active root + hedge-child composites being managed as one strategic risk unit.</p></div>
              <div class="help-card"><h4>Realized while active</h4><p>Exact P/L already realised from partial exits while the position/composite is still open.</p></div>
              <div class="help-card"><h4>Floating P/L</h4><p>Current MT5 mark-to-market of remaining open volume.</p></div>
              <div class="help-card"><h4>Active lifecycle P/L</h4><p><strong>Realised while active + floating P/L.</strong> This is the best current economic picture of an unfinished lifecycle.</p></div>
            </div>
            <div class="help-callout"><strong>Risk allocation reconciliation:</strong> Operating ceiling = active reservations + prospective zone priority reservation + free operating risk. Hard-ceiling headroom is shown separately because it is not necessarily deployable immediately.</div>
            <dl>
              <div class="help-definition"><dt>Portfolio hard ceiling</dt><dd>The operator-owned maximum aggregate Atlas risk percentage converted to money. Atlas/Gemini may reduce deployment but cannot raise this ceiling.</dd></div>
              <div class="help-definition"><dt>Operating risk ceiling</dt><dd>The currently deployable aggregate risk envelope after deterministic modifiers such as loss streak, volatility, drawdown and risk state.</dd></div>
              <div class="help-definition"><dt>Active reservation</dt><dd>Risk capacity already committed to an active standalone trade, recovery chain or zone campaign. Recovery chains reserve their frozen chain ceiling rather than only current floating loss.</dd></div>
              <div class="help-definition"><dt>Prospective zone reservation</dt><dd>Capacity preserved for a strong zone campaign before its first fill. It prevents unrelated scalp risk from consuming campaign headroom.</dd></div>
              <div class="help-definition"><dt>Free operating risk</dt><dd>Operating capacity left after active and prospective reservations. This is not necessarily the risk of the next trade; per-opportunity caps still apply.</dd></div>
              <div class="help-definition"><dt>Hard headroom</dt><dd>Unused portion of the operator hard ceiling. It can be larger than free operating risk because Atlas may intentionally operate below the hard limit.</dd></div>
              <div class="help-definition"><dt>Volume 0.06 / 0.17</dt><dd>Remaining volume / original volume. In this example 0.11 lots have already been closed.</dd></div>
              <div class="help-definition"><dt>Realized</dt><dd>Exact MT5 realised net P/L already attached to partial exit deals for this still-active lifecycle.</dd></div>
              <div class="help-definition"><dt>Lifecycle</dt><dd>Realized-so-far plus current floating P/L. It remains provisional until the entire strategic unit is flat.</dd></div>
              <div class="help-definition"><dt>Context / Origin</dt><dd>How the trade entered: e.g. `FRESH_MARKET`, `FRESH_LIMIT`, `HEDGE_CHILD`, `ATLAS_ZONE`, or contextual classifications such as `ZONE_ALIGNED_SCALP` / `COUNTER_ZONE_SCALP`.</dd></div>
              <div class="help-definition"><dt>Policy epoch</dt><dd>The runtime policy locked at entry for lifecycle attribution and position-sensitive management.</dd></div>
              <div class="help-definition"><dt>Quality</dt><dd>Outcome-lineage quality, indicating whether realised values and entry identity are exact or partly reconstructed/inferred.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="performance expectancy win rate profit factor drawdown risk units recovery zone campaign mfe mae learning readiness evidence">
          <summary><span>6 · Performance Intelligence</span><span class="badge info">LEARNING EVIDENCE</span></summary>
          <div class="help-section-body">
            <div class="help-callout">Performance scores <strong>strategic risk units</strong>, not every MT5 ticket as an independent win/loss. A recovery root plus its hedge children score once when the chain is completely flat; a multi-layer zone campaign also scores once.</div>
            <dl>
              <div class="help-definition"><dt>Strategic net P/L</dt><dd>Sum of completed composite risk-unit outcomes used for strategy-level learning.</dd></div>
              <div class="help-definition"><dt>Completed risk units</dt><dd>Standalone trades, completed recovery chains and completed zone campaigns eligible to be scored.</dd></div>
              <div class="help-definition"><dt>Expectancy / unit</dt><dd>Average realised strategic P/L per completed risk unit.</dd></div>
              <div class="help-definition"><dt>Win rate</dt><dd>Percentage of completed strategic units with positive realised P/L.</dd></div>
              <div class="help-definition"><dt>Profit factor</dt><dd>Gross strategic wins divided by absolute gross strategic losses. Above 1 means gross wins exceed gross losses.</dd></div>
              <div class="help-definition"><dt>Max closed drawdown</dt><dd>Largest peak-to-trough decline in the sequence of completed strategic outcomes, not live account equity drawdown.</dd></div>
              <div class="help-definition"><dt>Standalone scalps</dt><dd>Independent non-composite trade outcomes.</dd></div>
              <div class="help-definition"><dt>Recovery chains</dt><dd>Root and hedge descendants aggregated into one completed outcome.</dd></div>
              <div class="help-definition"><dt>Zone campaigns</dt><dd>All campaign layers sharing the immutable zone plan token aggregated into one completed outcome.</dd></div>
              <div class="help-definition"><dt>Performance by policy epoch</dt><dd>Attributes each strategic unit to the policy active at its root entry so you can compare whether later runtime policies improved outcomes.</dd></div>
              <div class="help-definition"><dt>MFE</dt><dd>Maximum Favorable Excursion: best unrealised movement achieved during a ticket's life.</dd></div>
              <div class="help-definition"><dt>MAE</dt><dd>Maximum Adverse Excursion: worst unrealised movement experienced during a ticket's life.</dd></div>
              <div class="help-definition"><dt>MFE captured</dt><dd>How much of available favorable excursion was ultimately converted into realised outcome; used as a responsiveness/profit-capture diagnostic.</dd></div>
              <div class="help-definition"><dt>Exact outcomes</dt><dd>Strategic results backed by authoritative MT5 exit-deal lineage.</dd></div>
              <div class="help-definition"><dt>Inferred outcomes</dt><dd>Historical results reconstructed from incomplete/legacy lineage. Useful but lower-quality evidence.</dd></div>
              <div class="help-definition"><dt>Active unscored units</dt><dd>Open composites that must not influence completed win/loss streaks until fully flat.</dd></div>
              <div class="help-definition"><dt>Learning readiness</dt><dd>Evidence-maturity assessment preventing Atlas Brain from treating a tiny sample as proof.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="atlas brain gemini runtime policy candidate consensus observations runs epoch critic confidence dwell deferred autonomous supervised parameter intelligence">
          <summary><span>7 · Atlas Brain — Gemini, observations, consensus and policy epochs</span><span class="badge info">POLICY LIFECYCLE</span></summary>
          <div class="help-section-body">
            <div class="help-flow"><span>Gemini run</span><b>→</b><span>proposal / no-change</span><b>→ critic + deterministic validation</b><span>accepted observation</span><b>→</b><span>candidate consensus</span><b>→</b><span>new policy epoch</span></div>
            <div class="help-callout"><strong>Key distinction:</strong> a Gemini run is not automatically an accepted observation, and an accepted observation is not automatically a new policy.</div>
            <dl>
              <div class="help-definition"><dt>Runtime policy</dt><dd>The authoritative Nyao policy currently active. This card should never be overwritten by reasoning from a newer unapplied Gemini run.</dd></div>
              <div class="help-definition"><dt>Policy epoch</dt><dd>The active durable runtime-policy generation.</dd></div>
              <div class="help-definition"><dt>Runtime controls</dt><dd>Number of registered Nyao controls represented in the active policy snapshot.</dd></div>
              <div class="help-definition"><dt>Reconciliation</dt><dd>Whether Atlas's registered policy and Nyao's applied runtime values agree.</dd></div>
              <div class="help-definition"><dt>Gemini run history</dt><dd>Every durable policy-analysis cycle, including `NO CHANGE`, `OBSERVED`, `DEFERRED`, `REJECTED`, `FAILED` and `APPLIED` outcomes.</dd></div>
              <div class="help-definition"><dt>Accepted observation</dt><dd>A Gemini proposal/observation that passed the requirements to enter the consensus evidence window for the current baseline epoch.</dd></div>
              <div class="help-definition"><dt>0 of 3 minimum</dt><dd>Zero accepted observations exist in the current epoch's consensus window; at least three are required before consensus may qualify. It does not mean Gemini has never run.</dd></div>
              <div class="help-definition"><dt>Candidate consensus</dt><dd>Aggregation of accepted observations proposing compatible control values for the same active baseline. It is evidence for a possible next policy, not the active policy.</dd></div>
              <div class="help-definition"><dt>Baseline epoch</dt><dd>The policy epoch Gemini evaluated when creating the proposal. Consensus observations should not mix incompatible baseline epochs.</dd></div>
              <div class="help-definition"><dt>Confidence</dt><dd>Gemini's reported confidence; deterministic minimum-confidence requirements can prevent advancement.</dd></div>
              <div class="help-definition"><dt>Critic</dt><dd>The review layer evaluating whether the proposal is sufficiently grounded/safe to proceed into the deterministic policy pipeline.</dd></div>
              <div class="help-definition"><dt>Minimum dwell</dt><dd>Minimum time a policy must remain active before another autonomous policy replacement can normally occur.</dd></div>
              <div class="help-definition"><dt>Supervised mode</dt><dd>Gemini may propose and validate, but a human approval workflow is required before command application.</dd></div>
              <div class="help-definition"><dt>Autonomous mode</dt><dd>Atlas may apply a validated proposal only after all configured confidence, consensus, dwell, safety and position-lock rules pass.</dd></div>
              <div class="help-definition"><dt>Deferred locked change</dt><dd>A position-sensitive parameter suggested while exposure is open. Atlas records the suggestion but does not mutate that control for already-managed positions.</dd></div>
              <div class="help-definition"><dt>Scalping responsiveness</dt><dd>Evidence about opportunity latency, blocker pressure, hold duration and favorable-excursion capture. It measures quality/speed rather than encouraging more trades.</dd></div>
              <div class="help-definition"><dt>Parameter Intelligence</dt><dd>Ranks registered controls using parameter-specific evidence, observed runtime variation and outcome associations. Position-sensitive controls receive additional activation protection.</dd></div>
              <div class="help-definition"><dt>Change budget</dt><dd>Maximum number of validated control mutations Atlas permits in one policy update, limiting broad simultaneous changes.</dd></div>
              <div class="help-definition"><dt>PRE-FIX CONSENSUS BYPASS</dt><dd>Historical marker for an epoch created before the 1.30.42 consensus-gate correction. It is historical debt, not permission for future bypasses.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="settings risk appetite hard ceiling notifications supervised execution runtime controls command global enabled base lot">
          <summary><span>8 · Settings — operator authority and advanced controls</span><span class="badge warn">ADVANCED</span></summary>
          <div class="help-section-body">
            <dl>
              <div class="help-definition"><dt>Supervised execution</dt><dd>Human-review pipeline for building and applying an approved policy command. Backend fingerprint/epoch/review checks remain authoritative.</dd></div>
              <div class="help-definition"><dt>Current command</dt><dd>The policy command package currently requested on the Atlas↔Nyao bridge.</dd></div>
              <div class="help-definition"><dt>Base lot</dt><dd>Runtime base lot control. When dynamic sizing/capital sizing is active, final Nyao volume can differ because broker-risk calculations remain authoritative.</dd></div>
              <div class="help-definition"><dt>Global enabled</dt><dd>Master Atlas/Nyao strategy switch for fresh execution. Position management can remain relevant even when fresh entries are disabled.</dd></div>
              <div class="help-definition"><dt>Portfolio risk appetite</dt><dd>Operator-owned aggregate risk ceiling. It is <strong>not per-trade risk</strong>. Atlas can operate below it but cannot autonomously exceed it.</dd></div>
              <div class="help-definition"><dt>Current hard risk amount</dt><dd>Money value of the configured hard-ceiling percentage using current Atlas risk capital.</dd></div>
              <div class="help-definition"><dt>Atlas operating ceiling</dt><dd>Current lower deployable ceiling after deterministic risk modifiers.</dd></div>
              <div class="help-definition"><dt>Notifications</dt><dd>Human-facing material state changes. Repeated polling states are deduplicated; sound/browser preferences control presentation, not trading authority.</dd></div>
              <div class="help-definition"><dt>Advanced runtime controls</dt><dd>Direct view of the full registered Nyao control surface. Changing these can materially alter execution and should be treated as advanced operator action.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="system audit execution lifecycle policy epochs tracked outcomes authoritative history integrity">
          <summary><span>9 · System & Audit</span><span class="badge">READ ONLY</span></summary>
          <div class="help-section-body">
            <dl>
              <div class="help-definition"><dt>Execution audit</dt><dd>Integrity/verification state for recorded execution evidence.</dd></div>
              <div class="help-definition"><dt>Policy epochs</dt><dd>Count and history of durable applied policy generations.</dd></div>
              <div class="help-definition"><dt>Tracked outcomes</dt><dd>Number of trade/outcome lifecycles Atlas currently maintains for evidence and reconstruction.</dd></div>
              <div class="help-definition"><dt>Execution lifecycle</dt><dd>Most recent authoritative execution events across command application, Nyao acknowledgement, position actions and other lifecycle transitions.</dd></div>
              <div class="help-definition"><dt>Policy epoch timeline</dt><dd>Historical registered policies used to reconcile what was active when positions entered and when Gemini/Atlas changed policy.</dd></div>
            </dl>
            <div class="help-callout">When a dashboard card and System & Audit disagree, investigate the underlying authoritative endpoint/state rather than assuming the prettier card is correct.</div>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="status glossary watching qualifying ready blocked active complete unscored invalidated failed applied deferred no change inferred syncing stale">
          <summary><span>10 · Status & state glossary</span><span class="badge info">REFERENCE</span></summary>
          <div class="help-section-body">
            <div class="help-grid">
              <div class="help-card"><h4>Trading opportunity states</h4><p><strong>WATCHING</strong> prerequisite not met. <strong>QUALIFYING</strong> base setup passed but extra contextual evidence remains. <strong>READY</strong> current deterministic opportunity gates pass. <strong>BLOCKED</strong> a real veto prevents fresh execution. <strong>ACTIVE</strong> exposure/lifecycle exists.</p></div>
              <div class="help-card"><h4>Outcome states</h4><p><strong>COMPLETE</strong> strategic unit is flat and scoreable. <strong>UNSCORED</strong> still active or not eligible for final classification. <strong>INCOMPLETE_HISTORY</strong> legacy lineage is insufficient for exact strategic scoring.</p></div>
              <div class="help-card"><h4>Zone states</h4><p><strong>FRESH</strong> untouched. <strong>MITIGATED</strong> interacted but valid. <strong>INVALIDATED</strong> later closed candle broke the boundary. <strong>ZONE_AWARE_SCALP</strong> context guides scalps. <strong>ZONE_CAMPAIGN_ACTIVE</strong> actual zone exposure owns the campaign.</p></div>
              <div class="help-card"><h4>Brain states</h4><p><strong>NO CHANGE</strong> run recommended no mutation. <strong>OBSERVED</strong> accepted evidence. <strong>DEFERRED</strong> valid suggestion withheld by a lock/gate. <strong>REJECTED</strong> critic/validation rejected it. <strong>FAILED</strong> cycle error. <strong>APPLIED</strong> policy became runtime.</p></div>
            </div>
            <div class="help-chip-row" style="margin-top:12px"><span class="help-chip">LIVE</span><span class="help-chip">SYNCING</span><span class="help-chip">STALE</span><span class="help-chip">RECONCILED</span><span class="help-chip">PARTIALLY ALLOCATED</span><span class="help-chip">CAPITAL VETO</span><span class="help-chip">RECOVERY</span><span class="help-chip">ZONE-ALIGNED</span><span class="help-chip">COUNTER-ZONE</span></div>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="glossary atr fvg mfe mae mtm pl rsi ema rr spread points notional drawdown equity margin">
          <summary><span>11 · Trading & measurement glossary</span><span class="badge info">REFERENCE</span></summary>
          <div class="help-section-body">
            <dl>
              <div class="help-definition"><dt>P/L</dt><dd>Profit/loss. Floating P/L is unrealised; realised P/L is booked by MT5 exit deals.</dd></div>
              <div class="help-definition"><dt>MTM</dt><dd>Mark-to-market: current economic value of still-open exposure.</dd></div>
              <div class="help-definition"><dt>ATR</dt><dd>Average True Range, used as a volatility/geometry normalization unit.</dd></div>
              <div class="help-definition"><dt>RSI</dt><dd>Relative Strength Index used within momentum/health logic according to the active Nyao policy.</dd></div>
              <div class="help-definition"><dt>EMA</dt><dd>Exponential Moving Average used by Nyao trend/slope logic.</dd></div>
              <div class="help-definition"><dt>FVG</dt><dd>Fair Value Gap zone type.</dd></div>
              <div class="help-definition"><dt>MFE / MAE</dt><dd>Maximum Favorable / Adverse Excursion during a trade ticket lifecycle.</dd></div>
              <div class="help-definition"><dt>Spread points</dt><dd>Broker point-distance between ask and bid. Point size depends on the instrument; Atlas also exposes price-form spread for economic interpretation.</dd></div>
              <div class="help-definition"><dt>Notional exposure</dt><dd>Approximate market value represented by open volume. It is not the same as maximum loss because leverage, margin and stop distance differ.</dd></div>
              <div class="help-definition"><dt>Margin</dt><dd>Broker collateral currently required for open positions. High leverage can reduce margin usage but does not increase Atlas's permitted monetary loss.</dd></div>
              <div class="help-definition"><dt>Equity</dt><dd>Balance plus current floating P/L and related account effects.</dd></div>
              <div class="help-definition"><dt>Drawdown</dt><dd>Decline from a tracked peak. Atlas uses both live account drawdown and strategic closed-outcome drawdown in different contexts.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="block reasons score below threshold counter zone cost structure spread capital atlas zone mode duplicate cooldown broker">
          <summary><span>12 · Common block / decision reasons</span><span class="badge warn">TROUBLESHOOTING</span></summary>
          <div class="help-section-body">
            <dl>
              <div class="help-definition"><dt><code>SCORE_BELOW_THRESHOLD</code></dt><dd>Evaluated directional score has not reached the active runtime threshold. This is normally a watching condition, not a structural fault.</dd></div>
              <div class="help-definition"><dt><code>COUNTER_ZONE_EVIDENCE_INSUFFICIENT</code></dt><dd>A counter-zone scalp cleared the base signal gate but not the additional context-aware evidence premium.</dd></div>
              <div class="help-definition"><dt><code>COUNTER_ZONE_COMMIT_PROXIMITY</code></dt><dd>The higher-timeframe zone campaign is close enough to commitment that Atlas/Nyao blocks new exposure against it.</dd></div>
              <div class="help-definition"><dt><code>COUNTER_ZONE_SIGNAL_READY</code></dt><dd>The counter-zone evidence test has passed; other execution gates may still remain.</dd></div>
              <div class="help-definition"><dt><code>ATLAS_ZONE_MODE</code></dt><dd>A committed zone campaign currently owns fresh-entry authority, so ordinary/context-aware scalp entries are suspended.</dd></div>
              <div class="help-definition"><dt><code>STOP_EXPANSION_EXCESSIVE</code></dt><dd>Spread/cost would force protective structure far beyond acceptable geometry.</dd></div>
              <div class="help-definition"><dt>Spread outside limit</dt><dd>Current cost exceeds the adaptive strategy-specific spread cap. Zone and scalp limits can disagree because their geometry is different.</dd></div>
              <div class="help-definition"><dt>Capital veto / constrained</dt><dd>Atlas risk authority has no permitted capacity for new risk or has intentionally reduced it below a feasible opportunity size.</dd></div>
              <div class="help-definition"><dt>Duplicate distance</dt><dd>New same-direction exposure is too close to existing exposure under the active duplicate-distance policy.</dd></div>
              <div class="help-definition"><dt>Cooldown</dt><dd>A temporary timing/loss-protection rule prevents immediate re-entry.</dd></div>
              <div class="help-definition"><dt>Broker infeasible</dt><dd>Minimum lot/volume step or calculated loss cannot fit within Atlas's approved monetary risk. Nyao OrderCalcProfit remains final authority.</dd></div>
              <div class="help-definition"><dt><code>ZONE_INVALIDATED_MANAGEMENT_ONLY</code></dt><dd>The campaign's source zone invalidated after exposure existed; no new zone layers may open, but existing positions remain managed.</dd></div>
            </dl>
          </div>
        </details>

        <details class="help-section help-searchable" data-help="workflow new user how to use atlas daily checklist safety">
          <summary><span>13 · Recommended operator workflow</span><span class="badge ok">QUICK START</span></summary>
          <div class="help-section-body">
            <div class="help-grid three">
              <div class="help-card"><h4>1 · Check synchronization</h4><p>Open Command Center. Confirm Nyao is connected, system health is good, instrument is correct and there is no command/policy mismatch.</p></div>
              <div class="help-card"><h4>2 · Understand current authority</h4><p>Read operating mode. Is Atlas in normal scalp mode, zone-aware scalp context, committed zone campaign, recovery management or a blocked/protected state?</p></div>
              <div class="help-card"><h4>3 · Read risk before signals</h4><p>Open Portfolio. Confirm operating ceiling, active reservations, zone reservation and free risk reconcile before interpreting a high signal score.</p></div>
              <div class="help-card"><h4>4 · Inspect Market when curious</h4><p>Use Market to understand why BUY/SELL are watching, qualifying, ready or blocked and whether execution economics are acceptable.</p></div>
              <div class="help-card"><h4>5 · Inspect Zone Analysis when context changes</h4><p>Check the priority zone, lifecycle state, invalidation boundary, zone-aware handoff and campaign spread economics.</p></div>
              <div class="help-card"><h4>6 · Judge changes with evidence</h4><p>Use Performance and Atlas Brain to see whether outcomes support policy changes. Do not interpret one trade or one Gemini run as proof.</p></div>
            </div>
          </div>
        </details>
      </section>

  <div id="policy-inspector-modal" class="policy-modal" onclick="if(event.target===this)closePolicyInspector()">
    <div class="policy-modal-card">
      <div class="policy-modal-head"><div><div class="label" id="policy-inspector-kicker">POLICY</div><h2 id="policy-inspector-title" style="margin:3px 0 0">Policy inspector</h2><p id="policy-inspector-subtitle" class="muted" style="margin:5px 0 0">—</p></div><button class="btn" onclick="closePolicyInspector()">Close</button></div>
      <div id="policy-inspector-body"></div>
    </div>
  </div>

  <main class="main">
    <header class="topbar">
      <div><div class="title" id="top-title">Command Center</div><div class="subtitle" id="top-subtitle">What Atlas is watching now</div></div>
      <div class="top-meta">
        <div class="notify-wrap"><button class="notify-bell" id="notify-bell" onclick="toggleNotifications()" title="Notifications">♢<span id="notify-count" class="notify-count">0</span></button></div>
        <select id="symbol-select" class="symbol-select" onchange="switchSymbol(this.value)"><option value="">Symbol —</option></select>
        <span class="pill" id="account-pill">MT5 ACCOUNT</span>
        <span class="pill" id="epoch-pill">Epoch —</span>
        <span class="pill" id="command-pill">Command —</span>
      </div>
    </header>

    <div class="global-status-strip" id="global-status-strip">
      <button onclick="go('market')"><span class="dot" id="global-status-dot"></span><strong id="global-status-symbol">—</strong></button>
      <button onclick="go('overview')"><span class="global-label">MODE</span><strong id="global-status-mode">CONNECTING</strong></button>
      <button onclick="go('positions')"><span class="global-label">AVAILABLE RISK</span><strong id="global-status-risk">—</strong></button>
      <button onclick="go('positions')"><span class="global-label">POSITIONS</span><strong id="global-status-positions">—</strong></button>
      <button onclick="go('atlas')"><span class="global-label">BRAIN</span><strong id="global-status-brain">—</strong></button>
      <button onclick="go('history')"><span class="global-label">SYSTEM</span><strong id="global-status-health">CHECKING</strong></button>
    </div>


    <div id="ui-compatibility-sink" aria-hidden="true" style="display:none!important;">
      <span id="authority-lane"></span>
      <span id="authority-lane-badge"></span>
      <span id="context-zone-badge"></span>
      <span id="capital-regime-badge"></span>
      <span id="brain-mode-badge"></span>
      <span id="proposal-badge"></span>
      <span id="authority-lane-copy"></span>
      <span id="authority-scalp"></span>
      <span id="authority-zone"></span>
      <span id="brain-epoch"></span>
      <span id="brain-next"></span>
      <span id="brain-policy-copy"></span>
      <span id="brain-policy-state"></span>
      <span id="capital-risk-base"></span>
      <span id="capital-risk-copy"></span>
      <span id="capital-scalp-budget"></span>
      <span id="capital-zone-budget"></span>
      <span id="context-alignment"></span>
      <span id="context-bias"></span>
      <span id="context-zone"></span>
      <span id="context-zone-copy"></span>
      <span id="overview-proposal-note"></span>
      <div id="overview-changes"></div>
      <span id="protect-basket"></span>
      <span id="protect-chain-ceiling"></span>
      <span id="protect-composite-active"></span>
      <span id="protect-composite-latest"></span>
      <span id="protect-duplicate"></span>
      <span id="protect-portfolio-available"></span>
      <span id="protect-portfolio-reserved"></span>
      <span id="protect-positions"></span>
      <span id="protect-recovery"></span>
      <span id="protect-recovery-copy"></span>
      <span id="protect-recovery-sizing"></span>
      <span id="protect-risk-streak"></span>
      <span id="protect-unit-risk"></span>
    </div>

    <div id="notify-drawer" class="notify-drawer">
      <div class="notify-head"><div><strong>Atlas Notifications</strong><div class="muted" style="font-size:10px;margin-top:2px">Material state changes and execution events</div></div><div class="actions"><button class="btn" onclick="markAllNotificationsRead()">Mark read</button><button class="btn" onclick="toggleNotifications()">Close</button></div></div>
      <div id="notify-list" class="notify-list"></div>
    </div>

    <div class="content">
      <section id="view-overview" class="view active">
        <div class="page-head"><div><h2>Command Center</h2><p>What Atlas is watching, what changed, and what needs your attention.</p></div><span id="overview-live-badge" class="badge ok">LIVE</span></div>

        <div class="card hero">
          <div class="command-hero">
          <div class="command-primary">
            <div>
              <div class="mode-line"><span class="mode-dot"></span><span class="label" id="hero-mode-label">Atlas operating mode</span><span id="hero-mode-badge" class="badge info">CONNECTING</span></div>
              <div class="hero-status" id="hero-state">Connecting…</div>
              <div class="hero-copy" id="hero-copy">Reading Nyao status and Atlas policy state.</div>
            </div>
            <div class="hero-foot"><span>Instrument <strong id="hero-symbol">—</strong></span><span>Market <strong id="hero-market-state">—</strong></span><span>Last bridge check <strong id="hero-bridge">—</strong></span></div>
          </div>
          <div class="command-side"><div class="kpis">
            <div class="kpi"><div class="label">Trading mode</div><div class="value small" id="hero-risk">—</div></div>
            <div class="kpi"><div class="label">Campaign risk</div><div class="value small" id="hero-policy">—</div></div>
            <div class="kpi"><div class="label">Live / staged</div><div class="value small" id="hero-open">—</div></div>
            <div class="kpi"><div class="label">Next brain review</div><div class="value small" id="hero-chains">—</div></div>
          </div></div>
          </div>
        </div>

        <div class="grid account-strip section">
          <div class="card"><div class="label">Balance</div><div class="value" id="balance">—</div><div class="muted" id="equity">Equity —</div></div>
          <div class="card"><div class="label">Open P/L</div><div class="value" id="floating">—</div><div class="muted" id="drawdown">Drawdown —</div></div>
          <div class="card"><div class="label" id="market-label">Live market · —</div><div class="value small" id="market-price">—</div><div class="muted" id="market-spread">Spread —</div></div>
          <div class="card"><div class="label">System health</div><div class="value small" id="ack-state">—</div><div class="muted" id="ack-detail">Checking execution bridge</div></div>
        </div>


        <div class="observability-grid command-center-primary">
          <div class="card observability-card">
            <div class="observable-head"><div><h3>Opportunity Queue</h3><p>Live opportunities Atlas is evaluating, their current gate and the next condition required for execution.</p></div><span id="opportunity-queue-badge" class="badge info">SCANNING</span></div>
            <div id="opportunity-queue" class="opportunity-list"><div class="observability-empty">Waiting for live Atlas state.</div></div>
            <div id="opportunity-queue-summary" class="queue-summary"></div>
          </div>
          <div class="card observability-card">
            <div class="observable-head"><div><h3>Decision Timeline</h3><p>Material decision transitions only — signal gates, execution economics, zones, capital, policy and trade lifecycle.</p></div><div class="actions"><button class="btn" onclick="clearDecisionTimeline()">Clear</button><span class="badge info">EVENT LOG</span></div></div>
            <div id="decision-timeline" class="decision-timeline"><div class="observability-empty">Atlas will record the next material decision change.</div></div>
          </div>
        </div>

        <div class="command-focus">
          <div class="command-focus-main">
            <div class="label">Operator attention</div>
            <div id="overview-attention-title" class="decision-state">Checking…</div>
            <div id="overview-attention-copy" class="muted">Atlas is reconciling the live state.</div>
            <div id="overview-decision-list" class="decision-list"></div>
          </div>
          <div class="actions"><button class="btn primary" onclick="go('analysis')">Open zone analysis</button></div>
        </div>

        <details class="command-details">
          <summary><span>Active trade plan</span><span class="muted">Expand plan details</span></summary>
          <div class="command-details-body">
<div class="card campaign-card">
            <div class="campaign-head"><div><div class="label">Active trade plan</div><div id="overview-campaign-title" class="campaign-title">Waiting for Atlas</div><div id="overview-campaign-copy" class="muted">No active campaign has been loaded.</div></div><span id="overview-campaign-badge" class="badge">—</span></div>
            <div id="overview-campaign" class="campaign-ladder"></div>
          </div>
          </div>
        </details>



        <div class="command-workspaces section">
          <button class="workspace-card market" onclick="go('market')">
            <div class="workspace-icon">MKT</div>
            <div><span class="label">Market</span><strong>Signals & execution economics</strong><p>Live BUY/SELL gates, regime, volatility, spread economics and the current market thesis.</p></div>
            <span class="workspace-arrow">→</span>
          </button>
          <button class="workspace-card portfolio" onclick="go('positions')">
            <div class="workspace-icon">RISK</div>
            <div><span class="label">Portfolio</span><strong>Exposure & capital</strong><p>Open positions, concurrent risk allocation, reservations, recovery and capital capacity.</p></div>
            <span class="workspace-arrow">→</span>
          </button>
          <button class="workspace-card brain" onclick="go('atlas')">
            <div class="workspace-icon">AI</div>
            <div><span class="label">Atlas Brain</span><strong>Policy & reasoning</strong><p>Gemini reviews, policy epochs, evidence, deferred activation and autonomous adaptation.</p></div>
            <span class="workspace-arrow">→</span>
          </button>
          <button class="workspace-card performance" onclick="go('performance')">
            <div class="workspace-icon">P/L</div>
            <div><span class="label">Performance</span><strong>Evidence & learning</strong><p>Expectancy, composite outcomes, strategy breakdowns, execution quality and learning readiness.</p></div>
            <span class="workspace-arrow">→</span>
          </button>
        </div>

        <div class="command-footer-note">
          <span class="dot ok"></span>
          <span>Command Center is intentionally concise. Detailed analysis lives in the dedicated workspaces above.</span>
        </div>
      </section>

      <section id="view-market" class="view">
        <div class="page-head"><div><h2>Market</h2><p>Why Atlas sees the market the way it does: live signals, regime, volatility and execution economics.</p></div><span class="badge info">LIVE MARKET WORKSPACE</span></div>
        <div class="workspace-intro"><strong>How to use this page:</strong> read Atlas’s live market view and Nyao’s signal state here. Trade-location planning and zone campaigns remain on the separate Zone Analysis page.</div>
        <div id="scalp-context-banner" class="workspace-intro" style="display:none">
          <strong id="scalp-context-title">Scalp context</strong>
          <span id="scalp-context-copy">Waiting for Nyao context telemetry.</span>
        </div>
        <div id="live-execution-panel" class="section">
          <div class="section-head">
            <div><h3>Live Market & Entry Analysis</h3><p>Atlas bias and Nyao's live BUY / SELL state for the selected instrument.</p></div>
            <span id="signal-global-status" class="badge">—</span>
          </div>

          <div class="signal-grid">
            <div class="card">
              <div class="label">Atlas market view</div>
              <div id="signal-bias" class="bias-value bias-neutral">—</div>
              <div class="muted"><span id="signal-regime">Waiting for regime</span> · <span id="signal-volatility">—</span></div>
              <div class="signal-meta">
                <div class="kpi"><div class="label">Confidence</div><div class="value small" id="signal-confidence">—</div></div>
                <div class="kpi"><div class="label">Risk</div><div class="value small" id="signal-risk">—</div></div>
              </div>
              <div class="signal-reason" id="signal-summary">Waiting for Atlas intelligence.</div>
            </div>

            <div class="card">
              <div class="section-head"><div><div class="label">BUY signal</div><div id="signal-buy-score" class="signal-score signal-buy">0.00</div></div><span id="signal-buy-state" class="badge">—</span></div>
              <div class="muted">Live score / effective threshold</div>
              <div class="signal-track"><div id="signal-buy-bar" class="signal-fill signal-buy"></div></div>
              <div class="signal-meta">
                <div class="kpi"><div class="label">Evaluated</div><div class="value small" id="signal-buy-adjusted">0.00</div></div>
                <div class="kpi"><div class="label">Threshold</div><div class="value small" id="signal-buy-threshold">0.00</div></div>
              </div>
              <div class="signal-reason" id="signal-buy-reason">Not evaluated.</div>
            </div>

            <div class="card">
              <div class="section-head"><div><div class="label">SELL signal</div><div id="signal-sell-score" class="signal-score signal-sell">0.00</div></div><span id="signal-sell-state" class="badge">—</span></div>
              <div class="muted">Live score / effective threshold</div>
              <div class="signal-track"><div id="signal-sell-bar" class="signal-fill signal-sell"></div></div>
              <div class="signal-meta">
                <div class="kpi"><div class="label">Evaluated</div><div class="value small" id="signal-sell-adjusted">0.00</div></div>
                <div class="kpi"><div class="label">Threshold</div><div class="value small" id="signal-sell-threshold">0.00</div></div>
              </div>
              <div class="signal-reason" id="signal-sell-reason">Not evaluated.</div>
            </div>
          </div>

          <div class="card" style="margin-top:14px">
            <div class="grid g4">
              <div class="kpi"><div class="label">Global blocker</div><div class="value small" id="signal-global-block">—</div></div>
              <div class="kpi"><div class="label">New-bar gate</div><div class="value small" id="signal-newbar">—</div></div>
              <div class="kpi"><div class="label">Cooldown</div><div class="value small" id="signal-cooldown">—</div></div>
              <div class="kpi"><div class="label">Spread gate</div><div class="value small" id="signal-spread">—</div></div>
            </div>
          </div>
        </div>

        <div class="grid g4">
          <div class="card"><div class="label">Market bias</div><div class="value small" id="an-bias">—</div><div class="muted" id="an-regime">Waiting for Atlas</div></div>
          <div class="card"><div class="label">Volatility</div><div class="value small" id="an-volatility">—</div><div class="muted" id="an-vol-ratio">Ratio —</div></div>
          <div class="card"><div class="label">Execution fit</div><div class="value small" id="an-fit">—</div><div class="muted" id="an-confidence">Confidence —</div></div>
          <div class="card"><div class="label">Risk state</div><div class="value small" id="an-risk">—</div><div class="muted" id="an-responsiveness">Responsiveness —</div></div>
        </div>

        <div class="grid g2 section">
          <div class="card">
            <div class="section-head"><div><h3>Atlas market thesis</h3><p>The current internal interpretation—not an order or prediction.</p></div><span id="an-thesis-badge" class="badge">LIVE</span></div>
            <div id="an-thesis" class="analysis-thesis">Waiting for Atlas intelligence.</div>
            <div id="an-reasons" class="analysis-list"></div>
          </div>
          <div class="card">
            <div class="section-head"><div><h3>Range and trading cost</h3><p>Whether current movement is large enough to support trading after spread.</p></div><span id="an-cost-badge" class="badge">—</span></div>
            <div class="grid g2">
              <div class="kpi"><div class="label">Bid / ask gap</div><div class="value small" id="an-spread-price">—</div></div>
              <div class="kpi"><div class="label">Economic spread cap</div><div class="value small" id="an-atr">—</div></div>
              <div class="kpi"><div class="label">Spread / cap</div><div class="value small" id="an-spread-atr">—</div></div>
              <div class="kpi"><div class="label">Entry eligible</div><div class="value small" id="an-eligible">—</div></div>
            </div>
            <div class="callout" id="an-cost-note" style="margin-top:12px">Waiting for cost evidence.</div>
          </div>
        </div>
      </section>

      <section id="view-analysis" class="view">
        <div class="page-head"><div><h2>Zone Analysis</h2><p>Daily trade locations, live zone relationships, and the active Nyao zone campaign.</p></div><span class="badge info">LIVE ZONE WORKSPACE</span></div>
        <div class="workspace-intro"><strong>How to use this page:</strong> start with the daily zone map and active mode directive. Detailed evidence, live authority, entries, targets, and scalp handoff remain together below.</div>

        <div class="card section">
          <div class="section-head"><div><h3>Daily Zone Map</h3><p>Versioned M30/H1/H4 trade-location plan for the selected symbol.</p></div><span id="an-zone-status" class="badge warn">WAITING FOR CANDLES</span></div>
          <div class="zone-chart-shell">
            <div class="zone-chart-head">
              <div><strong id="an-zone-title">No approved internal zone map yet</strong><p id="an-candle-detail">Atlas is waiting for Nyao's validated, closed-bar multi-timeframe export.</p></div>
              <div class="zone-chart-legend"><span class="zone-chart-key"><span class="zone-chart-swatch demand"></span>Demand</span><span class="zone-chart-key"><span class="zone-chart-swatch supply"></span>Supply</span><span class="badge info">M30 PRICE · PRIORITY MTF ZONES</span></div>
            </div>
            <svg id="an-zone-chart" class="zone-chart-frame" viewBox="0 0 1200 520" role="img" aria-label="Atlas M30 candlestick chart with prioritized supply and demand zones"></svg>
          </div>
          <div id="an-zone-execution"></div>
          <div id="an-zone-lifecycle" class="callout" style="margin-top:12px">Zone lifecycle is waiting for validated candles.</div>
          <details class="raw" style="margin-top:12px"><summary>Zone evidence and engine diagnostics</summary>
            <div id="an-zone-stats" class="grid g4" style="margin-top:12px"></div>
            <div id="an-zone-list" class="zone-map-list"></div>
            <div class="section-head" style="margin-top:16px"><div><h3 style="font-size:13px">Invalidated zone history</h3><p>Closed-candle failures retained for audit. Invalidated zones cannot influence scalp context or new campaigns.</p></div><span id="an-invalidated-count" class="badge">0 INVALIDATED</span></div>
            <div id="an-invalidated-zone-list" class="zone-map-list"></div>
            <div id="an-zone-scenario-list" class="analysis-list" style="margin-top:12px"></div>
            <div id="an-mtf-grid" class="grid g3" style="margin-top:12px"></div>
            <div class="grid g4" style="margin-top:12px">
              <div class="kpi"><div class="label">1 · Analysis UI</div><div class="value small pos">READY</div></div>
              <div class="kpi"><div class="label">2 · MTF candles</div><div id="an-stage-candles" class="value small" style="color:var(--amber)">WAITING</div></div>
              <div class="kpi"><div class="label">3 · Zone engine</div><div id="an-stage-zone-engine" class="value small muted">PENDING</div></div>
              <div class="kpi"><div class="label">4 · Nyao zone gate</div><div id="an-stage-zone-gate" class="value small muted">PENDING</div></div>
            </div>
          </details>
        </div>

        <div class="grid g2 section">
          <div class="card">
            <div class="section-head"><div><h3>Zone authority and scalp handoff</h3><p>Shows whether the zone campaign owns execution or ordinary scalping may resume.</p></div></div>
            <div id="an-scenarios" class="analysis-list"></div>
          </div>
          <div class="card">
            <div class="section-head"><div><h3>Related Atlas policy context</h3><p>The latest model thesis and critic evidence relevant to zone execution and the eventual scalp handoff.</p></div><span id="an-gemini-badge" class="badge">—</span></div>
            <div id="an-gemini-thesis" class="analysis-thesis">No Gemini policy analysis loaded.</div>
            <div id="an-gemini-evidence" class="analysis-list"></div>
          </div>
        </div>
      </section>

      <section id="view-positions" class="view">
        <div class="page-head"><div><h2>Portfolio</h2><p>Live exposure, account impact, and position management.</p></div><div class="row"><span class="badge info">NYAO EXECUTION</span><span class="badge ok">RISK UI · 1.30.44</span></div></div>
        <div class="grid g3">
          <div class="card"><div class="label">Strategy positions</div><div class="value" id="p-count">0</div></div>
          <div class="card"><div class="label">Total lots remaining</div><div class="value" id="p-lots">0.00</div></div>
          <div class="card"><div class="label">Recovery chains</div><div class="value" id="p-chains">0</div></div>
          <div class="card"><div class="label">Realized while active</div><div class="value" id="p-realized">—</div><div class="muted">Partial exits only</div></div>
          <div class="card"><div class="label">Floating P/L</div><div class="value" id="p-pl">—</div></div>
          <div class="card"><div class="label">Active lifecycle P/L</div><div class="value" id="p-lifecycle">—</div><div class="muted">Realized + floating</div></div>
        </div>
        <div class="card section">
          <div class="section-head"><div><h3>Risk allocation · live capital usage</h3><p>Where Atlas's current operating risk is reserved and what remains available for new opportunities.</p></div><span id="portfolio-risk-badge" class="badge info">RECONCILING</span></div>
          <div class="risk-allocation-hero"><div><div class="label">Operating risk ceiling</div><div class="risk-allocation-total" id="portfolio-operating-ceiling">—</div><div class="muted" id="portfolio-risk-reconcile">Waiting for capital telemetry.</div></div><div class="risk-allocation-hard"><span class="label">Portfolio hard ceiling</span><strong id="portfolio-hard-ceiling">—</strong><span class="muted" id="portfolio-hard-headroom">— headroom</span></div></div>
          <div class="risk-allocation-bar" id="portfolio-risk-bar"><span class="risk-segment active" style="width:0%"></span><span class="risk-segment zone" style="width:0%"></span><span class="risk-segment free" style="width:100%"></span></div>
          <div class="risk-allocation-legend"><span><i class="risk-dot active"></i>Active reservations</span><span><i class="risk-dot zone"></i>Prospective zone</span><span><i class="risk-dot free"></i>Free operating risk</span></div>
          <div id="portfolio-risk-cards" class="risk-allocation-cards"><div class="observability-empty">Risk reservations will appear when capital telemetry is available.</div></div>
        </div>
        <div class="card section">
          <div class="section-head"><div><h3>Open positions</h3><p>The trading facts first. Policy lineage remains available in the audit log.</p></div></div>
          <div class="table-wrap"><table><thead><tr><th>Ticket</th><th>Side</th><th>Volume</th><th>Entry</th><th>Current</th><th>Realized</th><th>Floating</th><th>Lifecycle</th><th>Stop</th><th>Target</th><th>Context / Origin</th><th>Age</th></tr></thead><tbody id="positions-body"></tbody></table></div>
        </div>
        <div class="card section">
          <div class="section-head"><div><h3>Recent closed trades</h3><p>Authoritative ticket-level executions for the selected MT5 account. Recovery/zone members may appear as separate rows here, but strategic win/loss streaks and policy learning score the completed composite risk unit only.</p></div><span id="closed-trades-badge" class="badge">CURRENT ACCOUNT</span></div>
          <div class="table-wrap"><table><thead><tr><th>Ticket</th><th>Side</th><th>Lots</th><th>Entry</th><th>Exit</th><th>Realized P/L</th><th>Origin</th><th>Policy epoch</th><th>Mode</th><th>Closed</th><th>Quality</th></tr></thead><tbody id="closed-trades-body"></tbody></table></div>
        </div>

      </section>

      <section id="view-performance" class="view">
        <div class="page-head"><div><h2>Performance Intelligence</h2><p>Strategic outcomes, execution quality, policy evidence, and whether Atlas has enough data to learn responsibly.</p></div><span id="performance-page-badge" class="badge info">CURRENT ACCOUNT</span></div>
        <div class="workspace-intro"><strong>How to use this page:</strong> strategic performance is scored by completed risk unit, not raw MT5 ticket. Standalone trades score individually; recovery chains and zone campaigns score once when the whole composite is flat. Ticket-level evidence below is diagnostic only.</div>

        <div class="performance-hero">
          <div class="card performance-primary">
            <div class="row"><div><div class="label">Strategic net P/L</div><div class="performance-net" id="perf-net">—</div></div><span id="perf-quality" class="badge">COLLECTING</span></div>
            <div class="performance-sub" id="performance-headline">Waiting for completed Atlas risk units.</div>
            <div id="performance-equity-curve" class="performance-curve"><div class="observability-empty">Equity curve will appear after completed risk units.</div></div>
          </div>
          <div class="performance-kpis">
            <div class="card"><div class="label">Completed risk units</div><div class="value" id="perf-count">0</div><div class="muted" id="perf-sample">Sample —</div></div>
            <div class="card"><div class="label">Expectancy / unit</div><div class="value" id="perf-expectancy">—</div><div class="muted">Strategic outcome basis</div></div>
            <div class="card"><div class="label">Win rate</div><div class="value" id="perf-win-rate">—</div><div class="muted">Completed units only</div></div>
            <div class="card"><div class="label">Profit factor</div><div class="value" id="perf-factor">—</div><div class="muted">Gross wins / gross losses</div></div>
            <div class="card"><div class="label">Max closed drawdown</div><div class="value" id="perf-drawdown">—</div><div class="muted">Composite equity sequence</div></div>
            <div class="card"><div class="label">Data quality</div><div class="value small" id="perf-data-quality">—</div><div class="muted" id="perf-data-quality-copy">Waiting for outcomes</div></div>
          </div>
        </div>

        <div class="grid g3 section">
          <div class="card"><div class="section-head"><div><h3>Standalone scalps</h3><p>Independent risk units.</p></div><span id="perf-standalone-badge" class="badge">—</span></div><div id="perf-standalone" class="performance-unit-summary"></div></div>
          <div class="card"><div class="section-head"><div><h3>Recovery chains</h3><p>Root + hedge children scored once.</p></div><span id="perf-recovery-badge" class="badge">—</span></div><div id="perf-recovery" class="performance-unit-summary"></div></div>
          <div class="card"><div class="section-head"><div><h3>Zone campaigns</h3><p>All campaign layers scored once.</p></div><span id="perf-zone-badge" class="badge">—</span></div><div id="perf-zone" class="performance-unit-summary"></div></div>
        </div>

        <div class="grid g2 section">
          <div class="card">
            <div class="section-head"><div><h3>Performance by policy epoch</h3><p>Use this to see whether later Nyao policies are actually improving completed strategic outcomes.</p></div><span class="badge info">ATTRIBUTED AT ENTRY</span></div>
            <div class="table-wrap"><table><thead><tr><th>Epoch</th><th>Units</th><th>Net P/L</th><th>Expectancy</th><th>Win rate</th><th>Evidence</th></tr></thead><tbody id="perf-epochs"></tbody></table></div>
          </div>
          <div class="card">
            <div class="section-head"><div><h3>Performance by trading mode</h3><p>Separates scalp and zone strategy evidence.</p></div></div>
            <div class="table-wrap"><table><thead><tr><th>Mode</th><th>Units</th><th>Net P/L</th><th>Expectancy</th><th>Profit factor</th></tr></thead><tbody id="perf-modes"></tbody></table></div>
          </div>
        </div>

        <div class="grid g2 section">
          <div class="card">
            <div class="section-head"><div><h3>Recent strategic outcomes</h3><p>Composite risk-unit truth used by loss streaks and policy performance.</p></div><span id="perf-units-badge" class="badge">—</span></div>
            <div id="perf-recent-units" class="performance-results"></div>
          </div>
          <div class="card">
            <div class="section-head"><div><h3>Execution quality</h3><p>Ticket-level MFE / MAE and entry-context evidence. Diagnostic only; hedge and zone member tickets are not independent strategy wins or losses.</p></div><span class="badge warn">DIAGNOSTIC</span></div>
            <div class="grid g2">
              <div class="kpi"><div class="label">Median MFE</div><div class="value small" id="perf-mfe">—</div></div>
              <div class="kpi"><div class="label">Median MAE</div><div class="value small" id="perf-mae">—</div></div>
              <div class="kpi"><div class="label">Average realised ticket</div><div class="value small" id="perf-ticket-average">—</div></div>
              <div class="kpi"><div class="label">MT5-confirmed tickets</div><div class="value small" id="perf-exact-tickets">—</div></div>
            </div>
            <div class="label" style="margin-top:16px">Entry regime evidence</div><div id="perf-regimes" class="performance-bars"></div>
          </div>
        </div>

        <div class="card section">
          <div class="section-head"><div><h3>Learning readiness</h3><p>Atlas should not mistake a tiny sample for proof. This panel makes evidence maturity explicit.</p></div><span id="perf-learning-badge" class="badge warn">EARLY</span></div>
          <div class="grid g4">
            <div class="kpi"><div class="label">Exact strategic outcomes</div><div class="value small" id="perf-exact-units">—</div></div>
            <div class="kpi"><div class="label">Inferred strategic outcomes</div><div class="value small" id="perf-inferred-units">—</div></div>
            <div class="kpi"><div class="label">Active unscored units</div><div class="value small" id="perf-active-units">—</div></div>
            <div class="kpi"><div class="label">Completed loss streak</div><div class="value small" id="perf-loss-streak">—</div></div>
          </div>
          <div id="perf-note" class="callout" style="margin-top:12px">Waiting for closed strategic risk units.</div>
        </div>
      </section>

      <section id="view-atlas" class="view">
        <div class="page-head"><div><h2>Atlas Brain</h2><p>See what policy is active, what Gemini is learning, how consensus is forming, and how policy evolves over time.</p></div><span class="badge info">GEMINI + DETERMINISTIC LAYER</span></div>
        <div class="brain-section-label"><span>01</span><div><strong>Policy Control Center</strong><p>Active runtime authority and the next candidate policy window belong together.</p></div></div>
        <div class="brain-policy-control-grid">
          <div class="card">
            <div class="section-head"><div><h3>Runtime policy</h3><p>Authoritative Nyao policy actually active now. This card never displays reasoning from a newer Gemini observation.</p></div><span id="runtime-policy-badge" class="badge">—</span></div>
            <div class="grid g4">
              <div class="kpi"><div class="label">Policy epoch</div><div class="value small" id="runtime-policy-epoch">—</div></div>
              <div class="kpi"><div class="label">Command</div><div class="value small" id="runtime-policy-command">—</div></div>
              <div class="kpi"><div class="label">Runtime controls</div><div class="value small" id="runtime-policy-count">—</div></div>
              <div class="kpi"><div class="label">Reconciliation</div><div class="value small" id="runtime-policy-reconciliation">—</div></div>
            </div>
            <div id="runtime-policy-changes" class="changes" style="margin-top:12px"></div>
            <div id="runtime-policy-rationale" class="callout" style="margin-top:12px">Loading active runtime policy lineage.</div>
            <div class="policy-actions"><button class="btn primary" onclick="openActivePolicyInspector()">Inspect all runtime controls</button><button class="btn" onclick="brainTab('history')">Policy history</button></div>
          </div>
          <div class="card">
            <div class="section-head">
              <div><h3>Candidate consensus</h3><p>Accepted Gemini observations for the active policy baseline. Gemini runs and accepted observations are tracked separately.</p></div>
              <span class="badge info">LEARNING WINDOW</span>
            </div>
            <div id="policy-consensus-summary" class="callout">Consensus window is loading.</div>
            <div id="policy-consensus-controls" class="consensus-table consensus-full"></div>
            <div id="policy-window-history" class="policy-window-history"></div>
          </div>
        </div>
        <div class="card section">
          <div class="section-head"><div><h3>Policy lineage</h3><p>Inspect every applied policy epoch and the accepted Gemini observations that fed policy learning.</p></div><span class="badge info">AUDITABLE LINEAGE</span></div>
          <div class="brain-tabs">
            <button id="brain-tab-runs" class="brain-tab active" onclick="brainTab('runs')">Gemini run history</button>
            <button id="brain-tab-observations" class="brain-tab" onclick="brainTab('observations')">Accepted observations</button>
            <button id="brain-tab-history" class="brain-tab" onclick="brainTab('history')">Applied policy epochs</button>
          </div>
          <div id="brain-panel-runs" class="brain-tab-panel active"><div id="gemini-run-history" class="gemini-run-history"></div></div>
          <div id="brain-panel-observations" class="brain-tab-panel"><div id="policy-observation-list" class="observation-list"></div></div>
          <div id="brain-panel-history" class="brain-tab-panel"><div id="policy-registry-list" class="policy-timeline"></div></div>
        </div>

        <div class="brain-section-label"><span>02</span><div><strong>Learning & Market Evidence</strong><p>What Gemini currently sees and whether scalp execution is responsive enough.</p></div></div>
        <div class="brain-learning-grid">
          <div class="card">
            <div class="section-head"><div><h3>Latest Gemini analysis</h3><p>Newest proposal/observation. This may be newer than the active runtime policy and is not treated as active evidence.</p></div><span id="latest-analysis-badge" class="badge info">LATEST</span></div>
            <div class="grid g2">
              <div class="kpi"><div class="label">Candidate</div><div class="value small" id="a-candidate">—</div></div>
              <div class="kpi"><div class="label">Recommendation</div><div class="value small" id="a-readiness">—</div></div>
              <div class="kpi"><div class="label">Baseline epoch</div><div class="value small" id="a-epoch">—</div></div>
              <div class="kpi"><div class="label">Confidence</div><div class="value small" id="a-confidence">—</div></div>
            </div>
            <div id="atlas-llm-evidence" class="callout" style="margin-top:12px">No Gemini analysis attached.</div>
            <div id="a-blockers" class="callout" style="margin-top:10px">—</div>
          </div>
          <div class="card">
          <div class="section-head"><div><h3>Scalping responsiveness</h3><p>Measures entry opportunity, blocking pressure, holding time and profit capture. Speed is judged by net outcomes, not trade count.</p></div><span id="resp-badge" class="badge">—</span></div>
          <div class="grid g4">
            <div class="kpi"><div class="label">Latency pressure</div><div class="value small" id="resp-pressure">—</div></div>
            <div class="kpi"><div class="label">Entry eligible</div><div class="value small" id="resp-eligible">—</div></div>
            <div class="kpi"><div class="label">Median hold</div><div class="value small" id="resp-hold">—</div></div>
            <div class="kpi"><div class="label">MFE captured</div><div class="value small" id="resp-capture">—</div></div>
          </div>
          <div class="grid g2" style="margin-top:12px">
            <div><div class="label">Dominant entry blockers</div><div id="resp-blockers" class="changes" style="margin-top:8px"></div></div>
            <div><div class="label">Candidate responsiveness levers</div><div id="resp-levers" class="changes" style="margin-top:8px"></div></div>
          </div>
          <div id="resp-detail" class="callout" style="margin-top:12px">Responsiveness evidence is loading.</div>
        </div>
        
        </div>
        <div class="grid g4 section">
          <div class="card"><div class="label">Risk</div><div class="value small" id="a-risk">—</div></div>
          <div class="card"><div class="label">Evidence</div><div class="value small" id="a-evidence">—</div></div>
          <div class="card"><div class="label">Stability</div><div class="value small" id="a-stability">—</div></div>
          <div class="card"><div class="label">Review state</div><div class="value small" id="a-review-state">—</div></div>
        </div>
        

        <div class="brain-section-label"><span>03</span><div><strong>Policy Automation & Intelligence</strong><p>Control review cadence and inspect the evidence Atlas uses to investigate parameter changes.</p></div></div>
        <div class="card">
          <div class="section-head"><div><h3>Gemini policy cycle</h3><p>Optimizes the full Nyao scalp runtime policy using live state, performance, responsiveness and deterministic zone context. Zone policy remains read-only.</p></div><span id="cycle-badge" class="badge">—</span></div>
          <div class="grid g4">
            <div class="kpi"><div class="label">Last run</div><div class="value small" id="cycle-last">—</div></div>
            <div class="kpi"><div class="label">Next run</div><div class="value small" id="cycle-next">—</div></div>
            <div class="kpi"><div class="label">Run count</div><div class="value small" id="cycle-count">0</div></div>
            <div class="kpi"><div class="label">Last critic</div><div class="value small" id="cycle-critic">—</div></div>
          </div>
          <div class="row" style="margin-top:14px;align-items:flex-end;flex-wrap:wrap">
            <div style="min-width:170px"><div class="label" style="margin-bottom:6px">Interval (minutes)</div><input id="cycle-interval" class="search" type="number" min="15" max="1440" step="15" value="240"></div>
            <div style="min-width:170px"><div class="label" style="margin-bottom:6px">Application mode</div><select id="cycle-mode" class="search"><option value="SUPERVISED">Supervised</option><option value="AUTONOMOUS">Autonomous</option></select></div>
            <div style="min-width:170px"><div class="label" style="margin-bottom:6px">Minimum dwell (minutes)</div><input id="cycle-dwell" class="search" type="number" min="30" max="1440" step="30" value="240"></div>
            <div style="min-width:160px"><div class="label" style="margin-bottom:6px">Minimum confidence</div><input id="cycle-confidence" class="search" type="number" min="0" max="100" step="1" value="70"></div>
            <label class="callout" style="display:flex;align-items:center;gap:9px;margin:0"><input id="cycle-enabled" type="checkbox"> Enable scheduled policy cycles</label>
            <div class="actions"><button id="btn-save-cycle" class="btn" onclick="saveLlmCycleSchedule()">Save schedule</button><button id="btn-run-cycle" class="btn primary" onclick="runLlmCycleNow()">Run analysis now</button></div>
          </div>
          <div id="cycle-detail" class="callout" style="margin-top:12px">Schedule is loading. Application authority remains manual.</div>
        </div>
        
        <div class="card section">
          <div class="section-head"><div><h3>Parameter Intelligence</h3><p>P2.2 ranks all 157 controls using parameter-specific evidence, observed runtime variation and descriptive outcome associations.</p></div><span id="pi-mode" class="badge info">P2.2</span></div>
          <div class="grid g4">
            <div class="kpi"><div class="label">Registry</div><div class="value small" id="pi-count">157</div></div>
            <div class="kpi"><div class="label">Position-sensitive</div><div class="value small" id="pi-locked">53</div></div>
            <div class="kpi"><div class="label">Change budget</div><div class="value small" id="pi-budget">3</div></div>
            <div class="kpi"><div class="label">Validated auto apply</div><div class="value small" id="pi-exec">SUPERVISED</div></div>
          </div>
          <div class="grid g2" style="margin-top:14px">
            <div class="kpi"><div class="label">Validated numeric changes</div><div class="value small" id="pi-real-changes">0</div></div>
            <div class="kpi"><div class="label">No-op advisor changes filtered</div><div class="value small" id="pi-noop">0</div></div>
          </div>
          <div style="margin-top:14px"><div class="label">Evidence maturity by domain</div><div id="pi-domains" class="changes" style="margin-top:8px"></div></div>
          <div style="margin-top:14px"><div class="label">Highest-priority parameter candidates</div><div id="pi-candidates" class="changes" style="margin-top:8px"></div></div>
          <div class="callout" style="margin-top:12px" id="pi-authority-note">Historical value/outcome differences are descriptive associations, not causal proof.</div>
        </div>

        

        <div class="brain-section-label"><span>04</span><div><strong>Human Review & Application</strong><p>Manual approval workflow when Atlas is operating in supervised mode.</p></div></div>
        <div class="card section">
          <div class="section-head"><div><h3>Human review workflow</h3><p>The backend still validates exact fingerprint, epoch and review snapshot. The UI carries them automatically.</p></div></div>
          <div id="review-workflow" class="workflow"></div>
          <div class="actions" style="margin-top:14px">
            <button id="btn-request-review" class="btn" onclick="requestReview()">Request review</button>
            <button id="btn-approve" class="btn primary" onclick="approveCurrent()">Approve</button>
            <button id="btn-reject" class="btn danger" onclick="rejectCurrent()">Reject</button>
            <button id="btn-build-command" class="btn" onclick="buildSupervisedCommand()">Build command package</button>
          </div>
        </div>
      
      </section>

      <section id="view-control" class="view">
        <div class="page-head"><div><h2>Settings</h2><p>Execution authority and advanced runtime controls. Most trading sessions should not require this page.</p></div><span class="badge warn">ADVANCED</span></div>

        <div class="grid g2">
          <div class="card">
            <div class="section-head"><div><h3>Supervised execution</h3><p>Same safety pipeline regardless of whether MT5 is connected to demo or live.</p></div><span id="exec-badge" class="badge">NO PACKAGE</span></div>
            <div class="callout" style="margin-bottom:12px">
              <div class="row">
                <div><strong>Operator execution arm</strong><div class="muted" id="arm-detail">Disarmed</div></div>
                <div class="actions">
                  <span id="arm-badge" class="badge bad">DISARMED</span>
                  <button id="btn-arm" class="btn" onclick="armExecution()">Arm 30 min</button>
                  <button id="btn-disarm" class="btn danger" onclick="disarmExecution()">Disarm</button>
                </div>
              </div>
            </div>
            <div id="exec-summary" class="callout">Build an approved command package from the Atlas page first.</div>
            <div id="exec-workflow" class="workflow" style="margin-top:12px"></div>
            <div class="actions" style="margin-top:14px">
              <button id="btn-preflight" class="btn" onclick="runPreflight()">Run preflight</button>
              <button id="btn-execute" class="btn primary" onclick="executePackage()">Execute policy</button>
              <button id="btn-ack" class="btn" onclick="refreshAck()">Refresh Nyao ACK</button>
            </div>
          </div>
          <div class="card">
            <div class="section-head"><div><h3>Current command</h3><p>Requested policy currently on the bridge.</p></div></div>
            <div class="grid g2">
              <div class="kpi"><div class="label">Command version</div><div class="value small" id="c-version">—</div></div>
              <div class="kpi"><div class="label">Policy epoch</div><div class="value small" id="c-epoch">—</div></div>
              <div class="kpi"><div class="label">Base lot</div><div class="value small" id="c-lot">—</div></div>
              <div class="kpi"><div class="label">Global enabled</div><div class="value small" id="c-enabled">—</div></div>
            </div>
          </div>
        </div>

        <div class="card section">
          <div class="section-head"><div><h3>Portfolio risk appetite</h3><p>Operator-owned aggregate Atlas risk ceiling. This is not per-trade risk; Atlas can reduce effective deployment but cannot raise this ceiling.</p></div><span id="risk-appetite-badge" class="badge info">1.00%</span></div>
          <div class="grid g3">
            <div class="kpi"><div class="label">Configured hard ceiling</div><div class="value small" id="risk-appetite-current">1.00%</div></div>
            <div class="kpi"><div class="label">Current hard risk amount</div><div class="value small" id="risk-appetite-amount">—</div></div>
            <div class="kpi"><div class="label">Atlas operating ceiling</div><div class="value small" id="risk-appetite-operating">—</div></div>
          </div>
          <div class="callout" style="margin-top:12px">
            <div class="row" style="align-items:flex-end;gap:16px">
              <div style="flex:1">
                <label class="label" for="risk-appetite-input">Maximum aggregate portfolio risk (%)</label>
                <input id="risk-appetite-input" class="search" type="number" min="1" max="20" step="0.25" value="1" style="margin-top:6px">
                <div class="muted" style="margin-top:6px">Allowed: 1%–20%. Higher values increase Atlas' aggregate risk capacity; scalp, zone, recovery, broker, structure and protection gates still apply independently.</div>
              </div>
              <button id="btn-save-risk-appetite" class="btn primary" onclick="saveRiskAppetite()">Save risk ceiling</button>
            </div>
          </div>
          <div id="risk-appetite-warning" class="callout" style="margin-top:12px">Only you can increase this ceiling. Gemini and autonomous policy are not permitted to raise it.</div>
        </div>

        <div class="card section">
          <div class="section-head"><div><h3>Notifications</h3><p>Human-facing alerts for material Atlas state changes. Repeated polling states are deduplicated.</p></div><span class="badge info">EVENT AWARE</span></div>
          <div class="notification-settings">
            <div class="notification-setting"><div><strong>In-app notifications</strong><div class="muted">Persist alerts in the Atlas bell and notification drawer.</div></div><input id="notif-inapp" class="switch" type="checkbox" onchange="saveNotificationSettings()"></div>
            <div class="notification-setting"><div><strong>Browser notifications</strong><div class="muted">Show desktop/browser alerts when Atlas is in the background.</div></div><div class="actions"><input id="notif-browser" class="switch" type="checkbox" onchange="setBrowserNotifications(this.checked)"><button class="btn" onclick="requestBrowserNotifications()">Permission</button></div></div>
            <div class="notification-setting"><div><strong>Sound effects</strong><div class="muted">Play severity-aware tones on new material alerts.</div></div><input id="notif-sound" class="switch" type="checkbox" onchange="saveNotificationSettings()"></div>
            <div class="notification-setting"><div><strong>Sound volume</strong><div class="muted">Master notification volume.</div></div><div class="actions"><input id="notif-volume" class="volume" type="range" min="0" max="1" step="0.05" oninput="saveNotificationSettings()"><button class="btn" onclick="testNotificationSound()">Test sound</button></div></div>
            <div class="notification-setting"><div><strong>Minimum sound severity</strong><div class="muted">Lower-priority notifications remain visible but silent.</div></div><select id="notif-min-severity" class="symbol-select" onchange="saveNotificationSettings()"><option>INFO</option><option>IMPORTANT</option><option>WARNING</option><option>CRITICAL</option></select></div>
          </div>
          <div class="callout" style="margin-top:12px">Sounds are armed after your first interaction with Atlas because browsers block unsolicited audio. Atlas alerts on state transitions, not every polling tick.</div>
        </div>

        <div class="card section">
          <div class="section-head"><div><h3>Advanced runtime controls</h3><p>157 controls remain available, but they no longer dominate the dashboard.</p></div><span class="badge warn">ADVANCED</span></div>
          <input id="control-search" class="search" placeholder="Search runtime controls…" oninput="renderControls()">
          <div id="runtime-controls" class="controls" style="margin-top:12px"></div>
          <div class="sticky-actions">
            <span id="dirty-count" class="muted">No unsaved changes</span>
            <div class="actions"><button class="btn" onclick="discardEdits()">Discard</button><button class="btn primary" onclick="applyEdits()">Apply changed controls</button></div>
          </div>
        </div>
      </section>

      <section id="view-history" class="view">
        <div class="page-head"><div><h2>System & Audit</h2><p>System integrity, execution lifecycle, policy history and authoritative audit evidence.</p></div><span class="badge">READ ONLY</span></div>
        <div class="grid g3">
          <div class="card"><div class="label">Execution audit</div><div class="value small" id="h-audit">—</div><div class="muted" id="h-audit-count">—</div></div>
          <div class="card"><div class="label">Policy epochs</div><div class="value small" id="h-epochs">—</div></div>
          <div class="card"><div class="label">Tracked outcomes</div><div class="value small" id="h-outcomes">—</div></div>
        </div>
        <div class="grid g2 section">
          <div class="card"><div class="section-head"><div><h3>Execution lifecycle</h3><p>Most recent execution events.</p></div></div><div id="execution-events" class="timeline"></div></div>
          <div class="card"><div class="section-head"><div><h3>Policy epochs</h3><p>Most recent registered policies.</p></div></div><div id="policy-epochs" class="timeline"></div></div>
        </div>
        <details class="card raw section"><summary>Advanced raw diagnostics</summary><pre id="raw-diagnostics">Loading…</pre></details>
      </section>
    </div>
  </main>
</div>

<div id="confirm-modal" class="modal"><div class="modal-card">
  <h3>Execute approved policy</h3>
  <p class="muted">Atlas will re-check the operator arm, approval, current context, command baseline, Risk Governor and runtime validation before writing the command.</p>
  <div id="modal-exec-summary" class="callout"></div>
  <p style="margin:14px 0 6px" class="label">Operator</p>
  <input id="modal-actor" class="search" value="Nobel">
  <p style="margin:14px 0 6px" class="label">Confirmation</p>
  <div class="callout mono">EXECUTE_SUPERVISED_COMMAND</div>
  <div class="modal-actions"><button class="btn" onclick="closeModal()">Cancel</button><button class="btn primary" onclick="confirmExecute()">Execute policy</button></div>
</div></div>
<div id="toast" class="toast"></div>

<script>
const CONTROL_CONFIG = __CONTROL_CONFIG__;
const state = {
  status:null, command:null, intelligence:null, parameterIntel:null, proposal:null, review:null,
  supervised:null, preflight:null, execution:null, ack:null, arm:null, llmCycle:null, llmStatus:null, autoConsensus:null, responsiveness:null, candles:null, zoneMap:null, zonePlan:null,
  executionEvents:null, epochs:null, outcomes:null, performance:null, riskUnits:null, recoveryAttribution:null, recoveryRisk:null, riskAppetite:null, audit:null, autoApplications:null, dirty:{}, symbols:[], selectedSymbol:null, notificationBaseline:null, decisionBaseline:null
};

const viewMeta={
  overview:["Command Center","What Atlas is watching now"],
  market:["Market","Signals, regime, volatility and execution economics"],
  analysis:["Zone Analysis","Daily trade locations and live zone execution"],
  positions:["Portfolio","Exposure and position management"],
  performance:["Performance","Strategic outcomes, execution quality and learning readiness"],
  atlas:["Atlas Brain","Adaptation, evidence and model authority"],
  control:["Settings","Execution authority and advanced controls"],
  history:["System & Audit","System integrity, execution history and audit evidence"],
  help:["Help & Guide","How to understand and operate Atlas"]
};

function go(name){
  document.querySelectorAll(".view").forEach(x=>x.classList.remove("active"));
  document.querySelectorAll(".nav button").forEach(x=>x.classList.toggle("active",x.dataset.view===name));
  document.getElementById("view-"+name).classList.add("active");
  document.getElementById("top-title").textContent=viewMeta[name][0];
  document.getElementById("top-subtitle").textContent=viewMeta[name][1];
}
document.querySelectorAll(".nav button").forEach(b=>b.onclick=()=>go(b.dataset.view));
function filterHelp(query){
  const q=String(query||"").trim().toLowerCase();
  let visible=0;
  document.querySelectorAll("#view-help .help-searchable").forEach(section=>{
    const hay=(section.dataset.help||"")+" "+section.textContent;
    const show=!q||hay.toLowerCase().includes(q);
    section.classList.toggle("help-hidden",!show);
    if(show){visible++; if(q)section.open=true;}
  });
  const empty=document.getElementById("help-no-results");
  if(empty)empty.style.display=visible?"none":"block";
}
function clearHelpSearch(){
  const input=document.getElementById("help-search");
  if(input)input.value="";
  filterHelp("");
}
// Live Market & Entry Analysis has one canonical home in Market.
const fmt=(v,d=2)=>Number.isFinite(Number(v))?Number(v).toFixed(d):"—";
const money=v=>Number.isFinite(Number(v))?new Intl.NumberFormat(undefined,{style:"currency",currency:"USD",maximumFractionDigits:2}).format(Number(v)):"—";
const text=(v,f="—")=>(v===null||v===undefined||v==="")?f:String(v);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pretty=s=>String(s??"").replaceAll("_"," ").replace(/\b\w/g,m=>m.toUpperCase());
const age=s=>{s=Number(s||0); if(s<60)return Math.round(s)+"s"; if(s<3600)return Math.floor(s/60)+"m"; return Math.floor(s/3600)+"h "+Math.floor((s%3600)/60)+"m";}
const countdownAge=s=>{s=Math.max(0,Math.ceil(Number(s||0)));const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;return h?`${h}h ${String(m).padStart(2,"0")}m ${String(sec).padStart(2,"0")}s`:`${m}m ${String(sec).padStart(2,"0")}s`;};
function badgeClass(v){v=String(v||"").toUpperCase();if(v.includes("READY")||v.includes("PASS")||v.includes("CONFIRMED")||v.includes("APPLIED")||v.includes("EXECUTED")||v==="LOW"||v==="APPROVED")return"ok";if(v.includes("BLOCK")||v.includes("FAIL")||v.includes("HIGH")||v.includes("MISMATCH")||v.includes("TIMEOUT")||v.includes("REJECT"))return"bad";return"warn"}
function toast(msg,bad=false){const t=document.getElementById("toast");t.textContent=msg;t.className="toast show"+(bad?" bad":"");setTimeout(()=>t.className="toast",4500)}

const NOTIF_DEFAULTS={inApp:true,browser:false,sound:true,volume:.35,minSeverity:"INFO"};
const SEVERITY_RANK={INFO:0,IMPORTANT:1,WARNING:2,CRITICAL:3};
let notificationSettings={...NOTIF_DEFAULTS};
let notificationAudio=null;
function loadNotificationSettings(){try{notificationSettings={...NOTIF_DEFAULTS,...JSON.parse(localStorage.getItem("atlasNotificationSettings")||"{}")}}catch{};syncNotificationSettingsUI();renderNotifications()}
function syncNotificationSettingsUI(){const map={"notif-inapp":"inApp","notif-browser":"browser","notif-sound":"sound","notif-volume":"volume","notif-min-severity":"minSeverity"};for(const [id,k] of Object.entries(map)){const el=document.getElementById(id);if(!el)continue;if(el.type==="checkbox")el.checked=!!notificationSettings[k];else el.value=notificationSettings[k]}}
function saveNotificationSettings(){notificationSettings.inApp=!!document.getElementById("notif-inapp")?.checked;notificationSettings.browser=!!document.getElementById("notif-browser")?.checked;notificationSettings.sound=!!document.getElementById("notif-sound")?.checked;notificationSettings.volume=Number(document.getElementById("notif-volume")?.value??.35);notificationSettings.minSeverity=document.getElementById("notif-min-severity")?.value||"INFO";localStorage.setItem("atlasNotificationSettings",JSON.stringify(notificationSettings));}
async function requestBrowserNotifications(){if(!("Notification" in window)){toast("Browser notifications are not supported here",true);return}const p=await Notification.requestPermission();const el=document.getElementById("notif-browser");if(p==="granted"){notificationSettings.browser=true;if(el)el.checked=true;saveNotificationSettings();syncNotificationSettingsUI();toast("Browser notifications enabled")}else{notificationSettings.browser=false;if(el)el.checked=false;saveNotificationSettings();syncNotificationSettingsUI();toast("Browser notification permission not granted",true)}}
function setBrowserNotifications(on){if(on&&("Notification" in window)&&Notification.permission!=="granted"){requestBrowserNotifications();return}notificationSettings.browser=on;saveNotificationSettings()}
function notificationStoreKey(){return `atlasNotifications:${state.selectedSymbol||"default"}`}
function getNotifications(){try{return JSON.parse(localStorage.getItem(notificationStoreKey())||"[]")}catch{return[]}}
function setNotifications(v){localStorage.setItem(notificationStoreKey(),JSON.stringify(v.slice(0,150)));renderNotifications()}
function toggleNotifications(){const d=document.getElementById("notify-drawer");d.classList.toggle("open");if(d.classList.contains("open"))renderNotifications()}
function markAllNotificationsRead(){setNotifications(getNotifications().map(n=>({...n,read:true})))}
function renderNotifications(){const list=document.getElementById("notify-list"),count=document.getElementById("notify-count");if(!list||!count)return;const ns=getNotifications(),unread=ns.filter(n=>!n.read).length;count.textContent=unread>99?"99+":unread;count.classList.toggle("show",unread>0);list.innerHTML=ns.length?ns.map(n=>`<div class="notify-item ${n.read?"":"unread"}" onclick="readNotification('${esc(n.id)}')"><div class="notify-row"><div class="notify-title"><span class="notify-sev ${esc(n.severity)}">${esc(n.severity)}</span>${esc(n.title)}</div><span class="notify-time">${new Date(n.at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</span></div><div class="notify-body">${esc(n.body)}</div></div>`).join(""):'<div class="notify-empty">No Atlas notifications yet.</div>'}
function readNotification(id){setNotifications(getNotifications().map(n=>n.id===id?{...n,read:true}:n))}
function armNotificationAudio(){try{notificationAudio=notificationAudio||new (window.AudioContext||window.webkitAudioContext)();if(notificationAudio.state==="suspended")notificationAudio.resume()}catch{}}
document.addEventListener("pointerdown",armNotificationAudio,{once:true});
function playNotificationSound(severity="INFO"){if(!notificationSettings.sound||SEVERITY_RANK[severity]<SEVERITY_RANK[notificationSettings.minSeverity])return;armNotificationAudio();if(!notificationAudio)return;const patterns={INFO:[[660,.07]],IMPORTANT:[[660,.07],[880,.1]],WARNING:[[520,.09],[520,.09]],CRITICAL:[[440,.12],[660,.12],[440,.16]]};let t=notificationAudio.currentTime+.01;for(const [freq,dur] of patterns[severity]||patterns.INFO){const o=notificationAudio.createOscillator(),g=notificationAudio.createGain();o.frequency.value=freq;g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(.12*notificationSettings.volume,t+.01);g.gain.exponentialRampToValueAtTime(.001,t+dur);o.connect(g);g.connect(notificationAudio.destination);o.start(t);o.stop(t+dur+.02);t+=dur+.055}}
function testNotificationSound(){playNotificationSound("IMPORTANT")}
function pushAtlasNotification(severity,title,body,key){const now=Date.now(),ns=getNotifications();if(ns.some(n=>n.key===key&&now-new Date(n.at).getTime()<300000))return;const n={id:`${now}-${Math.random().toString(16).slice(2)}`,key,severity,title,body,at:new Date(now).toISOString(),read:false};if(notificationSettings.inApp)setNotifications([n,...ns]);playNotificationSound(severity);if(notificationSettings.browser&&("Notification" in window)&&Notification.permission==="granted"&&document.hidden){try{new Notification(`Atlas · ${title}`,{body,icon:"/assets/atlas-app-icon.png",tag:key})}catch{}}}
function notificationSnapshot(){const s=state.status||{},z=state.zonePlan||{},lp=z?.capital_sizing?.loss_protection||{};return{connected:!!s.connected,open:Number(s.strategy_open_positions||s.open_positions||0),lastTicket:Number(s.last_order_ticket||0),lastSuccess:!!s.last_order_success,zoneState:String(s.zone_directive_state||z.execution_lane||""),zoneSide:String(s.zone_side||z.side||"NONE"),zoneSuspended:!!s.zone_scalp_suspended,capitalVeto:!!s.capital_veto_new_risk,lossState:String(lp.state||"INACTIVE"),policyEpoch:Number(s.policy_epoch||0),appliedCommand:Number(s.applied_command_version||0),recoveryChains:Number(s.active_hedge_chains||0)}}
function evaluateNotifications(){const cur=notificationSnapshot(),prev=state.notificationBaseline;state.notificationBaseline=cur;if(!prev)return;if(prev.connected&&!cur.connected)pushAtlasNotification("CRITICAL","Nyao disconnected","Atlas lost the live Nyao bridge.","nyao-disconnected");if(!prev.connected&&cur.connected)pushAtlasNotification("INFO","Nyao connected","Live execution telemetry is available again.","nyao-connected");if(cur.lastSuccess&&cur.lastTicket&&cur.lastTicket!==prev.lastTicket)pushAtlasNotification("IMPORTANT","Trade opened",`${cur.zoneSide!=="NONE"?cur.zoneSide+" · ":""}Ticket ${cur.lastTicket} · ${state.selectedSymbol||"symbol"}.`,`trade-${cur.lastTicket}`);if(cur.open<prev.open)pushAtlasNotification("INFO","Position closed",`${prev.open-cur.open} strategy position${prev.open-cur.open===1?"":"s"} closed on ${state.selectedSymbol||"symbol"}.`,`close-${Date.now()}`);if(cur.zoneState!==prev.zoneState){if(cur.zoneState==="ZONE_AWARE_SCALP")pushAtlasNotification("INFO",`${cur.zoneSide} zone watching`,`Zone-aware scalping is active while the campaign waits for commit gates.`,`zone-watch-${cur.zoneSide}`);else if(cur.zoneState.includes("ZONE_CAMPAIGN"))pushAtlasNotification("IMPORTANT",`${cur.zoneSide} zone committed`,`Atlas granted the zone campaign execution priority.`,`zone-commit-${cur.zoneSide}`);else if(prev.zoneState&&cur.zoneState==="OUTSIDE_PRIORITY_ZONE")pushAtlasNotification("INFO","Priority zone released","Normal scalp authority restored outside the priority zone.","zone-released")}
if(!prev.capitalVeto&&cur.capitalVeto)pushAtlasNotification("WARNING","New risk vetoed","Atlas capital authority is blocking fresh risk.","capital-veto");if(prev.lossState!==cur.lossState&&cur.lossState&&cur.lossState!=="INACTIVE")pushAtlasNotification(cur.lossState==="HARD_VETO"?"CRITICAL":"WARNING","Loss protection changed",`Protection state is now ${pretty(cur.lossState)}.`,`loss-${cur.lossState}`);if(cur.recoveryChains>prev.recoveryChains)pushAtlasNotification("WARNING","Recovery chain active",`${cur.recoveryChains} recovery chain${cur.recoveryChains===1?"":"s"} now active.`,`recovery-${cur.recoveryChains}`);if(cur.policyEpoch!==prev.policyEpoch&&cur.policyEpoch>0)pushAtlasNotification("INFO","Policy epoch changed",`Nyao is now reporting policy epoch ${cur.policyEpoch}.`,`epoch-${cur.policyEpoch}`)}

function scopedUrl(url){
  if(!state.selectedSymbol || !url.startsWith("/api/v1/") || url.startsWith("/api/v1/atlas/symbols"))return url;
  const join=url.includes("?")?"&":"?";
  return `${url}${join}symbol=${encodeURIComponent(state.selectedSymbol)}`;
}
async function api(url,opts={}){const r=await fetch(scopedUrl(url),{cache:"no-store",...opts});let data=null;try{data=await r.json()}catch{}if(!r.ok){const detail=data?.detail;throw new Error(typeof detail==="string"?detail:(detail?.code?detail.code+": "+detail.message:`HTTP ${r.status}`))}return data}
function jsonPost(url,body){return api(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})}


function decisionStoreKey(){return `atlasDecisionTimeline:${state.selectedSymbol||"default"}`}
function getDecisionTimeline(){try{return JSON.parse(localStorage.getItem(decisionStoreKey())||"[]")}catch{return[]}}
function setDecisionTimeline(v){localStorage.setItem(decisionStoreKey(),JSON.stringify(v.slice(0,240)));renderDecisionTimeline()}
function clearDecisionTimeline(){setDecisionTimeline([]);state.decisionBaseline=decisionSnapshot()}
function addDecisionEvent(kind,title,body,action="overview",key=""){
  const now=Date.now(),events=getDecisionTimeline();
  if(key&&events.some(e=>e.key===key&&now-new Date(e.at).getTime()<60000))return;
  setDecisionTimeline([{id:`${now}-${Math.random().toString(16).slice(2)}`,kind,title,body,action,key,at:new Date(now).toISOString()},...events]);
}
function decisionSnapshot(){
  const s=state.status||{},zp=state.zonePlan||{},cap=zp.capital_sizing||{},lp=cap.loss_protection||{},plan=zp.zone_plan||{};
  return {
    connected:!!s.connected,
    buyEligible:!!s.buy_entry_eligible,sellEligible:!!s.sell_entry_eligible,
    buyReason:String(s.buy_block_reason||""),sellReason:String(s.sell_block_reason||""),
    buyScore:Number(s.buy_adjusted_score??s.buy_score??0),sellScore:Number(s.sell_adjusted_score??s.sell_score??0),
    buyThreshold:Number(s.buy_effective_threshold??s.runtime_min_buy_signal_score??0),sellThreshold:Number(s.sell_effective_threshold??s.runtime_min_sell_signal_score??0),
    scalpCost:!!s.scalp_cost_feasible,scalpStructure:String(s.scalp_structure_reason||""),
    zoneState:String(s.zone_directive_state||zp.execution_lane||""),zoneSide:String(s.zone_side||plan.side||"NONE"),zonePlan:String(s.zone_plan_id||plan.plan_id||""),
    zoneConfirm:Number(s.zone_confirmation_score??plan.confirmation?.zone_confirmation?.combined_score??0),zoneConfirmThreshold:Number(s.zone_confirmation_threshold??plan.confirmation?.zone_confirmation?.threshold??0),
    zoneDirectional:Number(s.zone_directional_score??0),zoneDirectionalThreshold:Number(s.zone_minimum_directional_score??0),zoneSpreadOk:s.zone_spread_within_limit!==false,
    capitalVeto:!!s.capital_veto_new_risk,scalpRisk:Number(cap.approved_scalp_risk_amount||0),zoneRisk:Number(cap.approved_zone_risk_amount||0),reserved:Number(cap.portfolio_allocation?.reserved_active_risk_amount||0),available:Number(cap.portfolio_allocation?.remaining_operating_risk_amount||0),
    lossState:String(lp.state||"INACTIVE"),policyEpoch:Number(s.policy_epoch||0),open:Number(s.strategy_open_positions??s.open_positions??0),lastTicket:Number(s.last_order_ticket||0),lastSuccess:!!s.last_order_success,recovery:Number(s.active_hedge_chains||0)
  }
}
function crossedUp(a,b,t){return Number.isFinite(t)&&t>0&&a<t&&b>=t}
function crossedDown(a,b,t){return Number.isFinite(t)&&t>0&&a>=t&&b<t}
function materiallyChanged(a,b){const base=Math.max(Math.abs(a),1);return Math.abs(b-a)/base>=.15}
function evaluateDecisionTimeline(){
  const cur=decisionSnapshot(),prev=state.decisionBaseline;state.decisionBaseline=cur;if(!prev)return;
  if(prev.connected!==cur.connected)addDecisionEvent(cur.connected?"SYSTEM":"CRITICAL",cur.connected?"Nyao connection restored":"Nyao connection lost",cur.connected?"Atlas can evaluate execution authority again.":"Execution decisions are suspended until live Nyao telemetry returns.","overview",`connected-${cur.connected}`);
  if(prev.zoneState!==cur.zoneState||prev.zonePlan!==cur.zonePlan){
    const title=cur.zoneState==="ZONE_AWARE_SCALP"?`${cur.zoneSide} zone entered WATCHING`:cur.zoneState.includes("ZONE_CAMPAIGN")?`${cur.zoneSide} zone committed`:cur.zoneState==="OUTSIDE_PRIORITY_ZONE"?"Priority zone released":`Zone state → ${pretty(cur.zoneState||"NONE")}`;
    const body=cur.zoneState==="ZONE_AWARE_SCALP"?"Aligned scalping remains active while Atlas waits for campaign commit gates.":cur.zoneState.includes("ZONE_CAMPAIGN")?"The zone campaign owns fresh-entry priority; policy activation is deferred to the campaign boundary.":cur.zoneState==="OUTSIDE_PRIORITY_ZONE"?"Normal scalp authority is restored.":`Current zone side ${cur.zoneSide}.`;
    addDecisionEvent(cur.zoneState.includes("ZONE_CAMPAIGN")?"READY":"ZONE",title,body,"analysis",`zone-${cur.zoneState}-${cur.zonePlan}`)
  }
  if(!prev.zoneSpreadOk&&cur.zoneSpreadOk)addDecisionEvent("READY","Zone execution cost became feasible",`Current spread is now inside the adaptive campaign limit for the ${cur.zoneSide} zone.`,"analysis","zone-spread-pass");
  if(prev.zoneSpreadOk&&!cur.zoneSpreadOk&&cur.zoneState&&cur.zoneState!=="OUTSIDE_PRIORITY_ZONE")addDecisionEvent("BLOCK","Zone execution cost became too expensive",`Spread moved outside the adaptive campaign limit; the zone remains context but cannot commit on cost.`,"analysis","zone-spread-block");
  if(crossedUp(prev.zoneConfirm,cur.zoneConfirm,cur.zoneConfirmThreshold))addDecisionEvent("READY","Zone confirmation threshold reached",`${fmt(cur.zoneConfirm,1)} ≥ ${fmt(cur.zoneConfirmThreshold,1)}. Directional and execution gates still remain authoritative.`,"analysis","zone-confirm-pass");
  if(crossedDown(prev.zoneConfirm,cur.zoneConfirm,cur.zoneConfirmThreshold))addDecisionEvent("BLOCK","Zone confirmation fell below threshold",`${fmt(cur.zoneConfirm,1)} < ${fmt(cur.zoneConfirmThreshold,1)}.`,"analysis","zone-confirm-fail");
  if(crossedUp(prev.zoneDirectional,cur.zoneDirectional,cur.zoneDirectionalThreshold))addDecisionEvent("READY","Zone directional evidence qualified",`${fmt(cur.zoneDirectional,2)} ≥ ${fmt(cur.zoneDirectionalThreshold,2)}.`,"analysis","zone-direction-pass");
  if(!prev.scalpCost&&cur.scalpCost)addDecisionEvent("READY","Scalp execution economics recovered","The current scalp structure can absorb transaction cost without excessive geometry expansion.","market","scalp-cost-pass");
  if(prev.scalpCost&&!cur.scalpCost)addDecisionEvent("BLOCK","Scalp execution economics blocked",pretty(cur.scalpStructure||"COST_STRUCTURE_MISMATCH"),"market","scalp-cost-block");
  for(const side of ["buy","sell"]){const S=side.toUpperCase(),pe=prev[`${side}Eligible`],ce=cur[`${side}Eligible`],pr=prev[`${side}Reason`],cr=cur[`${side}Reason`];if(!pe&&ce)addDecisionEvent("READY",`${S} scalp became eligible`,`${S} score ${fmt(cur[`${side}Score`],2)} / ${fmt(cur[`${side}Threshold`],2)} and all current Nyao entry gates passed.`,"market",`${side}-eligible`);else if(pe&&!ce)addDecisionEvent("BLOCK",`${S} scalp eligibility lost`,pretty(cr||"BLOCKED"),"market",`${side}-blocked-${cr}`);else if(pr!==cr&&cr)addDecisionEvent("GATE",`${S} blocker changed`,`${pretty(pr||"NONE")} → ${pretty(cr)}`,"market",`${side}-reason-${cr}`)}
  if(!prev.capitalVeto&&cur.capitalVeto)addDecisionEvent("RISK","Fresh-risk capital veto activated","Atlas has temporarily closed new independent risk authority.","overview","capital-veto-on");
  if(prev.capitalVeto&&!cur.capitalVeto)addDecisionEvent("READY","Fresh-risk capital authority restored",`${money(cur.available)} operating capacity is currently available.`,"overview","capital-veto-off");
  if(prev.lossState!==cur.lossState)addDecisionEvent(cur.lossState==="HARD_VETO"?"CRITICAL":"RISK",`Loss protection → ${pretty(cur.lossState)}`,`Previous state: ${pretty(prev.lossState)}.`,"overview",`loss-${cur.lossState}`);
  if(cur.policyEpoch&&prev.policyEpoch&&cur.policyEpoch!==prev.policyEpoch)addDecisionEvent("POLICY",`Nyao policy epoch ${cur.policyEpoch} active`,`Atlas/Nyao moved from policy epoch ${prev.policyEpoch} to ${cur.policyEpoch}.`,"atlas",`epoch-${cur.policyEpoch}`);
  if(cur.lastSuccess&&cur.lastTicket&&cur.lastTicket!==prev.lastTicket)addDecisionEvent("TRADE","Order execution confirmed",`Ticket ${cur.lastTicket} opened on ${state.selectedSymbol||"the selected symbol"}.`,"positions",`trade-${cur.lastTicket}`);
  if(cur.open<prev.open)addDecisionEvent("TRADE","Position lifecycle changed",`${prev.open-cur.open} strategy position${prev.open-cur.open===1?"":"s"} closed; Atlas will reconcile the authoritative outcome ledger.`,"positions",`close-${Date.now()}`);
  if(prev.recovery===0&&cur.recovery>0)addDecisionEvent("RISK","Recovery chain activated",`${cur.recovery} active recovery chain${cur.recovery===1?"":"s"}; composite risk accounting is authoritative.`,"positions","recovery-on");
  if(prev.recovery>0&&cur.recovery===0)addDecisionEvent("TRADE","Recovery chain resolved","The active recovery chain is flat; Atlas will score the completed composite result.","positions","recovery-off");
  if(materiallyChanged(prev.scalpRisk,cur.scalpRisk)||materiallyChanged(prev.zoneRisk,cur.zoneRisk))addDecisionEvent("RISK","Opportunity risk allocation updated",`Scalp ${money(cur.scalpRisk)} · zone ${money(cur.zoneRisk)} · available operating risk ${money(cur.available)}.`,"overview",`risk-${Math.round(cur.scalpRisk)}-${Math.round(cur.zoneRisk)}`)
}
function renderDecisionTimeline(){const el=document.getElementById("decision-timeline");if(!el)return;const events=getDecisionTimeline();el.innerHTML=events.length?events.slice(0,40).map(e=>`<div class="decision-event" onclick="go('${esc(e.action||"overview")}')"><span class="decision-dot ${esc(e.kind)}"></span><div><div class="decision-title">${esc(e.title)}</div><div class="decision-body">${esc(e.body)}</div></div><span class="decision-time">${new Date(e.at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"})}</span></div>`).join(""):'<div class="observability-empty">Atlas will record the next material decision change.</div>'}
function opportunityStatusClass(status){return status==="READY"?"ready":status==="ACTIVE"?"active":status==="BLOCKED"?"blocked":status==="QUALIFYING"?"qualifying":""}
function opportunityBadgeClass(status){return status==="READY"||status==="ACTIVE"?"ok":status==="BLOCKED"?"bad":"warn"}
function opportunityRow(name,value,status,next,meta,view){return `<div class="opportunity-item ${opportunityStatusClass(status)}" onclick="go('${view}')"><div><div class="opportunity-name">${esc(name)}</div><div class="opportunity-value">${esc(value)}</div></div><div class="opportunity-next"><strong>Next:</strong> ${esc(next)}<div class="opportunity-meta">${esc(meta)}</div></div><span class="badge ${opportunityBadgeClass(status)} opportunity-status">${esc(status)}</span></div>`}
function scalpOpportunity(side){
  const s=state.status||{},cap=state.zonePlan?.capital_sizing||{},upper=side.toUpperCase();
  const score=Number(s[`${side}_adjusted_score`]??s[`${side}_score`]??0);
  const threshold=Number(s[`${side}_effective_threshold`]??s[`runtime_min_${side}_signal_score`]??0);
  const eligible=!!s[`${side}_entry_eligible`];
  const reason=String(s[`${side}_block_reason`]||"").toUpperCase();
  const risk=Number(cap.approved_scalp_risk_amount||0);
  const zoneState=String(s.zone_directive_state||"").toUpperCase();
  const zoneSide=String(s.zone_side||"NONE").toUpperCase();
  const zoneAware=Boolean(s.zone_aware_scalping_active||(zoneState==="ZONE_AWARE_SCALP"&&!s.zone_scalp_suspended));
  const contextual=zoneAware&&zoneSide!=="NONE";
  const counter=contextual&&zoneSide!==upper;
  const aligned=contextual&&zoneSide===upper;
  const label=contextual?`${upper} SCALP · ${counter?"COUNTER-ZONE":"ZONE-ALIGNED"}`:`${upper} SCALP`;
  let status=eligible?"READY":"WATCHING";
  let next=eligible?"All deterministic entry gates currently pass.":"Waiting for the next eligible scalp condition.";
  if(reason==="SCORE_BELOW_THRESHOLD"||score<threshold){
    next=`Score must first reach ${fmt(threshold,2)}; currently ${fmt(score,2)}.${counter?" Counter-zone evidence requirements apply after the base signal gate.":""}`;
  }else if(reason==="COUNTER_ZONE_EVIDENCE_INSUFFICIENT"){
    status="QUALIFYING";next="Base signal qualifies, but the additional counter-zone evidence premium has not cleared yet.";
  }else if(reason==="COUNTER_ZONE_COMMIT_PROXIMITY"){
    status="BLOCKED";next=`The ${zoneSide} zone campaign is too close to commitment for a fresh ${upper} counter-zone scalp.`;
  }else if(reason==="COUNTER_ZONE_SIGNAL_READY"){
    status=eligible?"READY":"QUALIFYING";next=eligible?"Counter-zone evidence is qualified and all remaining Nyao gates pass.":"Counter-zone evidence is qualified; another execution gate is still pending.";
  }else if(reason.includes("COST")||s.scalp_cost_feasible===false){
    next=`Execution economics must recover (${pretty(s.scalp_structure_reason||reason||"cost gate")}).`;
  }else if(reason.includes("CAPITAL")||s.capital_veto_new_risk){
    status="BLOCKED";next="Atlas capital authority must reopen fresh risk.";
  }else if(reason==="ATLAS_ZONE_MODE"){
    status="BLOCKED";next="The committed zone campaign currently owns fresh-entry authority.";
  }else if(reason&&reason!=="NONE"&&reason!=="INITIALIZED"){
    status="BLOCKED";next=pretty(reason);
  }
  const contextMeta=counter?`${zoneSide} zone · counter-zone rules`:aligned?`${zoneSide} zone · aligned rules`:"normal scalp rules";
  return opportunityRow(label,`${fmt(score,2)} / ${fmt(threshold,2)}`,status,next,`Current opportunity limit ${money(risk)} · ${contextMeta} · ${pretty(reason||"NO BLOCK")}`,"market");
}
function zoneOpportunity(){
  const s=state.status||{},zp=state.zonePlan||{},plan=zp.zone_plan||null,cap=zp.capital_sizing||{};if(!plan&&!s.zone_plan_id)return opportunityRow("ZONE CAMPAIGN","NO PRIORITY ZONE","WATCHING","Wait for Atlas to detect and qualify higher-timeframe structure.",`Current zone opportunity limit ${money(cap.approved_zone_risk_amount||0)}`,"analysis");
  const side=String(plan?.side||s.zone_side||"ZONE"),confirm=Number(s.zone_confirmation_score??plan?.confirmation?.zone_confirmation?.combined_score??0),ct=Number(s.zone_confirmation_threshold??plan?.confirmation?.zone_confirmation?.threshold??0),dir=Number(s.zone_directional_score||0),dt=Number(s.zone_minimum_directional_score||0),spreadOk=s.zone_spread_within_limit!==false,stateName=String(s.zone_directive_state||zp.execution_lane||""),committed=stateName.includes("ZONE_CAMPAIGN")&&s.zone_scalp_suspended;
  let status=committed?"ACTIVE":"WATCHING",needs=[];if(ct>0&&confirm<ct)needs.push(`confirmation ${fmt(confirm,1)} → ${fmt(ct,1)}`);if(dt>0&&dir<dt)needs.push(`directional ${fmt(dir,2)} → ${fmt(dt,2)}`);if(!spreadOk)needs.push(`spread must return inside adaptive cap`);if(s.capital_veto_new_risk)needs.push("capital authority");if(!needs.length&&!committed){status="READY";needs.push("Atlas/Nyao commit boundary")}
  return opportunityRow(`${side} ZONE CAMPAIGN`,ct>0?`${fmt(confirm,1)} / ${fmt(ct,1)}`:pretty(stateName||"DETECTED"),status,committed?"Campaign has committed execution priority.":needs.join(" · "),`Directional ${fmt(dir,2)} / ${fmt(dt,2)} · ${spreadOk?"cost PASS":"cost BLOCK"} · limit ${money(cap.approved_zone_risk_amount||0)}`,"analysis")
}
function recoveryOpportunity(){const s=state.status||{},rr=state.recoveryRisk||{},chains=rr.active_chains||[];if(!chains.length&&!Number(s.active_hedge_chains||0))return opportunityRow("RECOVERY","STANDBY","WATCHING","No active recovery chain; Atlas will create recovery authority only from an eligible root lifecycle.","Composite-chain risk remains isolated from fresh opportunity budgets.","positions");const c=chains[0]||{},remaining=Number(c.hard_loss_budget_remaining_usd),ceiling=Number(c.hard_loss_budget_usd);return opportunityRow("RECOVERY CHAIN",money(c.mark_to_market||s.hedge_chain_floating_pl||0),"ACTIVE",Number.isFinite(remaining)?`${money(remaining)} chain risk remains inside the frozen ceiling.`:"Manage the active chain inside its frozen Atlas authority.",`Ceiling ${money(ceiling||0)} · ${Number(c.member_count||0)} member(s)`,"positions")}
function renderOpportunityQueue(){const el=document.getElementById("opportunity-queue"),badge=document.getElementById("opportunity-queue-badge"),summary=document.getElementById("opportunity-queue-summary");if(!el)return;const s=state.status||{},cap=state.zonePlan?.capital_sizing||{};el.innerHTML=[scalpOpportunity("buy"),scalpOpportunity("sell"),zoneOpportunity(),recoveryOpportunity()].join("");const anyReady=!!s.buy_entry_eligible||!!s.sell_entry_eligible||String(s.zone_directive_state||"").includes("ZONE_CAMPAIGN");badge.textContent=anyReady?"ACTIONABLE":"SCANNING";badge.className="badge "+(anyReady?"ok":"info");const alloc=cap.portfolio_allocation||{};summary.innerHTML=`<span><strong>${money(alloc.remaining_operating_risk_amount||0)}</strong> operating capacity</span><span>·</span><span><strong>${money(alloc.reserved_active_risk_amount||0)}</strong> reserved</span><span>·</span><span>Hard ceiling <strong>${money(alloc.portfolio_hard_ceiling_amount||0)}</strong></span>`}

async function loadSymbols(){
  try{
    const data=await api("/api/v1/atlas/symbols");
    state.symbols=data.symbols||[];

    const stored=localStorage.getItem("atlasSelectedSymbol");
    const available=state.symbols.map(x=>x.symbol);
    if(!state.selectedSymbol){
      if(stored && available.includes(stored))state.selectedSymbol=stored;
      else state.selectedSymbol=data.default_symbol||available[0]||null;
    }

    const select=document.getElementById("symbol-select");
    select.innerHTML=state.symbols.length
      ? state.symbols.map(item=>{
          const status=item.connected?"●":"○";
          return `<option value="${esc(item.symbol)}">${status} ${esc(item.symbol)}</option>`;
        }).join("")
      : '<option value="">No symbols</option>';

    if(state.selectedSymbol)select.value=state.selectedSymbol;
  }catch(e){
    console.warn("Symbol discovery failed",e);
  }
}

async function switchSymbol(symbol){
  if(!symbol || symbol===state.selectedSymbol)return;
  state.selectedSymbol=symbol;
  localStorage.setItem("atlasSelectedSymbol",symbol);

  state.status=null;
  state.command=null;
  state.intelligence=null;
  state.proposal=null;
  state.review=null;
  state.supervised=null;
  state.preflight=null;
  state.execution=null;
  state.ack=null;
  state.executionEvents=null;
  state.epochs=null;
  state.outcomes=null;
  state.audit=null;
  state.llmCycle=null;
  state.responsiveness=null;
  state.candles=null;
  state.zoneMap=null;
  state.zonePlan=null;
  state.dirty={};

  const controls=document.getElementById("runtime-controls");
  if(controls)controls.innerHTML="";

  toast(`Switched Atlas context to ${symbol}.`);
  await loadCore();
  await loadRiskAppetite();
  await loadIntelligence();
  await loadParameterIntelligence();
  await loadArm();
  await loadLlmCycle();
  await loadResponsiveness();
  await loadMarketCandles();
  await loadZoneMap();
  await loadProposal();
  await loadHistory();
  renderAll();
  renderControls();
}

function accountType(){
  const s=state.status||{};
  return text(s.account_type||s.account_trade_mode||s.trade_mode||s.account_mode,"ACCOUNT CONNECTED").toUpperCase();
}
function updateChrome(){
  const s=state.status||{}, c=state.command||{};
  const connected=s.connected!==false && !!state.status;
  const symbol=text(s.symbol||state.selectedSymbol,"—");
  const select=document.getElementById("symbol-select");
  if(select && state.selectedSymbol)select.value=state.selectedSymbol;
  document.getElementById("side-dot").className="dot "+(connected?"ok":"bad");
  document.getElementById("side-connection").textContent=connected?"Connected":"Offline";
  document.getElementById("side-symbol").textContent=symbol;
  document.getElementById("account-pill").textContent=accountType();
  document.getElementById("epoch-pill").textContent="Epoch "+text(c.policy_epoch??s.policy_epoch);
  document.getElementById("command-pill").textContent="Command "+text(c.command_version??s.applied_command_version);
}

function currentRisk(){
  const p=state.proposal||{};
  const i=state.intelligence||{};
  return p.risk?.state||p.review_summary?.risk_state||i.risk_governor?.state||i.risk?.state||"—";
}
function renderOverview(){
  const s=state.status||{}, c=state.command||{}, p=state.proposal||{};
  const zp=state.zonePlan||{}, activePlan=zp.zone_plan||null, capital=zp.capital_sizing||{};
  const cycle=state.llmCycle||{};
  const connected=!!state.status && s.connected!==false;
  const applied=s.applied_command_version;
  const synchronized=applied==null || c.command_version==null ? connected : Number(applied)===Number(c.command_version);
  const zoneAwarePlanned=Boolean(zp.zone_aware_scalping_active);
  const zoneAware=Boolean(
    s.zone_aware_scalping_active ||
    (
      s.zone_directive_fresh!==false &&
      !s.zone_scalp_suspended &&
      ["ZONE_AWARE_SCALP","ZONE_CAPITAL_INFEASIBLE"].includes(String(s.zone_directive_state||"").toUpperCase())
    )
  );
  const zoneMode=Boolean(s.zone_mode_active&&!zoneAware), side=text(activePlan?.side||s.zone_side,"ZONE");
  const executionLane=zoneAware?"ZONE-AWARE SCALP":zoneMode?"ZONE CAMPAIGN":"NORMAL SCALP";
  const liveCount=Number(s.strategy_open_positions??s.open_positions??0), stagedCount=Number(s.working_limit_orders||0);
  const permissionsOk=s.terminal_algo_trading_allowed!==false&&s.ea_trading_allowed!==false&&s.account_trade_allowed!==false&&s.account_expert_trading_allowed!==false;
  const confirmed=Boolean((zp.directive_preview||{}).zone_entry_allowed);
  const campaignRisk=Number(activePlan?.risk?.account_risk_pct||capital.approved_zone_risk_pct||0);
  const modeName=zoneAware?`${side} ZONE-AWARE SCALP`:zoneMode?`${side} ZONE CAMPAIGN`:"NORMAL SCALP";
  const setGlobal=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value};
  setGlobal("global-status-symbol",text(s.symbol||state.selectedSymbol));
  setGlobal("global-status-mode",modeName);
  setGlobal("global-status-positions",`${liveCount} live`);
  const alloc=capital.portfolio_allocation||{};
  setGlobal("global-status-risk",Number.isFinite(Number(alloc.remaining_operating_risk_amount))?`${money(alloc.remaining_operating_risk_amount)} free`:"—");
  setGlobal("global-status-brain",cycle.running?"REVIEWING":cycle.enabled&&Number.isFinite(Number(cycle.seconds_until_next_run))?`REVIEW ${age(cycle.seconds_until_next_run)}`:"IDLE");
  setGlobal("global-status-health",connected&&permissionsOk&&s.zone_directive_fresh!==false?"HEALTHY":connected?"DEGRADED":"OFFLINE");
  const gsd=document.getElementById("global-status-dot");if(gsd)gsd.className="dot "+(connected?"ok":"bad");
  document.getElementById("hero-state").textContent=!connected?"Nyao is offline":zoneAware?`${side} zone context guiding scalps`:zoneMode?`${side} zone campaign owns execution`:"Atlas is scanning for scalps";
  document.getElementById("hero-copy").textContent=!connected
    ?"Atlas cannot verify market state or execution authority."
    :zoneAware
      ?`A qualified ${side} zone is informing scalp direction, but the full zone campaign does not own execution. Nyao keeps normal scalp thresholds, costs and Atlas risk limits.`
      :zoneMode
        ?`${liveCount} live position${liveCount===1?"":"s"} and ${stagedCount} staged entr${stagedCount===1?"y":"ies"}. Ordinary scalping is paused while this campaign owns the risk budget.`
        :"No priority zone currently owns execution. Nyao may scalp when Atlas direction, cost, signal and capital gates agree.";
  const modeBadge=document.getElementById("hero-mode-badge");modeBadge.textContent=connected?modeName:"OFFLINE";modeBadge.className="badge "+(connected?(zoneMode?"info":"ok"):"bad");
  document.getElementById("hero-symbol").textContent=text(s.symbol||state.selectedSymbol);
  document.getElementById("hero-market-state").textContent=zoneAware?`${side} aligned preferred · counter-zone conditional`:zoneMode?(confirmed?"zone confirmed":"awaiting confirmation"):(s.spread_within_limit===false?"cost blocked":"scalp scan active");
  document.getElementById("hero-bridge").textContent=s.zone_directive_fresh===false?"stale":"live";
  document.getElementById("hero-risk").textContent=modeName;
  document.getElementById("hero-policy").textContent=campaignRisk>0?`${fmt(campaignRisk,3)}% equity`:capital.approved_scalp_risk_pct>0?`${fmt(capital.approved_scalp_risk_pct,3)}% equity`:"No new risk";
  document.getElementById("hero-open").textContent=`${liveCount} live · ${stagedCount} staged`;
  document.getElementById("hero-chains").textContent=cycle.running?"Running now":cycle.enabled&&Number.isFinite(Number(cycle.seconds_until_next_run))?age(cycle.seconds_until_next_run):"Not scheduled";
  const liveBadge=document.getElementById("overview-live-badge");liveBadge.textContent=connected&&permissionsOk?"SYSTEM LIVE":"ATTENTION";liveBadge.className="badge "+(connected&&permissionsOk?"ok":"bad");
  document.getElementById("balance").textContent=money(s.balance);
  document.getElementById("equity").textContent="Equity "+money(s.equity);
  const pl=s.strategy_floating_pl??s.floating_profit;
  const pel=document.getElementById("floating");pel.textContent=money(pl);pel.className="value "+(Number(pl)>0?"pos":Number(pl)<0?"neg":"");
  document.getElementById("drawdown").textContent=`Drawdown ${fmt(s.equity_drawdown_pct)}%`;
  document.getElementById("market-label").textContent=`Live market · ${text(s.symbol)}`;
  document.getElementById("market-price").textContent=`${text(s.bid)} / ${text(s.ask)}`;
  document.getElementById("market-spread").textContent=`Spread ${fmt(s.spread_points,1)} pts`;
  document.getElementById("protect-positions").textContent=text(s.strategy_open_positions??s.open_positions,0);
  document.getElementById("protect-recovery").textContent=text(s.active_hedge_chains,0);
  document.getElementById("protect-basket").textContent=`${fmt(s.basket_loss_pct)}%`;
  document.getElementById("protect-duplicate").textContent=s.runtime_enable_duplicate_distance_filter===false?"OFF":"ON";
  const riskUnits=state.riskUnits||{};
  document.getElementById("protect-risk-streak").textContent=`${text(riskUnits.consecutive_completed_loss_units,0)} completed unit${Number(riskUnits.consecutive_completed_loss_units||0)===1?"":"s"}`;
  const recoveryLedger=state.recoveryRisk||{};
  const lastRecoverySizing=recoveryLedger.last_recovery_sizing||{};
  const recoveryReason=text(lastRecoverySizing.reason||s.recovery_sizing_reason,"NOT EVALUATED");
  const recoveryFinalLot=Number(lastRecoverySizing.final_lot||s.recovery_final_lot||0);
  document.getElementById("protect-recovery-sizing").textContent=recoveryFinalLot>0?`${fmt(recoveryFinalLot,2)} lot · ${pretty(recoveryReason)}`:pretty(recoveryReason);
  document.getElementById("protect-unit-risk").textContent=Number(lastRecoverySizing.original_unit_risk_usd)>0?money(lastRecoverySizing.original_unit_risk_usd):"—";
  document.getElementById("protect-chain-ceiling").textContent=Number(lastRecoverySizing.chain_budget_usd)>0?`${money(lastRecoverySizing.chain_budget_usd)} · ${fmt(lastRecoverySizing.unit_budget_multiplier||0,2)}×`:"—";
  const portfolioAllocation=capital.portfolio_allocation||{};
  document.getElementById("protect-portfolio-reserved").textContent=money(portfolioAllocation.reserved_active_risk_amount||0);
  document.getElementById("protect-portfolio-available").textContent=money(portfolioAllocation.remaining_operating_risk_amount||0);
  const activeComposite=(riskUnits.units||[]).filter(u=>u.state==="ACTIVE"&&u.unit_type!=="STANDALONE_TRADE");
  const completedComposite=(riskUnits.units||[]).filter(u=>u.state==="COMPLETE"&&u.unit_type!=="STANDALONE_TRADE");
  const latestComposite=completedComposite.length?completedComposite[completedComposite.length-1]:null;
  document.getElementById("protect-composite-active").textContent=activeComposite.length?activeComposite.map(u=>pretty(u.unit_type)).join(" · "):"NONE";
  document.getElementById("protect-composite-latest").textContent=latestComposite?`${pretty(latestComposite.unit_type)} · ${latestComposite.result_class} · ${money(latestComposite.realized_net_pl)}`:"NONE";
  const chainBudget=Number(lastRecoverySizing.chain_budget_usd||s.recovery_chain_budget_usd||0);
  const activeLedgerChain=(recoveryLedger.active_chains||[])[0]||{};
  const budgetRemaining=Number(activeLedgerChain.hard_loss_budget_remaining_usd);
  const recoveryBudgetBasis=text(activeLedgerChain.budget_basis||lastRecoverySizing.budget_basis,"UNOBSERVED");
  document.getElementById("protect-recovery-copy").textContent=activeComposite.length
    ?`${activeComposite.length} composite risk unit${activeComposite.length===1?" is":"s are"} in flight. Member closes remain provisional. Recovery ceiling ${chainBudget>0?money(chainBudget):"unavailable"}${Number(lastRecoverySizing.original_unit_risk_usd)>0?` from ${money(lastRecoverySizing.original_unit_risk_usd)} original unit risk × ${fmt(lastRecoverySizing.unit_budget_multiplier||0,2)}`:""}${Number.isFinite(budgetRemaining)?` · ${money(budgetRemaining)} remaining`:""}. Budget basis: ${pretty(recoveryBudgetBasis)}. Portfolio ceiling remains ${money(recoveryLedger.portfolio_hard_risk_budget_usd||0)}. Last limiter: ${pretty(recoveryReason)}.`
    :`No composite risk unit is currently in flight. Completed loss streak is ${text(riskUnits.consecutive_completed_loss_units,0)} risk unit(s); recovery-chain and zone-campaign legs are scored only as their completed composite unit.`;
  const ack=state.ack;
  document.getElementById("ack-state").textContent=!connected?"OFFLINE":permissionsOk&&s.zone_directive_fresh!==false?"HEALTHY":"CHECK REQUIRED";
  document.getElementById("ack-state").className="value small "+(!connected||!permissionsOk?"neg":"pos");
  document.getElementById("ack-detail").textContent=permissionsOk?`Nyao connected · ${ack?.state||latestAckState()} acknowledgement`:"One or more MT5 trading permissions are disabled";

  // P3.23 dashboard: make execution ownership, structural context, hard capital
  // authority and Gemini's Nyao-policy authority visibly separate.
  const laneEl=document.getElementById("authority-lane");
  laneEl.textContent=executionLane;
  laneEl.className="authority-main "+(zoneAware?"lane-zone-aware":zoneMode?"lane-zone":"lane-normal");
  const laneBadge=document.getElementById("authority-lane-badge");
  laneBadge.textContent=zoneMode?"ZONE OWNS ENTRIES":zoneAware?"SCALP + ZONE CONTEXT":"SCALP OWNS ENTRIES";
  laneBadge.className="badge "+(zoneMode?"info":zoneAware?"warn":"ok");
  document.getElementById("authority-lane-copy").textContent=zoneMode
    ?"A broker-feasible zone campaign owns fresh-entry authority; ordinary scalp entries are suspended."
    :zoneAware
      ?`The ${side} zone remains read-only structural context. ${side} scalps may qualify; counter-zone scalps remain conditional: they require stronger evidence, reduced risk authority, and remain subject to campaign-proximity blocking.`
      :"Ordinary Nyao scalping owns fresh-entry authority. Zone analysis continues in the background.";
  document.getElementById("authority-scalp").textContent=zoneMode?"SUSPENDED":zoneAware?`${side} ALIGNED ONLY`:"ACTIVE";
  document.getElementById("authority-zone").textContent=zoneMode?"ACTIVE":activePlan?(Number(activePlan.entries?.length||0)>0?"ARMED / WAITING":"CONTEXT ONLY"):"MONITORING";

  const sourceZone=activePlan?.source_zone||{};
  const zoneScore=Number(sourceZone.score||0);
  const zoneLabel=activePlan?`${side} · ${text(sourceZone.timeframe,"—")} ${pretty(sourceZone.kind||"ZONE")}`:"NO PRIORITY ZONE";
  document.getElementById("context-zone").textContent=zoneLabel;
  const contextBadge=document.getElementById("context-zone-badge");
  contextBadge.textContent=activePlan?text(sourceZone.status||zp.state,"ZONE"):"SCANNING";
  contextBadge.className="badge "+(activePlan?"info":"warn");
  document.getElementById("context-zone-copy").textContent=activePlan
    ?`${fmt(sourceZone.low,3)} – ${fmt(sourceZone.high,3)}${zoneScore>0?` · score ${fmt(zoneScore,1)}`:""}. Gemini receives this as read-only scalp context.`
    :"No active priority-zone context is constraining the current scalp lane.";
  const htfStructure=text(state.zoneMap?.composite_bias,"NEUTRAL");
  const liveThesis=text(state.intelligence?.regime?.direction,"NEUTRAL");
  const normalizeDirection=value=>{const v=String(value||"").toUpperCase();return v.includes("BEAR")||v==="SELL"?"BEARISH":v.includes("BULL")||v==="BUY"?"BULLISH":v.includes("NEUTRAL")||v==="MIXED"?"NEUTRAL":v};
  const htfDir=normalizeDirection(htfStructure), liveDir=normalizeDirection(liveThesis);
  const thesisRelation=zoneAware?`${side} ZONE CONSTRAINT`:zoneMode?`${side} CAMPAIGN`:htfDir!=="NEUTRAL"&&liveDir!=="NEUTRAL"?(htfDir===liveDir?"ALIGNED":"CONFLICTING"):"NO CONFLICT SIGNAL";
  document.getElementById("context-bias").textContent=pretty(htfStructure);
  document.getElementById("context-alignment").textContent=thesisRelation;
  document.getElementById("context-zone-copy").textContent=activePlan
    ?`${fmt(sourceZone.low,3)} – ${fmt(sourceZone.high,3)}${zoneScore>0?` · score ${fmt(zoneScore,1)}`:""}. HTF structure ${pretty(htfStructure)}; live Atlas thesis ${pretty(liveThesis)}. Gemini receives the zone as read-only scalp context.`
    :`No priority-zone constraint. HTF structure is ${pretty(htfStructure)} while the live Atlas thesis is ${pretty(liveThesis)}${thesisRelation==="CONFLICTING"?" — directional layers currently disagree.":"."}`;

  const simulated=capital.demo_capital_simulation||{};
  const simActive=Boolean(simulated.active);
  const capitalPresent=Boolean(capital&&Object.keys(capital).length&&capital.version);
  const capitalExplicitVeto=capitalPresent&&capital.veto_new_risk===true;
  const capitalExplicitAllow=capitalPresent&&capital.veto_new_risk===false;
  const statusHasCapitalDecision=typeof s.capital_veto_new_risk==="boolean";
  const capitalMismatch=capitalPresent&&statusHasCapitalDecision&&Boolean(s.capital_veto_new_risk)!==Boolean(capital.veto_new_risk);
  const capitalSyncing=!capitalPresent||!capitalExplicitVeto&&!capitalExplicitAllow||capitalMismatch;
  const riskCapital=Number(capital.risk_capital||capital.real_risk_capital||s.equity||0);
  const regimeName=text(capital.capital_regime||capital.regime,"—");
  const vetoReasons=Array.isArray(capital.veto_reasons)?capital.veto_reasons:[];
  const allocation=capital.portfolio_allocation||{};
  const allocationState=text(allocation.allocation_state,"AVAILABLE");
  const preLossProtection=capital.loss_protection||{};
  const recoveryProbeInFlight=text(preLossProtection.state)==="RECOVERY_PROBE"&&Number(s.strategy_open_positions||0)>0;
  const fullyAllocated=allocationState==="FULLY_ALLOCATED";
  const partiallyAllocated=allocationState==="PARTIALLY_ALLOCATED";
  const capitalBadge=document.getElementById("capital-regime-badge");
  capitalBadge.textContent=capitalSyncing?"SYNCING":recoveryProbeInFlight?"RECOVERY PROBE · IN FLIGHT":fullyAllocated?"FULLY ALLOCATED":partiallyAllocated?"PARTIALLY ALLOCATED":capitalExplicitVeto?"CAPITAL VETO":simActive?`DEMO ${pretty(regimeName)}`:pretty(regimeName);
  capitalBadge.className="badge "+(capitalSyncing?"warn":recoveryProbeInFlight||partiallyAllocated?"info":fullyAllocated?"warn":capitalExplicitVeto?"bad":simActive?"warn":"ok");
  document.getElementById("capital-risk-base").textContent=money(riskCapital);
  const portfolioHard=Number(allocation.portfolio_hard_ceiling_amount||capital.maximum_total_strategy_risk_amount||0);
  const operatingCap=Number(allocation.operating_risk_ceiling_amount||portfolioHard);
  const reservedRisk=Number(allocation.reserved_active_risk_amount||0);
  const availableRisk=Number(allocation.remaining_operating_risk_amount||0);
  document.getElementById("capital-risk-copy").textContent=capitalSyncing
    ?"Capital state is reconciling across Nyao telemetry and Atlas sizing. Last complete budget is not treated as a fresh veto."
    :recoveryProbeInFlight
      ?"A reduced-risk recovery probe is in flight. Independent fresh risk remains intentionally paused until the composite probe resolves so the probe remains valid evidence; only the final composite chain result can break or escalate the loss streak."
      :capitalExplicitVeto
        ?`New risk is explicitly vetoed${vetoReasons.length?`: ${vetoReasons.map(pretty).join(" · ")}`:" by the capital governor."}`
        :partiallyAllocated
          ?`Concurrent allocator: ${money(reservedRisk)} reserved across active risk units · ${money(availableRisk)} operating capacity remains (${money(operatingCap)} operating / ${money(portfolioHard)} hard ceiling). Existing trades do not automatically block independent opportunities.`
          :simActive
            ?`Demo simulated risk capital; MT5 equity remains ${money(s.equity)}. Hard Atlas limits still apply.`
            :`Atlas risk capital · ${money(availableRisk||operatingCap)} operating capacity available · portfolio hard ceiling ${money(portfolioHard)}.`;
  const scalpAmount=Number(capital.approved_scalp_risk_amount||0), zoneAmount=Number(capital.approved_zone_risk_amount||0);
  const scalpPct=Number(capital.approved_scalp_risk_pct||0), zonePct=Number(capital.approved_zone_risk_pct||0);
  const lossProtection=capital.loss_protection||{};
  const protectionState=text(lossProtection.state,"INACTIVE");
  if(!capitalSyncing&&protectionState==="HARD_VETO"){
    const remaining=countdownAge(lossProtection.remaining_seconds||0);
    capitalBadge.textContent=`LOSS VETO · ${remaining}`;
    capitalBadge.className="badge bad";
    document.getElementById("capital-risk-copy").textContent=`${text(lossProtection.consecutive_losses,0)} consecutive losses · stage ${text(lossProtection.escalation_level,1)} of 3 · ${text(lossProtection.timeout_minutes,15)}m protection · recovery probe in ${remaining}. Historical losses do not escalate stages; only failed recovery probes do. Qualified Gemini consensus may bypass policy dwell, but not consensus/confidence/safety gates.`;
  }else if(!capitalSyncing&&protectionState==="RECOVERY_PROBE"){
    const release=lossProtection.policy_release||{};
    const adapted=lossProtection.release_reason==="MATERIAL_POLICY_RUNTIME_CONFIRMED";
    capitalBadge.textContent=adapted?"POLICY-ADAPTED RECOVERY":"RECOVERY PROBE";
    capitalBadge.className="badge warn";
    document.getElementById("capital-risk-copy").textContent=adapted
      ?`Epoch ${text(release.policy_epoch)} is runtime-confirmed after the latest loss and materially changed fresh-entry policy (${(release.material_controls||[]).map(pretty).join(", ")||"entry controls"}). The old loss timer was released; only a reduced ${fmt(lossProtection.recovery_probe_scalp_risk_pct||scalpPct,3)}% scalp probe is permitted. The ${text(lossProtection.consecutive_losses,0)} prior losses remain evidence; zone risk stays zero.`
      :`Loss-protection timer completed. Only a reduced ${fmt(lossProtection.recovery_probe_scalp_risk_pct||scalpPct,3)}% scalp probe is permitted; zone risk remains zero until the streak breaks.`;
  }
  document.getElementById("capital-scalp-budget").textContent=capitalSyncing?"SYNCING":capitalExplicitVeto?"0.000% · VETOED":scalpAmount>0?`${money(scalpAmount)} · ${fmt(scalpPct,3)}%`:`${fmt(scalpPct,3)}%`;
  document.getElementById("capital-zone-budget").textContent=capitalSyncing?"SYNCING":capitalExplicitVeto?"0.000% · VETOED":zoneAmount>0?`${money(zoneAmount)} · ${fmt(zonePct,3)}%`:`${fmt(zonePct,3)}%`;

  const auto=cycle.execution_mode==="AUTONOMOUS";
  const brainBadge=document.getElementById("brain-mode-badge");
  brainBadge.textContent=auto?"AUTONOMOUS NYAO POLICY":"SUPERVISED";
  brainBadge.className="badge "+(auto?"ok":"info");
  const brainLifecycle=text(auto?(cycle.last_auto_apply_status||p.lifecycle?.state||p.review_state):(p.lifecycle?.state||p.review_state||cycle.last_auto_apply_status),"NO CHANGE");
  const brainStateLabel=brainLifecycle==="MINIMUM_DWELL_ACTIVE"?"STABILITY HOLD":brainLifecycle==="CONSENSUS_NOT_READY"?"BUILDING CONSENSUS":brainLifecycle==="DEFERRED_ACTIVE_ZONE_PLAN"?"ACTIVATION DEFERRED":brainLifecycle==="APPLIED"?"POLICY ACTIVE":pretty(brainLifecycle);
  document.getElementById("brain-policy-state").textContent=brainStateLabel;
  document.getElementById("brain-policy-copy").textContent=zoneMode
    ?"Gemini can continue reasoning about Nyao policy, but a new policy waits for the live zone campaign boundary before activation."
    :zoneAware
      ?`Gemini is allowed to use the ${side} zone as scalp context while Atlas keeps zone construction and hard risk deterministic.`
      :"Gemini may optimize the full Nyao scalp lifecycle; Atlas retains zone, capital, broker-feasibility and hard-risk authority.";
  document.getElementById("brain-epoch").textContent=text(c.policy_epoch??s.policy_epoch);
  document.getElementById("brain-next").textContent=cycle.running?"RUNNING":cycle.enabled&&Number.isFinite(Number(cycle.seconds_until_next_run))?age(cycle.seconds_until_next_run):"NOT SCHEDULED";

  const campaignBadge=document.getElementById("overview-campaign-badge");
  if(activePlan&&zoneAware){
    const ideal=Array.isArray(activePlan.ideal_entries)?activePlan.ideal_entries:[], admitted=Array.isArray(activePlan.entries)?activePlan.entries:[];
    document.getElementById("overview-campaign-title").textContent=`${side} zone context → scalp fallback`;
    document.getElementById("overview-campaign-copy").textContent=`The technical zone remains valid context, but its executable campaign structure is ${admitted.length} leg${admitted.length===1?"":"s"}. Atlas returned fresh-entry authority to context-aware scalping: aligned entries use normal gates while counter-zone entries require stronger evidence and reduced risk.`;
    campaignBadge.textContent="ZONE-AWARE SCALP";campaignBadge.className="badge warn";
    const rows=(ideal.length?ideal:[{leg:1,entry_price:activePlan.source_zone?.low},{leg:2,entry_price:(Number(activePlan.source_zone?.low||0)+Number(activePlan.source_zone?.high||0))/2},{leg:3,entry_price:activePlan.source_zone?.high}]);
    document.getElementById("overview-campaign").innerHTML=rows.map((entry,index)=>`<div class="campaign-leg"><div class="row"><span class="label">IDEAL ENTRY ${entry.leg||index+1}</span><span class="badge ${index<admitted.length?"info":"bad"}">${index<admitted.length?"ADMITTED":"NOT EXECUTABLE"}</span></div><div class="campaign-price">${fmt(entry.entry_price,3)}</div><div class="muted">Zone geometry preserved · scalp fallback does not convert this into a zone order</div></div>`).join("");
  }else if(activePlan){
    const entries=Array.isArray(activePlan.entries)?activePlan.entries:[],targets=Array.isArray(activePlan.take_profits)?activePlan.take_profits:[];
    document.getElementById("overview-campaign-title").textContent=`${side} from ${text(activePlan.source_zone?.timeframe)} ${pretty(activePlan.source_zone?.kind||"ZONE")}`;
    document.getElementById("overview-campaign-copy").textContent=`Shared stop ${fmt(activePlan.stop_loss,3)} · total risk ${fmt(campaignRisk,3)}% · confirmation ${fmt(activePlan.confirmation?.zone_confirmation?.combined_score,1)} / ${fmt(activePlan.confirmation?.zone_confirmation?.threshold,1)}.`;
    campaignBadge.textContent=confirmed?"CONFIRMED":"WAITING";campaignBadge.className="badge "+(confirmed?"ok":"warn");
    document.getElementById("overview-campaign").innerHTML=entries.map((entry,index)=>{const live=index<liveCount,staged=!live&&index<liveCount+stagedCount,target=targets[index];return `<div class="campaign-leg ${live?"live":""}"><div class="row"><span class="label">ENTRY ${entry.leg}</span><span class="badge ${live?"ok":staged?"info":"warn"}">${live?"LIVE":staged?"STAGED":"PLANNED"}</span></div><div class="campaign-price">${fmt(entry.entry_price,3)}</div><div class="muted">${fmt(entry.risk_allocation_pct,0)}% of campaign risk${target?` · TP ${fmt(target.price,3)}`:""}</div></div>`}).join("");
  }else{
    document.getElementById("overview-campaign-title").textContent="No zone campaign active";
    document.getElementById("overview-campaign-copy").textContent="Atlas is monitoring the market and ordinary scalp gates remain authoritative.";
    campaignBadge.textContent="SCANNING";campaignBadge.className="badge info";
    document.getElementById("overview-campaign").innerHTML=[[`BUY signal`,fmt(s.buy_adjusted_score,2)],['SELL signal',fmt(s.sell_adjusted_score,2)],['Capital budget',capitalSyncing?'SYNCING':capitalExplicitVeto?'VETOED':`${fmt(capital.approved_scalp_risk_pct,3)}%`]].map(([label,value])=>`<div class="campaign-leg"><div class="label">${label}</div><div class="campaign-price">${value}</div><div class="muted">Live Atlas gate</div></div>`).join("");
  }

  let attentionTitle="No action needed",attentionCopy="Atlas is operating inside its current authority.";
  if(!connected){attentionTitle="Reconnect Nyao";attentionCopy="Live state is unavailable, so Atlas cannot supervise execution."}
  else if(!permissionsOk){attentionTitle="Enable MT5 trading";attentionCopy="At least one terminal, EA, or account trading permission is disabled."}
  else if(p.lifecycle?.state==="READY_FOR_HUMAN_REVIEW"&&cycle.execution_mode!=="AUTONOMOUS"){attentionTitle="Policy review available";attentionCopy="Atlas has prepared a supervised policy change for your review."}
  else if(zoneAware){attentionTitle="Zone-aware scalping active";attentionCopy=`The full ${side} zone campaign is not executable, so Atlas released the scalp lane while keeping ${side} zone context. Normal scalp thresholds and risk gates still apply.`}
  else if(zoneMode&&!confirmed){attentionTitle="Atlas is waiting";attentionCopy="Price is in a feasible zone campaign, but confirmation has not qualified. Ordinary scalping remains suspended while the zone lane owns fresh-entry authority."}
  document.getElementById("overview-attention-title").textContent=attentionTitle;
  document.getElementById("overview-attention-copy").textContent=attentionCopy;
  document.getElementById("overview-decision-list").innerHTML=[
    permissionsOk?"MT5 execution permissions are available":"MT5 execution permissions need attention",
    zoneMode?`${liveCount} live and ${stagedCount} staged zone entries`:capitalSyncing?"Scalp capital state is syncing":`Scalp capital gate ${capitalExplicitVeto?"is closed":"is available"}`,
    cycle.enabled?`Atlas Brain reviews every ${text(cycle.interval_minutes)} minutes`:"Scheduled Brain reviews are disabled"
  ].map(item=>`<div class="decision-item">${esc(item)}</div>`).join("");
  renderProposalChanges("overview-changes",p.changed_controls);
  const pb=document.getElementById("proposal-badge");pb.textContent=p.lifecycle?.state||p.review_state||"NO PROPOSAL";pb.className="badge "+badgeClass(pb.textContent);
  const lifecycle=p.lifecycle?.state;
  document.getElementById("overview-proposal-note").textContent=!p.proposal_id
    ? "No proposal loaded."
    : lifecycle==="APPLIED"
      ? `Applied to command ${text(c.command_version)} / policy epoch ${text(c.policy_epoch)} and confirmed by Nyao.`
      : lifecycle==="AUTO_APPLY_DEFERRED_ZONE"
        ? `Queued for automatic activation after the active zone campaign reaches a clean mode boundary. Current policy remains epoch ${text(c.policy_epoch)}; proposed epoch ${text(p.proposed_policy_epoch)} is not applied yet.`
      : lifecycle==="AWAITING_NYAO_ACK"
        ? `Command written for policy epoch ${text(p.proposed_policy_epoch)}; awaiting Nyao acknowledgement.`
        : `${p.selected_candidate||"Candidate"} · proposed epoch ${text(p.proposed_policy_epoch)} · ${Object.keys(p.changed_controls||{}).length} material change(s).`;
}
function renderLiveAnalysis(){
  const s=state.status||{}, i=state.intelligence||{}, regime=i.regime||{}, risk=i.risk||i.risk_governor||{};
  const direction=String(regime.direction||"").toUpperCase();
  const bias=document.getElementById("signal-bias");
  let bt="NEUTRAL / UNCLEAR", bc="bias-neutral";
  if(direction.includes("BULL")){bt="BULLISH";bc="bias-bull"}else if(direction.includes("BEAR")){bt="BEARISH";bc="bias-bear"}else if(direction){bt=pretty(direction)}
  bias.textContent=bt; bias.className="bias-value "+bc;
  document.getElementById("signal-regime").textContent=pretty(regime.regime||"UNKNOWN");
  document.getElementById("signal-volatility").textContent=pretty(regime.volatility||"UNKNOWN");
  document.getElementById("signal-confidence").textContent=i.confidence==null?"—":fmt(i.confidence,1)+"%";
  document.getElementById("signal-risk").textContent=pretty(risk.state||currentRisk());
  document.getElementById("signal-summary").textContent=i.summary||((regime.reasons||[])[0])||"Atlas intelligence has not produced a current assessment yet.";

  const contextBanner=document.getElementById("scalp-context-banner");
  const contextTitle=document.getElementById("scalp-context-title");
  const contextCopy=document.getElementById("scalp-context-copy");
  const livePlan=state.zonePlan||{};
  const liveActivePlan=livePlan.zone_plan||{};
  const plannedZoneAware=Boolean(livePlan.zone_aware_scalping_active);
  const appliedZoneAware=Boolean(
    s.zone_aware_scalping_active ||
    (
      s.zone_directive_fresh!==false &&
      !s.zone_scalp_suspended &&
      ["ZONE_AWARE_SCALP","ZONE_CAPITAL_INFEASIBLE"].includes(String(s.zone_directive_state||"").toUpperCase())
    )
  );
  const contextSide=String(
    s.zone_side ||
    livePlan.zone_aware_scalping_side ||
    liveActivePlan.side ||
    "NONE"
  ).toUpperCase();

  if(contextBanner){
    contextBanner.style.display=(plannedZoneAware||appliedZoneAware)?"block":"none";

    if(appliedZoneAware && ["BUY","SELL"].includes(contextSide)){
      const pressure=Math.max(
        Number(s.zone_confirmation_threshold||0)>0
          ? Number(s.zone_confirmation_score||0)/Number(s.zone_confirmation_threshold) : 0,
        Number(s.zone_minimum_directional_score||0)>0
          ? Number(s.zone_directional_score||0)/Number(s.zone_minimum_directional_score) : 0
      );
      contextTitle.textContent=`${contextSide} ZONE CONTEXT · LIVE IN NYAO`;
      contextCopy.textContent=`Context-aware scalping is applied. ${contextSide} entries are zone-aligned and use normal gates. ${contextSide==="SELL"?"BUY":"SELL"} entries are counter-zone: stronger evidence, reduced risk, and campaign-proximity blocking apply. Commit pressure ${fmt(Math.min(1,Math.max(0,pressure))*100,0)}%.`;
    }else if(plannedZoneAware){
      contextTitle.textContent=`${contextSide} ZONE CONTEXT · AWAITING NYAO SYNC`;
      contextCopy.textContent=`Atlas has planned zone-aware scalping, but Nyao has not yet confirmed that its scalp lane is released. Applied directive: ${pretty(s.zone_directive_state||"UNKNOWN")} · scalp suspended ${s.zone_scalp_suspended?"YES":"NO"}.`;
    }
  }

  const buy=Number(s.buy_score||0), sell=Number(s.sell_score||0);
  const buyAdj=Number(s.buy_adjusted_score||0), sellAdj=Number(s.sell_adjusted_score||0);
  const buyTh=Number(s.buy_effective_threshold??s.runtime_min_buy_signal_score??0), sellTh=Number(s.sell_effective_threshold??s.runtime_min_sell_signal_score??0);
  document.getElementById("signal-buy-score").textContent=buy.toFixed(2);
  document.getElementById("signal-sell-score").textContent=sell.toFixed(2);
  // Net signal penalties can mathematically push a score below zero. Zero is
  // the executable floor, so display that floor and preserve the raw penalty
  // value in the blocker explanation instead of showing contradictory scores.
  document.getElementById("signal-buy-adjusted").textContent=Math.max(0,buyAdj).toFixed(2);
  document.getElementById("signal-sell-adjusted").textContent=Math.max(0,sellAdj).toFixed(2);
  document.getElementById("signal-buy-threshold").textContent=buyTh.toFixed(2);
  document.getElementById("signal-sell-threshold").textContent=sellTh.toFixed(2);
  document.getElementById("signal-buy-bar").style.width=(buyTh>0?Math.min(100,Math.max(0,buy/buyTh*100)):0)+"%";
  document.getElementById("signal-sell-bar").style.width=(sellTh>0?Math.min(100,Math.max(0,sell/sellTh*100)):0)+"%";

  const orderReason=(side,reason)=>{
    const code=Number(s.last_order_retcode||0), direction=String(s.last_order_direction||"").toLowerCase();
    if(direction!==side || !String(reason||"").includes("ORDER"))return pretty(text(reason,"NONE"));
    const descriptions={10026:"Algo trading disabled by broker/server",10027:"Algo trading disabled in MT5 terminal",10018:"Market closed",10019:"Insufficient funds",10030:"Unsupported order filling mode",10016:"Invalid stops"};
    const reasonMap={
      ATLAS_ZONE_MODE:"ZONE CAMPAIGN OWNS FRESH ENTRIES",
      ZONE_CONTEXT_COUNTER_DIRECTION:"COUNTER-ZONE DIRECTION BLOCKED (LEGACY 44.4)",
      COUNTER_ZONE_EVIDENCE_INSUFFICIENT:"COUNTER-ZONE · STRONGER EVIDENCE REQUIRED",
      COUNTER_ZONE_COMMIT_PROXIMITY:"COUNTER-ZONE · ZONE CAMPAIGN NEAR COMMIT",
      COUNTER_ZONE_SIGNAL_READY:"COUNTER-ZONE · QUALIFIED",
      ZONE_CONTEXT_ALIGNED:"ZONE-ALIGNED SCALP"
    };
    const raw=String(reason||"NONE").toUpperCase();
    if(reasonMap[raw])return reasonMap[raw];
    return descriptions[code]?`${descriptions[code]} (MT5 ${code})`:`${pretty(text(reason,"NONE"))}${code?` (MT5 ${code})`:""}`;
  };
  [["buy",Boolean(s.buy_entry_eligible),s.buy_block_reason],["sell",Boolean(s.sell_entry_eligible),s.sell_block_reason]].forEach(([side,ready,reason])=>{
    const el=document.getElementById(`signal-${side}-state`);
    el.textContent=ready?"READY":"BLOCKED"; el.className="badge "+(ready?"ok":"bad");
    const adjusted=side==="buy"?buyAdj:sellAdj;
    const penaltyNote=adjusted<0?` · post-penalty score ${adjusted.toFixed(2)}, executable floor 0.00`:"";
    document.getElementById(`signal-${side}-reason`).textContent=orderReason(side,reason)+penaltyNote;
  });

  let block=String(s.last_global_block_reason||"NONE").toUpperCase();
  const capital=state.zonePlan?.capital_sizing||{};
  const capitalHardVeto=capital.veto_new_risk===true || s.capital_veto_new_risk===true;
  const recoveryProbe=String(capital.loss_protection?.state||"").toUpperCase()==="RECOVERY_PROBE";
  if(s.terminal_algo_trading_allowed===false)block="MT5_ALGO_TRADING_DISABLED";
  else if(s.ea_trading_allowed===false)block="EA_LIVE_TRADING_DISABLED";
  else if(s.account_trade_allowed===false||s.account_expert_trading_allowed===false)block="ACCOUNT_ALGO_TRADING_DISABLED";
  else if(capitalHardVeto)block="ATLAS_CAPITAL_RISK_VETO";
  const clear=block==="NONE"||block==="CLEAR";
  const g=document.getElementById("signal-global-status");
  g.textContent=capitalHardVeto?"CAPITAL PROTECTION ACTIVE":recoveryProbe?"RECOVERY PROBE ARMED":clear?"ENTRY SYSTEM CLEAR":"ENTRY SYSTEM BLOCKED";
  g.className="badge "+(capitalHardVeto?"bad":recoveryProbe?"warn":clear?"ok":"bad");
  document.getElementById("signal-global-block").textContent=pretty(block);
  document.getElementById("signal-newbar").textContent=s.new_bar_entry_only?(s.new_bar_ready?"READY":"WAITING"):"INTRABAR";
  document.getElementById("signal-cooldown").textContent=s.cooldown_active?"ACTIVE":"INACTIVE";
  document.getElementById("signal-spread").textContent=s.spread_within_limit===false?"BLOCKED":s.spread_within_limit===true?"CLEAR":"—";
}

function renderZoneChart(zoneMap,livePrice=null){
  const svg=document.getElementById("an-zone-chart");if(!svg)return;
  const bars=Array.isArray(zoneMap?.chart?.bars)?zoneMap.chart.bars:[];
  if(!bars.length){
    svg.innerHTML=`<rect width="1200" height="520" fill="rgba(5,9,16,.25)"/><text x="600" y="250" text-anchor="middle" fill="#94a3b8" font-size="18">Waiting for validated M30 candles and a detected zone map</text><text x="600" y="280" text-anchor="middle" fill="#64748b" font-size="13">Atlas will render closed candles and prioritized multi-timeframe zones here.</text>`;
    return;
  }

  const width=1200,height=520,margin={left:20,right:150,top:20,bottom:44};
  const plotWidth=width-margin.left-margin.right,plotHeight=height-margin.top-margin.bottom;
  const barLow=Math.min(...bars.map(bar=>Number(bar.low)));
  const barHigh=Math.max(...bars.map(bar=>Number(bar.high)));
  const baseRange=Math.max(barHigh-barLow,Math.abs(barHigh)*0.001,1);
  const allZones=Array.isArray(zoneMap.zones)?zoneMap.zones:[];
  const current=Number(livePrice||zoneMap.current_price||bars[bars.length-1].close);
  const distance=zone=>current<Number(zone.low)?Number(zone.low)-current:current>Number(zone.high)?current-Number(zone.high):0;
  const nearby=allZones.filter(zone=>Number(zone.high)>=barLow-baseRange*.35&&Number(zone.low)<=barHigh+baseRange*.35);
  let visibleZones=["DEMAND","SUPPLY"].flatMap(side=>nearby.filter(zone=>zone.side===side).sort((a,b)=>distance(a)-distance(b)||Number(b.score)-Number(a.score)).slice(0,2));
  [zoneMap.nearest_demand,zoneMap.nearest_supply].filter(Boolean).forEach(zone=>{if(!visibleZones.some(item=>item.zone_id===zone.zone_id))visibleZones.push(zone)});
  visibleZones=visibleZones.sort((a,b)=>distance(a)-distance(b)||Number(b.score)-Number(a.score)).slice(0,4);
  const rawMin=Math.min(barLow,...visibleZones.map(zone=>Number(zone.low)));
  const rawMax=Math.max(barHigh,...visibleZones.map(zone=>Number(zone.high)));
  const scaleRange=Math.max(rawMax-rawMin,1),priceMin=rawMin-scaleRange*.055,priceMax=rawMax+scaleRange*.055;
  const y=price=>margin.top+(priceMax-Number(price))/(priceMax-priceMin)*plotHeight;
  const step=plotWidth/bars.length,candleWidth=Math.max(2,Math.min(9,step*.62));
  const parts=[`<rect x="0" y="0" width="${width}" height="${height}" fill="rgba(5,9,16,.22)"/>`];

  for(let index=0;index<=6;index++){
    const price=priceMax-(priceMax-priceMin)*index/6,py=y(price);
    parts.push(`<line x1="${margin.left}" y1="${py}" x2="${margin.left+plotWidth}" y2="${py}" stroke="rgba(148,163,184,.13)" stroke-width="1"/>`);
    parts.push(`<text x="${margin.left+plotWidth+10}" y="${py+4}" fill="#7f8da3" font-size="11">${fmt(price,2)}</text>`);
  }

  const zoneVisuals=[];
  visibleZones.forEach(zone=>{
    const highY=y(zone.high),lowY=y(zone.low),zoneHeight=Math.max(3,lowY-highY);
    const demand=zone.side==="DEMAND",fill=demand?"rgba(74,222,128,.14)":"rgba(251,113,133,.13)",stroke=demand?"rgba(74,222,128,.62)":"rgba(251,113,133,.62)";
    const label=`${zone.side} · ${zone.timeframe} ${pretty(zone.kind)} · ${fmt(zone.low,2)}–${fmt(zone.high,2)}`;
    zoneVisuals.push({zone,highY,lowY,demand,stroke,label,desiredY:(highY+lowY)/2});
    parts.push(`<g><title>${esc(label)} · score ${fmt(zone.score,1)}</title><rect x="${margin.left}" y="${highY}" width="${plotWidth}" height="${zoneHeight}" fill="${fill}" stroke="${stroke}" stroke-width="1" stroke-dasharray="5 4"/></g>`);
  });

  bars.forEach((bar,index)=>{
    const x=margin.left+step*(index+.5),openY=y(bar.open),closeY=y(bar.close),highY=y(bar.high),lowY=y(bar.low);
    const bullish=Number(bar.close)>=Number(bar.open),color=bullish?"#4ade80":"#fb7185";
    parts.push(`<line x1="${x}" y1="${highY}" x2="${x}" y2="${lowY}" stroke="${color}" stroke-width="1" opacity=".88"/>`);
    parts.push(`<rect x="${x-candleWidth/2}" y="${Math.min(openY,closeY)}" width="${candleWidth}" height="${Math.max(1.5,Math.abs(closeY-openY))}" fill="${color}" opacity=".94"/>`);
  });

  let lastLabelY=margin.top+5;
  zoneVisuals.sort((a,b)=>a.desiredY-b.desiredY).forEach(item=>{
    const labelY=Math.min(margin.top+plotHeight-4,Math.max(item.desiredY,lastLabelY+18));
    lastLabelY=labelY;
    const shortKind=item.zone.kind==="ORDER_BLOCK"?"OB":item.zone.kind==="SUPPORT_RESISTANCE"?"S/R":"FVG";
    const shortLabel=`${item.zone.timeframe} ${shortKind} · ${item.zone.side}`;
    parts.push(`<line x1="${margin.left+205}" y1="${labelY-4}" x2="${margin.left+222}" y2="${item.desiredY}" stroke="${item.stroke}" stroke-width="1" opacity=".7"/>`);
    parts.push(`<rect x="${margin.left+4}" y="${labelY-15}" width="202" height="17" rx="4" fill="rgba(5,9,16,.78)" stroke="${item.stroke}" stroke-width=".6"/>`);
    parts.push(`<text x="${margin.left+10}" y="${labelY-4}" fill="${item.demand?"#86efac":"#fda4af"}" font-size="9" font-weight="700">${esc(shortLabel)}</text>`);
  });

  const currentY=y(current);
  parts.push(`<line x1="${margin.left}" y1="${currentY}" x2="${margin.left+plotWidth}" y2="${currentY}" stroke="#60a5fa" stroke-width="1.4" stroke-dasharray="7 5"/>`);
  parts.push(`<rect x="${margin.left+plotWidth+5}" y="${currentY-11}" width="106" height="22" rx="5" fill="#2563eb"/><text x="${margin.left+plotWidth+12}" y="${currentY+4}" fill="white" font-size="11" font-weight="700">${fmt(current,3)}</text>`);
  parts.push(`<text x="${margin.left+8}" y="${margin.top+17}" fill="#dbeafe" font-size="13" font-weight="700">${esc(text(zoneMap.symbol))} · M30 · ${esc(pretty(zoneMap.composite_bias))} STRUCTURE</text>`);

  [0,Math.floor((bars.length-1)/4),Math.floor((bars.length-1)/2),Math.floor((bars.length-1)*3/4),bars.length-1].forEach((index,labelIndex)=>{
    const x=margin.left+step*(index+.5),date=new Date(Number(bars[index].time_epoch)*1000);
    const label=date.toLocaleString([],{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"});
    const anchor=labelIndex===0?"start":labelIndex===4?"end":"middle";
    parts.push(`<text x="${x}" y="${height-14}" text-anchor="${anchor}" fill="#7f8da3" font-size="10">${esc(label)}</text>`);
  });
  const hidden=Math.max(0,allZones.length-visibleZones.length);
  if(hidden)parts.push(`<text x="${margin.left+plotWidth-4}" y="${margin.top+17}" text-anchor="end" fill="#94a3b8" font-size="10">${hidden} farther zone${hidden===1?"":"s"} listed below</text>`);
  svg.innerHTML=parts.join("");
}

function renderAnalysis(){
  const s=state.status||{}, i=state.intelligence||{}, p=state.proposal||{}, r=state.responsiveness||{};
  const regime=i.regime||{}, risk=i.risk||i.risk_governor||{};
  const direction=String(regime.direction||"NEUTRAL").toUpperCase();
  const bias=direction.includes("BULL")?"BULLISH":direction.includes("BEAR")?"BEARISH":"NEUTRAL";
  document.getElementById("an-bias").textContent=bias;
  document.getElementById("an-bias").className="value small "+(bias==="BULLISH"?"pos":bias==="BEARISH"?"neg":"");
  document.getElementById("an-regime").textContent=pretty(regime.regime||"UNKNOWN");
  document.getElementById("an-volatility").textContent=pretty(regime.volatility||"UNKNOWN");
  document.getElementById("an-vol-ratio").textContent=`Ratio ${fmt(s.volatility_ratio,2)} · ATR ${fmt(s.current_atr,3)}`;
  document.getElementById("an-fit").textContent=pretty(i.fit||"UNKNOWN");
  document.getElementById("an-confidence").textContent=i.confidence==null?"Confidence —":`Confidence ${fmt(i.confidence,1)}%`;
  document.getElementById("an-risk").textContent=pretty(risk.state||currentRisk());
  document.getElementById("an-responsiveness").textContent=`Responsiveness ${text(r.profile)}`;
  document.getElementById("an-thesis").textContent=i.summary||"Atlas has not produced a current market thesis.";
  const reasons=[...(regime.reasons||[]),...(i.recommendations||[]),...(i.cautions||[])].slice(0,8);
  document.getElementById("an-reasons").innerHTML=reasons.map((x,index)=>`<div class="analysis-item ${index<2?"info":""}">${esc(text(typeof x==="string"?x:x?.message||x?.reason||JSON.stringify(x)))}</div>`).join("")||`<div class="analysis-item">No supporting reasons returned yet.</div>`;

  const spreadPrice=Math.abs(Number(s.ask||0)-Number(s.bid||0));
  const spreadPoints=Number(s.spread_points||0);
  const point=Number(s.symbol_point||((spreadPrice>0&&spreadPoints>0)?spreadPrice/spreadPoints:0));
  const spreadCapPoints=Number(s.effective_spread_cap_points||0);
  const spreadCapPrice=spreadCapPoints>0&&point>0?spreadCapPoints*point:0;
  const costRatio=spreadCapPrice>0?spreadPrice/spreadCapPrice:null;
  const gateBasis=text(s.scalp_cost_gate_basis,"UNKNOWN");
  const costLimiter=text(s.scalp_cost_limiting_factor,"NONE");
  const costAdjusted=Boolean(s.scalp_cost_adjusted);
  const costFeasible=s.scalp_cost_feasible!==false;
  const baseStopPoints=Number(s.scalp_base_stop_points||0);
  const baseTargetPoints=Number(s.scalp_base_target_points||0);
  const plannedStopPoints=Number(s.scalp_planned_stop_points||0);
  const plannedTargetPoints=Number(s.scalp_planned_target_points||0);
  const baseStop=baseStopPoints>0&&point>0?baseStopPoints*point:null;
  const baseTarget=baseTargetPoints>0&&point>0?baseTargetPoints*point:null;
  const plannedStop=plannedStopPoints>0&&point>0?plannedStopPoints*point:null;
  const plannedTarget=plannedTargetPoints>0&&point>0?plannedTargetPoints*point:null;
  const spreadToStop=Number(s.scalp_spread_to_stop_ratio||0);
  const spreadToTarget=Number(s.scalp_spread_to_target_ratio||0);
  const maxStopRatio=Number(s.scalp_max_spread_stop_ratio||0.20);
  const maxTargetRatio=Number(s.scalp_max_spread_target_ratio||0.15);
  const costRatioFeasible=s.scalp_cost_ratio_feasible!==false;
  const structureFeasible=s.scalp_structure_feasible!==false;
  const structureReason=text(s.scalp_structure_reason,"UNKNOWN");
  const stopExpansion=Number(s.scalp_stop_expansion_ratio||1);
  const targetExpansion=Number(s.scalp_target_expansion_ratio||1);
  const stopAtrRatio=Number(s.scalp_planned_stop_atr_ratio||0);
  const spreadAtrRatio=Number(s.scalp_spread_atr_ratio||0);
  const maxExpansion=Number(s.scalp_max_stop_expansion_ratio||0);
  const maxStopAtr=Number(s.scalp_max_stop_atr_ratio||0);
  const maxSpreadAtr=Number(s.scalp_max_spread_atr_ratio||0);
  let costState="INSUFFICIENT DATA", costClass="warn", costNote="Nyao needs a valid economic spread cap before judging scalp transaction cost.";
  if(costRatio!==null){
    if(costRatioFeasible && !structureFeasible){
      costState="STRUCTURE MISMATCH";costClass="bad";
      costNote=`Transaction-cost ratios can be made viable, but doing so would distort the scalp beyond its market-structure envelope (${pretty(structureReason)}). Stop expansion ${fmt(stopExpansion,1)}× / max ${fmt(maxExpansion,1)}× · planned stop ${fmt(stopAtrRatio,1)} ATR / max ${fmt(maxStopAtr,1)} · spread ${fmt(spreadAtrRatio,1)} ATR / max ${fmt(maxSpreadAtr,1)}. Atlas waits for a larger genuine market opportunity rather than manufacturing a huge stop around the spread.`;
    }else if(!costFeasible || !costRatioFeasible || costRatio>1){
      costState="COST BLOCKED";costClass="bad";
      costNote=`Spread ${fmt(spreadPrice,3)} cannot be supported by the current scalp economics. ${plannedStop!=null?`Planned stop ${fmt(plannedStop,3)} (${fmt(spreadToStop*100,1)}% spread/stop; max ${fmt(maxStopRatio*100,0)}%) and target ${fmt(plannedTarget,3)} (${fmt(spreadToTarget*100,1)}% spread/target; max ${fmt(maxTargetRatio*100,0)}%). `:""}Basis ${pretty(gateBasis)} · limiter ${pretty(costLimiter)}.`;
    }else if(costRatio>=0.8){
      costState="COST NEAR LIMIT";costClass="warn";
      costNote=`Spread is ${fmt(costRatio*100,1)}% of the allowed economic cap. The trade can pass cost preflight, but there is little cost headroom.`;
    }else{
      costState=costAdjusted?"COST-ADAPTED VIABLE":"COST VIABLE";costClass="ok";
      costNote=`Spread uses ${fmt(costRatio*100,1)}% of the economic cap. ${costAdjusted&&baseStop!=null?`Nyao adapted stop ${fmt(baseStop,3)} → ${fmt(plannedStop,3)} and target ${fmt(baseTarget,3)} → ${fmt(plannedTarget,3)} before capital sizing. `:""}${plannedStop!=null?`Spread/stop ${fmt(spreadToStop*100,1)}% and spread/target ${fmt(spreadToTarget*100,1)}%. `:""}Structure ${fmt(stopExpansion,1)}× base stop · ${fmt(stopAtrRatio,1)} ATR stop · ${fmt(spreadAtrRatio,1)} ATR spread. Limiter ${pretty(costLimiter)}. Final preflight rechecks market structure, executable geometry and Atlas risk budget immediately before OrderSend.`;
    }
  }
  const costBadge=document.getElementById("an-cost-badge");costBadge.textContent=costState;costBadge.className="badge "+costClass;
  document.getElementById("an-spread-price").textContent=spreadPrice?fmt(spreadPrice,3):"—";
  document.getElementById("an-atr").textContent=spreadCapPrice?fmt(spreadCapPrice,3):"—";
  document.getElementById("an-spread-atr").textContent=costRatio===null?"—":`${fmt(costRatio,2)}×`;
  document.getElementById("an-eligible").textContent=r.entry_observations?.eligible_rate_pct==null?"—":`${fmt(r.entry_observations.eligible_rate_pct,1)}%`;
  document.getElementById("an-cost-note").textContent=costNote;

  const candles=state.candles||{}, candleReady=Boolean(candles.ready_for_zone_analysis);
  const zoneMap=state.zoneMap||{}, zonesDetected=zoneMap.state==="DETECTED_NOT_ACTIVATED";
  const zonePlan=state.zonePlan||{}, activePlan=zonePlan.zone_plan||null;
  const capital=zonePlan.capital_sizing||{};
  const liveBid=Number(s.bid),liveAsk=Number(s.ask);
  const liveChartPrice=liveBid>0?liveBid:liveAsk>0?liveAsk:Number(zoneMap.current_price||0);
  const zoneExecutorInstalled=Boolean(s.zone_execution_supported),zoneExecutorEnabled=Boolean(s.zone_execution_enabled);
  const analysisZoneAwarePlanned=Boolean(zonePlan?.zone_aware_scalping_active);
  const analysisZoneAware=Boolean(
    s.zone_aware_scalping_active ||
    (
      s.zone_directive_fresh!==false &&
      !s.zone_scalp_suspended &&
      ["ZONE_AWARE_SCALP","ZONE_CAPITAL_INFEASIBLE"].includes(String(s.zone_directive_state||"").toUpperCase())
    )
  );
  const zoneModeLive=Boolean(s.zone_mode_active&&!analysisZoneAware);
  const candleState=text(candles.state,"WAITING_FOR_NYAO_EXPORT");
  const zoneBadge=document.getElementById("an-zone-status");
  zoneBadge.textContent=zonesDetected?"ZONE MAP DETECTED":candleReady?"CANDLES VALIDATED":pretty(candleState);
  zoneBadge.className="badge "+(zonesDetected||candleReady?"ok":candleState==="INVALID"?"bad":"warn");
  const stageCandles=document.getElementById("an-stage-candles");
  stageCandles.textContent=candleReady?"READY":candleState==="INVALID"?"INVALID":"WAITING";
  stageCandles.className="value small "+(candleReady?"pos":candleState==="INVALID"?"neg":"");
  const stageZone=document.getElementById("an-stage-zone-engine");
  stageZone.textContent=zonesDetected?"READY":candleReady?"NEXT":"PENDING";
  stageZone.className="value small "+(zonesDetected?"pos":candleReady?"":"muted");
  document.getElementById("an-zone-title").textContent=zonesDetected
    ? `${text(zoneMap.symbol)} deterministic daily zone map`
    : candleReady
      ? "Candle foundation ready; no approved zone map yet"
    : "No approved internal zone map yet";
  const candleMessages=[...(candles.blockers||[]),...(candles.warnings||[])];
  document.getElementById("an-candle-detail").textContent=zonesDetected
    ? `${text(zoneMap.zone_count,0)} active zones · ${text(zoneMap.invalidated_zone_count,0)} invalidated archived · ${pretty(zoneMap.composite_bias)} composite structure · map ${text(zoneMap.map_id)}. ${zoneModeLive?`${pretty(s.zone_side||"ZONE")} zone execution is currently active in Nyao.`:"The map is available; execution authority activates only when a qualified zone campaign is live."}`
    : candleReady
      ? `Validated closed M30/H1/H4 history for ${text(candles.symbol)}. Export age ${age(candles.export_age_seconds)}. The deterministic zone engine is now the next authority layer.`
    : candleMessages[0]||"Atlas is waiting for Nyao's validated, closed-bar multi-timeframe export. It will not invent price zones from live ticks alone.";
  document.getElementById("an-zone-stats").innerHTML=zonesDetected?[
    ["Map version",zoneMap.map_id],
    ["Live MT5 bid",liveBid>0?fmt(liveBid,3):"—"],
    ["Live MT5 ask",liveAsk>0?fmt(liveAsk,3):"—"],
    ["Closed M30 reference",fmt(zoneMap.current_price,3)]
  ].map(([label,value],index)=>`<div class="kpi"><div class="label">${esc(label)}</div><div class="value small ${index===3?"neg":""}">${esc(text(value))}</div></div>`).join(""):"";
  const zoneRows=Array.isArray(zoneMap.zones)?zoneMap.zones:[];
  const gateStage=document.getElementById("an-stage-zone-gate");
  gateStage.textContent=zoneModeLive?"ZONE MODE LIVE":zoneExecutorInstalled&&zoneExecutorEnabled?"READY":zoneExecutorInstalled?"DISABLED":"INSTALL BUILD";
  gateStage.className="value small "+(zoneModeLive||zoneExecutorInstalled&&zoneExecutorEnabled?"pos":zoneExecutorInstalled?"neg":"muted");
  const zoneExecution=document.getElementById("an-zone-execution");
  if(activePlan){
    const entries=Array.isArray(activePlan.entries)?activePlan.entries:[], targets=Array.isArray(activePlan.take_profits)?activePlan.take_profits:[],zc=activePlan.confirmation?.zone_confirmation||{};
    const quoteLabel=zonePlan.price_basis==="BID_SELL_EXECUTION"?"live bid":zonePlan.price_basis==="ASK_BUY_EXECUTION"?"live ask":pretty(zonePlan.price_basis||"execution quote");
  const zoneSpread=activePlan.confirmation?.spread_assessment||{};
  const sourceInvalidated=Boolean(zonePlan.source_zone_invalidated||zonePlan.campaign_lock?.source_zone_invalidated);
  const zoneLifecycleLabel=sourceInvalidated?"INVALIDATED · MANAGEMENT ONLY":(zonePlan.zone_aware_scalping_active?"ZONE-AWARE SCALP":"ZONE CAMPAIGN");
  zoneExecution.innerHTML=`<div class="zone-plan ${sourceInvalidated?"invalidated":""}"><div class="zone-plan-head"><div><div class="label">ATLAS MODE DIRECTIVE · ${esc(text(activePlan.plan_id))}</div><div class="zone-price" style="margin-top:5px">${esc(activePlan.side)} ${esc(zoneLifecycleLabel)} · ${sourceInvalidated?"source thesis failed; new campaign layers disabled while existing exposure remains managed":zonePlan.zone_aware_scalping_active?"zone context retained; ordinary scalp engine released":"ordinary scalping suspended"}</div><div class="muted" style="margin-top:5px">${esc(quoteLabel)} ${fmt(zonePlan.live_price,3)} is inside ${esc(activePlan.source_zone?.timeframe||"")} ${esc(pretty(activePlan.source_zone?.kind||"ZONE"))}. MT5 bid ${fmt(zonePlan.live_bid,3)} · ask ${fmt(zonePlan.live_ask,3)} · closed M30 reference ${fmt(zonePlan.closed_m30_reference,3)}. Zone spread ${fmt(zoneSpread.spread_price,3)} / adaptive cap ${fmt(zoneSpread.effective_cap_price,3)}${zoneSpread.limiting_factor?` · ${esc(pretty(zoneSpread.limiting_factor))} limited`:""}; scalp cost gate is separate. ${zoneExecutorInstalled?`Nyao executor: ${esc(pretty(s.zone_last_execution_reason||"READY"))}.`:"Install the newly compiled Nyao build to enforce this directive."}</div></div><span class="badge ${sourceInvalidated?"bad":zoneModeLive?"ok":"warn"}">${esc(sourceInvalidated?"ZONE INVALIDATED":zoneModeLive?"LIVE IN NYAO":pretty(zonePlan.state))}</span></div><div class="zone-plan-grid">${entries.map((entry,index)=>`<div class="zone-plan-leg"><div class="label">ENTRY ${entry.leg} · ${fmt(entry.risk_allocation_pct,0)}% · ${esc(pretty(entry.order_type))}</div><strong>${entry.order_type==="MARKET_ON_CONFIRMATION"?`LIVE (ref ${fmt(entry.entry_price,3)})`:fmt(entry.entry_price,3)}</strong><div class="muted">${targets[index]?`TP${targets[index].target} ${fmt(targets[index].price,3)} · close ${fmt(targets[index].close_allocation_pct,0)}%`:"Target pending"}</div></div>`).join("")}</div><div class="grid g4" style="margin-top:9px"><div class="kpi"><div class="label">Shared stop</div><div class="value small neg">${fmt(activePlan.stop_loss,3)}</div></div><div class="kpi"><div class="label">Total account risk</div><div class="value small">${fmt(activePlan.risk?.account_risk_pct,2)}%</div></div><div class="kpi"><div class="label">Zone confirmation</div><div class="value small ${zc.eligible?"pos":""}">${fmt(zc.combined_score,1)} / ${fmt(zc.threshold,1)}</div><div class="muted">Directional ${fmt(zc.directional_score,2)} / ${fmt(zc.minimum_directional_score,2)} · policy ${text(zc.policy_epoch)}</div></div><div class="kpi"><div class="label">Execution authority</div><div class="value small ${zoneModeLive?"pos":"neg"}">${zoneModeLive?"ACTIVE":"NOT ACTIVE"}</div></div></div>${(zonePlan.blockers||[]).length?`<div class="callout" style="margin-top:9px">${esc(zonePlan.blockers.join(" "))}</div>`:""}</div>`;
  }else{
    const sizingNote=capital.version?` Atlas capital budget: ${fmt(capital.approved_scalp_risk_pct,3)}% equity per qualified scalp (${esc(pretty(capital.decision))}); current-account loss streak ${text(capital.consecutive_losses,0)}.`:"";
    zoneExecution.innerHTML=`<div class="zone-plan"><div class="zone-plan-head"><div><div class="label">ATLAS MODE DIRECTIVE</div><div class="zone-price" style="margin-top:5px">${esc(pretty(zonePlan.mode||"WAITING"))}</div><div class="muted" style="margin-top:5px">${zonePlan.mode==="SCALP_MODE"?"Live price is outside the priority zones, so the ordinary scalp strategy remains the proposed mode.":esc((zonePlan.blockers||[])[0]||"Waiting for the live zone execution plan.")}${sizingNote}</div></div><span class="badge ${capital.veto_new_risk?"bad":zonePlan.mode==="SCALP_MODE"?"info":"warn"}">${esc(capital.veto_new_risk?"CAPITAL VETO":pretty(zonePlan.state||"PENDING"))}</span></div></div>`;
  }
  const liveZoneRelation=zone=>{
    const decisionPrice=zone.side==="DEMAND"?(liveAsk>0?liveAsk:liveBid):(liveBid>0?liveBid:liveAsk);
    const relation=decisionPrice<Number(zone.low)?"BELOW":decisionPrice>Number(zone.high)?"ABOVE":"INSIDE";
    const basis=zone.side==="DEMAND"?"ASK":"BID";
    return {decisionPrice,relation,basis};
  };
  document.getElementById("an-zone-list").innerHTML=zoneRows.map(zone=>{const live=liveZoneRelation(zone);return `<div class="zone-card ${zone.side==="DEMAND"?"demand":"supply"}"><div><span class="badge ${zone.side==="DEMAND"?"ok":"bad"}">${esc(zone.side)}</span><div class="muted" style="margin-top:5px">${esc(zone.timeframe)} · ${esc(pretty(zone.kind))}</div></div><div><div class="zone-price">${fmt(zone.low,3)} – ${fmt(zone.high,3)}</div><div class="muted zone-evidence">${esc((zone.evidence||[])[0]||"Closed-candle structure zone")}</div></div><div><span class="badge ${live.relation==="INSIDE"?"ok":zone.status==="FRESH"?"info":"warn"}">LIVE ${esc(live.relation)}</span><div class="muted" style="margin-top:5px">${live.basis} ${fmt(live.decisionPrice,3)} · ${esc(text((zone.confluence||[]).length,0))} confluence</div></div><div class="zone-score"><strong>${fmt(zone.score,1)}</strong><div class="muted">score</div></div></div>`}).join("");
  const invalidatedRows=Array.isArray(zoneMap.invalidated_zones)?zoneMap.invalidated_zones:[];
  const lifecycleRoot=document.getElementById("an-zone-lifecycle");
  if(lifecycleRoot){
    const latestInvalid=invalidatedRows[0]||null;
    lifecycleRoot.innerHTML=zonesDetected
      ?`<strong>ZONE LIFECYCLE</strong> · ${text(zoneMap.zone_count,0)} active · ${text(zoneMap.invalidated_zone_count,0)} invalidated archived. <span class="muted">Invalidation requires a later closed candle beyond the technical boundary; wick-only penetration is retained as mitigation.</span>${latestInvalid?`<div style="margin-top:6px"><span class="badge bad">LATEST INVALIDATION</span> ${esc(latestInvalid.timeframe)} ${esc(pretty(latestInvalid.kind))} ${esc(latestInvalid.side)} · ${esc(latestInvalid.invalidation_reason||"")}</div>`:""}`
      :"Zone lifecycle is waiting for a validated deterministic map.";
  }
  const invalidatedCount=document.getElementById("an-invalidated-count");
  if(invalidatedCount){invalidatedCount.textContent=`${invalidatedRows.length} INVALIDATED`;invalidatedCount.className="badge "+(invalidatedRows.length?"bad":"info");}
  const invalidatedRoot=document.getElementById("an-invalidated-zone-list");
  if(invalidatedRoot){invalidatedRoot.innerHTML=invalidatedRows.length?invalidatedRows.map(zone=>`<div class="zone-card invalidated"><div><span class="badge bad">INVALIDATED</span><div class="muted" style="margin-top:5px">${esc(zone.timeframe)} · ${esc(pretty(zone.kind))} · ${esc(zone.side)}</div></div><div><div class="zone-price">${fmt(zone.low,3)} – ${fmt(zone.high,3)}</div><div class="muted zone-evidence">${esc(zone.invalidation_reason||"Closed candle invalidated the technical boundary.")}</div></div><div><span class="badge bad">${esc(pretty(zone.invalidation_rule||"CLOSED_CANDLE_BREAK"))}</span><div class="muted" style="margin-top:5px">Close ${fmt(zone.invalidating_close,3)} · boundary ${fmt(zone.invalidation_boundary,3)} · penetration ${fmt(zone.invalidation_penetration_atr,2)} ATR</div></div><div class="zone-score"><strong>${zone.invalidated_at_epoch?age(Math.max(0,Date.now()/1000-Number(zone.invalidated_at_epoch))):"—"}</strong><div class="muted">ago</div></div></div>`).join(""):`<div class="callout">No invalidated zones in the current validated candle history.</div>`;}
  const zoneScenarios=Array.isArray(zoneMap.scenarios)?zoneMap.scenarios:[];
  document.getElementById("an-zone-scenario-list").innerHTML=zoneScenarios.map(item=>`<div class="analysis-item ${item.side==="BUY"?"buy":"sell"}"><div class="row"><strong>${esc(item.side)} CLOSED-CANDLE MAP SCENARIO</strong><span class="badge warn">${esc(pretty(item.state))}</span></div><div class="muted" style="margin-top:5px">Closed M30 reference ${fmt(item.reference_price,3)} · ${item.zone_id?`${fmt(item.zone_low,3)} – ${fmt(item.zone_high,3)} · `:""}${esc((item.conditions||[])[0]||"No qualified zone available.")} Live authority is shown in the mode directive above.</div></div>`).join("");
  renderZoneChart(zoneMap,liveChartPrice);
  document.getElementById("an-mtf-grid").innerHTML=["M30","H1","H4"].map(tf=>{
    const item=candles.timeframes?.[tf]||{};
    const ready=item.state==="READY";
    return `<div class="kpi"><div class="row"><div class="label">${tf} closed bars</div><span class="badge ${ready?"ok":"warn"}">${esc(pretty(item.state||"WAITING"))}</span></div><div class="value small">${esc(text(item.bar_count,0))} / ${esc(text(item.minimum_bars,"—"))}</div><div class="muted">Latest ${item.latest_bar_age_seconds==null?"—":age(item.latest_bar_age_seconds)+" ago"}</div></div>`;
  }).join("");

  const scenarios=[
    {side:"BUY",ready:Boolean(s.buy_entry_eligible),score:Number(s.buy_adjusted_score||0),threshold:Number(s.buy_effective_threshold||0),reason:String(s.buy_block_reason||"NONE"),kind:"buy"},
    {side:"SELL",ready:Boolean(s.sell_entry_eligible),score:Number(s.sell_adjusted_score||0),threshold:Number(s.sell_effective_threshold||0),reason:String(s.sell_block_reason||"NONE"),kind:"sell"}
  ];
  const activeZoneSide=pretty(activePlan?.side||s.zone_side||"ZONE");
  const qualified=scenarios.filter(x=>x.ready);
  const strongestQualified=qualified.length?qualified.reduce((a,b)=>b.score>a.score?b:a):null;
  const lastOrderDirection=String(s.last_order_direction||"NONE").toUpperCase();
  const lastOrderRetcode=Number(s.last_order_retcode||0);
  document.getElementById("an-scenarios").innerHTML=scenarios.map(x=>{
    const counterDirection=analysisZoneAware&&activeZoneSide!=="ZONE"&&x.side!==activeZoneSide;
    const executionError=/ORDER_(SEND_ERROR|REJECTED|PREFLIGHT_REJECTED)|LOCAL_STOP_PREFLIGHT/.test(x.reason);
    const lostArbitration=!zoneModeLive&&!counterDirection&&x.ready&&strongestQualified&&strongestQualified.side!==x.side;
    let scalpState="WAIT";
    if(zoneModeLive) scalpState="ORDINARY SCALP SUSPENDED";
    else if(counterDirection) scalpState="ZONE-CONTEXT BLOCKED";
    else if(executionError) scalpState=x.reason.includes("PREFLIGHT")?"LOCAL PREFLIGHT BLOCKED":"BROKER / SEND REJECTED";
    else if(lostArbitration) scalpState="SIGNAL QUALIFIED · NOT SELECTED";
    else if(x.ready) scalpState="SIGNAL QUALIFIED · SELECTED";
    const authority=zoneModeLive?`ACTIVE · ${activeZoneSide} CAMPAIGN`:analysisZoneAware?`ZONE-AWARE SCALP · ${activeZoneSide} ALIGNED`:zoneExecutorInstalled&&zoneExecutorEnabled?"SCALP ACTIVE · ZONE ENGINE ARMED":"SCALP ACTIVE";
    let explanation="";
    if(zoneModeLive) explanation=`Active ${activeZoneSide} zone campaign owns execution authority; this ${x.side} score is informational and cannot launch an ordinary scalp.`;
    else if(counterDirection) explanation=`${x.side} is counter-zone to the active ${activeZoneSide} zone context; it requires the additional counter-zone evidence premium and may be blocked near campaign commitment.`;
    else if(executionError) explanation=`Execution did not complete: ${pretty(x.reason)}${lastOrderDirection===x.side&&lastOrderRetcode?` · MT5 ${lastOrderRetcode}`:""}. Nyao will re-evaluate on the next eligible cycle; it does not fall back into the opposite direction.`;
    else if(lostArbitration) explanation=`Signal passed its own threshold, but ${strongestQualified.side} won this cycle's directional arbitration (${fmt(strongestQualified.score,2)} vs ${fmt(x.score,2)}). No opposite-direction fallback is attempted if the selected side later fails execution.`;
    else if(x.ready) explanation=`Signal passed its threshold and won the currently qualified directional arbitration. Normal capital, spread, sizing, stop preflight and broker checks still apply before an order is accepted.`;
    else explanation=`Current blocker: ${pretty(text(x.reason,"NONE"))}`;
    const badgeClassName=executionError?"bad":lostArbitration?"info":zoneModeLive?"info":x.ready?"ok":"warn";
    return `<div class="analysis-item ${x.kind}"><div class="row"><strong>${x.side} · ${scalpState}</strong><span class="badge ${badgeClassName}">${fmt(x.score,2)} / ${fmt(x.threshold,2)}</span></div><div class="muted" style="margin-top:5px">${esc(explanation)} · Zone authority: ${esc(authority)}</div></div>`;
  }).join("");

  const bundle=p.llm_policy?.bundle||{}, critic=p.llm_policy?.critic||{};
  const criticBadge=document.getElementById("an-gemini-badge");criticBadge.textContent=text(critic.verdict,"NO LLM MAP");criticBadge.className="badge "+badgeClass(criticBadge.textContent);
  document.getElementById("an-gemini-thesis").textContent=bundle.policy_thesis||"No Gemini policy thesis is attached to the current analysis.";
  const llmEvidence=[...(bundle.performance_diagnosis||[]),...(bundle.responsiveness_diagnosis||[]),...(bundle.risks_and_tradeoffs||[])].slice(0,8);
  document.getElementById("an-gemini-evidence").innerHTML=llmEvidence.map(x=>`<div class="analysis-item info">${esc(x)}</div>`).join("")||`<div class="analysis-item">Run a Gemini policy cycle to populate this interpretation.</div>`;
}

function latestAckState(){
  const events=state.executionEvents?.events||[];
  const e=events.find(x=>String(x.action||"").startsWith("NYAO_ACK_"));
  return e?String(e.action).replace("NYAO_ACK_",""):"—";
}
function renderProposalChanges(id,changes){
  const root=document.getElementById(id);
  if(!root)return;
  const rows=Object.entries(changes||{});
  root.innerHTML=rows.length?rows.map(([k,v])=>`<div class="change"><strong>${esc(pretty(k))}</strong><span>${esc(text(v.current))}</span><span><span class="arrow">→</span> ${esc(text(v.shadow))}</span></div>`).join(""):`<div class="callout">No material runtime changes.</div>`;
}

function renderPortfolioRiskAllocation(){
  const capital=state.zonePlan?.capital_sizing||{},alloc=capital.portfolio_allocation||{},priority=capital.zone_priority_reservation||{};
  const operating=Math.max(0,Number(alloc.operating_risk_ceiling_amount||0)),active=Math.max(0,Number(alloc.reserved_active_risk_amount||0));
  const remainingBefore=Math.max(0,Number(priority.remaining_operating_before_priority??alloc.remaining_operating_risk_amount??Math.max(0,operating-active)));
  const zone=priority.active?Math.max(0,Math.min(remainingBefore,Number(priority.zone_priority_amount||0))):0,free=Math.max(0,remainingBefore-zone);
  const hard=Math.max(0,Number(alloc.portfolio_hard_ceiling_amount||0)),hardFree=Math.max(0,Number(alloc.remaining_hard_risk_amount||Math.max(0,hard-active)));
  const delta=operating-(active+zone+free),ok=Math.abs(delta)<=Math.max(.02,operating*.001);
  const badge=document.getElementById('portfolio-risk-badge');if(badge){badge.textContent=ok?'RECONCILED':'CHECK ALLOCATION';badge.className='badge '+(ok?'ok':'bad')}
  const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v};set('portfolio-operating-ceiling',money(operating));set('portfolio-hard-ceiling',money(hard));set('portfolio-hard-headroom',`${money(hardFree)} hard headroom`);set('portfolio-risk-reconcile',ok?`${money(active)} active + ${money(zone)} zone priority + ${money(free)} free = ${money(operating)}`:`Allocation differs by ${money(delta)}.`);
  const bar=document.getElementById('portfolio-risk-bar');if(bar){const pct=x=>operating?Math.max(0,Math.min(100,x/operating*100)):0,segs=bar.querySelectorAll('.risk-segment');if(segs[0])segs[0].style.width=`${pct(active)}%`;if(segs[1])segs[1].style.width=`${pct(zone)}%`;if(segs[2])segs[2].style.width=`${pct(free)}%`}
  const cards=[];for(const r of (Array.isArray(alloc.reservations)?alloc.reservations:[])){const mtm=Number(r.current_mark_to_market||0);cards.push(`<div class="risk-allocation-card"><div class="risk-card-head"><div><span class="label">ACTIVE RESERVATION</span><strong>${esc(pretty(r.unit_type||'ACTIVE_RISK'))}</strong></div><span class="badge info">${esc(text(r.member_count,1))} MEMBER${Number(r.member_count||1)===1?'':'S'}</span></div><div class="risk-amount">${money(r.reserved_risk_amount||0)}</div><div class="risk-detail"><span>Unit</span><strong class="mono">${esc(text(r.unit_id,'—'))}</strong><span>Basis</span><strong>${esc(pretty(r.reservation_basis||'RESERVED'))}</strong><span>Current MTM</span><strong class="${mtm>0?'pos':mtm<0?'neg':''}">${money(mtm)}</strong></div></div>`)}
  if(zone>0){const plan=state.zonePlan?.zone_plan||{},side=String(state.zonePlan?.zone_aware_scalping_side||plan.side||state.status?.zone_side||'ZONE').toUpperCase();cards.push(`<div class="risk-allocation-card"><div class="risk-card-head"><div><span class="label">PROSPECTIVE RESERVATION</span><strong>${esc(side)} zone priority</strong></div><span class="badge warn">PRESERVED</span></div><div class="risk-amount">${money(zone)}</div><div class="risk-detail"><span>Basis</span><strong>${esc(pretty(priority.basis||'ZONE_PRIORITY'))}</strong><span>Plan</span><strong class="mono">${esc(text(plan.plan_id||state.status?.zone_plan_id||'—'))}</strong><span>Zone budget</span><strong>${money(capital.approved_zone_risk_amount||zone)}</strong></div></div>`)}
  cards.push(`<div class="risk-allocation-card"><div class="risk-card-head"><div><span class="label">FREE OPERATING RISK</span><strong>Fresh opportunity capacity</strong></div><span class="badge ${free>0?'ok':'bad'}">${free>0?'AVAILABLE':'FULLY ALLOCATED'}</span></div><div class="risk-amount">${money(free)}</div><div class="risk-detail"><span>Current scalp budget</span><strong>${money(capital.approved_scalp_risk_amount||0)}</strong><span>Remaining hard capacity</span><strong>${money(hardFree)}</strong><span>Operating utilization</span><strong>${operating?fmt((active+zone)/operating*100,1):'0.0'}%</strong></div></div>`);
  const root=document.getElementById('portfolio-risk-cards');if(root)root.innerHTML=cards.join('');
}

function renderPositions(){
  const s=state.status||{}, ps=Array.isArray(s.positions)?s.positions:[];
  const activePayload=state.outcomes?.active||{};
  const activeRows=Array.isArray(activePayload)
    ? activePayload
    : Object.values(activePayload||{});
  const lifecycleByTicket=new Map(
    activeRows.map(t=>[String(t.ticket),t])
  );

  document.getElementById("p-count").textContent=ps.length;
  document.getElementById("p-lots").textContent=fmt(s.total_lots,2);

  let activeRealized=0;
  let activeFloating=0;

  for(const p of ps){
    const life=lifecycleByTicket.get(String(p.ticket))||{};
    activeRealized+=Number(life.realized_net_pl||0);
    activeFloating+=Number(p.net_pl||0);
  }

  const realizedEl=document.getElementById("p-realized");
  realizedEl.textContent=money(activeRealized);
  realizedEl.className="value "+(activeRealized>0?"pos":activeRealized<0?"neg":"");

  const pl=s.strategy_floating_pl??s.floating_profit;
  const el=document.getElementById("p-pl");
  el.textContent=money(pl);
  el.className="value "+(Number(pl)>0?"pos":Number(pl)<0?"neg":"");

  const lifecycleTotal=activeRealized+Number(pl||0);
  const lifeEl=document.getElementById("p-lifecycle");
  lifeEl.textContent=money(lifecycleTotal);
  lifeEl.className="value "+(lifecycleTotal>0?"pos":lifecycleTotal<0?"neg":"");

  document.getElementById("p-chains").textContent=text(s.active_hedge_chains,0);
  renderPortfolioRiskAllocation();

  document.getElementById("positions-body").innerHTML=ps.length?ps.map(p=>{
    const life=lifecycleByTicket.get(String(p.ticket))||{};
    const floating=Number(p.net_pl||0);
    const realized=Number(life.realized_net_pl||0);
    const lifecycle=realized+floating;
    const initialVolume=Number(life.initial_volume??p.volume??0);
    const remaining=Number(p.volume||0);
    const closed=Number(life.closed_volume||Math.max(0,initialVolume-remaining));
    const volumeLabel=closed>0.0000001
      ? `${fmt(remaining,2)} / ${fmt(initialVolume,2)}`
      : fmt(remaining,2);
    const context=p.scalp_context_class&&p.scalp_context_class!=="NEUTRAL_SCALP"
      ? p.scalp_context_class
      : (p.order_origin||p.origin);
    return `<tr>
      <td class="mono">${esc(text(p.ticket))}</td>
      <td>${esc(text(p.type))}</td>
      <td title="${closed>0?`${fmt(closed,2)} lots already closed`:"Current open volume"}">${esc(volumeLabel)}</td>
      <td>${fmt(p.entry_price,3)}</td>
      <td>${fmt(p.current_price,3)}</td>
      <td class="${realized>0?"pos":realized<0?"neg":""}">${money(realized)}</td>
      <td class="${floating>0?"pos":floating<0?"neg":""}">${money(floating)}</td>
      <td class="${lifecycle>0?"pos":lifecycle<0?"neg":""}"><strong>${money(lifecycle)}</strong></td>
      <td class="neg">${fmt(p.sl,3)}</td>
      <td class="pos">${fmt(p.tp,3)}</td>
      <td>${esc(pretty(context))}${p.scalp_context_zone_side&&p.scalp_context_zone_side!=="NONE"?`<div class="muted">${esc(p.scalp_context_zone_side)} zone · pressure ${fmt(Number(p.scalp_context_pressure||0)*100,0)}%</div>`:""}</td>
      <td>${age(p.age_seconds)}</td>
    </tr>`}).join(""):`<tr><td colspan="12" class="muted">No strategy positions.</td></tr>`;

  renderClosedTrades();
  renderPerformance();
}

function renderClosedTrades(){
  const payload=state.outcomes||{};
  const closed=Array.isArray(payload.closed)?[...payload.closed]:[];
  closed.sort((a,b)=>Number(b.close_time_msc||b.close_time_epoch||0)-Number(a.close_time_msc||a.close_time_epoch||0));
  const root=document.getElementById("closed-trades-body");if(!root)return;
  const badge=document.getElementById("closed-trades-badge");
  const exact=closed.filter(t=>t.exact_realized_pl_available).length;
  badge.textContent=closed.length?`${closed.length} RECENT · ${exact} MT5 CONFIRMED`:"CURRENT ACCOUNT";
  badge.className="badge "+(exact?"ok":"info");
  root.innerHTML=closed.length?closed.slice(0,20).map(t=>{
    const initial=t.initial_position||{}, latest=t.latest_position||{};
    const pl=t.exact_realized_pl_available?Number(t.realized_net_pl||0):Number(t.final_observed_net_pl_before_disappearance||0);
    const closedAt=t.close_time_epoch?new Date(Number(t.close_time_epoch)*1000):t.disappeared_at?new Date(t.disappeared_at):null;
    const quality=t.exact_realized_pl_available?"MT5 CONFIRMED":pretty(t.outcome_quality||"INFERRED");
    return `<tr>
      <td class="mono">${esc(text(t.ticket||initial.ticket))}</td>
      <td>${esc(text(t.type||initial.type))}</td>
      <td>${fmt(t.initial_volume??initial.volume,2)}</td>
      <td>${fmt(t.entry_price??initial.entry_price,3)}</td>
      <td>${fmt(t.close_price??latest.current_price,3)}</td>
      <td class="${pl>0?"pos":pl<0?"neg":""}">${money(pl)}</td>
      <td>${esc(pretty(
  t.scalp_context_class&&t.scalp_context_class!=="NEUTRAL_SCALP"
    ? t.scalp_context_class
    : (t.order_origin||initial.order_origin||t.origin_guess)
))}</td>
      <td>${esc(text(t.entry_policy_epoch??initial.entry_policy_epoch,"—"))}</td>
      <td>${esc(pretty(t.trading_mode||"UNKNOWN"))}</td>
      <td>${closedAt&&!Number.isNaN(closedAt.getTime())?esc(closedAt.toLocaleString()):"—"}</td>
      <td><span class="badge ${t.exact_realized_pl_available?"ok":"warn"}">${esc(quality)}</span></td>
    </tr>`;
  }).join(""):`<tr><td colspan="11" class="muted">No closed trades recorded for the selected MT5 account yet.</td></tr>`;
}

function performanceUnitRow(label,row){
  row=row||{};const n=Number(row.closed_risk_units||0), net=Number(row.net_pl||0), exp=Number(row.expectancy||0), wr=Number(row.win_rate_pct||0);
  return `<div class="mini"><span class="label">Units</span><strong>${n}</strong></div><div class="mini"><span class="label">Net P/L</span><strong class="${net>0?"pos":net<0?"neg":""}">${money(net)}</strong></div><div class="mini"><span class="label">Expectancy</span><strong class="${exp>0?"pos":exp<0?"neg":""}">${money(exp)}</strong></div><div class="mini"><span class="label">Win rate</span><strong>${fmt(wr,1)}%</strong></div>`;
}
function median(values){const a=values.map(Number).filter(Number.isFinite).sort((x,y)=>x-y);if(!a.length)return null;const m=Math.floor(a.length/2);return a.length%2?a[m]:(a[m-1]+a[m])/2}
function renderPerformanceCurve(units){
  const root=document.getElementById("performance-equity-curve");if(!root)return;
  const ordered=[...units].sort((a,b)=>new Date(a.closed_at||0)-new Date(b.closed_at||0));if(!ordered.length){root.innerHTML='<div class="observability-empty">Equity curve will appear after completed risk units.</div>';return}
  let run=0;const vals=[0,...ordered.map(u=>(run+=Number(u.realized_net_pl||0)))];const lo=Math.min(...vals),hi=Math.max(...vals),span=Math.max(1,hi-lo),w=760,h=170,pad=18;
  const pts=vals.map((v,i)=>`${pad+(w-2*pad)*(i/Math.max(1,vals.length-1))},${pad+(h-2*pad)*(1-(v-lo)/span)}`).join(' ');
  const zeroY=pad+(h-2*pad)*(1-(0-lo)/span);
  root.innerHTML=`<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="Cumulative strategic realised P/L"><line x1="${pad}" y1="${zeroY}" x2="${w-pad}" y2="${zeroY}" stroke="rgba(142,160,184,.22)" stroke-width="1"/><polyline points="${pts}" fill="none" stroke="currentColor" stroke-width="2.5" vector-effect="non-scaling-stroke"/><text x="${pad}" y="15" fill="currentColor" font-size="10">${esc(money(hi))}</text><text x="${pad}" y="${h-5}" fill="currentColor" font-size="10">${esc(money(lo))}</text></svg>`;
}
function renderPerformance(){
  const p=state.performance||{},o=p.overall||{},risk=state.riskUnits||{};
  const allUnits=Array.isArray(risk.units)?risk.units:[], completed=allUnits.filter(u=>u.state==="COMPLETE");
  const byType=Object.fromEntries((p.by_risk_unit_type||[]).map(r=>[String(r.risk_unit_type||""),r]));
  const netEl=document.getElementById("perf-net");if(!netEl)return;
  netEl.textContent=money(o.net_pl);netEl.className="performance-net "+(Number(o.net_pl)>0?"pos":Number(o.net_pl)<0?"neg":"");
  document.getElementById("perf-count").textContent=text(o.closed_risk_units,0);
  const exp=document.getElementById("perf-expectancy");exp.textContent=money(o.expectancy);exp.className="value "+(Number(o.expectancy)>0?"pos":Number(o.expectancy)<0?"neg":"");
  document.getElementById("perf-win-rate").textContent=`${fmt(o.win_rate_pct,1)}%`;
  document.getElementById("perf-factor").textContent=o.profit_factor==null?"—":fmt(o.profit_factor,2);
  document.getElementById("perf-drawdown").textContent=money(o.maximum_closed_unit_drawdown);
  document.getElementById("perf-sample").textContent=`Sample ${pretty(o.sample_state||"INSUFFICIENT")}`;
  const quality=document.getElementById("perf-quality"), exact=Number(p.quality?.exact_realized_count||0), inferred=Number(p.quality?.inferred_count||0);
  quality.textContent=exact?"MT5 REALIZED":"INFERRED";quality.className="badge "+(exact&&inferred===0?"ok":exact?"info":"warn");
  document.getElementById("perf-data-quality").textContent=exact&&inferred===0?"AUTHORITATIVE":exact?"MIXED":"INFERRED";
  document.getElementById("perf-data-quality-copy").textContent=`${exact} exact · ${inferred} inferred risk units`;
  const headline=document.getElementById("performance-headline");
  headline.textContent=!Number(o.closed_risk_units)?"Atlas is collecting its first completed strategic outcomes.":Number(o.closed_risk_units)<20?"Early evidence only — useful for observation, not causal policy conclusions.":"Strategic performance evidence is accumulating; compare policy epochs and risk-unit types before adapting.";
  document.getElementById("performance-page-badge").textContent=`${text(state.selectedSymbol,"CURRENT")} · ${text(o.sample_state,"INSUFFICIENT")}`;
  renderPerformanceCurve(completed);

  const typeMap=[['STANDALONE_TRADE','perf-standalone','perf-standalone-badge'],['RECOVERY_CHAIN','perf-recovery','perf-recovery-badge'],['ZONE_CAMPAIGN','perf-zone','perf-zone-badge']];
  for(const [key,id,bid] of typeMap){const row=byType[key]||{};document.getElementById(id).innerHTML=performanceUnitRow(key,row);const b=document.getElementById(bid);b.textContent=text(row.sample_state,'NO DATA');b.className='badge '+(Number(row.closed_risk_units)>=20?'ok':Number(row.closed_risk_units)>0?'warn':'');}

  document.getElementById("perf-epochs").innerHTML=(p.by_policy_epoch||[]).slice(0,14).map(r=>`<tr><td>${esc(text(r.policy_epoch))}</td><td>${esc(text(r.closed_risk_units))}</td><td class="${Number(r.net_pl)>0?"pos":Number(r.net_pl)<0?"neg":""}">${money(r.net_pl)}</td><td>${money(r.expectancy)}</td><td>${fmt(r.win_rate_pct,1)}%</td><td><span class="badge ${Number(r.closed_risk_units)>=20?"ok":"warn"}">${esc(pretty(r.sample_state))}</span></td></tr>`).join("")||`<tr><td colspan="6" class="muted">No completed policy outcomes yet.</td></tr>`;
  document.getElementById("perf-modes").innerHTML=(p.by_trading_mode||[]).map(r=>`<tr><td>${esc(pretty(r.trading_mode))}</td><td>${esc(text(r.closed_risk_units))}</td><td class="${Number(r.net_pl)>0?"pos":Number(r.net_pl)<0?"neg":""}">${money(r.net_pl)}</td><td>${money(r.expectancy)}</td><td>${r.profit_factor==null?"—":fmt(r.profit_factor,2)}</td></tr>`).join("")||`<tr><td colspan="5" class="muted">No completed mode outcomes yet.</td></tr>`;

  const recent=[...completed].sort((a,b)=>new Date(b.closed_at||0)-new Date(a.closed_at||0)).slice(0,10);document.getElementById("perf-units-badge").textContent=`${completed.length} COMPLETE`;
  document.getElementById("perf-recent-units").innerHTML=recent.length?recent.map(u=>{const pl=Number(u.realized_net_pl||0);return `<div class="performance-result"><div><strong>${esc(pretty(u.unit_type))}</strong><div class="muted">${esc(text(u.unit_id))} · epoch ${esc(text(u.policy_epoch,'—'))}</div></div><strong class="${pl>0?'pos':pl<0?'neg':''}">${money(pl)}</strong><div class="muted">${u.closed_at?new Date(u.closed_at).toLocaleString():'—'}</div></div>`}).join(''):'<div class="observability-empty">No completed strategic risk units yet.</div>';

  const payload=state.outcomes||{}, tickets=Array.isArray(payload.closed)?payload.closed:[];const mfe=tickets.map(t=>t.max_favorable_net_pl_observed).filter(v=>Number.isFinite(Number(v))),mae=tickets.map(t=>t.max_adverse_net_pl_observed).filter(v=>Number.isFinite(Number(v)));const pls=tickets.map(t=>t.exact_realized_pl_available?Number(t.realized_net_pl||0):Number(t.final_observed_net_pl_before_disappearance||0)).filter(Number.isFinite);
  document.getElementById("perf-mfe").textContent=median(mfe)==null?'—':money(median(mfe));document.getElementById("perf-mae").textContent=median(mae)==null?'—':money(median(mae));document.getElementById("perf-ticket-average").textContent=pls.length?money(pls.reduce((a,b)=>a+b,0)/pls.length):'—';document.getElementById("perf-exact-tickets").textContent=`${tickets.filter(t=>t.exact_realized_pl_available).length} / ${tickets.length}`;
  const contextRoot=document.getElementById("perf-scalp-context");
  if(contextRoot){
    const ctx={};

    for(const t of tickets){
      const key=text(
        t.scalp_context_class || "NEUTRAL_SCALP"
      );

      const pl=t.exact_realized_pl_available
        ? Number(t.realized_net_pl||0)
        : Number(t.final_observed_net_pl_before_disappearance||0);

      if(!ctx[key])
        ctx[key]={n:0,w:0,pl:0};

      ctx[key].n++;

      if(Number.isFinite(pl)){
        ctx[key].pl+=pl;
        if(pl>0)ctx[key].w++;
      }
    }

    const rows=Object.entries(ctx)
      .sort((a,b)=>b[1].n-a[1].n);

    const maxN=Math.max(
      1,
      ...rows.map(x=>x[1].n)
    );

    contextRoot.innerHTML=rows.length
      ? rows.map(([k,v])=>`
        <div class="performance-bar">
          <span>${esc(pretty(k))}</span>
          <div class="performance-bar-track">
            <div class="performance-bar-fill"
              style="width:${Math.min(100,100*v.n/maxN)}%">
            </div>
          </div>
          <span class="${v.pl>0?'pos':v.pl<0?'neg':''}">
            ${v.n} · ${money(v.pl)} · ${fmt(100*v.w/Math.max(1,v.n),0)}% win
          </span>
        </div>
      `).join("")
      : '<div class="muted">No contextual scalp outcomes yet.</div>';
  }

  const reg={};for(const t of tickets){const key=text(t.entry_context?.regime,'UNKNOWN');const pl=t.exact_realized_pl_available?Number(t.realized_net_pl||0):Number(t.final_observed_net_pl_before_disappearance||0);if(!reg[key])reg[key]={n:0,pl:0};reg[key].n++;reg[key].pl+=Number.isFinite(pl)?pl:0}const rr=Object.entries(reg).sort((a,b)=>b[1].n-a[1].n),maxN=Math.max(1,...rr.map(x=>x[1].n));document.getElementById("perf-regimes").innerHTML=rr.length?rr.map(([k,v])=>`<div class="performance-bar"><span>${esc(pretty(k))}</span><div class="performance-bar-track"><div class="performance-bar-fill" style="width:${100*v.n/maxN}%"></div></div><span class="${v.pl>0?'pos':v.pl<0?'neg':''}">${v.n} · ${money(v.pl)}</span></div>`).join(''):'<div class="muted">No entry-context evidence yet.</div>';
  document.getElementById("perf-exact-units").textContent=exact;document.getElementById("perf-inferred-units").textContent=inferred;document.getElementById("perf-active-units").textContent=text(p.active_risk_unit_count??risk.active_unit_count,0);document.getElementById("perf-loss-streak").textContent=text(p.consecutive_completed_loss_units??risk.consecutive_completed_loss_units,0);
  const lb=document.getElementById("perf-learning-badge");lb.textContent=pretty(o.sample_state||'INSUFFICIENT');lb.className='badge '+(Number(o.closed_risk_units)>=100?'ok':Number(o.closed_risk_units)>=20?'info':'warn');document.getElementById("perf-note").textContent=p.interpretation||"Strategic performance requires completed risk units; small samples are preliminary and not causal proof.";
}
function renderLlmCycle(){
  const c=state.llmCycle||{};
  const models=state.llmStatus?.model_chain||[];
  const status=c.running?"RUNNING":c.enabled?"SCHEDULED":"DISABLED";
  const badge=document.getElementById("cycle-badge");if(!badge)return;
  badge.textContent=status;badge.className="badge "+(c.running?"info":c.enabled?"ok":"warn");
  document.getElementById("cycle-last").textContent=c.last_completed_at?new Date(c.last_completed_at).toLocaleString():"Never";
  const seconds=Number(c.seconds_until_next_run);
  document.getElementById("cycle-next").textContent=c.running?"Running now":c.enabled&&Number.isFinite(seconds)?age(seconds):"Not scheduled";
  document.getElementById("cycle-count").textContent=text(c.run_count,0);
  document.getElementById("cycle-critic").textContent=text(c.last_critic_verdict);
  const interval=document.getElementById("cycle-interval");
  if(interval && document.activeElement!==interval)interval.value=text(c.interval_minutes,240);
  const enabled=document.getElementById("cycle-enabled");
  if(enabled && document.activeElement!==enabled)enabled.checked=Boolean(c.enabled);
  const mode=document.getElementById("cycle-mode");if(mode&&document.activeElement!==mode)mode.value=text(c.execution_mode,"SUPERVISED");
  const dwell=document.getElementById("cycle-dwell");if(dwell&&document.activeElement!==dwell)dwell.value=text(c.minimum_dwell_minutes,240);
  const confidence=document.getElementById("cycle-confidence");if(confidence&&document.activeElement!==confidence)confidence.value=text(c.minimum_confidence,70);
  document.getElementById("btn-run-cycle").disabled=Boolean(c.running);
  const autoWait=Number(c.seconds_until_auto_apply_eligible||0);
  const consensus=state.autoConsensus||{};
  const consensusText=c.execution_mode==="AUTONOMOUS"
    ? ` Consensus window: ${text(consensus.observation_count,0)} current observations (${text(consensus.lifetime_observation_count??consensus.observation_count,0)} lifetime) · ${text(consensus.consensus_control_count,0)} controls currently meet ≥${fmt(Number(consensus.minimum_support_ratio||0.6)*100,0)}% support${consensus.ready?" · READY":""}.`
    : "";
  const detail=c.running
    ? `Gemini is analyzing ${text(state.selectedSymbol)}. This may take a few minutes.`
    : c.last_error
      ? `${pretty(c.last_status)}: ${c.last_error}`
      : c.execution_mode==="AUTONOMOUS"&&c.last_auto_apply_status==="MINIMUM_DWELL_ACTIVE"
        ? `AUTO APPLY DEFERRED · current policy minimum dwell${autoWait>0?` · eligible in ${age(autoWait)}`:" complete"}. Gemini observations continue accumulating during the hold.`
        : c.execution_mode==="AUTONOMOUS"&&c.last_auto_apply_status==="CONSENSUS_NOT_READY"
          ? `AUTO APPLY DEFERRED · dwell is complete, but the accumulated Gemini observations have not reached policy consensus yet.`
          : `${pretty(c.last_status||"NEVER_RUN")} · ${c.execution_mode==="AUTONOMOUS"?`validated Nyao scalp-policy autonomous activation; last apply ${pretty(c.last_auto_apply_status||"NEVER_APPLIED")}`:"human approval and application required"}.`;
  document.getElementById("cycle-detail").textContent=`${detail}${consensusText}${models.length?` Configured model chain: ${models.join(" → ")}.`:""}`;
}

function renderAutonomousConsensus(){
  const root=document.getElementById("consensus-controls");
  if(!root)return;
  const c=state.autoConsensus||{};
  const autonomous=state.llmCycle?.execution_mode==="AUTONOMOUS";
  const total=Number(c.observation_count||0);
  const minObs=Number(c.minimum_observations||3);
  const minRatio=Number(c.minimum_support_ratio||0.6);
  const backendQualified=Number(c.consensus_control_count||0);
  const qualified=total>=minObs?backendQualified:0;
  const controls=Object.entries(c.controls||{}).map(([name,row])=>({name,...(row||{})}));
  const badge=document.getElementById("consensus-badge");
  const ready=Boolean(c.ready);
  badge.textContent=!autonomous?"SUPERVISED":ready?"CONSENSUS READY":total?"COLLECTING":"WAITING";
  badge.className="badge "+(!autonomous?"info":ready?"ok":total?"warn":"");
  document.getElementById("consensus-observations").textContent=text(total,0);
  document.getElementById("consensus-qualified").textContent=text(qualified,0);
  document.getElementById("consensus-threshold").textContent=`${fmt(minRatio*100,0)}%`;
  document.getElementById("consensus-epoch").textContent=c.baseline_policy_epoch==null?"—":text(c.baseline_policy_epoch);
  const lifetime=Number(c.lifetime_observation_count??total);
  const archived=Number(c.archived_window_count||0);
  const lifetimeEl=document.getElementById("consensus-lifetime");if(lifetimeEl)lifetimeEl.textContent=text(lifetime,0);
  const historyNote=document.getElementById("consensus-history-note");if(historyNote)historyNote.textContent=archived?`${archived} prior policy window${archived===1?"":"s"} archived`:"No archived windows yet";
  document.getElementById("consensus-observation-rule").textContent=total<minObs?`${minObs-total} more accepted observation${minObs-total===1?"":"s"} before consensus can qualify`:`Minimum ${minObs} observations satisfied`;
  const anchor=c.baseline_anchor?new Date(c.baseline_anchor):null;
  document.getElementById("consensus-window-age").textContent=anchor&&!Number.isNaN(anchor.getTime())?`Window started ${anchor.toLocaleString()}`:"Window not anchored yet";
  const wait=Number(state.llmCycle?.seconds_until_auto_apply_eligible||0);
  const dwellDone=wait<=0;
  document.getElementById("consensus-headline").textContent=!autonomous
    ?"Consensus is observational while application mode is supervised."
    : ready&&dwellDone
      ?`${qualified} control${qualified===1?" is":"s are"} consensus-qualified and dwell is complete.`
      : ready
        ?`${qualified} control${qualified===1?" has":"s have"} consensus; activation still waits for policy dwell.`
        : total
          ?"Gemini observations are accumulating; no control has cleared all consensus gates yet."
          :"Waiting for the first accepted Gemini observation in this dwell window.";
  document.getElementById("consensus-detail").textContent=!autonomous
    ?"Switching to autonomous mode does not automatically apply these observations; normal confidence, epoch, risk and mode-boundary gates still apply."
    : `${dwellDone?"Policy dwell complete":"Policy dwell remaining: "+age(wait)} · ${qualified} qualifying control${qualified===1?"":"s"} · each control needs ≥${fmt(minRatio*100,0)}% support and at least ${minObs} supporting observations.`;
  const historyRoot=document.getElementById("consensus-history");
  if(historyRoot){
    const windows=Array.isArray(c.recent_windows)?c.recent_windows:[];
    historyRoot.innerHTML=windows.length?windows.map(w=>{const produced=w.produced_policy_epoch;const label=w.current_window?`Baseline Epoch ${esc(text(w.baseline_policy_epoch))}`:produced?`Baseline Epoch ${esc(text(w.baseline_policy_epoch))} → Produced Epoch ${esc(text(produced))}`:`Baseline Epoch ${esc(text(w.baseline_policy_epoch))}`;const applied=w.applied_at?` · applied ${esc(new Date(w.applied_at).toLocaleString())}`:"";return `<div class="analysis-item ${w.current_window?"info":""}"><div class="row"><strong>${label}</strong><span class="badge ${w.current_window?"info":produced?"ok":""}">${w.current_window?"CURRENT WINDOW":produced?"APPLIED WINDOW":"ARCHIVED"}</span></div><div class="muted" style="margin-top:5px">${esc(text(w.observation_count,0))} accepted observation${Number(w.observation_count)===1?"":"s"}${w.last_observed_at?` · last ${esc(new Date(w.last_observed_at).toLocaleString())}`:""}${applied}${w.minimum_dwell_overridden?" · dwell override":""}</div></div>`}).join(""):`<div class="analysis-item">No policy-window history recorded yet.</div>`;
  }
  if(!controls.length){
    root.innerHTML=`<div class="consensus-empty">No controls have been proposed during the current policy dwell window yet. Prior windows remain archived below.</div>`;
    return;
  }
  controls.sort((a,b)=>Number(Boolean(b.ready))-Number(Boolean(a.ready)) || Number(b.support_ratio||0)-Number(a.support_ratio||0) || Number(b.support_count||0)-Number(a.support_count||0) || a.name.localeCompare(b.name));
  root.innerHTML=controls.map(row=>{
    const support=Number(row.support_count||0);
    const ratio=Number(row.support_ratio||0);
    const requiredNow=Math.max(minObs,Math.ceil(total*minRatio));
    const supportGap=Math.max(0,requiredNow-support);
    const globalGap=Math.max(0,minObs-total);
    const pct=Math.max(0,Math.min(100,ratio*100));
    const trulyReady=Boolean(row.ready)&&total>=minObs&&support>=minObs&&ratio>=minRatio;
    const status=trulyReady?"QUALIFIED":globalGap>0?"EARLY SUPPORT":supportGap>0?"BUILDING SUPPORT":"NOT QUALIFIED";
    const gate=trulyReady
      ?`Clears the minimum-observation and ${fmt(minRatio*100,0)}% support gates.`
      : globalGap>0
        ?`${support}/${total} currently supports this change, but consensus cannot qualify until ${globalGap} more accepted observation${globalGap===1?"":"s"} exist in this policy window.`
        : `${supportGap} more supporting observation${supportGap===1?"":"s"} needed at the current window size.`;
    return `<div class="consensus-row ${trulyReady?"ready":""}">
      <div class="consensus-name"><strong>${esc(pretty(row.name))}</strong><div class="muted">${esc(pretty(row.method||"EXACT_TARGET"))}</div></div>
      <div class="consensus-values"><span class="muted">Current</span> <strong>${esc(text(row.baseline))}</strong><br><span class="muted">Consensus</span> <strong>${esc(text(row.selected))}</strong></div>
      <div class="consensus-support"><div class="consensus-support-line"><span>${support}/${total} support</span><strong>${fmt(pct,0)}%</strong></div><div class="consensus-meter"><span style="width:${pct}%"></span></div></div>
      <div class="consensus-gate">${esc(gate)}</div>
      <span class="badge ${trulyReady?"ok":"warn"}">${esc(status)}</span>
    </div>`;
  }).join("");
}

function renderResponsiveness(){
  const r=state.responsiveness||{}, entry=r.entry_observations||{}, exit=r.exit_observations||{};
  const badge=document.getElementById("resp-badge");if(!badge)return;
  badge.textContent=text(r.profile);badge.className="badge "+(r.profile==="FAST"?"ok":r.profile==="BALANCED"?"info":"warn");
  document.getElementById("resp-pressure").textContent=r.latency_pressure_score==null?"—":`${fmt(r.latency_pressure_score,1)} / 100`;
  document.getElementById("resp-eligible").textContent=entry.eligible_rate_pct==null?"—":`${fmt(entry.eligible_rate_pct,1)}%`;
  document.getElementById("resp-hold").textContent=exit.median_holding_minutes==null?"—":`${fmt(exit.median_holding_minutes,1)} min`;
  document.getElementById("resp-capture").textContent=exit.average_mfe_capture_ratio==null?"—":`${fmt(Number(exit.average_mfe_capture_ratio)*100,1)}%`;
  document.getElementById("resp-blockers").innerHTML=(entry.dominant_block_reasons||[]).slice(0,6).map(x=>`<div class="change"><strong>${esc(pretty(x.reason))}</strong><span>${esc(text(x.count))}</span><span>${esc(fmt(x.share_pct,1))}%</span></div>`).join("")||`<div class="callout">No blocker history available yet.</div>`;
  document.getElementById("resp-levers").innerHTML=(r.candidate_levers||[]).slice(0,6).map(x=>`<div class="change" style="grid-template-columns:1fr auto"><div><strong>${esc(pretty(x.control))}</strong><div class="muted">${esc(x.effect)}</div></div><span class="badge info">${esc(pretty(x.direction))}</span></div>`).join("")||`<div class="callout">Current responsiveness has no obvious latency lever.</div>`;
  document.getElementById("resp-detail").textContent=`${pretty(r.evidence_quality||"LIMITED")} evidence · ${text(entry.history_snapshot_count,0)} market snapshots · ${text(exit.closed_trade_count,0)} closed trades. Gemini receives this analysis on every policy cycle.`;
}


function brainTab(name){
  ["runs","observations","history"].forEach(k=>{
    document.getElementById(`brain-tab-${k}`)?.classList.toggle("active",k===name);
    document.getElementById(`brain-panel-${k}`)?.classList.toggle("active",k===name);
  });
}
function closePolicyInspector(){document.getElementById("policy-inspector-modal")?.classList.remove("open")}
function policyRuntimeRows(runtime,before={}){
  const entries=Object.entries(runtime||{}).sort(([a],[b])=>a.localeCompare(b));
  return entries.map(([name,value])=>{const prior=before?.[name];const changed=prior!==undefined&&JSON.stringify(prior)!==JSON.stringify(value);return `<div class="policy-control-row ${changed?"changed":""}"><strong>${esc(pretty(name))}</strong><span>${esc(text(prior,changed?"—":""))}</span><span>${esc(text(value))}</span></div>`}).join("")||`<div class="callout">No runtime controls captured for this epoch.</div>`;
}
function openPolicyInspector(epoch){
  const apps=state.autoApplications?.applications||[];const app=apps.find(x=>Number(x.policy_epoch)===Number(epoch));if(!app)return;
  const modal=document.getElementById("policy-inspector-modal");if(!modal)return;
  document.getElementById("policy-inspector-kicker").textContent=Number(epoch)===Number(state.autoApplications?.current_command_epoch)?"ACTIVE RUNTIME POLICY":"HISTORICAL POLICY";
  document.getElementById("policy-inspector-title").textContent=`Policy Epoch ${text(epoch)}`;
  document.getElementById("policy-inspector-subtitle").textContent=`Command ${text(app.command_version)} · ${pretty(app.reconciliation)} · applied ${(app.timestamp||"").replace("T"," ").slice(0,19)}`;
  const obs=(state.policyObservations?.observations||[]).filter(o=>Number(o.baseline_policy_epoch)===Number(app.baseline_policy_epoch));
  const changes=Object.entries(app.changes||{}).map(([name,row])=>`<div class="change"><strong>${esc(pretty(name))}</strong><span>${esc(text(row?.before))}</span><span>→ ${esc(text(row?.intended))}</span></div>`).join("")||`<div class="callout">No material control patch recorded.</div>`;
  const evidence=obs.length?obs.map((o,i)=>`<div class="analysis-item"><div class="row"><strong>Observation ${esc(text(o.proposal_id||`#${i+1}`))}</strong><span class="badge info">${esc(fmt(o.overall_confidence||0,0))}%</span></div><div class="muted" style="margin-top:4px">${esc((o.observed_at||"").replace("T"," ").slice(0,19))}</div><div class="observation-changes">${Object.entries(o.changes||{}).map(([n,r])=>`<span class="observation-chip">${esc(pretty(n))}: ${esc(text(r.current))} → ${esc(text(r.proposed))}</span>`).join("")||`<span class="muted">No control mutation proposed</span>`}</div></div>`).join(""):`<div class="callout">No durable per-observation detail exists for this historical window. Atlas does not reconstruct missing Gemini prose.</div>`;
  document.getElementById("policy-inspector-body").innerHTML=`<div class="grid g3"><div class="kpi"><div class="label">Consensus observations</div><div class="value small">${esc(text(app.consensus_observation_count,0))}</div></div><div class="kpi"><div class="label">Changed controls</div><div class="value small">${Object.keys(app.changes||{}).length}</div></div><div class="kpi"><div class="label">Runtime controls captured</div><div class="value small">${Object.keys(app.runtime||{}).length}</div></div></div><div class="label" style="margin-top:16px">Applied changes</div><div class="changes" style="margin-top:8px">${changes}</div><div class="label" style="margin-top:16px">Supporting consensus observations</div><div class="analysis-list" style="margin-top:8px">${evidence}</div><div class="label" style="margin-top:16px">Full registered runtime</div><div class="policy-control-table"><div class="policy-control-row"><strong>CONTROL</strong><span>PREVIOUS</span><span>THIS EPOCH</span></div>${policyRuntimeRows(app.runtime||{},app.previous_runtime||{})}</div>`;
  modal.classList.add("open");
}
function openActivePolicyInspector(){const epoch=state.autoApplications?.current_active?.policy_epoch||state.autoApplications?.current_command_epoch;openPolicyInspector(epoch)}
function openObservationInspector(index){
  const obs=(state.policyObservations?.observations||[])[index];if(!obs)return;const modal=document.getElementById("policy-inspector-modal");if(!modal)return;
  document.getElementById("policy-inspector-kicker").textContent="GEMINI OBSERVATION";document.getElementById("policy-inspector-title").textContent=text(obs.proposal_id,"Accepted observation");document.getElementById("policy-inspector-subtitle").textContent=`Baseline epoch ${text(obs.baseline_policy_epoch)} · ${(obs.observed_at||"").replace("T"," ").slice(0,19)} · confidence ${fmt(obs.overall_confidence||0,0)}%`;
  const rows=Object.entries(obs.changes||{}).map(([name,r])=>`<div class="change"><div><strong>${esc(pretty(name))}</strong>${r?.rationale?`<div class="muted">${esc(r.rationale)}</div>`:""}</div><span>${esc(text(r?.current))}</span><span>→ ${esc(text(r?.proposed))}</span></div>`).join("")||`<div class="callout">This accepted observation recommended holding the current runtime controls.</div>`;
  const analysis=obs.analysis||{};const analysisParts=[];if((analysis.performance_diagnosis||[]).length)analysisParts.push(`<strong>Performance diagnosis</strong><br>${esc(analysis.performance_diagnosis.join(" · "))}`);if((analysis.responsiveness_diagnosis||[]).length)analysisParts.push(`<strong>Responsiveness</strong><br>${esc(analysis.responsiveness_diagnosis.join(" · "))}`);if((analysis.weaknesses_targeted||[]).length)analysisParts.push(`<strong>Targets</strong><br>${esc(analysis.weaknesses_targeted.join(" · "))}`);if(analysis.critic_verdict||analysis.critic_summary)analysisParts.push(`<strong>Critic</strong><br>${esc(text(analysis.critic_verdict))} — ${esc(text(analysis.critic_summary))}`);
  document.getElementById("policy-inspector-body").innerHTML=`${analysisParts.length?`<div class="callout">${analysisParts.join("<br><br>")}</div>`:`<div class="callout">This legacy observation predates durable Gemini-analysis storage. Atlas shows the confidence and proposed controls that were actually preserved and does not reconstruct missing prose.</div>`}<div class="label" style="margin-top:16px">Observed control recommendations</div><div class="changes" style="margin-top:8px">${rows}</div>`;modal.classList.add("open");
}

function openGeminiRunInspector(index){
  const runs=Array.isArray(state.llmCycle?.run_history)?[...state.llmCycle.run_history].reverse():[];
  const run=runs[index];if(!run)return;
  const modal=document.getElementById("policy-inspector-modal");if(!modal)return;
  document.getElementById("policy-inspector-kicker").textContent="GEMINI POLICY RUN";
  document.getElementById("policy-inspector-title").textContent=`Run #${text(run.run_number)} · ${pretty(run.outcome||run.status)}`;
  document.getElementById("policy-inspector-subtitle").textContent=`Baseline epoch ${text(run.baseline_policy_epoch)} · ${(run.completed_at||"").replace("T"," ").slice(0,19)} · ${fmt(run.overall_confidence||0,0)}% confidence`;
  const changes=Object.entries(run.changes||{}).map(([name,row])=>`<div class="change"><div><strong>${esc(pretty(name))}</strong>${row?.rationale?`<div class="muted">${esc(row.rationale)}</div>`:""}</div><span>${esc(text(row?.current))}</span><span>→ ${esc(text(row?.proposed))}</span></div>`).join("")||`<div class="callout">No material runtime mutation was proposed by this run.</div>`;
  const deferred=(run.deferred_locked_changes||[]).map(row=>{const name=row?.name||row?.control||row?.parameter||"position-sensitive control";return `<div class="change"><div><strong>${esc(pretty(name))}</strong><div class="muted">Deferred while existing-position policy locks remain authoritative.</div></div><span>${esc(text(row?.current))}</span><span>DEFERRED</span></div>`}).join("");
  const a=run.analysis||{};const parts=[];if((a.performance_diagnosis||[]).length)parts.push(`<strong>Performance</strong><br>${esc(a.performance_diagnosis.join(" · "))}`);if((a.responsiveness_diagnosis||[]).length)parts.push(`<strong>Responsiveness</strong><br>${esc(a.responsiveness_diagnosis.join(" · "))}`);if((a.weaknesses_targeted||[]).length)parts.push(`<strong>Targets</strong><br>${esc(a.weaknesses_targeted.join(" · "))}`);
  const consensus=run.consensus_observation_recorded?`Accepted consensus observation recorded · window became ${text(run.consensus_observation_count_after_run,0)} of ${text(run.consensus_minimum_observations,3)} minimum · ${text(run.consensus_control_count_after_run,0)} qualifying controls.`:"This run did not create an accepted consensus observation.";
  document.getElementById("policy-inspector-body").innerHTML=`<div class="callout"><strong>Outcome</strong> ${esc(pretty(run.outcome||run.status))}${run.autonomous_status?` · ${esc(pretty(run.autonomous_status))}`:""}<br><strong>Consensus</strong> ${esc(consensus)}${run.critic_verdict?`<br><strong>Critic</strong> ${esc(pretty(run.critic_verdict))}${run.critic_summary?` — ${esc(run.critic_summary)}`:""}`:""}</div>${parts.length?`<div class="callout" style="margin-top:10px">${parts.join("<br><br>")}</div>`:""}<div class="label" style="margin-top:16px">Proposed runtime changes</div><div class="changes" style="margin-top:8px">${changes}</div>${deferred?`<div class="label" style="margin-top:16px">Deferred locked changes</div><div class="changes" style="margin-top:8px">${deferred}</div>`:""}`;
  modal.classList.add("open");
}

function renderAtlas(){
  const p=state.proposal||{}, rs=p.review_summary||{}, ev=rs.shadow_evidence||{}, st=rs.stability||{};
  const lifecycle=p.lifecycle?.state||p.review_state;const applications=state.autoApplications||{};const active=applications.current_active||null;const consensus=state.autoConsensus||{};
  const runtime=applications.current_status_runtime&&Object.keys(applications.current_status_runtime).length?applications.current_status_runtime:(active?.runtime||applications.current_command_runtime||{});
  document.getElementById("runtime-policy-epoch").textContent=text(applications.current_status_epoch||active?.policy_epoch||applications.current_command_epoch);
  document.getElementById("runtime-policy-command").textContent=text(active?.command_version||state.command?.command_version);
  document.getElementById("runtime-policy-count").textContent=text(Object.keys(runtime||{}).length,0);
  const reconciliation=active?.reconciliation||((applications.current_status_epoch===applications.current_command_epoch)?"RUNTIME_CONFIRMED":"AWAITING_RUNTIME");
  document.getElementById("runtime-policy-reconciliation").textContent=pretty(reconciliation);const rb=document.getElementById("runtime-policy-badge");rb.textContent=pretty(reconciliation);rb.className="badge "+(String(reconciliation).includes("CONFIRMED")?"ok":String(reconciliation).includes("MISMATCH")?"bad":"warn");
  const activeChanges={};Object.entries(active?.changes||{}).forEach(([name,row])=>activeChanges[name]={current:row?.before,shadow:row?.registered??row?.intended});renderProposalChanges("runtime-policy-changes",activeChanges);
  const supporting=(state.policyObservations?.observations||[]).filter(o=>Number(o.baseline_policy_epoch)===Number(active?.baseline_policy_epoch));
  const integrity=String(active?.consensus_gate_integrity||"VERIFIED");
  document.getElementById("runtime-policy-rationale").textContent=active
    ? integrity==="LEGACY_BYPASS"
      ? `Epoch ${text(active.policy_epoch)} was applied from baseline epoch ${text(active.baseline_policy_epoch)} with only ${text(active.consensus_observation_count,0)} / ${text(active.consensus_minimum_observations,3)} accepted observations under the pre-1.30.43 autonomous-bootstrap bug. Atlas preserves this active runtime but will not permit the next mature-epoch mutation to bypass consensus.`
      : `Epoch ${text(active.policy_epoch)} was produced from baseline epoch ${text(active.baseline_policy_epoch)} using ${text(active.consensus_observation_count,0)} accepted observations. ${supporting.length?`${supporting.length} supporting observation records are available to inspect.`:"Older full Gemini prose is not reconstructed when it was not durably stored."}`
    : "No autonomous policy application is currently registered.";

  document.getElementById("a-candidate").textContent=text(p.selected_candidate);document.getElementById("a-readiness").textContent=pretty(lifecycle||"—");document.getElementById("a-epoch").textContent=text(p.current_policy_epoch??state.command?.policy_epoch);document.getElementById("a-confidence").textContent=rs.confidence==null?"—":fmt(rs.confidence,1)+"%";
  const llm=p.llm_policy||{},bundle=llm.bundle||{},critic=llm.critic||{};const diagnoses=bundle.performance_diagnosis||rs.performance_diagnosis||[];const weaknesses=bundle.weaknesses_targeted||rs.weaknesses_targeted||[];const speed=bundle.responsiveness_diagnosis||rs.responsiveness_diagnosis||[];
  document.getElementById("atlas-llm-evidence").innerHTML=llm.proposal_id?`<strong>Latest Gemini + critic analysis</strong><br>${esc((diagnoses.length?diagnoses:["No performance diagnosis supplied."]).join(" · "))}${speed.length?`<br><span class="muted">Responsiveness (${esc(text(bundle.responsiveness_profile||rs.responsiveness_profile))}): ${esc(speed.join(" · "))}</span>`:""}<br><span class="muted">Targets: ${esc((weaknesses.length?weaknesses:["not specified"]).join(" · "))} · Critic: ${esc(text(critic.verdict||rs.critic_verdict))} — ${esc(text(critic.summary||rs.critic_summary,"No summary"))}</span>`:"No Gemini analysis attached to the latest proposal.";
  const blockers=p.recommendation_blockers||[];document.getElementById("a-blockers").textContent=blockers.length?`Latest candidate blockers: ${blockers.map(pretty).join(" · ")}`:"Latest candidate has no recommendation blockers.";
  document.getElementById("a-risk").textContent=text(p.risk?.state||rs.risk_state);document.getElementById("a-evidence").textContent=text(ev.quality);document.getElementById("a-stability").textContent=st.stable?"STABLE":"NOT STABLE";document.getElementById("a-review-state").textContent=pretty(lifecycle||"—");

  const registry=document.getElementById("policy-registry-list");const apps=Array.isArray(applications.applications)?applications.applications:[];if(registry)registry.innerHTML=apps.length?apps.map(app=>{const isActive=Number(app.policy_epoch)===Number(applications.current_command_epoch);const changes=Object.entries(app.changes||{});const detail=changes.length?changes.slice(0,4).map(([n,r])=>`${pretty(n)} ${text(r?.before)} → ${text(r?.intended)}`).join(" · ")+(changes.length>4?` · +${changes.length-4} more`:""):"No material control patch recorded";const cls=String(app.reconciliation||"").includes("MISMATCH")?"bad":String(app.reconciliation||"").includes("CONFIRMED")?"ok":"warn";const integrity=String(app.consensus_gate_integrity||"VERIFIED");return `<div class="policy-record ${isActive?"active":""}" onclick="openPolicyInspector(${Number(app.policy_epoch)||0})"><div class="policy-record-head"><div><strong>Epoch ${esc(text(app.policy_epoch))}</strong>${isActive?` <span class="badge ok">ACTIVE</span>`:""}${integrity==="LEGACY_BYPASS"?` <span class="badge bad">PRE-FIX CONSENSUS BYPASS</span>`:""}</div><span class="badge ${cls}">${esc(pretty(app.reconciliation))}</span></div><div class="policy-record-meta"><span>Command ${esc(text(app.command_version))}</span><span>${esc((app.timestamp||"").replace("T"," ").slice(0,19))}</span><span>${esc(text(app.consensus_observation_count,0))} / ${esc(text(app.consensus_minimum_observations,3))} accepted observations</span></div><div class="policy-record-changes">${esc(detail)}</div></div>`}).join(""):`<div class="callout">No autonomous policy applications recorded yet.</div>`;

  const pc=document.getElementById("policy-consensus-summary");
  const consensusRows=Array.isArray(consensus.controls)
    ? consensus.controls
    : Object.entries(consensus.controls||{}).map(([name,row])=>({name,...(row||{})}));
  const consensusTotal=Number(consensus.observation_count||0);
  const consensusSupportThreshold=Number(consensus.minimum_support_ratio||.6);
  const consensusMinObservations=Number(consensus.minimum_observations||consensus.minimum_observation_count||0);
  if(pc){
    const readiness=Number(consensus.consensus_control_count||0)>0
      ?"One or more candidate controls have reached consensus."
      :"Atlas is still accumulating support; the runtime policy remains unchanged.";
    pc.innerHTML=`<div class="consensus-overview">
      <div><span class="label">Baseline policy</span><strong>Epoch ${esc(text(consensus.baseline_policy_epoch))}</strong></div>
      <div><span class="label">Accepted observations</span><strong>${esc(text(consensusTotal,0))}${consensusMinObservations?` of ${esc(text(consensusMinObservations))} minimum`:""}</strong></div>
      <div><span class="label">Support threshold</span><strong>${fmt(consensusSupportThreshold*100,0)}%</strong></div>
      <div><span class="label">Qualified controls</span><strong>${esc(text(consensus.consensus_control_count,0))}</strong></div>
    </div><div class="muted" style="margin-top:9px">${esc(readiness)}</div>`;
  }
  const pcr=document.getElementById("policy-consensus-controls");
  if(pcr){
    pcr.innerHTML=consensusRows.length?consensusRows.map((row,index)=>{
      const support=Number(row.support_count||0);
      const pct=consensusTotal?support/consensusTotal*100:0;
      const ready=Boolean(row.consensus_ready);
      const required=Math.max(1,Math.ceil(consensusTotal*consensusSupportThreshold));
      const supportGap=Math.max(0,required-support);
      const status=ready?"QUALIFIED":supportGap===0?"AWAITING WINDOW":"BUILDING SUPPORT";
      const gate=ready
        ?"Support and observation requirements are satisfied for this control."
        : supportGap===0
          ?"Support ratio is sufficient; another consensus requirement is still pending."
          : `${supportGap} more supporting observation${supportGap===1?"":"s"} needed at the current window size.`;
      const method=pretty(row.method||row.selection_method||"EXACT_TARGET");
      return `<article class="consensus-card ${ready?"ready":""}">
        <div class="consensus-card-head">
          <div><span class="label">Candidate control ${index+1}</span><strong>${esc(pretty(row.name||row.control||"Unnamed control"))}</strong><div class="muted">${esc(method)}</div></div>
          <span class="badge ${ready?"ok":"warn"}">${esc(status)}</span>
        </div>
        <div class="consensus-value-grid">
          <div><span class="label">Active runtime</span><strong>${esc(text(row.baseline??row.current))}</strong></div>
          <div><span class="label">Consensus candidate</span><strong>${esc(text(row.selected??row.proposed))}</strong></div>
        </div>
        <div class="consensus-support-block">
          <div class="consensus-support-line"><span>${support} / ${consensusTotal} observations support this value</span><strong>${fmt(pct,0)}%</strong></div>
          <div class="consensus-meter"><span style="width:${Math.min(100,pct)}%"></span></div>
        </div>
        <div class="consensus-gate"><strong>Gate</strong><span>${esc(gate)}</span></div>
      </article>`;
    }).join(""):`<div class="consensus-empty">No control mutations are currently accumulating consensus. The active runtime policy remains unchanged.</div>`;
  }

  const windowRoot=document.getElementById("policy-window-history");
  if(windowRoot){
    const windows=Array.isArray(consensus.recent_windows)?consensus.recent_windows:[];
    windowRoot.innerHTML=windows.length?`<div class="label" style="margin-top:14px">Policy learning windows</div><div class="policy-window-list">${windows.map(w=>{const produced=w.produced_policy_epoch;return `<div class="policy-window-row ${w.current_window?"current":""}"><div><strong>Baseline Epoch ${esc(text(w.baseline_policy_epoch))}${produced?` → Epoch ${esc(text(produced))}`:""}</strong><div class="muted">${esc(text(w.observation_count,0))} accepted observation${Number(w.observation_count)===1?"":"s"}${w.applied_at?` · applied ${esc(new Date(w.applied_at).toLocaleString())}`:""}</div></div><span class="badge ${w.current_window?"info":produced?"ok":"warn"}">${w.current_window?"CURRENT":produced?"PRODUCED POLICY":"ARCHIVED"}</span></div>`}).join("")}</div>`:"";
  }

  const runsRoot=document.getElementById("gemini-run-history");
  if(runsRoot){
    const runs=Array.isArray(state.llmCycle?.run_history)?[...state.llmCycle.run_history].reverse():[];
    runsRoot.innerHTML=runs.length?runs.map((run,i)=>{const changes=Object.keys(run.changes||{});const outcome=String(run.outcome||run.status||"UNKNOWN");const cls=outcome==="APPLIED"?"ok":outcome==="FAILED"||outcome==="REJECTED"?"bad":outcome==="DEFERRED"?"warn":"info";const obs=run.consensus_observation_recorded?`Observation ${text(run.consensus_observation_count_after_run,0)} / ${text(run.consensus_minimum_observations,3)}`:"No consensus observation";return `<div class="gemini-run-row" onclick="openGeminiRunInspector(${i})"><div class="gemini-run-head"><div><strong>Run #${esc(text(run.run_number))}</strong><div class="muted">Baseline Epoch ${esc(text(run.baseline_policy_epoch))} · ${esc((run.completed_at||"").replace("T"," ").slice(0,19))} · ${esc(pretty(run.trigger||"SCHEDULED"))}</div></div><span class="badge ${cls}">${esc(pretty(outcome))}</span></div><div class="gemini-run-meta"><span>${fmt(run.overall_confidence||0,0)}% confidence</span><span>${esc(obs)}</span><span>${changes.length?`${changes.length} proposed control${changes.length===1?"":"s"}`:"No material change"}</span>${run.critic_verdict?`<span>Critic ${esc(pretty(run.critic_verdict))}</span>`:""}</div></div>`}).join(""):`<div class="callout">Run-level lineage begins with Atlas 1.30.44. Earlier runs remain represented by accepted observations and applied-policy history where those records exist.</div>`;
  }

  const obsRoot=document.getElementById("policy-observation-list");const observations=state.policyObservations?.observations||[];if(obsRoot)obsRoot.innerHTML=observations.length?observations.map((o,i)=>{const ch=Object.entries(o.changes||{});return `<div class="observation-row" onclick="openObservationInspector(${i})"><div class="row"><div><strong>${esc(text(o.proposal_id,"Accepted Gemini observation"))}</strong><div class="muted">Baseline epoch ${esc(text(o.baseline_policy_epoch))} · ${esc((o.observed_at||"").replace("T"," ").slice(0,19))}</div></div><span class="badge info">${fmt(o.overall_confidence||0,0)}%</span></div><div class="observation-changes">${ch.length?ch.slice(0,5).map(([n,r])=>`<span class="observation-chip">${esc(pretty(n))}: ${esc(text(r.current))} → ${esc(text(r.proposed))}</span>`).join(""):`<span class="muted">Hold observation · no runtime mutation</span>`}</div></div>`}).join(""):`<div class="callout">No accepted Gemini observations have been recorded yet.</div>`;

  const approval=state.review?.approval||p.approval||{};const status=approval.status||"NOT_REQUESTED";const applied=["APPLIED","AWAITING_NYAO_ACK"].includes(String(lifecycle));const autonomous=state.llmCycle?.execution_mode==="AUTONOMOUS";const steps=[["Proposal",p.proposal_id?"READY":"WAITING"],["Review",status==="NOT_REQUESTED"?"WAITING":"DONE"],["Approval",status],["Command package",applied?lifecycle:state.supervised?"READY":"WAITING"]];document.getElementById("review-workflow").innerHTML=steps.map((x,i)=>`<div class="step ${["DONE","APPROVED","READY"].some(v=>String(x[1]).includes(v))?"done":""}"><div class="step-num">${i+1}</div><div><strong>${x[0]}</strong></div><span class="badge ${badgeClass(x[1])}">${esc(x[1])}</span></div>`).join("");document.getElementById("btn-request-review").disabled=autonomous||applied||!p.proposal_id||p.review_state!=="READY_FOR_HUMAN_REVIEW"||status!=="NOT_REQUESTED";document.getElementById("btn-approve").disabled=autonomous||applied||status!=="PENDING_APPROVAL";document.getElementById("btn-reject").disabled=autonomous||applied||status!=="PENDING_APPROVAL";document.getElementById("btn-build-command").disabled=autonomous||applied||status!=="APPROVED";
}

function renderParameterIntelligence(){
  const p=state.parameterIntel||{}, r=p.registry||{}, domains=p.domain_maturity||{};
  const count=document.getElementById("pi-count"); if(!count)return;
  count.textContent=text(r.parameter_count,157);
  document.getElementById("pi-locked").textContent=text(r.position_sensitive_count,53);
  document.getElementById("pi-budget").textContent=text(p.change_budget??r.change_budget,3);
  const autonomous=state.llmCycle?.execution_mode==="AUTONOMOUS";
  document.getElementById("pi-exec").textContent=autonomous?"ENABLED":"SUPERVISED";
  document.getElementById("pi-authority-note").textContent=autonomous
    ? "Historical value/outcome differences are descriptive associations, not causal proof. Gemini changes require critic acceptance, schema validation, confidence and dwell checks, a current policy epoch, and a clean mode boundary before Atlas can apply them."
    : "Historical value/outcome differences are descriptive associations, not causal proof. Gemini can propose validated numeric changes, but human approval and application remain required in supervised mode.";
  document.getElementById("pi-real-changes").textContent=text(p.current_advisor_change_count,0);
  document.getElementById("pi-noop").textContent=text(p.no_op_advisor_changes_filtered,0);

  document.getElementById("pi-domains").innerHTML=Object.entries(domains).map(([name,v])=>{
    const dist=v.distribution||{};
    const detail=`${text(v.mature_or_moderate_parameters,0)}/${text(v.parameter_count,0)} moderate+ · ${text(dist.MATURE,0)} mature`;
    return `<div class="change"><div><strong>${esc(pretty(name))}</strong><div class="muted">${esc(detail)}</div></div><span class="badge ${v.level==="MATURE"?"ok":v.level==="MODERATE"?"info":"warn"}">${esc(text(v.level))}</span></div>`
  }).join("")||`<div class="callout">No evidence maturity calculated yet.</div>`;

  const candidates=[...(p.supervised_candidates||[]),...(p.top_investigation_candidates||[])].slice(0,10);
  document.getElementById("pi-candidates").innerHTML=candidates.map(c=>{
    const maturity=c.parameter_maturity||{};
    const assoc=c.descriptive_association||{};
    const why=(c.why_relevant||[])[0]||"No direct relevance reason yet.";
    const caution=(c.why_not_change||[])[0]||"";
    const assocText=assoc.available?`${pretty(assoc.strength)} association · Δ mean P/L ${text(assoc.mean_pl_gap)}`:"no comparable value/outcome groups";
    return `<div class="change" style="align-items:flex-start">
      <div style="min-width:0">
        <strong>${esc(c.label||pretty(c.parameter))}</strong>
        <div class="muted">${esc(pretty(c.domain))} · ${esc(pretty(c.family||""))}${c.position_sensitive?" · policy locked":""}</div>
        <div class="muted" style="margin-top:5px">${esc(why)}</div>
        ${caution?`<div class="muted" style="margin-top:3px">Hold: ${esc(caution)}</div>`:""}
        <div class="muted" style="margin-top:3px">${esc(assocText)} · values ${esc(text(maturity.distinct_values,0))} · outcomes ${esc(text(maturity.outcomes_with_value,0))}</div>
      </div>
      <div style="text-align:right;flex:0 0 auto">
        <span class="badge ${c.action==="CURRENT_ADVISOR_PROPOSAL"?"ok":c.readiness==="WAIT_FOR_EVIDENCE"?"warn":"info"}">${esc(c.action==="CURRENT_ADVISOR_PROPOSAL"?"PROPOSED":c.readiness==="WAIT_FOR_EVIDENCE"?"WAIT":"INVESTIGATE")}</span>
        <div class="muted" style="margin-top:4px">${c.proposed!==null&&c.proposed!==undefined?`${esc(text(c.current))} → ${esc(text(c.proposed))}`:`score ${esc(text(c.relevance_score))}`}</div>
        <div class="muted">${esc(text(c.evidence_maturity))}</div>
      </div>
    </div>`
  }).join("")||`<div class="callout">No candidates yet.</div>`;
}
function renderControl(){
  const c=state.command||{}, arm=state.arm||{};
  const ab=document.getElementById("arm-badge");
  ab.textContent=arm.armed?"ARMED":"DISARMED";
  ab.className="badge "+(arm.armed?"ok":"bad");
  document.getElementById("arm-detail").textContent=arm.armed
    ? `Armed by ${text(arm.armed_by)} · ${Math.ceil(Number(arm.remaining_seconds||0)/60)} min remaining`
    : "Execution is fail-closed until explicitly armed.";
  document.getElementById("btn-arm").disabled=Boolean(arm.armed);
  document.getElementById("btn-disarm").disabled=!arm.armed;
  document.getElementById("c-version").textContent=text(c.command_version);
  document.getElementById("c-epoch").textContent=text(c.policy_epoch);
  document.getElementById("c-lot").textContent=text(c.base_lot_size);
  document.getElementById("c-enabled").textContent=c.enabled===false?"NO":"YES";
  const pkg=state.supervised?.supervised_command_proposal||state.supervised;
  const packageEvents=(state.executionEvents?.events||[]).filter(e=>e.supervised_command_id===pkg?.supervised_command_id);
  const completedEvent=packageEvents.find(e=>["EXECUTED","EXECUTED_RECOVERED"].includes(e.action));
  const ackEvent=packageEvents.find(e=>String(e.action||"").startsWith("NYAO_ACK_"));
  const packageLifecycle=ackEvent?.action==="NYAO_ACK_CONFIRMED"?"APPLIED":completedEvent?"AWAITING_NYAO_ACK":pkg?.state;
  const eb=document.getElementById("exec-badge");
  if(pkg?.supervised_command_id){eb.textContent=text(packageLifecycle);eb.className="badge "+badgeClass(packageLifecycle);
    document.getElementById("exec-summary").innerHTML=packageLifecycle==="APPLIED"
      ? `<strong>Policy applied and confirmed by Nyao</strong><br>Command ${esc(text(pkg.command_preview?.hypothetical_command_version))} / policy epoch ${esc(text(pkg.command_preview?.target_policy_epoch))} · package ${esc(pkg.supervised_command_id)}.`
      : `<strong>Command package ${esc(pkg.supervised_command_id)}</strong><br>Baseline ${esc(text(pkg.current_context?.baseline_command_version))} / epoch ${esc(text(pkg.current_context?.baseline_policy_epoch))} → command ${esc(text(pkg.command_preview?.hypothetical_command_version))} / epoch ${esc(text(pkg.command_preview?.target_policy_epoch))}.`;
  } else {eb.textContent="NO PACKAGE";eb.className="badge";document.getElementById("exec-summary").textContent="Build an approved command package from the Atlas page first."}
  const ex=state.execution, ack=state.ack;
  const executionState=ex?.status||(completedEvent?completedEvent.action:"WAITING");
  const ackMatchesExecution=Boolean(
    ack && completedEvent && ack.execution_id===completedEvent.execution_id
  );
  const ackState=ackMatchesExecution
    ? ack.state
    : ackEvent
      ? String(ackEvent.action).replace("NYAO_ACK_","")
      : "WAITING";
  const steps=[
    ["Package",pkg?"READY":"WAITING"],
    ["Preflight",(state.preflight?.ready_for_supervised_execution??state.preflight?.ready_for_explicit_demo_execution)?"PASS":"WAITING"],
    ["Execution",executionState],
    ["Nyao ACK",ackState]
  ];
  document.getElementById("exec-workflow").innerHTML=steps.map((x,i)=>`<div class="step ${badgeClass(x[1])==="ok"?"done":""}"><div class="step-num">${i+1}</div><div><strong>${x[0]}</strong></div><span class="badge ${badgeClass(x[1])}">${esc(text(x[1]))}</span></div>`).join("");
  document.getElementById("btn-preflight").disabled=!pkg||Boolean(completedEvent);
  document.getElementById("btn-execute").disabled=!pkg||Boolean(completedEvent);
  document.getElementById("btn-ack").disabled=!completedEvent||ackState==="CONFIRMED";
  document.getElementById("btn-execute").textContent=completedEvent?"Policy applied":"Execute policy";
  document.getElementById("btn-ack").textContent=ackState==="CONFIRMED"?"Nyao confirmed":"Refresh Nyao ACK";
  renderRiskAppetite();
}
function renderRiskAppetite(){
  const ra=state.riskAppetite||{};
  const capital=state.zonePlan?.capital_sizing||state.intelligence?.capital_sizing||state.intelligence?.capital||{};
  const pct=Number(ra.portfolio_hard_risk_pct??capital.risk_appetite?.portfolio_hard_risk_pct??1);
  const equity=Number(state.status?.equity||capital.equity||0);
  const hard=Number(capital.maximum_total_strategy_risk_amount||equity*pct/100);
  const operating=Number(capital.portfolio_allocation?.operating_risk_ceiling_amount||0);
  const badge=document.getElementById("risk-appetite-badge");
  if(!badge)return;
  badge.textContent=`${fmt(pct,2)}%`;
  badge.className="badge "+(pct>=10?"bad":pct>=5?"warn":"info");
  document.getElementById("risk-appetite-current").textContent=`${fmt(pct,2)}%`;
  document.getElementById("risk-appetite-amount").textContent=money(hard);
  document.getElementById("risk-appetite-operating").textContent=operating>0?money(operating):"—";
  const input=document.getElementById("risk-appetite-input");
  if(input && document.activeElement!==input)input.value=String(pct);
  const warning=document.getElementById("risk-appetite-warning");
  warning.textContent=pct>=10
    ?`HIGH RISK CEILING · ${fmt(pct,2)}% allows substantial simultaneous strategy risk. Atlas still scales the operating envelope and individual units independently.`
    :pct>=5
      ?`Elevated risk ceiling · ${fmt(pct,2)}%. This expands aggregate capacity, not per-trade risk. Atlas safety governors remain active.`
      :"Only you can increase this ceiling. Gemini and autonomous policy are not permitted to raise it.";
}
async function loadRiskAppetite(){
  try{state.riskAppetite=await api("/api/v1/atlas/risk-appetite")}catch(e){console.warn("Risk appetite refresh failed",e)}
}
async function saveRiskAppetite(){
  const input=document.getElementById("risk-appetite-input");
  const pct=Number(input?.value);
  if(!Number.isFinite(pct)||pct<1||pct>20)return toast("Risk ceiling must be between 1% and 20%.",true);
  const equity=Number(state.status?.equity||0);
  const amount=equity>0?equity*pct/100:0;
  const current=Number(state.riskAppetite?.portfolio_hard_risk_pct||1);
  const msg=pct>current
    ?`Increase Atlas maximum aggregate portfolio risk from ${fmt(current,2)}% to ${fmt(pct,2)}%${amount>0?` (about ${money(amount)} at current equity)`:""}?`
    :`Set Atlas maximum aggregate portfolio risk to ${fmt(pct,2)}%?`;
  if(!confirm(msg))return;
  try{
    state.riskAppetite=await api("/api/v1/atlas/risk-appetite",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({portfolio_hard_risk_pct:pct,actor:"Nobel"})});
    await loadIntelligence();
    renderAll();
    toast(`Portfolio hard risk ceiling set to ${fmt(pct,2)}%.`);
  }catch(e){toast(e.message,true)}
}
function renderControls(){
  const q=document.getElementById("control-search")?.value?.trim().toLowerCase()||"";
  const root=document.getElementById("runtime-controls");if(!root)return;
  root.innerHTML=CONTROL_CONFIG.map((g,gi)=>{
    const cs=(g.controls||[]).filter(c=>!q||(`${c.label} ${c.name}`).toLowerCase().includes(q));
    if(!cs.length)return"";
    return `<details class="control-group" ${q?"open":""}><summary>${esc(g.name)} <span class="muted">· ${cs.length}</span></summary><div class="control-grid">${cs.map(c=>controlHtml(c)).join("")}</div></details>`;
  }).join("");
  updateDirtyCount();
}
function controlHtml(c){
  const actual=state.dirty.hasOwnProperty(c.name)?state.dirty[c.name]:effectiveControl(c);
  let input="";
  if(c.kind==="bool"){input=`<select onchange="editControl('${c.name}',this.value==='true',this)"><option value="true" ${actual===true?"selected":""}>On</option><option value="false" ${actual===false?"selected":""}>Off</option></select>`}
  else if(c.kind==="select"){input=`<select onchange="editControl('${c.name}',Number(this.value),this)">${(c.options||[]).map(o=>`<option value="${o.value}" ${Number(actual)===Number(o.value)?"selected":""}>${esc(o.label)}</option>`).join("")}</select>`}
  else if(c.kind==="time"||c.kind==="string"){input=`<input value="${esc(text(actual,""))}" onchange="editControl('${c.name}',this.value,this)">`}
  else {input=`<input type="number" value="${esc(text(actual,""))}" min="${c.min??""}" max="${c.max??""}" step="${c.step??"any"}" onchange="editControl('${c.name}',Number(this.value),this)">`}
  return `<div class="control ${state.dirty.hasOwnProperty(c.name)?"dirty":""}"><label>${esc(c.label)}</label>${input}</div>`;
}
function effectiveControl(c){const s=state.status||{},cmd=state.command||{};return cmd[c.name]!==undefined?cmd[c.name]:s[c.status_key]}
function editControl(k,v,el){
  state.dirty[k]=v;
  const control=el?.closest(".control");
  if(control)control.classList.add("dirty");
  updateDirtyCount();
}
function updateDirtyCount(){const n=Object.keys(state.dirty).length;const e=document.getElementById("dirty-count");if(e)e.textContent=n?`${n} unsaved change${n===1?"":"s"}`:"No unsaved changes"}
function discardEdits(){state.dirty={};renderControls()}
async function applyEdits(){
  const n=Object.keys(state.dirty).length;
  if(!n)return toast("No runtime changes to apply.");
  if(!confirm(`Apply ${n} runtime change${n===1?"":"s"} through the Atlas command API?`))return;

  try{
    const result=await api("/api/v1/nyao/command",{
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(state.dirty)
    });

    state.command=result?.command||result;
    state.dirty={};

    // renderAll() intentionally avoids rebuilding the 157-control editor on
    // every polling refresh. After a successful save, force one rebuild so
    // dirty styling and the unsaved-change counter are cleared immediately.
    loadNotificationSettings();
    renderAll();
    renderControls();
    evaluateNotifications();

    toast("Runtime changes applied.");
  }catch(e){
    toast(e.message,true);
  }
}

async function loadReview(){
  const p=state.proposal;if(!p?.proposal_id){state.review=null;return}
  try{state.review=await api(`/api/v1/atlas/advisory-proposals/${p.proposal_id}/review`)}catch{state.review=null}
}
async function loadSupervised(){
  const proposalId=state.proposal?.proposal_id;
  if(!proposalId){state.supervised=null;return}
  try{
    const data=await api("/api/v1/atlas/supervised-command-proposals?limit=100");
    const rows=data.proposals||data.supervised_command_proposals||[];
    state.supervised=rows.find(x=>(x.source||{}).proposal_id===proposalId)||null;
  }catch(e){console.warn("Command package refresh failed",e)}
}
async function loadLlmCycle(){
  const results=await Promise.allSettled([
    api("/api/v1/atlas/llm/cycle-schedule"),
    api("/api/v1/atlas/llm/status"),
    api("/api/v1/atlas/autonomous-policy-consensus"),
    api("/api/v1/atlas/autonomous-policy-observations?limit=200")
  ]);
  if(results[0].status==="fulfilled")state.llmCycle=results[0].value;else console.warn("Gemini cycle refresh failed",results[0].reason);
  if(results[1].status==="fulfilled")state.llmStatus=results[1].value;else console.warn("Gemini status refresh failed",results[1].reason);
  if(results[2].status==="fulfilled")state.autoConsensus=results[2].value;else console.warn("Autonomous consensus refresh failed",results[2].reason);
  if(results[3].status==="fulfilled")state.policyObservations=results[3].value;else console.warn("Policy observation refresh failed",results[3].reason);
}
async function loadResponsiveness(){
  try{state.responsiveness=await api("/api/v1/atlas/scalping-responsiveness")}catch(e){console.warn("Responsiveness refresh failed",e)}
}
async function loadMarketCandles(){
  try{state.candles=await api("/api/v1/atlas/market-candles")}catch(e){console.warn("Market candle refresh failed",e)}
}
async function loadZoneMap(){
  try{state.zoneMap=await api("/api/v1/atlas/zone-map")}catch(e){console.warn("Zone map refresh failed",e)}
}
async function loadZonePlan(){
  try{state.zonePlan=await api("/api/v1/atlas/zone-execution-plan");state.zonePlanLoadedAt=Date.now()}catch(e){console.warn("Zone execution plan refresh failed",e)}
}
async function saveLlmCycleSchedule(){
  const interval=Number(document.getElementById("cycle-interval").value||240);
  const enabled=document.getElementById("cycle-enabled").checked;
  const execution_mode=document.getElementById("cycle-mode").value||"SUPERVISED";
  const minimum_dwell_minutes=Number(document.getElementById("cycle-dwell").value||interval);
  const minimum_confidence=Number(document.getElementById("cycle-confidence").value||70);
  try{
    state.llmCycle=await api("/api/v1/atlas/llm/cycle-schedule",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled,interval_minutes:interval,execution_mode,minimum_dwell_minutes,minimum_confidence})});
    renderAll();toast(enabled?`Gemini ${execution_mode.toLowerCase()} cycle scheduled every ${interval} minutes.`:"Gemini schedule disabled.");
  }catch(e){toast(e.message,true)}
}
async function runLlmCycleNow(){
  try{
    state.llmCycle=await jsonPost("/api/v1/atlas/llm/cycle-schedule/run-now",{});
    renderAll();toast(state.llmCycle.claimed?"Gemini policy analysis started.":pretty(state.llmCycle.reason),!state.llmCycle.claimed);
  }catch(e){toast(e.message,true)}
}
function reviewPayload(){
  const p=state.proposal;return {reviewer:"Nobel",note:"Atlas Operator Control Center",expected_runtime_fingerprint:p.runtime_fingerprint,expected_proposed_policy_epoch:p.proposed_policy_epoch}
}
async function requestReview(){try{await jsonPost(`/api/v1/atlas/advisory-proposals/${state.proposal.proposal_id}/request-review`,reviewPayload());await loadReview();renderAll();toast("Review requested.")}catch(e){toast(e.message,true)}}
async function approveCurrent(){try{await jsonPost(`/api/v1/atlas/advisory-proposals/${state.proposal.proposal_id}/approve`,reviewPayload());await loadReview();renderAll();toast("Proposal approved.")}catch(e){toast(e.message,true)}}
async function rejectCurrent(){try{await jsonPost(`/api/v1/atlas/advisory-proposals/${state.proposal.proposal_id}/reject`,reviewPayload());await loadReview();renderAll();toast("Proposal rejected.")}catch(e){toast(e.message,true)}}
async function buildSupervisedCommand(){
  const p=state.proposal, review=state.review?.approval||state.review||{};
  const hash=review.review_snapshot_hash||p.approval?.review_snapshot_hash;
  try{
    state.supervised=await jsonPost(`/api/v1/atlas/advisory-proposals/${p.proposal_id}/supervised-command-proposal`,{
      reviewer:"Nobel",note:"Atlas Operator Control Center command package",
      expected_runtime_fingerprint:p.runtime_fingerprint,expected_proposed_policy_epoch:p.proposed_policy_epoch,expected_review_snapshot_hash:hash
    });
    renderAll();go("control");toast("Supervised command package built.");
  }catch(e){toast(e.message,true)}
}
function pkg(){return state.supervised?.supervised_command_proposal||state.supervised}
async function loadArm(){
  try{state.arm=await api("/api/v1/atlas/supervised-execution-arm")}catch(e){console.warn(e)}
}
async function armExecution(){
  try{
    state.arm=await jsonPost("/api/v1/atlas/supervised-execution-arm",{
      actor:"Nobel",
      confirmation_phrase:"ARM_SUPERVISED_EXECUTION",
      minutes:30
    });
    renderAll();toast("Supervised execution armed for 30 minutes.");
  }catch(e){toast(e.message,true)}
}
async function disarmExecution(){
  try{
    state.arm=await jsonPost("/api/v1/atlas/supervised-execution-arm/disarm",{actor:"Nobel"});
    renderAll();toast("Supervised execution disarmed.");
  }catch(e){toast(e.message,true)}
}

async function runPreflight(){
  const p=pkg();if(!p)return;
  try{state.preflight=await api(`/api/v1/atlas/supervised-command-proposals/${p.supervised_command_id}/execution-preflight`);renderAll();toast((state.preflight.ready_for_supervised_execution??state.preflight.ready_for_explicit_demo_execution)?"Preflight passed.":"Preflight returned blockers.",!(state.preflight.ready_for_supervised_execution??state.preflight.ready_for_explicit_demo_execution))}
  catch(e){toast(e.message,true)}
}
function executePackage(){
  const p=pkg();if(!p)return;
  document.getElementById("modal-exec-summary").innerHTML=`Command <strong>${esc(text(p.command_preview?.hypothetical_command_version))}</strong> · Policy epoch <strong>${esc(text(p.command_preview?.target_policy_epoch))}</strong> · ${esc(text(p.command_preview?.runtime_control_count))} runtime controls.`;
  document.getElementById("confirm-modal").classList.add("show")
}
function closeModal(){document.getElementById("confirm-modal").classList.remove("show")}
async function confirmExecute(){
  const p=pkg();const s=p.source||{},ctx=p.current_context||{};
  try{
    state.execution=await jsonPost(`/api/v1/atlas/supervised-command-proposals/${p.supervised_command_id}/execute`,{
      actor:document.getElementById("modal-actor").value||"human_operator",
      note:"Atlas Operator Control Center execution",
      confirmation_phrase:"EXECUTE_SUPERVISED_COMMAND",
      allow_test_override_execution:Boolean(s.test_override_active),
      expected_source_proposal_id:s.proposal_id,
      expected_runtime_fingerprint:s.runtime_fingerprint,
      expected_target_policy_epoch:s.proposed_policy_epoch,
      expected_review_snapshot_hash:s.review_snapshot_hash,
      expected_baseline_command_version:ctx.baseline_command_version,
      expected_baseline_policy_epoch:ctx.baseline_policy_epoch
    });
    closeModal();
    await reconcileAuthoritativeState();
    renderAll();renderControls();toast("Policy execution completed. Atlas state refreshed; waiting for Nyao acknowledgement.");
  }catch(e){toast(e.message,true)}
}
function currentExecutionId(){
  if(state.execution?.execution_id)return state.execution.execution_id;
  const p=pkg();
  const event=(state.executionEvents?.events||[]).find(e=>e.supervised_command_id===p?.supervised_command_id&&["EXECUTED","EXECUTED_RECOVERED"].includes(e.action));
  return event?.execution_id||null;
}
async function reconcileAuthoritativeState(){
  await loadCore();
  await loadHistory();
  await loadProposal();
  await Promise.all([loadArm(),loadParameterIntelligence(),loadIntelligence(),loadResponsiveness(),loadMarketCandles(),loadZoneMap(),loadZonePlan()]);
}
async function refreshAck(){
  const executionId=currentExecutionId();if(!executionId)return;
  try{state.ack=await jsonPost(`/api/v1/atlas/supervised-executions/${executionId}/nyao-ack/refresh`,{});await reconcileAuthoritativeState();renderAll();renderControls();toast("Nyao acknowledgement: "+state.ack.state,badgeClass(state.ack.state)==="bad")}
  catch(e){toast(e.message,true)}
}

function renderHistory(){
  const a=state.audit||{};document.getElementById("h-audit").textContent=a.valid===true?"VALID":"—";document.getElementById("h-audit-count").textContent=a.checked_event_count==null?"—":`${a.checked_event_count} chained events`;
  const eps=state.epochs?.epochs||state.epochs?.policy_epochs||[];document.getElementById("h-epochs").textContent=Array.isArray(eps)?eps.length:text(state.epochs?.count);
  const outs=state.outcomes?.outcomes||state.outcomes?.closed||[];document.getElementById("h-outcomes").textContent=Array.isArray(outs)?outs.length:text(state.outcomes?.count);
  const events=state.executionEvents?.events||[];
  document.getElementById("execution-events").innerHTML=events.slice(0,16).map(e=>`<div class="event"><span class="muted">${esc((e.timestamp||"").replace("T"," ").slice(0,19))}</span><div><strong>${esc(pretty(e.action))}</strong><div class="muted mono">${esc(text(e.execution_id))}</div></div><span class="badge ${badgeClass(e.action)}">${esc(text(e.sequence))}</span></div>`).join("")||`<div class="callout">No execution events.</div>`;
  document.getElementById("policy-epochs").innerHTML=(Array.isArray(eps)?eps.slice(-12).reverse():[]).map(e=>`<div class="event"><span class="muted">${esc(text(e.created_at||e.registered_at||""))}</span><div><strong>Epoch ${esc(text(e.policy_epoch??e.epoch))}</strong><div class="muted">Command ${esc(text(e.applied_command_version??e.command_version))}</div></div><span class="badge info">${esc(text(e.runtime_control_count??157))}</span></div>`).join("")||`<div class="callout">No policy epochs returned.</div>`;
  document.getElementById("raw-diagnostics").textContent=JSON.stringify({audit:state.audit,latest_execution:events[0]||null,command:{command_version:state.command?.command_version,policy_epoch:state.command?.policy_epoch},status:{applied_command_version:state.status?.applied_command_version,policy_epoch:state.status?.policy_epoch}},null,2)
}
function renderAll(){updateChrome();renderOverview();renderOpportunityQueue();renderDecisionTimeline();renderLiveAnalysis();renderAnalysis();renderPositions();renderLlmCycle();renderAutonomousConsensus();renderResponsiveness();renderAtlas();renderParameterIntelligence();renderControl();renderHistory();if(!document.getElementById("runtime-controls").children.length)renderControls()}

async function loadCore(){
  const before=`${state.command?.command_version??""}:${state.command?.policy_epoch??""}:${state.status?.applied_command_version??""}:${state.status?.policy_epoch??""}`;
  const [status,command]=await Promise.allSettled([api("/api/v1/nyao/status"),api("/api/v1/nyao/command")]);
  if(status.status==="fulfilled")state.status=status.value;
  if(command.status==="fulfilled")state.command=command.value;
  const after=`${state.command?.command_version??""}:${state.command?.policy_epoch??""}:${state.status?.applied_command_version??""}:${state.status?.policy_epoch??""}`;
  return before!==after;
}
async function loadIntelligence(){
  try{state.intelligence=await api("/api/v1/atlas/intelligence")}catch(e){console.warn("Intelligence refresh failed",e)}
}
async function loadParameterIntelligence(){
  try{state.parameterIntel=await api("/api/v1/atlas/parameter-intelligence")}catch(e){console.warn("Parameter intelligence refresh failed",e)}
}
async function loadProposal(){
  try{const d=await api("/api/v1/atlas/advisory-proposal");state.proposal=d.proposal||d;await Promise.all([loadReview(),loadSupervised()])}catch(e){console.warn(e)}
}
async function loadHistory(){
  const rs=await Promise.allSettled([
    api("/api/v1/atlas/supervised-execution-events?limit=100"),
    api("/api/v1/atlas/supervised-execution-events/verify"),
    api("/api/v1/atlas/policy-epochs?limit=100"),
    api("/api/v1/atlas/outcomes?closed_limit=100&include_active=true"),
    api("/api/v1/atlas/policy-performance"),
    api("/api/v1/atlas/autonomous-policy-applications?limit=50"),
    api("/api/v1/atlas/risk-units"),
    api("/api/v1/atlas/recovery-attribution"),
    api("/api/v1/atlas/recovery-risk")
  ]);
  if(rs[0].status==="fulfilled")state.executionEvents=rs[0].value;
  if(rs[1].status==="fulfilled")state.audit=rs[1].value;
  if(rs[2].status==="fulfilled")state.epochs=rs[2].value;
  if(rs[3].status==="fulfilled")state.outcomes=rs[3].value;
  if(rs[4].status==="fulfilled")state.performance=rs[4].value;
  if(rs[5].status==="fulfilled")state.autoApplications=rs[5].value;
  if(rs[6].status==="fulfilled")state.riskUnits=rs[6].value;
  if(rs[7].status==="fulfilled")state.recoveryAttribution=rs[7].value;
  if(rs[8].status==="fulfilled")state.recoveryRisk=rs[8].value;
}
async function boot(){
  // Restore operator notification preferences before the first live render.
  // The controls persist in browser localStorage and must survive refreshes.
  loadNotificationSettings();
  try{
    await loadSymbols();
    await loadCore();
    await loadRiskAppetite();
    await loadIntelligence();
    await loadParameterIntelligence();
    await loadArm();
    await loadLlmCycle();
    await loadResponsiveness();
    await loadMarketCandles();
    await Promise.all([loadZoneMap(),loadZonePlan()]);
    await loadProposal();
    await loadHistory();
    renderAll();
    renderControls();
    // Establish decision history baseline only after all authoritative state is loaded.
    state.decisionBaseline=decisionSnapshot();
  }catch(e){toast(e.message,true)}

  setInterval(async()=>{const changed=await loadCore();await loadArm();if(changed){await loadHistory();await loadProposal()}renderAll();evaluateNotifications();evaluateDecisionTimeline()},2000);
  setInterval(async()=>{await loadIntelligence();renderAll()},5000);
  setInterval(async()=>{await loadLlmCycle();renderAll();evaluateDecisionTimeline()},5000);
  setInterval(async()=>{await loadResponsiveness();renderAll()},15000);
  setInterval(async()=>{await loadMarketCandles();renderAll()},15000);
  setInterval(async()=>{await loadZoneMap();renderAll()},15000);
  setInterval(async()=>{await loadZonePlan();renderAll();evaluateDecisionTimeline()},5000);
  setInterval(async()=>{await loadParameterIntelligence();renderAll()},10000);
  setInterval(async()=>{await loadSymbols();await loadProposal();renderAll()},10000);
  setInterval(async()=>{await loadHistory();renderAll();evaluateDecisionTimeline()},15000);
  setInterval(()=>{if(state.zonePlan?.capital_sizing?.loss_protection?.state==="HARD_VETO"){const lp=state.zonePlan.capital_sizing.loss_protection;const loaded=Number(state.zonePlanLoadedAt||Date.now());lp.remaining_seconds=Math.max(0,Number(lp.remaining_seconds||0)-(Date.now()-loaded)/1000);state.zonePlanLoadedAt=Date.now();renderOverview();}},1000);
}
boot();
</script>
</body>
</html>
"""


ASSET_DIR = Path(__file__).resolve().parent / "assets"


@app.get("/assets/{asset_name}")
def atlas_asset(asset_name: str):
    allowed = {
        "atlas-favicon.png",
        "atlas-sidebar-icon.png",
        "atlas-app-icon.png",
    }
    if asset_name not in allowed:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(ASSET_DIR / asset_name, media_type="image/png")


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
