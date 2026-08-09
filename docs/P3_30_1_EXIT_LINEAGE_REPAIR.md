# P3.30.1 — Exit Ownership and Recovery Lineage Repair

## Why this patch exists
A live BTC recovery chain exposed two coupled defects:

- MT5 showed root `231325832` closed at `-1.59` and hedge child `231326411` closed at `+3.67`, but Atlas only ingested the root.
- Graduating a hedge clears its live `chainId`, which is correct for management but historically erased its recovery lineage.

That caused the root to be scored as a standalone loss and produced an incorrect eight-unit loss streak even though the completed recovery episode netted about `+2.08`.

## Changes
- Historical exit ownership is now proven from the authoritative entry-deal magic when the closing deal does not preserve Nyao's magic number.
- Nyao 43.9 writes compact immutable hedge lineage comments: `H|<chain>|<level>|<policy_epoch>`.
- Exit telemetry exposes `entry_order_origin`, `entry_chain_id`, and `entry_hedge_level`.
- Exit-only outcome reconstruction preserves those fields.
- Legacy pre-43.9 hedge children with no durable chain id may be conservatively re-linked only when their entry overlaps a same-policy root lifecycle.
- The Recent closed trades UI now explicitly identifies itself as ticket-level execution evidence; strategic scoring remains composite.

## Expected repair for the observed BTC chain
`231325832 -1.59 + 231326411 +3.67 = recovery chain +2.08`, classified as one `WIN`.

## Versions
- Atlas backend/dashboard: `1.30.14`
- Nyao source: `43.9`
