<p align="center">
  <img src="atlas-logo.png" alt="Atlas — Adaptive Trading Intelligence" width="220">
</p>

# Atlas --- Adaptive Trading Intelligence

**Current release:** Atlas 1.30.19 · Nyao 44.3

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
