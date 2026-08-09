# Nyao --- Atlas MT5 Execution Layer

**Current release:** Nyao 44.3 · paired with Atlas 1.30.19

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

Nyao 44.3 is compatible with Atlas concurrent portfolio allocation.

Existing exposure is represented by strategic risk units rather than a
blanket global lock. Nyao therefore permits another qualified entry when
Atlas reports sufficient capacity and all execution gates pass.

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
