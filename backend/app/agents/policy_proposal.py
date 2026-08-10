from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.agents.llm_provider import LlmProvider
from backend.app.agents.llm_review import _parse_json, _schema_prompt
from backend.app.intelligence.parameter_registry import all_parameters


class ProposedPolicyChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter: str
    proposed: Any
    rationale: str
    expected_effect: str
    evidence_used: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=100)


class GeminiZoneContextAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_used: bool = False
    execution_lane: Literal[
        "NORMAL_SCALP",
        "ZONE_AWARE_SCALP",
        "ZONE_CAMPAIGN",
        "UNKNOWN",
    ] = "UNKNOWN"
    directional_context: Literal["BUY", "SELL", "BOTH", "NONE"] = "NONE"

    @field_validator("directional_context", mode="before")
    @classmethod
    def normalize_directional_context(cls, value: Any) -> Any:
        if value is None:
            return "NONE"
        token = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "BULLISH": "BUY",
            "LONG": "BUY",
            "UPSIDE": "BUY",
            "BEARISH": "SELL",
            "SHORT": "SELL",
            "DOWNSIDE": "SELL",
            "MIXED": "BOTH",
            "BIDIRECTIONAL": "BOTH",
            "TWO_SIDED": "BOTH",
            "NEUTRAL": "NONE",
            "NO_BIAS": "NONE",
            "UNKNOWN": "NONE",
        }
        return aliases.get(token, token)

    assessment: str = "No zone context assessment was supplied."
    scalping_implications: list[str] = Field(default_factory=list, max_length=12)
    evidence_used: list[str] = Field(default_factory=list, max_length=12)


class GemmaPolicyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_name: str = Field(min_length=3, max_length=100)
    market_regime: str
    market_summary: str
    policy_thesis: str
    past_performance_used: bool
    atlas_prior_analysis_used: bool = False
    responsiveness_analysis_used: bool = False
    responsiveness_profile: str = "UNKNOWN"
    responsiveness_diagnosis: list[str] = Field(default_factory=list, max_length=12)
    atlas_analysis_agreements: list[str] = Field(default_factory=list, max_length=12)
    atlas_analysis_disagreements: list[str] = Field(default_factory=list, max_length=12)
    performance_diagnosis: list[str] = Field(default_factory=list, max_length=12)
    weaknesses_targeted: list[str] = Field(default_factory=list, max_length=12)
    zone_context_assessment: GeminiZoneContextAssessment = Field(
        default_factory=GeminiZoneContextAssessment
    )
    reviewed_parameters: list[str] = Field(default_factory=list, max_length=200)
    changes: list[ProposedPolicyChange] = Field(default_factory=list, max_length=157)
    expected_behavior: list[str] = Field(default_factory=list, max_length=10)
    risks_and_tradeoffs: list[str] = Field(default_factory=list, max_length=10)
    revert_conditions: list[str] = Field(min_length=1, max_length=10)
    observation_window: str
    overall_confidence: float = Field(ge=0, le=100)


class CriticRejectedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter: str
    reason: str


class PolicyCriticReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["ACCEPT_FOR_SUPERVISED_REVIEW", "REVISE", "REJECT"]
    summary: str
    approved_parameters: list[str] = Field(default_factory=list, max_length=157)
    rejected_changes: list[CriticRejectedChange] = Field(
        default_factory=list, max_length=157
    )
    interaction_warnings: list[str] = Field(default_factory=list, max_length=12)
    required_revisions: list[str] = Field(default_factory=list, max_length=12)
    confirms_no_direct_execution: bool


POLICY_ANALYST_PROMPT = """You are the primary Gemini reasoning brain for the
Atlas NYAO SCALPING strategy. Review the complete supplied NYAO runtime-control
catalog and decide whether each control should stay at its current value or change
for the current account, live market regime, execution conditions, and observed
performance. All controls in control_catalog belong to the NYAO scalp strategy
lifecycle, including entry, signal construction, sizing preferences, exits,
position management, trailing, recovery/hedging, and operational filters.

Atlas already owns the authoritative catalog. Do not echo every unchanged name.
Put changed controls and any controls you explicitly discuss in reviewed_parameters,
and only actual changes in changes. Respect every min, max, step, option, and
existing-position lock. Build one coherent full-runtime scalp policy rather than
optimizing isolated knobs.

IMPORTANT AUTHORITY BOUNDARY:
- You MAY optimize any control present in control_catalog.
- You MAY use deterministic zone analysis as market context for scalping.
- You MAY NOT change zone policy, zone geometry, zone confirmation rules, zone
  campaign construction, zone risk allocation, capital-regime budgets, broker
  feasibility, or Atlas risk-governor authority. Those are deterministic Atlas
  systems and are not part of control_catalog.
- Zone context is evidence, never a direct trade instruction. Never issue orders.

Use scalp_zone_context and zone_trading as read-only evidence. Pay attention to the
execution lane (NORMAL_SCALP, ZONE_AWARE_SCALP, or ZONE_CAMPAIGN), zone side,
timeframe, score, freshness, price location, higher-timeframe structure, and
campaign feasibility. When Atlas is in ZONE_AWARE_SCALP, the aligned direction is
a deterministic constraint enforced by Atlas/Nyao; reason about how the NYAO scalp
policy performs inside that context without overriding the constraint. Autonomous
scalp-policy updates may continue while the zone is WATCHING, because no campaign
risk has been committed yet. Do not tune merely to force the waiting zone to trade,
and do not weaken normal scalp cost/risk gates. When execution_lane becomes
ZONE_CAMPAIGN, Atlas has crossed the deterministic commit boundary: do not try to
force concurrent scalp entries, and allow new policy activation to defer until the
campaign releases execution authority.

Use performance context as mandatory feedback when closed outcomes exist. Diagnose
loss streaks, expectancy, entry/exit behavior, regime splits, MFE/MAE, recovery
chains, runtime fingerprints, and policy epochs. Results labelled NYAO_BASELINE
predate Atlas-applied policies and establish the baseline. Historical associations
marked CONFOUNDED are bundle-level clues, not causal proof about one control. Set
past_performance_used=true whenever current-account closed outcomes exist and name
concrete weaknesses targeted by the proposed policy.

Performance evidence is strictly scoped to account_fingerprint. If closed_count is
zero, set past_performance_used=false and do not invent a win/loss streak, P/L
history, or failed trades for this account. Cross-account learning may provide
generalized Nyao, regime, execution, and risk knowledge only; never transplant a
prior account's trade counts, P/L, balance, equity, drawdown, or streaks.

When scalping_responsiveness is supplied, treat latency and opportunity cost as a
first-class objective but never optimize raw trade frequency. Set
responsiveness_analysis_used=true, select FAST, BALANCED, or SELECTIVE, and provide
a concrete responsiveness_diagnosis. Intrabar entry is valid only when
max_trades_per_candle <= 1 and duplicate-distance protection remains enabled.

Sizing controls are strategy preferences, not permission to exceed Atlas's
deterministic approved monetary-risk envelope. Never increase sizing or recovery
aggressiveness to recover losses or bypass an Atlas capital/risk veto. Existing
positions retain their entry policy epoch; do not assume a new policy rewrites an
open position's locked management policy.

Atlas prior analysis is independent evidence, not an instruction to copy. Compare
your conclusion with shadow policy/evaluation/replay, stability, transition, and
policy-epoch diagnostics when supplied. Set atlas_prior_analysis_used=true and
state concrete agreements and genuine disagreements.

For symbol-dependent point thresholds, do not infer calibration from the parameter
range alone. Compare fixed-point gates with observed point/tick scale and ATR; if
scale is ambiguous, prefer a validated ATR-relative gate or retain the existing
fixed threshold rather than creating a total execution lockout.

Populate zone_context_assessment to show how the read-only zone context influenced
your scalp-policy reasoning. It must describe context only and must never propose a
zone-policy mutation. Return strict JSON matching the required schema and nothing
else.
"""

POLICY_CRITIC_PROMPT = """You are the Atlas Gemini Policy Critic.
Independently audit the proposed complete NYAO scalp-runtime policy against the
supplied evidence and validated 157-control catalog. Check that changes form a
coherent bundle, do not contradict one another, do not overclaim confounded history,
and respect existing-position locks and deterministic Atlas risk/capital authority.

The supplied zone information is READ-ONLY context. Reject reasoning that treats a
zone as permission to issue an order or attempts to mutate zone policy, geometry,
confirmation, risk allocation, capital sizing, broker feasibility, or risk-governor
limits. Those systems are outside the NYAO runtime-control catalog.

This is proposal review only: never issue a trade, order, or command. In
approved_parameters, list only parameters present in validated_proposal.changes
that you explicitly approve; never list unchanged catalog controls. Put rejected
proposed changes in rejected_changes. Return strict JSON matching the required
schema.
"""


def adaptive_change_budget(status: dict[str, Any]) -> dict[str, Any]:
    open_positions = int(status.get("strategy_open_positions") or 0)
    parameters = all_parameters()
    budget = (
        len(parameters)
        if open_positions == 0
        else sum(1 for row in parameters if not row.get("position_sensitive"))
    )
    return {
        "max_changes": budget,
        "parameters_that_must_be_reviewed": len(parameters),
        "strategy_open_positions": open_positions,
        "position_sensitive_changes_allowed": open_positions == 0,
        "model": "FULL_REGISTRY_POLICY_V2",
        "interpretation": (
            "Gemma decides KEEP or CHANGE for every control. The change count is "
            "limited only by existing-position locks, not an arbitrary small budget."
        ),
    }


def build_atlas_prior_analysis(
    *,
    shadow_policy: dict[str, Any],
    shadow_evaluation: dict[str, Any],
    shadow_replay: dict[str, Any],
    policy_decision: dict[str, Any],
    decision_stability: dict[str, Any],
    policy_epochs: dict[str, Any],
) -> dict[str, Any]:
    recent_episodes = []
    for episode in (shadow_evaluation.get("recent_episodes") or [])[-6:]:
        horizons = episode.get("horizons") or {}
        recent_episodes.append({
            "started_at": episode.get("started_at"),
            "regime": episode.get("regime"),
            "risk_state": episode.get("risk_state"),
            "fit": episode.get("fit"),
            "changed_controls": episode.get("changed_controls"),
            "policy_direction": episode.get("policy_direction"),
            "horizon_results": {
                horizon: {
                    "classification": (
                        row.get("directional_support") or {}
                    ).get("classification"),
                    "reasons": (
                        row.get("directional_support") or {}
                    ).get("reasons"),
                    "outcomes": row.get("outcomes"),
                }
                for horizon, row in horizons.items()
            },
        })

    recent_replays = [
        {
            key: replay.get(key)
            for key in (
                "ticket",
                "direction",
                "origin_guess",
                "regime",
                "risk_state",
                "fit",
                "changed_controls",
                "actual_decision",
                "shadow_decision",
                "decision_confidence",
                "blockers",
                "unresolved_constraints",
                "observed_outcome",
            )
        }
        for replay in (shadow_replay.get("recent_replays") or [])[-12:]
    ]
    epoch_summaries = [
        {
            "policy_epoch": row.get("policy_epoch"),
            "symbol": row.get("symbol"),
            "applied_command_version": row.get("applied_command_version"),
            "runtime_control_count": row.get("runtime_control_count"),
            "first_captured_at": row.get("first_captured_at"),
            "last_captured_at": row.get("last_captured_at"),
        }
        for row in (policy_epochs.get("epochs") or [])[-8:]
    ]
    return {
        "packet_version": "1.0",
        "instruction": (
            "Use these as independent Atlas analyses. Compare, do not blindly copy; "
            "cite agreements, disagreements, evidence quality, and transition limits."
        ),
        "current_shadow_policy": {
            key: shadow_policy.get(key)
            for key in (
                "policy_epoch",
                "current_runtime_fingerprint",
                "shadow_runtime_fingerprint",
                "changed_control_count",
                "changed_controls",
                "conceptual_controls",
                "transition_plan",
                "regime",
                "risk_state",
                "risk_score",
                "fit",
                "confidence",
                "rationale",
                "safety_notes",
            )
        },
        "shadow_evaluation": {
            "ready": shadow_evaluation.get("ready"),
            "shadow_episode_count": shadow_evaluation.get("shadow_episode_count"),
            "intelligence_snapshot_count": shadow_evaluation.get(
                "intelligence_snapshot_count"
            ),
            "closed_outcome_count": shadow_evaluation.get("closed_outcome_count"),
            "aggregate_5m_by_policy": shadow_evaluation.get(
                "aggregate_5m_by_policy"
            ),
            "recent_episodes": recent_episodes,
            "interpretation_rules": shadow_evaluation.get("interpretation_rules"),
        },
        "shadow_replay": {
            "ready": shadow_replay.get("ready"),
            "mode": shadow_replay.get("mode"),
            "source_counts": shadow_replay.get("source_counts"),
            "coverage": shadow_replay.get("coverage"),
            "observational_diagnostics": shadow_replay.get(
                "observational_diagnostics"
            ),
            "replayability_matrix": shadow_replay.get("replayability_matrix"),
            "recent_replays": recent_replays,
            "interpretation_rules": shadow_replay.get("interpretation_rules"),
        },
        "policy_decision": {
            key: policy_decision.get(key)
            for key in (
                "decision_state",
                "selected_candidate",
                "current_policy_epoch",
                "hypothetical_policy_epoch",
                "would_create_new_policy_epoch",
                "selected_changed_controls",
                "decision_score_margin",
                "shadow_evidence",
                "shadow_replay_evidence",
                "transition_plan",
                "risk",
                "regime",
                "fit",
                "confidence",
                "rationale",
                "promotion",
                "stability",
                "recommendation",
            )
        },
        "decision_stability": decision_stability,
        "policy_epoch_history": {
            "epoch_count": policy_epochs.get("epoch_count"),
            "recent_epochs": epoch_summaries,
        },
    }


def build_policy_input(
    status: dict[str, Any],
    parameter_intelligence: dict[str, Any],
    *,
    performance_analytics: dict[str, Any] | None = None,
    outcome_summary: dict[str, Any] | None = None,
    trade_outcomes: dict[str, Any] | None = None,
    atlas_prior_analysis: dict[str, Any] | None = None,
    responsiveness_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = parameter_intelligence.get("parameter_evidence") or {}
    ranked = {
        row["parameter"]: row
        for row in (
            parameter_intelligence.get("supervised_candidates", [])
            + parameter_intelligence.get("top_investigation_candidates", [])
        )
        if isinstance(row, dict) and row.get("parameter")
    }
    catalog: list[dict[str, Any]] = []
    for parameter in all_parameters():
        row = evidence.get(parameter["name"]) or {}
        rank = ranked.get(parameter["name"]) or {}
        control = {
            "parameter": parameter["name"],
            "domain": parameter["domain"],
            "family": parameter.get("family"),
            "kind": parameter["kind"],
            "current": row.get("current"),
            "min": parameter.get("min"),
            "max": parameter.get("max"),
            "step": parameter.get("step"),
            "options": parameter.get("options"),
            "risk_direction": parameter.get("risk_direction"),
            "position_sensitive": parameter.get("position_sensitive"),
        }
        # Every control retains its validation and risk metadata. Rich historical
        # evidence is attached only to the currently ranked controls so the full
        # 157-control packet remains within hosted-model request quotas.
        if rank:
            association = row.get("descriptive_association") or {}
            control["priority_evidence"] = {
                "meaning": parameter.get("meaning"),
                "maturity": (row.get("parameter_maturity") or {}).get("level"),
                "relevance_score": rank.get("relevance_score"),
                "supporting": (row.get("supporting_evidence") or [])[:2],
                "contradicting": (row.get("contradicting_evidence") or [])[:1],
                "historical_association": {
                    "strength": association.get("strength"),
                    "best_observed_value": association.get("best_observed_value"),
                    "worst_observed_value": association.get("worst_observed_value"),
                    "mean_pl_gap": association.get("mean_pl_gap"),
                    "note": association.get("note"),
                },
            }
        catalog.append(control)
    performance_analytics = performance_analytics or {}
    outcome_summary = outcome_summary or {}
    trade_outcomes = trade_outcomes or {}
    closed = trade_outcomes.get("closed") or []
    current_loss_streak = 0
    for trade in reversed(closed):
        if trade.get("exact_realized_pl_available"):
            realized = float(trade.get("realized_net_pl") or 0.0)
            if realized >= 0.0:
                break
        elif trade.get("observed_result_class") != "NEGATIVE_BEFORE_DISAPPEARANCE":
            break
        current_loss_streak += 1

    parameter_contexts = performance_analytics.get("parameter_contexts") or {}
    compact_configurations = [
        {
            "fingerprint": row.get("fingerprint"),
            "count": row.get("count"),
            "summary": row.get("summary"),
        }
        for row in (parameter_contexts.get("configurations") or [])[:12]
    ]
    recovery = performance_analytics.get("recovery_attribution") or {}
    recovery_summary_keys = (
        "ready",
        "identified_chain_groups",
        "recovery_chain_count",
        "complete_recovery_chain_count",
        "active_recovery_chain_count",
        "incomplete_history_chain_count",
        "standalone_trade_count",
        "unassigned_hedge_ticket_count",
        "recovery_chain_observed_positive",
        "recovery_chain_observed_negative",
        "recovery_chain_observed_pl_sum",
    )
    performance_context = {
        "attribution_label": "NYAO_BASELINE_UNTIL_FIRST_ATLAS_APPLIED_POLICY",
        "closed_count": outcome_summary.get(
            "closed_count", performance_analytics.get("closed_count", len(closed))
        ),
        "current_consecutive_loss_streak": current_loss_streak,
        "outcome_quality": outcome_summary.get(
            "outcome_quality", performance_analytics.get("outcome_quality")
        ),
        "exact_realized_pl_available": outcome_summary.get(
            "exact_realized_pl_available",
            performance_analytics.get("exact_realized_pl_available"),
        ),
        "exact_realized_closed_count": outcome_summary.get(
            "exact_realized_closed_count"
        ),
        "all_tracked": performance_analytics.get("all_tracked"),
        "fresh_or_reentry": performance_analytics.get("fresh_or_reentry"),
        "by_entry_regime": performance_analytics.get("by_entry_regime"),
        "by_entry_fit": performance_analytics.get("by_entry_fit"),
        "by_entry_risk": performance_analytics.get("by_entry_risk"),
        "by_origin": performance_analytics.get("by_origin"),
        "by_duplicate_filter": performance_analytics.get("by_duplicate_filter"),
        "by_scalp_context": performance_analytics.get("by_scalp_context"),
        "runtime_configuration_results": {
            "unique_runtime_configurations": parameter_contexts.get(
                "unique_runtime_configurations"
            ),
            "configurations": compact_configurations,
            "causality_warning": (
                "Runtime comparisons are observational and confounded; evaluate "
                "configuration bundles rather than claiming single-control causality."
            ),
        },
        "recovery_chain_results": {
            key: recovery.get(key) for key in recovery_summary_keys
        },
        "learning_instruction": (
            "Diagnose what has failed, propose a measurable improvement, and define "
            "an outcome-count-based retain/revise/revert test. Future outcomes must "
            "be compared by applied Atlas policy epoch and runtime fingerprint."
        ),
    }

    return {
        "packet_version": "2.3",
        "purpose": "FULL_NYAO_SCALP_RUNTIME_POLICY_PROPOSAL",
        "execution_authority": "PROPOSAL_ONLY",
        "symbol": status.get("symbol"),
        "budget": adaptive_change_budget(status),
        "account_context": {
            "balance": status.get("balance"),
            "equity": status.get("equity"),
            "free_margin": status.get("free_margin"),
            "account_margin": status.get("account_margin"),
            "margin_level_pct": status.get("margin_level_pct"),
            "account_leverage": status.get("account_leverage"),
            "peak_equity": status.get("peak_equity"),
            "equity_drawdown_usd": status.get("equity_drawdown_usd"),
            "equity_drawdown_pct": status.get("equity_drawdown_pct"),
            "strategy_open_positions": status.get("strategy_open_positions"),
            "total_lots": status.get("total_lots"),
            "strategy_floating_pl": status.get("strategy_floating_pl"),
        },
        "market_context": (
            parameter_intelligence.get("llm_evidence_packet", {})
            .get("market_context", {})
        ),
        "performance_context": performance_context,
        "atlas_prior_analysis": atlas_prior_analysis or {},
        "scalping_responsiveness": responsiveness_analysis or {},
        "data_quality_warnings": (
            parameter_intelligence.get("llm_evidence_packet", {})
            .get("data_quality_warnings", [])
        ),
        "current_deterministic_advisor_candidates": [
            {
                "parameter": row.get("parameter"),
                "current": row.get("current"),
                "proposed": row.get("proposed"),
                "why_relevant": row.get("why_relevant"),
                "why_not_change": row.get("why_not_change"),
            }
            for row in parameter_intelligence.get("supervised_candidates", [])
        ],
        "control_catalog": catalog,
    }


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    try:
        return abs(float(left) - float(right)) <= 1e-10
    except (TypeError, ValueError):
        return left == right


def _validated_value(parameter: dict[str, Any], value: Any) -> Any:
    kind = str(parameter.get("kind") or "")
    mql_type = str(parameter.get("mql_type") or "")
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be boolean")
        return value
    if kind == "time":
        if not isinstance(value, str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", value
        ):
            raise ValueError("must be an HH:MM time")
        return value
    if kind == "select":
        options = parameter.get("options") or []
        allowed = [option.get("value") for option in options]
        if value not in allowed:
            raise ValueError(f"must be one of {allowed}")
        return value
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("must be finite")
        minimum = parameter.get("min")
        maximum = parameter.get("max")
        if minimum is not None and number < float(minimum) - 1e-10:
            raise ValueError(f"must be >= {minimum}")
        if maximum is not None and number > float(maximum) + 1e-10:
            raise ValueError(f"must be <= {maximum}")
        step = parameter.get("step")
        if step:
            origin = float(minimum or 0)
            units = (number - origin) / float(step)
            if abs(units - round(units)) > 1e-7:
                raise ValueError(f"must align to step {step}")
        return int(round(number)) if mql_type == "int" else number
    if not isinstance(value, str):
        raise ValueError("must be a string")
    return value


def validate_policy_proposal(
    proposal: GemmaPolicyProposal,
    policy_input: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    catalog = {
        row["parameter"]: row
        for row in policy_input.get("control_catalog", [])
    }
    registry = {row["name"]: row for row in all_parameters()}
    reviewed = proposal.reviewed_parameters
    if len(reviewed) != len(set(reviewed)):
        raise ValueError("reviewed_parameters contains duplicates.")
    unknown_reviewed = sorted(set(reviewed) - set(catalog))
    if unknown_reviewed:
        raise ValueError(
            "Gemini reported reviewed parameters outside the supplied catalog: "
            f"{unknown_reviewed[:10]}."
        )
    closed_count = int(
        (policy_input.get("performance_context") or {}).get("closed_count") or 0
    )
    if closed_count > 0:
        if not proposal.past_performance_used:
            raise ValueError("Gemma ignored available past performance.")
        if not proposal.performance_diagnosis:
            raise ValueError("Gemma did not diagnose the available past performance.")
        if not proposal.weaknesses_targeted:
            raise ValueError("Gemma did not identify weaknesses targeted by the policy.")
    if policy_input.get("atlas_prior_analysis"):
        if not proposal.atlas_prior_analysis_used:
            raise ValueError("Gemini ignored Atlas prior analysis.")
        if not (
            proposal.atlas_analysis_agreements
            or proposal.atlas_analysis_disagreements
        ):
            raise ValueError(
                "Gemini did not explicitly compare its conclusion with Atlas analysis."
            )
    if policy_input.get("scalping_responsiveness"):
        if not proposal.responsiveness_analysis_used:
            raise ValueError("Gemini ignored Atlas scalping responsiveness analysis.")
        if not proposal.responsiveness_diagnosis:
            raise ValueError("Gemini did not diagnose scalping responsiveness.")
        if proposal.responsiveness_profile.upper() not in {
            "FAST", "BALANCED", "SELECTIVE"
        }:
            raise ValueError("Gemini returned an invalid responsiveness profile.")
    max_changes = int((policy_input.get("budget") or {}).get("max_changes") or 0)
    if len(proposal.changes) > max_changes:
        raise ValueError(
            f"Policy proposes {len(proposal.changes)} changes; budget is {max_changes}."
        )

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    deferred_locked: list[dict[str, Any]] = []
    positions_open = int(
        (policy_input.get("budget") or {}).get("strategy_open_positions") or 0
    ) > 0
    for change in proposal.changes:
        if change.parameter in seen:
            raise ValueError(f"Duplicate parameter: {change.parameter}")
        seen.add(change.parameter)
        parameter = registry.get(change.parameter)
        current_row = catalog.get(change.parameter)
        if parameter is None or current_row is None:
            raise ValueError(f"Unknown parameter: {change.parameter}")
        if positions_open and parameter.get("position_sensitive"):
            deferred_locked.append({
                **change.model_dump(),
                "current": current_row.get("current"),
                "domain": parameter.get("domain"),
                "family": parameter.get("family"),
                "risk_direction": parameter.get("risk_direction"),
                "position_sensitive": True,
                "deferred_reason": "POSITION_SENSITIVE_CONTROL_LOCKED_WHILE_EXPOSURE_OPEN",
            })
            continue
        try:
            proposed = _validated_value(parameter, change.proposed)
        except ValueError as exc:
            raise ValueError(f"{change.parameter} {exc}") from exc
        current = current_row.get("current")
        if _same_value(current, proposed):
            raise ValueError(f"{change.parameter} does not change its current value.")
        validated.append({
            **change.model_dump(),
            "current": current,
            "proposed": proposed,
            "domain": parameter.get("domain"),
            "family": parameter.get("family"),
            "risk_direction": parameter.get("risk_direction"),
            "position_sensitive": parameter.get("position_sensitive"),
        })

    proposed_patch = {row["parameter"]: row["proposed"] for row in validated}

    def final_value(name: str) -> Any:
        return proposed_patch.get(name, (catalog.get(name) or {}).get("current"))

    if final_value("enable_new_bar_entry_only") is False:
        trades_per_candle = final_value("max_trades_per_candle")
        if trades_per_candle is None or int(trades_per_candle) > 1:
            raise ValueError(
                "Intrabar entry requires max_trades_per_candle <= 1."
            )
        if final_value("enable_duplicate_distance_filter") is not True:
            raise ValueError(
                "Intrabar entry requires duplicate-distance protection enabled."
            )
    return validated, deferred_locked


def run_policy_proposal(
    policy_input: dict[str, Any],
    analyst_provider: LlmProvider,
    critic_provider: LlmProvider,
) -> dict[str, Any]:
    analyst_raw = analyst_provider.complete(
        system_prompt=POLICY_ANALYST_PROMPT,
        user_prompt=_schema_prompt(GemmaPolicyProposal, policy_input),
    )
    proposal = GemmaPolicyProposal.model_validate(_parse_json(analyst_raw))
    validated_changes, deferred_locked_changes = validate_policy_proposal(
        proposal, policy_input
    )

    proposed_names = {row["parameter"] for row in validated_changes}
    critic_input = {
        "policy_context": {
            "symbol": policy_input.get("symbol"),
            "execution_authority": policy_input.get("execution_authority"),
            "budget": policy_input.get("budget"),
            "account_context": policy_input.get("account_context"),
            "account_identity": policy_input.get("account_identity"),
            "cross_account_learning": policy_input.get("cross_account_learning"),
            "market_context": policy_input.get("market_context"),
            "performance_context": policy_input.get("performance_context"),
            "scalping_responsiveness": policy_input.get("scalping_responsiveness"),
            "scalp_zone_context": policy_input.get("scalp_zone_context"),
            "zone_trading": policy_input.get("zone_trading"),
            "data_quality_warnings": policy_input.get("data_quality_warnings"),
            "changed_control_catalog": [
                row
                for row in policy_input.get("control_catalog", [])
                if row.get("parameter") in proposed_names
            ],
        },
        "validated_proposal": {
            **proposal.model_dump(),
            "changes": validated_changes,
            "deferred_locked_changes": deferred_locked_changes,
        },
    }
    critic_raw = critic_provider.complete(
        system_prompt=POLICY_CRITIC_PROMPT,
        user_prompt=_schema_prompt(PolicyCriticReview, critic_input),
    )
    critic = PolicyCriticReview.model_validate(_parse_json(critic_raw))
    if not critic.confirms_no_direct_execution:
        raise ValueError("Critic failed the proposal-only execution boundary.")

    proposed_names = {row["parameter"] for row in validated_changes}
    reported_approvals = set(critic.approved_parameters)
    reported_rejections = {
        row.parameter for row in critic.rejected_changes
    }
    approved_proposed = proposed_names & reported_approvals
    ignored_non_change_approvals = reported_approvals - proposed_names
    ignored_non_change_rejections = reported_rejections - proposed_names
    unreviewed_proposed = (
        proposed_names - approved_proposed - reported_rejections
    )
    proposal_hash = hashlib.sha256(json.dumps(
        {"input": policy_input, "proposal": proposal.model_dump()},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")).hexdigest()[:24]

    accepted = (
        critic.verdict == "ACCEPT_FOR_SUPERVISED_REVIEW"
        and not unreviewed_proposed
        and not (reported_rejections & proposed_names)
    )
    critic_result = {
        **critic.model_dump(),
        "approved_parameters": sorted(approved_proposed),
        "ignored_non_change_approvals": sorted(ignored_non_change_approvals),
        "ignored_non_change_rejections": sorted(ignored_non_change_rejections),
        "unreviewed_proposed_changes": sorted(unreviewed_proposed),
        "proposal_coverage_complete": not unreviewed_proposed,
    }
    if critic.verdict == "ACCEPT_FOR_SUPERVISED_REVIEW" and not accepted:
        critic_result["effective_verdict"] = "REVISE"
        critic_result["required_revisions"] = [
            *critic.required_revisions,
            "Critic must explicitly approve or reject every proposed change.",
        ]
    else:
        critic_result["effective_verdict"] = critic.verdict
    catalog_names = [
        str(row["parameter"])
        for row in policy_input.get("control_catalog", [])
    ]
    return {
        "policy_proposal_version": "3.8",
        "proposal_id": proposal_hash,
        "symbol": policy_input.get("symbol"),
        "state": (
            "READY_FOR_RAPID_SUPERVISED_REVIEW" if accepted
            else "BLOCKED_BY_LLM_CRITIC"
        ),
        "execution_authority": "PROPOSAL_ONLY",
        "policy_scope": "FULL_157_CONTROL_NYAO_SCALP_POLICY",
        "adaptive_budget": policy_input.get("budget"),
        "deferred_locked_changes": deferred_locked_changes,
        "position_lock_deferral_active": bool(deferred_locked_changes),
        "bundle": {
            **proposal.model_dump(exclude={"changes", "reviewed_parameters"}),
            "reviewed_parameters": catalog_names,
            "model_reported_reviewed_parameters": proposal.reviewed_parameters,
            "catalog_review_scope_enforced": True,
            "changes": validated_changes,
            "deferred_locked_changes": deferred_locked_changes,
        },
        "runtime_patch": {
            row["parameter"]: row["proposed"] for row in validated_changes
        },
        "zone_context_assessment": proposal.zone_context_assessment.model_dump(mode="json"),
        "full_policy_decision": {
            "reviewed_control_count": len(catalog_names),
            "model_reported_reviewed_count": len(proposal.reviewed_parameters),
            "changed_control_count": len(validated_changes),
            "kept_control_count": (
                len(catalog_names) - len(validated_changes)
            ),
        },
        "critic": critic_result,
        "eligible_for_rapid_supervised_review": accepted,
        "eligible_for_direct_execution": False,
    }
