# P3.30.3 — Durable Recovery Budget Ledger

## Purpose

P3.30.3 closes the remaining recovery-capital observability and hierarchy gaps found in live BTC recovery chains.

## Recovery budget hierarchy

A recovery chain no longer receives the full `maximum_total_strategy_risk_pct` portfolio allowance by default.

1. Nyao reconstructs the root position's original monetary risk from its immutable entry price, original broker SL, volume, and broker `OrderCalcProfit` contract math.
2. The default recovery-unit ceiling is `original_unit_risk_usd × 1.50`.
3. Explicit `hedge_max_chain_loss_usd` / `hedge_max_chain_loss_pct` limits may tighten that ceiling.
4. Atlas `maximum_total_strategy_risk_pct` remains an absolute portfolio outer ceiling and may also tighten it.
5. The effective chain budget is frozen on first recovery sizing for that chain so later market/equity changes cannot silently expand it.
6. Legacy/restarted roots without recoverable original SL risk fall back to the already-owned anchor loss, never to the full portfolio budget.

## Durable sizing audit

Nyao publishes the last successfully opened recovery sizing event independently from working tick calculations. Atlas persists unique sizing events under the current MT5 account next to `trade_outcomes.json` in `recovery_risk_ledger.json`.

The `/api/v1/atlas/recovery-risk` endpoint now exposes the durable latest event, recent events, original unit risk, expansion multiplier, portfolio ceiling, effective chain ceiling, budget basis, consumed loss, and remaining capacity.

## Zone mode correction

Composite `ZONE_CAMPAIGN` risk units are always attributed to `trading_mode=ZONE`, including historical campaigns reconstructed from `AZ|<plan>|L<n>` entry comments.

## Versions

- Atlas backend/dashboard: `1.30.16`
- Nyao source: `44.1`
- Recovery sizing: `nyao-recovery-risk-v2`
