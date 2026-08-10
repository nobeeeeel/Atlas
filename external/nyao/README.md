# Nyao --- Atlas MT5 Execution Layer

**Current release:** Nyao 44.6.2 · paired with Atlas 1.30.57

### Recovery lifecycle & hedge profit integrity (1.30.57)

Atlas/Nyao now treats every unresolved rolling-hedge lifecycle as one book-level risk unit until flat. Independent fresh/zone entries are locked during any active recovery composite, not only RECOVERY_PROBE. Active HEDGE_CHILD legs receive broker-side profit protection before ordinary chain logic can allow a large positive MFE to reverse into a loss; if a protected hedge disappears, the surviving leg graduates with no-rehedge authority rather than immediately starting another uncontrolled cycle. Position management now uses MT5 `POSITION_PRICE_CURRENT` as the primary management mark, with the broker still the final SL authority, because live diagnostics exposed large divergence between position marks and raw symbol quotes. Capital reservations are also reconciled from immutable risk-unit lineage so a graduated survivor remains reserved as `recovery:<root>` instead of being misclassified as a standalone trade.


**Startup risk authority:** Nyao starts fail-closed, rejects capital/zone directives generated before the current EA startup, and reports `STARTUP_RISK_RECONCILIATION` until Atlas publishes a post-reconciliation directive.

Nyao is the MetaTrader 5 execution component of Atlas Adaptive Trading
Intelligence. It observes live broker state, publishes execution
telemetry, applies Atlas runtime authority, performs final broker-aware
sizing and manages the complete MT5 position lifecycle.

Nyao is not the portfolio risk authority. Atlas owns deterministic
strategy and capital governance; Nyao is the final execution authority
for what the broker can actually place and manage.

## Responsibilities

Nyao is responsible for: - MT5 terminal/account connectivity; - symbol
specification discovery; - bid/ask and spread telemetry; -
indicator/runtime signal telemetry; - final lot sizing using broker
truth; - `OrderCalcProfit` and broker-volume feasibility; - order
submission/modification/closure; - stop/target and trade-management
execution; - recovery/hedge lifecycle execution within Atlas
authority; - immutable recovery and zone lineage in entry comments; -
position/deal history exported back to Atlas.

## Authority boundary

``` text
Atlas
  decides whether risk is permitted
  determines capital budgets
  owns portfolio and chain ceilings
  owns deterministic zone authority
  owns strategic outcome accounting
        │
        ▼
Nyao
  validates broker feasibility
  calculates executable volume
  places/manages MT5 orders
  reports broker truth back to Atlas
```

Nyao must never interpret unused account margin as permission to exceed
Atlas monetary-risk authority.

## Fresh entries

A fresh scalp requires all applicable gates to agree, including: - Atlas
enable/side authority; - BUY/SELL signal threshold; - market/structure
conditions; - dynamic transaction-cost feasibility; - Atlas capital
budget; - concurrent portfolio capacity; - duplicate/distance
controls; - broker minimum/step/maximum volume; - final stop-risk
calculation.

Having an existing position is not by itself a reason to block another
independent opportunity. Atlas reserves active risk and provides the
remaining deterministic capacity.

## Dynamic spread and structure handling

Nyao participates in Atlas's structure-aware execution-economics model.
Spread is not treated only as a static hard number.

The execution path considers spread relative to volatility and the
intended stop/target geometry. A candidate may be rejected when making
transaction costs acceptable would require excessive stop expansion or
otherwise transform the trade beyond the intended scalp structure.

This is distinct from a capital veto.

## Broker-aware sizing

Atlas supplies monetary/percentage risk authority. Nyao remains
responsible for converting that authority into an executable broker
volume using the actual symbol specification and stop geometry.

Critical rule:

> If the safe calculated volume is below the broker minimum, Nyao must
> skip the trade rather than round upward into excess risk.

Leverage affects margin feasibility but does not increase permitted
loss.

## Concurrent risk units

Nyao 44.5.7 is compatible with Atlas concurrent portfolio allocation.

Existing exposure is represented by strategic risk units rather than a
blanket global lock. Nyao therefore permits another qualified entry when
Atlas reports sufficient capacity and all execution gates pass.

> Atlas 1.30.56 is a backend-only Gemini proposal-parser hotfix; Nyao remains 44.6.1.

### Recovery chain risk integrity (1.30.54)

The 1.30.54 package also enforces recovery-lifecycle atomicity: any unresolved immutable `RECOVERY_PROBE` lifecycle locally locks independent fresh entries in Nyao, the backend independently vetoes fresh risk while the composite is active, and root/child outcomes are scored only once after the whole composite is flat. A closed RP root is still linked to live historical children through durable root lineage; transient child closures cannot start a new loss-protection stage.

- Recovery-probe admission is re-priced again from the **actual broker fill**, actual broker SL, actual volume, and live equity. An adverse fill that makes the probe exceed the 0.30% cap is immediately emergency-closed.
- `RECOVERY_PROBE` is a deliberately single-leg diagnostic state. It cannot spawn `HEDGE_CHILD` rolling-hedge legs; ordinary non-probe recovery chains are unchanged.
- Debug integrity now exposes `RECOVERY_PROBE_SINGLE_LEG_INVARIANT` in addition to the active probe risk-envelope check.

### Losing-risk-unit counting

Recovery-chain legs are not counted as unrelated losing positions. A
recovery root and its hedge children form one composite risk unit and
are evaluated using the chain's combined state. Standalone losing trades
remain independent units.

This prevents a two-leg recovery chain from incorrectly consuming
multiple strategy-loss slots merely because it contains multiple MT5
tickets.

## Recovery execution

Recovery/hedge children carry immutable lineage identifying the chain
they belong to.

The complete chain is governed by a frozen Atlas risk ceiling.
Additional recovery legs must remain inside that ceiling and cannot
borrow unused portfolio capacity from unrelated strategies.

Nyao reports recovery sizing telemetry including requested, capped and
final volume plus the risk basis required for Atlas's durable recovery
ledger.

### Restart behaviour

When Nyao/Atlas discovers an already-active recovery chain after restart
or upgrade, further expansion is not allowed until Atlas has established
a finite adopted chain budget. Existing positions may still be managed
or reduced while authority is reconciled.


## Zone-aware scalp coexistence

Nyao 44.5.7 distinguishes a zone that is being **watched** from a zone campaign that has been **committed**. In `ZONE_AWARE_SCALP`, ordinary scalp evaluation continues with explicit context classification. The zone-aligned direction uses the normal scalp gates. A counter-zone candidate is not blocked merely because it opposes the zone; it must clear the ordinary signal gate, an additional context-sensitive evidence premium and reduced risk authority, and it is deterministically blocked as the higher-timeframe campaign approaches a feasible commit boundary. Both directions remain subject to spread/structure, capital, duplicate-distance and broker-volume gates.

When Atlas reports the zone as execution-ready, Nyao crosses the commit boundary: new scalp entries are suspended and the zone executor owns fresh-entry authority. Existing positions continue to be managed normally.

Atlas may continue applying autonomous Gemini/Nyao scalp-policy updates while a zone is only being watched. Once a committed campaign is acknowledged, new policy activation is deferred until the campaign releases execution authority so that the runtime does not drift underneath an active campaign.

## Zone campaigns

Zone entries carry immutable Atlas zone-plan lineage so multiple layers
can be reconstructed as one strategic campaign.

Nyao may execute and manage zone layers when Atlas zone authority,
confirmation, capital and broker feasibility agree. The existence of
unrelated exposure no longer creates an automatic zone lock when
portfolio capacity remains.

## Outcome telemetry

Nyao exposes sufficient MT5 history for Atlas to reconstruct
authoritative outcomes, including: - position identity; - entry/exit
deals; - realised profit/loss; - swap; - commission; - fees; -
policy/strategy lineage where available.

Trades that occur entirely between Atlas polling intervals can therefore
be reconstructed from MT5 history rather than silently omitted.

## Runtime policy

Atlas can control permitted Nyao runtime parameters through the
command/policy bridge. Applied command versions and policy epochs are
acknowledged back to Atlas so outcomes can be attributed to the policy
that existed at entry.

Gemini may reason about or propose permitted policy changes through
Atlas, but Nyao must continue to enforce Atlas deterministic risk and
broker constraints regardless of AI output.

## Operational checks

Before relying on live execution, verify: - MT5 terminal is connected; -
account trading is permitted; - Algo Trading is enabled; - the EA is
attached to the intended symbol/chart; - Atlas status/command bridge is
fresh; - Nyao has acknowledged the current command/policy epoch; -
symbol contract and volume specifications are available; - Atlas capital
and risk authority are resolved.

## Relationship to Atlas documentation

See the repository root `README.md` for the product overview and
`docs/architecture.md` for the canonical technical architecture.

This README intentionally documents Nyao's execution responsibilities
rather than historical development phases.

## Adaptive zone cost ratios

Atlas supplies dynamic zone stop/target cost ratios and may disable the legacy direct zone ATR spread ratio by setting it to zero. Nyao 44.5.7 interprets a zero ATR ratio as disabled and continues to perform its final live bid/ask check against the supplied stop/target ratios. Nyao 44.5.7 must be compiled when upgrading to Atlas 1.30.51 because the execution bridge also carries explicit source-zone invalidation state.


## Source-zone invalidation

Nyao 44.5.7 consumes Atlas source-zone invalidation state. If a prospective source zone invalidates before any Atlas zone exposure exists, zone-aware/campaign authority is released by Atlas. If the exact immutable zone plan already has live `ATLAS_ZONE` exposure, Nyao enters management-only invalidated-campaign handling: existing campaign positions remain managed, ordinary campaign lineage is preserved, and no unfilled or future zone layer may open from the invalidated source zone.
