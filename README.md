<p align="center">
  <img src="atlas-logo.png" alt="Atlas — Adaptive Trading Intelligence" width="220">
</p>

# Atlas --- Adaptive Trading Intelligence

**Current release:** Atlas 1.30.43 · Nyao 44.5.3

**Documentation:** [Architecture](docs/architecture.md) · [Nyao MT5 Execution Layer](external/nyao/README.md)

Atlas is an adaptive trading intelligence and risk-governance platform
built around MetaTrader 5. Atlas performs deterministic market, capital,
execution-economics, portfolio-risk and outcome analysis; Nyao is the
MT5 execution layer that applies Atlas authority using live broker
specifications and terminal state.

The design goal is simple: **evaluate opportunities continuously, act
when the expected trade is justified, and never confuse available
capital with permission to take bad risk.**

## Core capabilities

### Adaptive scalp execution

-   Directional BUY/SELL scoring with runtime thresholds.
-   Market-regime and volatility-aware decision making.
-   Structure-aware entries rather than signal-score-only execution.
-   Dynamic stop/target geometry.
-   Duplicate-entry and execution-safety controls.

### Dynamic execution economics

Atlas does not rely on a single hard spread number. Scalp feasibility
considers spread relative to: - ATR and current volatility; - intended
stop and target; - transaction-cost ratios; - required stop expansion; -
whether the resulting geometry still represents the intended strategy.

A signal can therefore be valid while execution is rejected because the
market is temporarily too expensive or the required structure has become
unreasonable.

### Capital regime and configurable risk appetite

Atlas separates **operator risk appetite** from **per-opportunity
sizing**.

The operator controls the maximum aggregate portfolio hard-risk ceiling
from **1% to 20%**. The default is 1%. This ceiling is not per-trade
risk.

Atlas may reduce the effective operating envelope using drawdown, loss
protection, market risk, volatility, concentration and other
deterministic controls. Atlas and Gemini cannot silently increase the
operator-owned ceiling.

Individual scalp and zone budgets remain independently calculated
beneath the portfolio ceiling.

### Adaptive opportunity risk allocation
Atlas can allocate a bounded share of the current operating envelope to a qualified scalp or zone campaign instead of permanently capping every opportunity at the capital-regime floor. The regime budget remains a conservative floor; per-opportunity hard caps, portfolio capacity and all execution gates remain authoritative.

### Adaptive zone execution economics
Zone campaigns use campaign-aware transaction-cost economics. The legacy direct `ATR × fixed ratio` veto is disabled in the Nyao directive; ATR remains market context while bounded dynamic stop/target cost ratios are derived from zone quality, confirmation progress and campaign reward/risk geometry.

### Concurrent portfolio risk allocation

Existing positions no longer create a blanket account-wide exposure
lock.

Atlas reserves deterministic risk for each active risk unit and
evaluates new opportunities against the remaining operating and hard
capacity. This allows independent qualified opportunities to execute
concurrently without double-counting capital.

Recovery chains reserve their frozen chain ceiling. Standalone positions
reserve remaining downside. Same-symbol concurrent exposure receives no
diversification credit.

### Composite risk units

Atlas evaluates strategic outcomes as complete risk units: -
`STANDALONE_TRADE` - `RECOVERY_CHAIN` - `ZONE_CAMPAIGN`

A recovery root and its hedge children are evaluated as one chain.
Individual member exits remain provisional until the complete chain is
flat. Zone layers sharing the same immutable campaign lineage are
likewise evaluated as one campaign.

### Recovery risk governance

Recovery is bounded rather than open-ended.

Each recovery chain receives a frozen deterministic risk envelope
derived from the original unit risk and recovery multiplier, tightened
by explicit chain and portfolio ceilings. Recovery legs cannot borrow
unused portfolio capacity beyond their chain authority.

Atlas persists recovery sizing events and can conservatively adopt an
already-active chain after a restart or upgrade so that unresolved
historical state never grants unlimited recovery authority.

### Authoritative MT5 outcomes

Atlas uses MT5 deal history as the authoritative source for realised
exits when available. It tracks exact realised P/L, reconstructs trades
that occur between polls, preserves policy attribution and maintains
immutable lineage for recovery and zone campaigns.


### Zone-aware scalp coexistence
A detected zone owns **context before execution**. While a qualified campaign is still waiting for confirmation or acceptable execution economics, Atlas keeps a `ZONE_AWARE_SCALP` lane open instead of idling the symbol. Scalp entries are constrained to the zone-aligned direction, keep their normal score/cost/risk gates, and are clipped when necessary to preserve prospective campaign headroom. Once every deterministic zone commit gate passes, Atlas atomically suspends new scalps and transfers fresh-entry authority to the zone campaign.

Gemini receives the same zone state as read-only scalp context. Autonomous Nyao policy updates may continue while the zone is only being watched; new policy activation is deferred once the campaign crosses the commit boundary and remains deferred until campaign authority is released.

### Zone campaigns

Atlas maintains deterministic higher-timeframe zone context and can
execute layered zone campaigns when geometry, confirmation, capital and
broker feasibility agree. When a full zone campaign does not own
execution, qualified zone context may still inform normal scalping
according to the active authority rules.

### Atlas Brain / Gemini

Gemini can reason about market context, performance evidence and Nyao
policy parameters, but deterministic safety remains Atlas-owned.

Gemini cannot override: - operator portfolio risk appetite; - Atlas
capital sizing; - broker feasibility; - recovery-chain ceilings; -
deterministic zone geometry; - hard execution and risk governors.

### Performance Intelligence workspace

Atlas exposes a dedicated Performance workspace separate from the Command Center. Strategic statistics are scored by completed composite risk unit rather than raw MT5 ticket: standalone trades score individually, while recovery chains and zone campaigns score once when fully flat. The workspace separates authoritative strategic outcomes from ticket-level execution diagnostics such as MFE/MAE, policy-epoch attribution, trading-mode results, data quality and learning readiness. Small samples are explicitly labelled preliminary and must not be treated as causal proof.

## Runtime architecture

``` text
Market + MT5 broker state
          │
          ▼
        Nyao
 telemetry / candles / positions / deals
          │
          ▼
        Atlas
 ├─ market & regime intelligence
 ├─ signal / structure analysis
 ├─ execution economics
 ├─ capital regime
 ├─ portfolio risk allocator
 ├─ recovery & zone governance
 ├─ outcome ledger
 └─ Atlas Brain / policy analysis
          │
          ▼
 deterministic command authority
          │
          ▼
        Nyao
 broker-aware sizing + OrderSend + management
          │
          ▼
         MT5
```

## Repository documentation

The repository intentionally keeps documentation small and canonical:

-   `README.md` --- product overview, capabilities and operating model.
-   `docs/architecture.md` --- technical architecture and authority
    model.
-   `external/nyao/README.md` --- Nyao/MT5 execution-layer
    documentation.

Development phase notes and one-off migration scripts are intentionally
not part of the canonical documentation set.

## Primary trading use

Atlas is designed to be instrument-adaptive. XAUUSD is the primary
intended trading market for the current deployment. BTC has also been
useful as a live-market stress environment when gold is closed,
particularly for validating transaction-cost, spread, recovery and
portfolio-risk behaviour.

No symbol is made tradable merely because capital is available. Atlas
must still establish valid signal, structure, execution economics,
broker feasibility and risk authority.

## Risk principle

**Available capital creates capacity, not an obligation to trade.**

Atlas is designed to avoid unnecessary opportunity loss while preserving
deterministic aggregate-risk control. It may run multiple justified risk
units concurrently, but every unit must fit within its own authority and
the current portfolio envelope.

### Notification center
Atlas includes an in-app notification bell with persistent browser-local history, unread state, optional desktop/browser notifications, and severity-aware sound effects. Alerts are transition-driven and deduplicated so polling does not produce repeated noise. Current events include Nyao connection changes, trade opens/closes, zone watching/commit/release transitions, capital vetoes, loss-protection changes, recovery activation, and policy-epoch changes. Notification and sound preferences live in Settings.

### Command Center hierarchy

The Command Center uses progressive disclosure: **Atlas Now**, the account strip, Opportunity Queue and Decision Timeline remain visible by default, while trade-plan detail, execution/context cards, live signal diagnostics, policy and protection internals are available in expandable sections. This keeps the operator workspace focused without removing diagnostic depth.


## Workspace model

Atlas 1.30.43 uses a task-oriented interface: Command Center is summary and action; Market owns live signal and execution-economics diagnostics; Zone Analysis owns trade-location campaigns; Portfolio owns exposure and capital; Performance owns evidence and learning; Atlas Brain owns policy reasoning; System & Audit owns integrity and historical evidence. A persistent global status strip keeps the current symbol, mode, risk capacity, positions, Brain state and health visible across workspaces.


### UI renderer compatibility

Atlas 1.30.43 retains the redesigned workspace layout hardening against legacy overview renderer writes. Removed Command Center diagnostic IDs are retained only in a non-rendered compatibility sink, preventing null-DOM failures while keeping the visible information architecture clean. No trading authority or data source changed.


### Policy lineage and observation history

Atlas Brain separates the authoritative runtime policy from the newest Gemini analysis. The Policy Registry exposes applied policy epochs, current consensus candidates, and accepted Gemini observations. Applied epochs can be inspected against their captured Nyao runtime and consensus lineage; new Gemini observations persist concise diagnosis and critic evidence prospectively. Legacy observations show only what was durably stored and are never reconstructed from later prose.


### Atlas Brain workspace

Atlas Brain now follows policy lineage. Runtime Policy and Candidate Consensus form the Policy Control Center; applied epochs and Gemini observations form Policy Lineage; Latest Gemini Analysis and Scalping Responsiveness form Learning & Market Evidence; policy cadence and Parameter Intelligence form Policy Automation & Intelligence. Candidate consensus controls use full responsive cards so current values, candidate values, support and gating remain visible without clipping.


### Context-aware scalp classification

Fresh Nyao scalps are durably classified as `NEUTRAL_SCALP`, `ZONE_ALIGNED_SCALP`, or `COUNTER_ZONE_SCALP`. Counter-zone entries require a dynamic evidence premium above the normal runtime threshold, receive reduced risk authority, and are blocked as the higher-timeframe zone campaign approaches a feasible commit boundary. Context classification is embedded in compact MT5 entry lineage and flows through Atlas outcomes, Performance Intelligence and Gemini evidence.


### Partial-close lifecycle accounting

Atlas attaches authoritative MT5 partial exit deals to the still-active position lifecycle. Portfolio shows remaining/original volume, realised P/L from partial exits, floating P/L, and combined lifecycle P/L. Recovery chains and other composite risk units expose provisional realised/floating/lifecycle economics while remaining `ACTIVE` and `UNSCORED`; strategic win/loss learning still occurs only after the full composite is flat.

### Context-aware scalp verification

Market now exposes an explicit context-aware scalp banner when Nyao has a fresh zone-aware directive. Signal blocker text distinguishes zone-aligned and counter-zone scalp rules from a committed Atlas zone campaign, removing the ambiguous legacy “Atlas zone” presentation.


### Zone-aware authority synchronization

Atlas distinguishes a prospective zone-aware plan from the state actually applied by Nyao. Nyao emits `zone_aware_scalping_active` only when a fresh WATCHING directive has released the scalp lane. A fresh `ZONE_AWARE_SCALP` directive cannot simultaneously leave `zone_scalp_suspended=true`. The Market workspace reports `LIVE IN NYAO` only after applied runtime confirmation; otherwise it reports `AWAITING NYAO SYNC`.


### Zone campaign exposure-lock hardening

Atlas now distinguishes *campaign acknowledgement* from *actual campaign exposure*. Loading a zone plan ID in Nyao is not sufficient to freeze a campaign. A campaign becomes immutable only after a live `ATLAS_ZONE` position carries that exact `zone_plan_id`. Unrelated scalp or recovery-chain positions therefore cannot falsely lock a prospective zone campaign, create a false conflicting-campaign state, or keep zone execution authority frozen after the market/confirmation state changes. A `campaign_exposure_confirmed` marker gates the short EA reattach grace, so legacy false locks are released safely.


### Portfolio risk allocation

Portfolio now reconciles the operating risk ceiling into active reservations, prospective zone-priority reservation, and genuinely free operating risk. Hard-ceiling headroom is shown separately from deployable operating capacity.

### Context-aware opportunity queue

The Opportunity Queue distinguishes zone-aligned and counter-zone scalp candidates. Counter-zone direction alone is not a blocker. Candidates below the base threshold remain `WATCHING`; candidates that clear the base threshold but not the counter-zone evidence premium become `QUALIFYING`; `BLOCKED` is reserved for deterministic vetoes.


### Portfolio risk allocation and Gemini lock deferral

Portfolio now renders operating-risk allocation directly from capital telemetry: active reservations, prospective zone priority, free operating capacity, hard ceiling and hard headroom. Gemini policy cycles no longer fail merely because the model suggests a position-sensitive control while exposure is open. Such controls are recorded as `deferred_locked_changes`; eligible unlocked changes continue through validation and critic review.


### Verified UI build lineage

The verified Risk Allocation UI and Gemini position-lock deferral remain part of the current Atlas 1.30.43 build. Portfolio renders operating-risk allocation immediately above Open Positions, while Gemini policy validation defers position-sensitive mutations during live exposure instead of failing the complete analysis cycle.


### Atlas Brain policy lineage and consensus hardening

Atlas Brain now separates Gemini analysis runs from accepted consensus observations and applied policy epochs. Every new Gemini cycle is durably recorded with its baseline epoch, proposed controls, critic result, deferrals, consensus contribution and final outcome. Mature autonomous baselines (Epoch 2+) can no longer bypass the minimum accepted-observation consensus gate merely because no prior autonomous-application timestamp exists. Historical applications that violated the current gate are surfaced as pre-fix consensus bypasses rather than silently rewritten.


### Zone invalidation lifecycle

Atlas 1.30.43 makes zone invalidation explicit and auditable. Demand zones invalidate only when a later closed candle closes below the lower boundary; supply zones invalidate only when a later closed candle closes above the upper boundary. Wick-only penetration may mitigate a zone but cannot invalidate it. Invalidated zones leave active priority selection and zone-aware scalp context while remaining available in Zone Analysis history with the invalidating close, boundary, penetration and reason. If an exact Atlas zone campaign already has live exposure, invalidation changes the campaign to management-only: existing positions remain managed under their locked lineage while new zone layers are disabled.
