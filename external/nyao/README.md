# Nyao --- Atlas MT5 Execution Layer

**Current release:** Nyao 44.4 · paired with Atlas 1.30.21

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

Likewise, a **watching but uncommitted zone** is not by itself a reason to
suspend an aligned scalp. Zone exclusivity begins at the deterministic
campaign commit boundary, not merely when price enters a priority zone.

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

## Zone-aware scalping and zone campaigns

Nyao 44.4 implements the Atlas zone execution-state boundary instead of
treating every qualified zone as an immediate global scalp suspension.

### Zone-aware scalp / watching

When Atlas identifies a qualified zone but the campaign has **not yet
passed all commit gates**, Nyao remains on the normal scalp execution
path with deterministic zone context.

For a SELL zone:

- SELL-aligned scalps may continue through normal Nyao signal,
  execution-economics, duplicate, cooldown, broker and capital gates.
- BUY scalps are blocked as counter-directional zone exposure.

For a BUY zone, the directional rule is reversed.

The presence of a watching zone does not lower scalp thresholds or
override scalp transaction-cost feasibility.

### Zone campaign commit

Atlas requests exclusive zone execution only when the campaign has passed
its deterministic commit gates, including:

- zone confirmation;
- required directional evidence;
- adaptive zone execution economics;
- broker feasibility;
- Atlas capital authority.

At that boundary, Nyao suspends conflicting fresh scalps and executes the
zone campaign under the immutable Atlas plan identity.

### Prospective zone headroom

Atlas may reduce the risk authority of an aligned scalp while a zone is
watching so the prospective zone campaign retains enough operating
headroom to commit on the next decision cycle. Nyao treats that reduced
scalp authority as final and does not substitute unused margin for the
reserved Atlas capacity.

### Adaptive zone execution economics

The direct legacy ATR spread veto is not authoritative for zone
campaigns. Atlas supplies bounded dynamic stop/target spread ratios based
on campaign geometry and quality. ATR remains context. Nyao enforces the
Atlas-supplied execution economics at the live execution tick.
## Outcome telemetry

Nyao exposes sufficient MT5 history for Atlas to reconstruct
authoritative outcomes, including: - position identity; - entry/exit
deals; - realised profit/loss; - swap; - commission; - fees; -
policy/strategy lineage where available.

Trades that occur entirely between Atlas polling intervals can therefore
be reconstructed from MT5 history rather than silently omitted.

## Runtime policy

Atlas controls permitted Nyao runtime parameters through the
command/policy bridge. Applied command versions and policy epochs are
acknowledged back to Atlas so outcomes can be attributed to the policy
that existed at entry.

While Atlas is in **zone-aware scalp / watching** mode, normal scheduled or
autonomous Gemini policy updates may continue because no zone campaign has
yet committed execution authority. Gemini receives the active zone as
read-only scalp context through Atlas.

Once a zone campaign crosses the deterministic commit boundary, new policy
activation is deferred until the campaign reaches a clean mode boundary.
Gemini may continue analysing and producing candidates, but Nyao does not
accept mid-campaign policy drift for the committed campaign.

Gemini may reason about or propose permitted policy changes through Atlas,
but Nyao must continue to enforce Atlas deterministic risk, zone authority
and broker constraints regardless of AI output.
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

Atlas 1.30.20 supplies dynamic zone stop/target cost ratios and sets the legacy direct zone ATR spread ratio to zero. Nyao 44.3 already interprets a zero ATR ratio as disabled and continues to perform its final live bid/ask check against the supplied stop/target ratios, so no MQL recompilation is required for this Atlas-side economics upgrade.
