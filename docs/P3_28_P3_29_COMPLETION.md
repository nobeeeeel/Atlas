# Atlas P3.28–P3.29 Completion Pass

## Versions
- Atlas backend/dashboard: 1.30.12
- Nyao source: 43.7

## P3.28 completion
- Preserves Nyao entry-side MT5 history metadata through the Python bridge:
  - entry_order_ticket
  - entry_time_epoch / entry_time_msc
  - entry_price / entry_volume
  - original_position_type
  - entry_comment
  - entry_policy_epoch
- Status, position, and exit-deal telemetry models now preserve forward-compatible unknown producer fields instead of silently dropping them.
- Existing exact-once/recovery outcome logic remains intact and the P3.28.0–P3.28.4 regression scripts pass.
- Added API/bridge round-trip coverage proving P3.28 metadata survives POST -> status.json -> GET.

## P3.29 completion
The ordinary scalp lane no longer treats spread as only a post-hoc hard veto.

### Dynamic trade construction
1. Read the live executable spread.
2. Resolve the strategy's base SL/TP structure.
3. Keep `MaxSpreadPoints` only as an emergency outer ceiling when non-zero.
4. If the normal spread is too large relative to the base payoff geometry, widen the planned structure so that:
   - spread <= 20% of planned stop distance
   - spread <= 15% of planned target distance
   - a 10% spread headroom buffer is included
5. Preserve configured risk:reward after stop widening.
6. Build broker-valid executable prices.
7. Recalculate Atlas capital sizing against the widened stop.
8. If broker minimum lot / capital risk cannot fund the widened structure, block with `SCALP_COST_RISK_BUDGET_INFEASIBLE` rather than a misleading generic spread block.
9. Recheck live spread against the final executable geometry immediately before OrderSend.

### New telemetry
- scalp_cost_gate_version = nyao-scalp-cost-v3
- scalp_cost_gate_basis
- scalp_cost_limiting_factor
- scalp_cost_adjusted
- scalp_cost_feasible
- scalp_cost_headroom_multiplier
- scalp_base_stop_points / scalp_base_target_points
- scalp_planned_stop_points / scalp_planned_target_points
- scalp_spread_to_stop_ratio / scalp_spread_to_target_ratio
- scalp_max_spread_stop_ratio / scalp_max_spread_target_ratio

## BTC example from the supplied live status
Using the supplied #BTCUSD sample:
- spread = 60,950 points (~$60.95 when point = 0.001)
- old effective economic cap = 1,101.83 points (~$1.10)
- inferred base stop ~= 5,509.15 points (~$5.51)

With v2 adaptive construction and 10% headroom:
- planned stop floor ~= 335,225 points (~$335.23)
- planned target (1.5R) ~= 502,837.5 points (~$502.84)
- economic cap from stop ~= 67,045 points (~$67.05)
- 60,950 spread points can therefore pass the cost geometry check, subject to signal eligibility, Atlas risk sizing, broker minimum lot, margin, and final OrderCheck.

This makes BTC eligibility dynamic rather than permanently blocked by a tiny ATR-derived structure while still refusing trades that cannot be funded safely.

## Verification run
Passing checks:
- Python compile: schemas.py, main.py, outcomes.py
- P3.28/P3.29 bridge round trip
- P3.28/P3.29 API status round trip
- P3.28 lossless deal/policy history
- P3.28.1 capital recovery/sizing baseline
- P3.28.2 policy-adapted recovery
- P3.28.3 policy recovery handoff
- P3.28.4 recovery probe evidence
- P3.29 scalp cost economics
- P3.29 scalp cost feasibility
- Dashboard JavaScript syntax regression

## Deployment note
`external/nyao/nyao_scalper.ex5` is a previously compiled binary. This environment has no MetaEditor/MQL5 compiler, so compile `external/nyao/nyao_scalper.mq5` locally in MetaEditor before running Nyao 43.7 in MT5.

## P3.29 v3 — structure-aware transaction-cost economics

Atlas/Nyao now separates three independent truths for ordinary scalp entries:

1. **Transaction-cost feasibility** — spread versus the proposed stop/target economics.
2. **Market-structure feasibility** — whether the spread-driven adaptation still resembles the market setup that generated the scalp signal.
3. **Fresh-risk availability** — capital, loss-protection and existing-exposure ownership.

The v2 adaptive economics could technically make a large spread affordable by widening SL/TP dramatically. v3 adds dimensionless, volatility-aware structure constraints so a quiet-market scalp cannot be transformed into a hundreds-of-ATR position merely to accommodate spread.

New telemetry includes:

- `scalp_cost_ratio_feasible`
- `scalp_structure_feasible`
- `scalp_structure_reason`
- `scalp_stop_expansion_ratio`
- `scalp_target_expansion_ratio`
- `scalp_planned_stop_atr_ratio`
- `scalp_spread_atr_ratio`
- `scalp_max_stop_expansion_ratio`
- `scalp_max_stop_atr_ratio`
- `scalp_max_spread_atr_ratio`

A structure failure blocks the entry with `SCALP_COST_STRUCTURE_MISMATCH_<reason>`. This is not a fixed BTC/USD price-spread ban: a high-spread symbol can pass when its genuine ATR and base trade geometry are large enough to support the transaction cost.

### Recovery-probe UI clarification

When a reduced-risk recovery probe is live, existing exposure intentionally owns the fresh-risk budget until that probe closes. The dashboard now labels this as `RECOVERY PROBE · IN FLIGHT` (or `EXPOSURE LOCK` for ordinary exposure-only cases) rather than presenting it as a generic hard `CAPITAL VETO`.

A winning recovery probe breaks the qualifying loss streak and resets protection. A losing probe increments the streak and escalates the durable protection stage. No additional independent fresh-risk position is stacked while the probe is unresolved.

### Revision

- Atlas backend/dashboard: `1.30.12`
- Nyao source: `43.7`
- Scalp cost gate: `nyao-scalp-cost-v3`
