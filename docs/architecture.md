# Atlas System Architecture

**Current release:** Atlas **1.30.19** · Nyao **44.3** · Capital engine **atlas-capital-regime-v2.0**

Atlas is an adaptive trading-intelligence and deterministic risk-control platform. Atlas owns market interpretation, strategy policy, portfolio capital authority, composite risk accounting, durable evidence and operator controls; Nyao is the MetaTrader 5 execution layer and retains final broker-side feasibility and order execution authority.

The design objective is not simply to trade more often. Atlas is intended to continuously evaluate opportunities, avoid wasting valid capacity, and execute whenever an opportunity is justified **without allowing speed or concurrency to bypass deterministic risk authority**.

## 1. Runtime boundary

```text
Market / MT5 broker state
        │
        ▼
┌──────────────────────────┐
│ Nyao 44.3 · MT5 Executor │
│ signals · orders · fills │
│ broker math · positions  │
└─────────────┬────────────┘
              │ status / positions / deals
              ▼
┌──────────────────────────────────────────┐
│ Atlas 1.30.19                            │
│                                          │
│ deterministic market intelligence       │
│ capital regime + portfolio allocator     │
│ spread / structure economics            │
│ zone planning                            │
│ composite risk units                     │
│ recovery authority + durable ledger      │
│ policy epochs + outcomes                 │
│ Gemini analyst / critic                  │
│ operator settings and dashboard          │
└─────────────┬────────────────────────────┘
              │ validated command / policy
              ▼
┌──────────────────────────┐
│ Nyao execution preflight │
│ OrderCalcProfit / Check  │
│ broker volume / stops    │
└─────────────┬────────────┘
              ▼
            MT5
```

### Authority model

| Authority | Owner | Rule |
|---|---|---|
| Operator portfolio risk appetite | Operator | 1–20% aggregate hard ceiling; Atlas/Gemini may reduce but cannot raise it |
| Market/regime interpretation | Atlas | Deterministic evidence plus policy context |
| Scalp policy optimization | Atlas + Gemini | Gemini proposes/criticizes within schemas; hard risk remains deterministic |
| Zone construction | Atlas | Deterministic candle/structure evidence; Gemini cannot invent zones |
| Capital allocation | Atlas | Concurrent reservation-based allocator |
| Recovery-chain ceiling | Atlas/Nyao contract | Frozen per risk unit; recovery cannot borrow unused portfolio capacity |
| Broker feasibility | Nyao/MT5 | Final volume, stops, OrderCheck/OrderCalcProfit and execution truth |
| Realized P/L | MT5 | Authoritative exit deals |

## 2. Capital architecture

Atlas separates risk appetite from actual deployment. A configured 20% ceiling does **not** mean a 20% trade.

```text
OPERATOR HARD CEILING (1–20%)
              │
              ▼
ATLAS DETERMINISTIC MODIFIERS
(drawdown · loss state · market risk · volatility)
              │
              ▼
CURRENT OPERATING CEILING
              │
              ├── minus recovery-chain reservations
              ├── minus standalone downside reservations
              ├── minus zone-campaign reservations
              └── minus working-order reservations
              │
              ▼
REMAINING OPERATING CAPACITY
              │
       ┌──────┴──────┐
       ▼             ▼
  SCALP CANDIDATE   ZONE CANDIDATE
       │             │
       └──── broker / structure / cost / concentration gates ────► execute
```

### P3.31 concurrent portfolio allocation

Before P3.31, any strategy exposure forced fresh risk to zero. Atlas now uses deterministic reservations instead:

- existing exposure **reserves risk** but does not automatically veto unrelated opportunities;
- recovery chains reserve their **full frozen chain ceiling**;
- standalone positions reserve remaining downside to their broker stop;
- positions whose stops have moved to break-even or locked profit release unused downside capacity;
- working orders reserve capacity before execution so Atlas cannot double-promise capital;
- same-symbol active risk receives **no diversification credit**;
- hard protection states can still veto all fresh risk.

Allocation states exposed to the dashboard are `AVAILABLE`, `PARTIALLY_ALLOCATED`, `FULLY_ALLOCATED`, and hard protection/veto states.

### P3.31.1 configurable risk appetite

The Settings page persists an operator-owned `portfolio_hard_risk_pct` from **1% to 20%**, default **1%**. This setting controls aggregate portfolio authority only. Per-opportunity scalp/zone sizing continues to come from the capital regime and current risk modifiers.

## 3. Composite risk-unit model

Strategic performance and loss protection operate on **risk units**, not blindly on MT5 tickets.

```text
STANDALONE_TRADE
  └── one position

RECOVERY_CHAIN
  ├── root
  ├── hedge child 1
  ├── hedge child 2 ...
  └── scored once when the whole chain is flat

ZONE_CAMPAIGN
  ├── layer 1
  ├── layer 2
  ├── layer 3
  └── scored once when the whole campaign is flat
```

Rules:

- member exits inside an active recovery chain or zone campaign are provisional;
- active composite units never increment a completed-loss streak;
- when all members close, Atlas sums authoritative MT5 realized P/L and creates one `WIN`, `LOSS`, or `FLAT`;
- a composite win resets the strategic loss streak;
- a composite loss increments it once;
- a flat unit preserves the prior streak;
- policy performance is attributed to the frozen/root lineage rather than each child ticket independently.

## 4. Recovery risk architecture

Recovery is permitted to manage an existing risk unit, but it is not permitted to become an unbounded martingale.

```text
root admitted risk
      │
      ▼
original unit risk
      │ × recovery envelope (currently 1.5× baseline)
      ▼
frozen chain ceiling
      │
      ├── raw recovery lot requirement
      ├── broker min/max/step
      ├── current chain loss / remaining capacity
      └── OrderCheck / OrderCalcProfit
      │
      ▼
capital-safe recovery lot or deterministic rejection
```

The recovery ledger persists sizing/adoption decisions so a later idle tick cannot erase why a hedge was authorized. On restart, an already-active pre-ledger chain is conservatively adopted into a finite ceiling before any additional expansion can occur.

Important recovery reason families include `ATLAS_CHAIN_RISK_CAP`, `RECOVERY_RISK_BUDGET_INFEASIBLE`, `RECOVERY_CHAIN_BUDGET_UNRESOLVED`, and `ACTIVE_RECOVERY_CHAIN_ADOPTED`.

## 5. Transaction-cost and market-structure economics

P3.29 removed the assumption that one static spread threshold is intelligent across instruments. For each scalp opportunity Atlas/Nyao separate:

1. **cost-ratio feasibility** — spread relative to planned stop/target;
2. **market-structure feasibility** — whether satisfying the cost would distort the setup beyond acceptable ATR/base geometry;
3. **capital feasibility** — whether the final structure fits the approved risk amount and broker minimum volume.

A large BTC spread therefore does not create a permanent symbol ban. The opportunity is rejected when the required geometry is economically or structurally unreasonable, e.g. `SCALP_COST_STRUCTURE_MISMATCH` / `STOP_EXPANSION_EXCESSIVE`.

## 6. Outcome truth and lineage

MT5 deal history is the source of truth for realized P/L. Atlas reconstructs and preserves entry lineage so restarts and broker-side exits do not destroy strategic attribution.

Current lineage mechanisms include:

- entry policy epoch;
- `FRESH_MARKET`, `HEDGE_CHILD`, reconstructed-history and zone origin;
- immutable recovery entry lineage (`H|<chain>|<level>|<epoch>` for new-format children);
- immutable zone lineage (`AZ|<plan>|L<layer>|P<epoch>` for new-format zone legs);
- conservative legacy inference only when lifecycle/policy evidence is strong enough.

## 7. Primary API surfaces

Representative runtime endpoints:

```text
GET /api/v1/nyao/status?symbol=<SYMBOL>
GET /api/v1/atlas/capital-sizing?symbol=<SYMBOL>
GET /api/v1/atlas/risk-units?symbol=<SYMBOL>
GET /api/v1/atlas/recovery-risk?symbol=<SYMBOL>
GET /api/v1/atlas/risk-appetite?symbol=<SYMBOL>
PUT /api/v1/atlas/risk-appetite?symbol=<SYMBOL>
GET /api/v1/atlas/outcomes?symbol=<SYMBOL>
GET /api/v1/atlas/outcomes/summary?symbol=<SYMBOL>
GET /api/v1/atlas/policy-epochs?symbol=<SYMBOL>
GET /api/v1/atlas/policy-performance?symbol=<SYMBOL>
```

## 8. Current phase map

| Phase | Capability | Status |
|---|---|---|
| P3.28 | Authoritative MT5 outcome ingestion and entry attribution | Implemented / live verified |
| P3.29 | Dynamic cost + structure-aware scalp economics | Implemented / live verified |
| P3.30 | Composite recovery risk units | Implemented / live verified |
| P3.30.1 | Exit-lineage repair | Implemented / live verified |
| P3.30.2 | Zone-campaign composite units | Implemented / live verified |
| P3.30.3 | Durable recovery budget ledger | Implemented |
| P3.30.4 | Active recovery-chain adoption after restart | Implemented / live verified |
| P3.31 | Concurrent portfolio risk allocation | Implemented / live verified |
| P3.31.1 | Operator-configurable 1–20% portfolio risk appetite | Implemented / live verified |

## 9. Deployment and safety boundary

- Keep repository `data/` account evidence across upgrades; do not overwrite live history with packaged sample/runtime data.
- Recompile `external/nyao/nyao_scalper.mq5` only when the Nyao version changes. Atlas-only UI/backend releases do not require MetaEditor compilation.
- Nyao remains final broker execution authority. Atlas percentages do not bypass broker minimum volume, stop constraints, margin checks, `OrderCheck`, or `OrderCalcProfit`.
- High leverage changes margin availability, not Atlas's permitted monetary loss.
- The operator risk-appetite ceiling is an upper boundary, not a deployment target.

---

## Appendix A — Atlas ↔ Nyao Runtime Control Inventory

The inventory below is retained as the low-level control contract. It documents runtime-controllable Nyao inputs and their corresponding status telemetry.

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