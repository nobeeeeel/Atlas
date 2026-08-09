# P3.30 — Composite Recovery Risk & Risk-Unit Outcomes

## Purpose

P3.30 closes two recovery-governance gaps discovered during live `#BTCUSD` testing:

1. recovery hedge auto-sizing could optimize for rapid loss recovery and then clamp only to `hedge_max_lot`, without an Atlas capital-risk preflight; and
2. loss protection could treat a losing member of an active hedge chain as an independent completed loss even though another chain member could later recover the chain.

## Strategic outcome rule

Atlas now scores **risk units**, not blindly individual MT5 tickets.

- `STANDALONE_TRADE`: one ticket = one strategic outcome.
- `RECOVERY_CHAIN`: root + all hedge/recovery children = one strategic outcome.
- `ZONE_CAMPAIGN`: all campaign legs sharing a zone plan = one strategic outcome.

A composite risk unit is **provisional while any member remains active**. Member closures continue to be recorded exactly for execution diagnostics, but they do not increment/reset the strategic loss streak and do not independently decide recovery-probe success/failure.

When the whole unit is flat, Atlas sums authoritative realised MT5 P/L (falling back only for legacy inferred records) and emits one `WIN`, `LOSS`, or `FLAT` result. `FLAT` preserves the previous loss streak.

## Recovery sizing authority

Nyao 43.9 keeps the recovery-loss-aware auto-lot calculation, but the requested lot now passes through an Atlas recovery-risk cap before `OrderSend`.

The effective recovery chain hard-loss budget is the tightest positive value among:

- configured `hedge_max_chain_loss_usd`,
- configured `hedge_max_chain_loss_pct`, and
- Atlas `maximum_total_strategy_risk_pct` of live equity.

If Atlas capital sizing is active and no finite recovery budget is available, a new recovery hedge is rejected.

The lot cap uses the same recovery horizon used by auto-sizing. The recovery child may exceed the older leg only when the resulting net delta can move one recovery horizon against the hedge while remaining inside the chain's remaining risk capacity. The cap is rounded **down** to broker volume step.

The recovery path also performs `OrderCheck` before `OrderSend`.

## Hard chain stop

`ChainLossStopThreshold()` now always includes Atlas maximum total strategy risk. Zero recovery-specific limits no longer imply an unbounded active hedge chain when Atlas capital authority is present.

## Live telemetry

Nyao publishes:

- `recovery_sizing_version`
- `recovery_sizing_reason`
- `recovery_requested_lot`
- `recovery_capital_capped_lot`
- `recovery_final_lot`
- `recovery_anchor_loss_usd`
- `recovery_chain_budget_usd`
- `recovery_remaining_budget_usd`
- `recovery_target_move_price`
- `recovery_estimated_adverse_risk_usd`

Important reasons include:

- `RECOVERY_REQUEST_ACCEPTED`
- `RECOVERY_MAX_LOT_CAP`
- `ATLAS_CHAIN_RISK_CAP`
- `RECOVERY_RISK_BUDGET_EXHAUSTED`
- `RECOVERY_RISK_BUDGET_INFEASIBLE`
- `RECOVERY_ATLAS_BUDGET_UNAVAILABLE`
- `RECOVERY_NO_NET_POWER_AFTER_RISK_CAP`
- `RECOVERY_ORDER_CHECK_FAILED`

## New APIs

- `GET /api/v1/atlas/risk-units`
- `GET /api/v1/atlas/capital-sizing`
- `GET /api/v1/atlas/recovery-risk`

Policy performance now uses completed strategic risk units rather than counting recovery legs independently.

## Recovery attribution repair

A normal `FRESH_MARKET` root whose ticket is the chain ID is now recognized as the root after it closes. Closed member P/L uses authoritative MT5 realised P/L when available.

## Dashboard

Protection Status now shows:

- completed risk-unit loss streak,
- recovery sizing result/limiter,
- active composite risk units,
- recovery hard-loss budget and remaining capacity.

Recovery-probe copy explicitly states that individual hedge-chain member exits are provisional and that only the final composite result can break or escalate loss protection.

## Versions

- Atlas backend/dashboard: `1.30.14`
- Capital sizing: `atlas-capital-regime-v1.8`
- Loss-protection durable state: v4
- Nyao source: `43.9`
- Recovery sizing telemetry: `nyao-recovery-risk-v1`

## Validation

Targeted regression gate covers P3.28 through P3.30, including:

- authoritative deal history and entry-policy attribution,
- policy-adapted recovery,
- recovery probe evidence,
- API bridge round-trip,
- dynamic/structure-aware scalp cost economics,
- composite recovery-chain loss streak semantics,
- root attribution repair,
- recovery budget source markers,
- dashboard JavaScript syntax,
- Python compile checks.

MetaEditor compilation is still required locally for the changed `.mq5` source.
