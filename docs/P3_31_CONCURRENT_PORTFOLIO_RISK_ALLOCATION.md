# P3.31 — Concurrent Portfolio Risk Allocation

Release: Atlas 1.30.18 / Nyao 44.3  
Capital engine: `atlas-capital-regime-v1.9`  
Allocation engine: `atlas-concurrent-risk-allocation-v1`  
Zone plan: `zone-execution-plan-v0.8`

## Purpose

P3.31 removes the old binary rule that any live Atlas exposure owns the entire fresh-risk budget. Active trades now reserve deterministic risk capacity, while independent new opportunities may use genuinely unallocated operating capacity.

## Portfolio hierarchy

1. Atlas computes the capital-regime hard portfolio ceiling.
2. Drawdown, risk state, loss protection and volatility determine a smaller current operating envelope.
3. Active risk units reserve capacity inside that envelope.
4. New scalp and zone candidates receive the smaller of their normal per-opportunity budget and remaining operating capacity.
5. If capacity is exhausted, fresh risk is vetoed. Existing positions alone are not a veto.

## Risk reservations

- Recovery chain: reserves its frozen P3.30 recovery-chain ceiling.
- Zone campaign: reserves observable broker-stop risk; if stop risk is unavailable, reserves the current approved zone budget.
- Standalone scalp: reserves remaining downside to its broker stop; if stop risk is unavailable, reserves the current approved scalp budget.
- Stop moved to break-even/profit: remaining downside is zero, allowing capital to be reused efficiently.
- Working orders: reserve candidate risk unless already represented by the same active zone campaign.
- Unresolved recovery chain: fail closed for independent new risk until P3.30.4 adoption establishes a finite ceiling.

Same-symbol risk receives no diversification credit.

## Recovery semantics

Recovery legs remain inside their own frozen chain ceiling. They cannot borrow otherwise unallocated portfolio capacity. A loss-protection `RECOVERY_PROBE` remains deliberately single-unit: once the probe is in flight, independent fresh risk is paused until its composite outcome resolves.

## Nyao execution change

Nyao 44.3 replaces the fresh-entry `CountLosingPositions()` gate with `CountLosingRiskUnits()`:

- standalone losing trade = one losing risk unit;
- a multi-leg recovery chain = one losing risk unit based on combined live P/L;
- individual hedge legs no longer consume the loss-position count independently.

`MaxOpenOrders`, duplicate-distance checks, cost/structure gates, signal thresholds, broker feasibility and all deterministic hard protections remain active.

## Zone execution

A standalone scalp or recovery chain no longer automatically blocks a new zone campaign. A zone campaign may start when Atlas has approved zone risk capacity and all zone confirmation/broker gates pass. A different already-active zone campaign still owns the symbol's zone-campaign identity and blocks a competing zone campaign.

## Dashboard

The Capital & Risk card now distinguishes:

- AVAILABLE
- PARTIALLY ALLOCATED
- FULLY ALLOCATED
- CAPITAL VETO
- RECOVERY PROBE · IN FLIGHT

Protection Status exposes Reserved portfolio risk and Available operating risk.

## Live BTC example used during development

Using the observed account state around equity $10,965 and recovery chain ceiling $15.09:

- hard portfolio ceiling: ~$109.65;
- MODERATE-risk operating ceiling: ~$87.72;
- reserved active recovery risk: $15.09;
- remaining operating capacity: ~$72.63;
- normal scalp candidate budget: ~$26.32;
- normal zone candidate budget: ~$39.48.

The account is therefore partially allocated, not exposure-locked. BTC can still be rejected independently by P3.29 transaction-cost/market-structure gates.
