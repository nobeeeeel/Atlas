# Atlas

Atlas is a local trading-control system that combines deterministic market and
risk logic with AI-assisted policy analysis. It supervises the Nyao MetaTrader 5
Expert Advisor through a symbol-scoped JSON bridge.

Atlas is under active development and should be used on demo accounts. It does
not guarantee profitability.

## Repository layout

```text
backend/app/             FastAPI API, dashboard, bridge and intelligence modules
external/nyao/           Canonical Nyao MQ5 source, compiled EA and profiles
scripts/                 Migration, maintenance and executable test scripts
docs/                    Architecture notes and project handoffs
data/                    Local evidence and audit state (ignored by Git)
```

The two README files have separate purposes:

- This file documents Atlas and local development.
- [`external/nyao/README.md`](external/nyao/README.md) documents the upstream
  Nyao EA and its profiles.

See [`docs/architecture.md`](docs/architecture.md) for the system boundary and
execution-authority model.

## Local setup

Atlas currently targets Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/dashboard` after the server starts. MT5 bridge files
live in the terminal's `MQL5/Files/Atlas/<SYMBOL>/` directory; repository-local
`data/` contains generated evidence and is intentionally not versioned.

## Gemini Analyst/Critic and policy proposals

Atlas 1.28 uses Gemini 3.6 Flash through the Gemini API. Gemini reviews all 157
NYAO controls and the dedicated zone-execution policy, then decides which values
to keep or change as a coherent market- and account-aware policy. Atlas validates
each proposed value against the relevant schema and runs a second Gemini pass as
a critic.

The policy input also contains performance feedback: outcome quality, current loss
streak, expectancy and tail behavior, regime/origin splits, recovery-chain results,
and runtime-configuration fingerprints. Gemini must diagnose this history and name
the weaknesses its next policy targets. Pre-Atlas results are labelled as the NYAO
baseline; after application is added, results will be compared by policy epoch so
Atlas can retain, revise, or revert each tested policy.

```bash
export ATLAS_LLM_PROVIDER="GEMINI"
export ATLAS_LLM_ENABLED=true
export ATLAS_LLM_MODEL="gemini-3.6-flash"
export ATLAS_LLM_FALLBACK_MODELS="gemini-3.5-flash,gemini-3.5-flash-lite"
export ATLAS_GEMMA_THINKING_LEVEL="high"
export GEMINI_API_KEY="your-replacement-key"
```

Alternatively, copy `.env.example` to `.env` and put the replacement key there.
The `.env` file is excluded from Git.

Atlas tries the configured model chain in order. It advances to the next model
only for rate limits, temporary service failures, timeouts, malformed responses,
or a model-specific unavailable response. Authentication and other non-retryable
HTTP errors stop the chain. Model fallback can use a different model's quota, but
cannot bypass a project-wide spend or daily quota shared by the whole API project.

Inspect readiness:

```bash
curl "http://127.0.0.1:8000/api/v1/atlas/llm/status?symbol=%23BTCUSD"
```

Run a supervised review:

```bash
curl -X POST \
  "http://127.0.0.1:8000/api/v1/atlas/llm/review?symbol=%23BTCUSD" \
  -H "Content-Type: application/json" \
  -d '{"run_critic":true}'
```

Generate a validated multi-parameter policy proposal:

```bash
curl -X POST \
  "http://127.0.0.1:8000/api/v1/atlas/llm/policy-proposal?symbol=%23BTCUSD"
```

In `SUPERVISED` mode, proposals retain `execution_authority: PROPOSAL_ONLY` and
cannot write `commands.json`. In `AUTONOMOUS` mode, an accepted critic result can
apply a validated scalp policy and/or zone policy after the configured confidence
and minimum-dwell checks. Atlas backs up the prior state and refuses stale command
epochs. A policy prepared during active zone execution is queued until a clean
mode boundary instead of changing an in-flight plan.

The dashboard includes a per-symbol Gemini policy-cycle schedule (15 minutes to
24 hours, 4 hours by default) with last/next run state, countdown, critic verdict,
application mode, minimum confidence, minimum dwell, and a manual **Run analysis
now** action. Scheduled cycles analyze live state, past performance, shadow
policy/evaluation/replay, policy epochs, the deterministic zone map, and current
zone plan. The schedule is disabled until an operator enables it in the Atlas
view.

## Scalp and zone modes

Atlas builds a deterministic M30/H1/H4 zone map from validated closed candles.
Outside a priority zone, Nyao follows its Gemini-optimized scalp policy. Inside a
priority zone, Atlas suspends ordinary scalping and uses a separate zone policy
for direction confirmation, three-layer entries, a shared stop, three targets,
and total account risk. Zone confirmation combines directional evidence, zone
quality, live price depth, timeframe, structure alignment, and confluence; it does
not inherit the scalp entry threshold.

The zone map is deterministic trade-location evidence. Gemini may tune how Atlas
trades those zones, but cannot invent or move a live zone without candle evidence.
Outcome records carry both policy epochs and `SCALP`/`ZONE` mode attribution so
later reviews can identify what actually improved or degraded performance.

## Scalping responsiveness

Atlas 1.28 also measures scalping responsiveness per symbol. The dashboard and
Gemini policy packet include entry-eligibility rate, dominant block reasons,
score deficits, holding duration, MFE capture/giveback when available, live
position age, and the latency pressure created by the current runtime controls.
Atlas classifies the active policy as `FAST`, `BALANCED`, or `SELECTIVE` and asks
Gemini to choose the appropriate profile for the current regime and outcomes.

Responsiveness is optimized for net outcome quality rather than raw trade count.
The policy validator rejects intrabar-entry proposals unless
`max_trades_per_candle <= 1` and duplicate-distance protection remains enabled.

## Development checks

The current checks are executable Python scripts rather than a pytest suite:

```bash
for check in scripts/test_*.py; do .venv/bin/python "$check"; done
```

The compiled `external/nyao/nyao_scalper.ex5` is retained intentionally as the
local deployable artifact. Update it only after compiling the canonical
`external/nyao/nyao_scalper.mq5` source successfully.

## P3.31 — Concurrent Portfolio Risk Allocation

Atlas 1.30.18 / Nyao 44.3 replaces the binary exposure lock with reservation-based concurrent capital allocation. Active risk units reserve deterministic ceilings while qualified independent scalp/zone opportunities may use remaining operating capacity. Recovery chains remain isolated inside their frozen chain budgets. See `docs/P3_31_CONCURRENT_PORTFOLIO_RISK_ALLOCATION.md`.

## Current release — Atlas 1.30.19 / Nyao 44.3

![Atlas — Adaptive Trading Intelligence](atlas-logo.png)

Atlas has progressed from a single-position scalper supervisor into a deterministic, portfolio-aware trading control system. The current release keeps MT5/Nyao as final broker execution authority while Atlas owns market interpretation, policy, capital allocation, composite risk accounting, evidence capture, and supervised/adaptive intelligence.

### Current capability baseline

- **P3.28 — Authoritative outcome ingestion:** exact MT5 exit-deal P/L, restart reconstruction, policy-epoch attribution, and durable trade evidence.
- **P3.29 — Dynamic transaction-cost economics:** spread is evaluated against ATR, planned stop/target geometry, and structural feasibility instead of a fixed hard spread cap alone.
- **P3.30 — Composite recovery risk:** recovery roots and hedge children are scored as one strategic risk unit only after the entire chain is flat.
- **P3.30.1 — Exit lineage repair:** immutable recovery lineage plus conservative legacy reconstruction across restarts/history gaps.
- **P3.30.2 — Zone campaign composite:** all layers sharing an Atlas zone-plan token are evaluated as one campaign and remain distinct from scalp outcomes.
- **P3.30.3 — Durable recovery budget ledger:** recovery sizing decisions and frozen chain budgets persist and remain auditable.
- **P3.30.4 — Active recovery-chain adoption:** pre-existing chains discovered after restart/upgrade receive a finite conservative risk authority before further expansion.
- **P3.31 — Concurrent portfolio risk allocation:** existing exposure reserves deterministic risk instead of globally locking fresh opportunities; independent qualified scalps/zones may use remaining operating capacity.
- **P3.31.1 — Configurable portfolio risk appetite:** the operator owns the aggregate hard-risk ceiling from **1% to 20%** (1% default). Atlas may reduce the effective operating ceiling but Atlas/Gemini cannot raise the operator setting.

### Capital model

Atlas separates four concepts that must not be confused:

1. **Operator portfolio hard ceiling** — absolute aggregate strategy-risk authority (1–20%).
2. **Atlas operating ceiling** — hard ceiling reduced by deterministic drawdown, loss-state, market-risk and volatility controls.
3. **Active reservations** — standalone trades, zone campaigns, pending orders and recovery chains reserve their remaining/frozen deterministic risk.
4. **Per-opportunity budget** — each new scalp/zone is independently sized beneath the remaining operating capacity and still must pass broker, structure, spread/cost, duplicate and execution gates.

A higher portfolio risk appetite therefore increases *concurrent aggregate capacity*; it does **not** multiply every trade by that percentage. Recovery chains remain isolated inside their own frozen chain ceiling and cannot borrow unused portfolio capacity.

### Current operating principle

> An existing trade is not itself a reason to miss another opportunity. Atlas rejects incremental risk only when the new opportunity is not justified by remaining portfolio capacity, concentration, market structure, transaction costs, broker feasibility, or protection state.

This preserves opportunity efficiency while keeping deterministic risk authority above AI reasoning.

### Primary instrument and validation

The primary intended live instrument is **XAUUSD**. `#BTCUSD` has also been used as a weekend stress-test market, particularly for high-spread transaction-cost economics and recovery/risk-ledger validation. Symbol eligibility is not hard-coded: Atlas evaluates the actual broker contract, minimum volume, spread, ATR, stop geometry and available capital before allowing execution.

### Important endpoints

```text
GET /api/v1/nyao/status?symbol=XAUUSD
GET /api/v1/atlas/capital-sizing?symbol=XAUUSD
GET /api/v1/atlas/recovery-risk?symbol=XAUUSD
GET /api/v1/atlas/risk-appetite?symbol=XAUUSD
PUT /api/v1/atlas/risk-appetite?symbol=XAUUSD
```

Example operator risk-appetite update:

```json
{
  "portfolio_hard_risk_pct": 5,
  "actor": "operator"
}
```

See the milestone documents in `docs/` for implementation details and regression expectations.
