# P3.30.4 — Active Recovery Chain Adoption

P3.30.4 closes the restart/upgrade migration gap for recovery chains that were already open before the durable v2 recovery ledger observed their hedge-sizing event.

## Behaviour

When Nyao discovers an active recovery chain with no in-memory frozen budget, it adopts that chain before any recovery expansion is allowed. The adopted budget uses the root's original stop risk when recoverable. If that historical risk is unavailable, it uses the already-owned anchor/current chain loss as a conservative basis and applies the normal 1.5x risk-unit recovery envelope. Explicit chain caps and the Atlas portfolio hard limit can only tighten the result.

The full portfolio risk ceiling is never granted merely because the original sizing event was missed.

A successful adoption emits `ACTIVE_RECOVERY_CHAIN_ADOPTED` with an immutable audit snapshot. If no finite budget can be reconstructed, Nyao emits `RECOVERY_CHAIN_BUDGET_UNRESOLVED`; existing legs may still unwind or be reduced, but additional recovery expansion is blocked.

## Observability

The adoption is emitted through the existing recovery-sizing telemetry and is therefore persisted by Atlas in `recovery_risk_ledger.json`. The dashboard shows the adopted chain ceiling, remaining capacity, budget basis and last limiter/reason.

## Release

- Atlas backend/dashboard: `1.30.17`
- Nyao source: `44.2`
- Recovery engine: `nyao-recovery-risk-v2`
