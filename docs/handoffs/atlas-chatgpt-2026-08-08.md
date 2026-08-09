# Atlas Project — ChatGPT Context Handoff

Generated: 2026-08-08 (Asia/Singapore)

## How to use this document

Upload or paste this document into a normal ChatGPT conversation and say:

> Treat this as the authoritative context for my Atlas trading-system project. Help me reason about product direction, architecture, trading logic, diagnostics, and next steps. Codex has direct repository access, but this ChatGPT conversation does not unless I upload relevant files. Never assume a feature is implemented merely because it is discussed here; distinguish verified implementation from plans and recommendations.

This is a structured handoff rather than a verbatim transcript. It captures the project's objectives, decisions, implementation state, live observations, bugs, and unresolved work from the Codex conversation.

## Security note

A Google AI Studio API key was pasted into the original conversation. It has been intentionally omitted here. The owner should rotate that key if it has not already been rotated and keep the replacement only in `.env`. Never place credentials in source control or future chat exports.

## Owner's vision

Atlas is intended to become the decision-making brain above an existing MetaTrader 5 Expert Advisor named Nyao.

The long-term goal is a symbol-agnostic, continuously improving trading system that:

- Preserves capital first and seeks sustainable long-term profitability.
- Understands current market regime, price action, volatility, spread, equity, drawdown, open exposure, and past performance.
- Chooses how and when to trade instead of merely changing a few static parameters.
- Operates two distinct strategies:
  - Fast ordinary scalping outside important zones.
  - Planned, layered zone trading inside qualified supply/demand zones.
- Adjusts risk and position sizing according to opportunity quality and account conditions, without increasing risk simply to recover losses.
- Learns from current-account outcomes while retaining general strategy knowledge across accounts.
- Eventually incorporates external information such as news and Telegram analysis/signals, but only after the internal market-data pipeline is reliable.
- Produces a clear, intuitive “master trader” dashboard rather than a collection of disconnected diagnostics.

No system can guarantee daily or long-term profits. Atlas should optimize evidence-based decision quality and controlled risk, not promise that losses will always be recovered.

## Repository and runtime

- Repository: `/Users/nobel/Documents/Atlas`
- Backend: Python/FastAPI
- Dashboard: currently served by the backend from `backend/app/main.py`
- MT5 EA source: `external/nyao/nyao_scalper.mq5`
- Active local backend: `http://127.0.0.1:8000`
- Current symbol discussed: `#BTCUSD`
- Current demo account observed: approximately USD 5,000
- Google provider chain:
  - `gemini-3.6-flash`
  - `gemini-3.5-flash`
  - `gemini-3.5-flash-lite`
- LLM cycle interval was set to 30 minutes; the system supports a 15-minute minimum.

The MT5 bridge is stored under the MetaTrader Files directory, with one namespace per broker symbol. For `#BTCUSD`, runtime files include `status.json`, `commands.json`, `candles.json`, and `zone_directive.json`.

## Current high-level architecture

### Nyao

Nyao remains the broker-facing execution engine. It:

- Reads Atlas commands and zone directives.
- Publishes account, position, signal, market, policy, spread, and execution telemetry.
- Executes ordinary scalp entries when scalp mode is permitted.
- Suspends ordinary scalping when Atlas activates zone mode.
- Executes zone legs using broker-valid risk sizing via `OrderCalcProfit`.
- Manages live positions, stops, take profits, trailing logic, partial closes, and other execution mechanics.

### Deterministic Atlas layer

The hardcoded Atlas layer is the authority boundary around the model. It:

- Validates symbol-scoped MT5 telemetry and closed M30/H1/H4 candles.
- Creates deterministic zone maps.
- Assesses market structure, risk, performance, account identity, and capital sizing.
- Builds policy proposals, shadow evaluations/replays, parameter evidence, and execution directives.
- Validates LLM output against schemas and parameter registries.
- Keeps scalping and zone execution controls distinct.
- Applies autonomous policies only through defined workflow rules.

### Gemini Analyst/Critic layer

Gemini is an advisory and policy-reasoning layer, not an unrestricted broker executor. It:

- Receives Atlas evidence, current runtime controls, current-account outcomes, shadow analysis, market context, and prior generalized learnings.
- Proposes parameter changes.
- Reviews the full control surface.
- Uses a separate critic pass to challenge unsupported or incoherent changes.
- Produces schema-constrained output that deterministic Atlas validates.

The model does not directly bypass risk, broker, schema, or execution constraints. This division is intentional: the model provides adaptive judgment while deterministic code enforces consistency and execution correctness.

## Account learning behavior

Atlas distinguishes between:

- Generalized learnings about Nyao, parameter behavior, and market regimes, which may persist across accounts.
- Trade evidence and loss streaks, which must be scoped to the current broker account identity.

A newly connected account with no trades must not be described as having the old account's 15-loss streak. Current-account performance isolation was implemented and tested.

## LLM policy workflow

The intended flow is:

1. Atlas collects current symbol, account, market, performance, and control evidence.
2. Gemini Analyst reviews the evidence and proposes changes.
3. Gemini Critic checks disagreements, unsupported claims, completeness, and coherence.
4. Atlas validates every proposed value against the known parameter registry and Pydantic schema.
5. In supervised mode, a human reviews/arms/applies the proposal.
6. In autonomous mode, eligible scalp-policy changes auto-apply at the configured interval.
7. If a zone campaign is active, incompatible scalp changes may be deferred even if the proposal record is marked processed/applied in the workflow.

“DEFERRED ACTIVE ZONE PLAN” means the autonomous workflow was valid, but Atlas did not replace controls that would interfere with a live zone campaign.

### Critic purpose

The critic is a second independent review pass. It does not invent a separate policy. It should:

- Identify disagreements with Atlas's deterministic evidence.
- Challenge unjustified parameter changes.
- Verify that changed controls are within the proposed set and registry.
- Reject incomplete or unsafe reasoning.
- Approve only a coherent proposal for the configured workflow.

## LLM failures encountered and corrections

Several Gemini responses failed because of:

- Extra text after JSON (`Extra data`).
- Missing disagreement statements.
- Incomplete full-control reviews.
- Critic-approved parameters outside the Analyst's proposed change set.
- Malformed JSON such as a missing comma (`Expecting ',' delimiter`).

Corrections implemented:

- Prompts and validators were adjusted for full control review and explicit disagreements.
- Critic/Analyst proposed-change reconciliation was corrected.
- The provider now sends Atlas's actual Pydantic JSON Schema through Gemini structured output.
- JSON syntax is validated inside the provider before accepting a model response.
- Malformed structured output now advances to the next configured model rather than failing after the first response.
- Semantic validation remains strict after syntactic JSON validation.

The previous failed message remains visible as audit history until a later Brain cycle replaces the last-run display.

## Daily zone analysis

Atlas now has a deterministic daily zone-map pipeline based on validated, closed M30/H1/H4 candles.

The goal was inspired by human analyses that identify:

- Supply and demand zones.
- Order blocks (OB).
- Fair value gaps (FVG).
- Support/resistance flips (RBS/SBR).
- Breakout and pullback scenarios.
- Shared invalidation, multiple entries, and multiple profit targets.

The dashboard can render price charts with zone overlays, rather than only textual zone cards. Market and Zones were separated into distinct dashboard pages.

Too many detected zones can reduce usefulness. Atlas ranks/selects priority zones rather than treating every historical zone as equally actionable.

## Zone trading behavior

Atlas is designed to switch automatically between strategies:

- Outside a qualified active zone: ordinary Nyao scalping may continue under the active scalp policy.
- Inside a qualified zone with confirmation: ordinary scalping is suspended and Atlas activates a zone campaign.

A zone campaign contains:

- Direction (BUY or SELL).
- Source zone and map identity.
- Three layered entries.
- Shared stop/invalidation.
- Three take-profit targets.
- Total account-risk budget split across the legs.
- Dedicated confirmation and spread controls.

Typical entry allocations currently used:

- Entry 1: 40%, market on confirmation.
- Entry 2: 35%, virtual market order on touch.
- Entry 3: 25%, virtual market order on touch.

The percentages divide one total campaign risk budget; each leg must not independently risk the entire budget.

Deeper entries are virtual rather than standing broker limit orders. Nyao waits for the executable market quote to reach the planned level, rechecks current transaction cost and risk, then submits a market order. This prevents an old pending order from filling during a later spread blowout.

### SELL/BUY quote semantics

- BUY zone membership and virtual touches use ASK where possible, because buys execute at ASK.
- SELL zone membership and virtual touches use BID where possible, because sells execute at BID.

With BTC spread near USD 60, the visible ASK can appear to touch a SELL layer while the executable BID is still about USD 60 below it. Dashboard values must clearly label BID/ASK basis to prevent confusion.

## Separate scalping and zone controls

Scalping and zone trading are treated as separate strategies.

Ordinary scalping has its own:

- Signal thresholds.
- New-bar/intrabar behavior.
- Spread filters.
- Limit-entry behavior.
- Order-frequency and duplicate-distance controls.
- Scalping risk cap.

Zone trading has its own:

- Combined zone confirmation.
- Dedicated spread gate using ATR, stop distance, and target distance.
- Layer activation tolerance.
- Shared campaign risk.
- Entries, stop and profit targets.

A scalp spread veto should not automatically veto an otherwise valid zone campaign. Each zone leg is checked against its dedicated cost cap. However, an excessively wide zone spread can still block a zone layer.

## Capital sizing

Atlas uses risk percentage and broker-aware conversion rather than simply choosing a fixed lot based on account balance.

Current deterministic base caps are approximately:

- Scalp base risk: 0.25% of equity.
- Zone base risk: 0.35% of equity.
- Maximum combined strategy risk cap: 1.0%.

Modifiers can only reduce or veto risk based on:

- Drawdown.
- Current-account loss streak.
- Risk state.
- Volatility.
- Existing exposure.
- Spread and execution conditions.

Nyao calculates broker-valid volume using the actual entry, stop, equity, tick value, minimum volume, maximum volume, and volume step. A larger account can therefore produce a larger broker-valid lot for the same percentage risk, but Gemini should not increase percentage risk merely because the balance is larger.

Confidence may reduce risk within a cap. It must not be used as an unconstrained reason to increase size.

## Current live BTC campaign at handoff

At the last verification:

- Symbol: `#BTCUSD`
- Campaign plan: `05e5d597089b537258c0`
- Mode: SELL ZONE MODE
- Campaign state: active and locked
- Ordinary scalping: suspended
- Open positions: one SELL, 0.01 lot
- Entry 1 broker fill: approximately `64942.458`
- Entry 2 planned level: `65166.113`, 35% allocation
- Entry 3 planned level: `65312.6264`, 25% allocation
- Shared stop: approximately `65593.152` in the Atlas plan (the broker position showed a very close stop around `65595.633`)
- TP1: approximately `64695.12`
- TP2: approximately `64470.61`
- TP3: approximately `64246.10`
- Restored total campaign risk: `0.24%`
- Approximate total campaign maximum-loss budget at USD 5,000 equity: `$11.99`
- Two virtual layers were waiting.

### Current campaign risk repair

An EA reattachment/transient status issue caused the active campaign's persisted total risk to become `0.0%`. This was incorrect.

Corrections:

- Active campaign parameters now survive a 90-second EA-reattachment grace period.
- The exact current campaign risk shown earlier by the dashboard (`0.24%`) was restored with operator authorization.
- A backup of the runtime directive was created before repair.
- The repair survived repeated backend refreshes/restarts.
- The API now shows both `0.24%` and approximately `$11.99` maximum campaign loss.

The repair does not bypass touch, spread, broker minimum-volume, stop, or other risk gates.

### Why Entry 2 had not executed

At final verification:

- Entry 2 SELL level: `65166.113`
- Executable BID: approximately `65098`
- ASK could be near/above the level due to the very large spread.
- Actual spread: approximately USD 61.
- Nyao's effective zone spread cap was approximately USD 29 for the relevant live calculation.

Therefore Entry 2 had not actually been touched by the executable BID, and the zone spread was also too wide. Once BID genuinely reaches the layer, remains within activation tolerance, spread clears, and the allocated risk supports a broker-valid lot, Nyao can submit it.

## Campaign immutability and restart behavior

Once Nyao acknowledges a zone plan and broker exposure exists, Atlas should preserve the campaign's:

- Plan ID.
- Direction.
- Entry levels and allocations.
- Shared stop.
- Profit targets.
- Original risk budget.

Market-score fluctuations or a new calculation must manage, not silently de-authorize or replace, an already-open campaign.

The campaign now remains locked during active exposure. A 90-second reattachment grace window prevents a momentary blank acknowledgement or zero-position report during EA restart from replacing it. After a genuinely flat campaign remains confirmed flat beyond the grace window, Atlas may release it and resume normal mode selection.

## Dashboard work completed

The dashboard was reorganized into clearer areas such as:

- Command Center.
- Market.
- Zones.
- Portfolio.
- Atlas Brain.
- Settings.
- Audit Log.

Relevant fixes included:

- Null-safe control rendering after browser refresh.
- Correct reconciliation after commands are applied.
- Removal of stale “READY_FOR_SECOND_HUMAN_ACTION” state after successful application.
- Clearer distinction between proposal workflow state and live Nyao acknowledgement.
- Separate Market and Zones pages.
- Zone chart rendering and ranked zone cards.
- Clearer active-zone authority/campaign state.
- Better explanation of why BUY/SELL is waiting or blocked.

Further UI refinement is still desirable. The primary page should answer, in order:

1. What is Atlas doing now?
2. Why is it doing that?
3. What exposure and risk exist?
4. What must happen next?
5. What did Gemini most recently decide?
6. What changed and what was actually acknowledged by Nyao?

## Important terminology

- **AUTO_EVALUATING**: Atlas is automatically running the Analyst/Critic policy workflow. It does not mean a trade is currently allowed.
- **APPLIED**: A proposal completed its configured policy workflow. During an active zone campaign, incompatible runtime changes may be deferred rather than immediately replacing live campaign controls.
- **DEFERRED ACTIVE ZONE PLAN**: The proposal was accepted for autonomous handling, but activation waits until the current immutable zone campaign is clear.
- **Zone authority active**: Atlas has authorized Nyao's zone executor for the active plan.
- **Zone mode active**: Nyao has loaded the plan and ordinary scalping is suspended.
- **Virtual layer waiting for touch**: The executable BID/ASK has not satisfied the layer touch and proximity rules.
- **Zone spread too wide**: Transaction cost exceeds the dedicated zone cap.
- **Risk volume below broker minimum or unavailable**: The allocated monetary risk cannot fund the broker's minimum lot at the planned stop distance, or broker calculation data is unavailable.

## Testing status

The following focused test groups passed after the latest work:

- Analyst/Critic contracts.
- Policy proposal and performance-learning behavior.
- Autonomous mode policy behavior.
- Gemini model fallback and malformed-JSON failover.
- Current-account performance isolation.
- Capital sizing.
- Bridge reliability.
- Policy performance.
- Nyao zone executor and campaign persistence.
- Python compilation checks.

The backend was restarted successfully after the final changes and the relevant live endpoints returned HTTP 200.

## External data roadmap

External sources should come after the internal pipeline is stable.

Potential future inputs:

- Scheduled macroeconomic news.
- Real-time market news.
- Telegram channel text.
- Telegram chart screenshots.
- Human-authored zones and trade signals.

Recommended approach:

1. Ingest external content as timestamped, source-attributed evidence.
2. Parse it into a non-executable scenario schema.
3. Compare external zones and bias with Atlas's internal map.
4. Track source reliability and performance over time.
5. Let external information adjust confidence or scenarios within defined bounds.
6. Never allow unverified Telegram text to directly place trades or bypass account risk controls.

## Known gaps and recommended next work

### 1. Live execution observability

Add a per-zone-leg state machine visible in the dashboard:

- Not approached.
- Near activation.
- Touched by BID/ASK.
- Spread blocked.
- Risk below minimum lot.
- Sent.
- Filled.
- Canceled.
- Already spent.

Show the exact executable quote and required distance for each leg. This would immediately explain Entry 2 behavior without interpreting raw telemetry.

### 2. Campaign risk ledger

Keep a durable, append-only campaign admission record separate from the frequently refreshed directive. It should store:

- Original equity.
- Original total risk percentage and amount.
- Per-leg allocated risk.
- Broker-calculated intended volume.
- Filled risk and remaining risk.
- Every cancellation, restoration, and repair event.

This is stronger than relying on the current mutable directive alone.

### 3. Broker-minimum-aware layer construction

Before activating a campaign, Atlas/Nyao should verify whether every allocated leg can fund the broker minimum volume at its entry and stop. If a leg is too small, Atlas should deterministically choose among safe options such as:

- Merge that allocation into another layer.
- Reduce the number of layers.
- Mark the layer non-executable before campaign admission.

It must not silently round volume upward beyond the approved total risk.

### 4. Spread calibration

BTC spread has been unusually large relative to the planned scalp and zone distances. Collect execution evidence before relaxing caps. The correct question is whether expected edge after spread/slippage remains positive, not merely whether the layer was touched.

### 5. Position-policy snapshot locking

The active position telemetry showed legacy fallback sources for some management, recovery, and trailing policy snapshots after restart. Verify that new positions permanently retain the exact policy epoch under which they opened.

### 6. Outcome-driven evaluation

Build strategy-separated reporting for:

- Scalp versus zone trades.
- Market regime.
- Spread/ATR bucket.
- Signal/zone confidence bucket.
- Entry leg.
- MFE/MAE.
- Slippage and transaction cost.
- Expected versus realized risk and reward.

Only change policies after sufficient comparable evidence. Avoid reacting to one or two trades as if they prove a parameter is good or bad.

### 7. Dashboard simplification

Continue reducing duplicated status cards. Use one authoritative “what Atlas is doing now” summary and move raw diagnostics behind expandable sections.

## Suggested immediate plan

1. Observe the current BTC campaign without bypassing the touch or spread gates.
2. Add the per-leg execution-state diagnostics to the dashboard.
3. Implement the durable campaign risk ledger and broker-minimum preflight.
4. Run multiple demo campaigns and verify actual risk, fill, TP/SL, cancellation, restart, and reconciliation behavior.
5. Evaluate scalp and zone outcomes separately.
6. Refine policy/risk logic using evidence.
7. Only then begin external-news and Telegram ingestion.

## Instructions for future ChatGPT responses

- Be candid that profitability is uncertain and cannot be guaranteed.
- Treat capital preservation as the first objective.
- Distinguish deterministic Atlas logic, Gemini advice, Nyao execution, and dashboard presentation.
- Do not recommend bypassing spread, stop, equity, or broker-volume protections merely to increase trade frequency.
- Do not assume ASK touching a SELL level or BID touching a BUY level means the executable quote touched.
- Keep scalp and zone strategies analytically separate.
- Remember that current-account trade evidence is isolated, while generalized learnings may persist.
- When proposing code changes, state that normal ChatGPT cannot directly inspect or modify the local repository unless the user uploads files; Codex can be used later for implementation.
- Ask for fresh screenshots or exported endpoint JSON when live state matters.

