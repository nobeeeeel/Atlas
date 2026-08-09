from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
DECISION_HISTORY_FILE = DATA_DIR / "policy_decision_history.json"
DECISION_STABILITY_FILE = DATA_DIR / "policy_decision_stability.json"

_LOCK = threading.Lock()
MAX_RECORDS = 20_000
HEARTBEAT_SECONDS = 60

# v0.2 recommendation-readiness gates. These do NOT execute anything.
MIN_RECOMMENDATION_CONFIDENCE = 60.0
MIN_RECOMMENDATION_SCORE_MARGIN = 7.5
MIN_RECOMMENDATION_DWELL_SECONDS = 180
MIN_RECOMMENDATION_OBSERVATIONS = 3
MIN_SUPPORTED_USABLE_EPISODES = 5
MIN_SUPPORTED_RATIO = 0.60
MAX_CHURN_15M = 3
MAX_CHURN_60M = 8

FIT_SCORE = {
    "GOOD": 10.0,
    "NEUTRAL": 3.0,
    "WEAK": -3.0,
    "POOR": -8.0,
}

RISK_RANK = {
    "LOW": 0,
    "MODERATE": 1,
    "ELEVATED": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(config: dict[str, Any]) -> str:
    payload = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _policy_key(changed_controls: dict[str, Any]) -> str:
    if not changed_controls:
        return "NO_RUNTIME_CHANGE"

    parts = []
    for name in sorted(changed_controls):
        change = changed_controls[name] or {}
        parts.append(
            f"{name}:{change.get('current')}->{change.get('shadow')}"
        )
    return " | ".join(parts)


def _evidence_for_policy(
    shadow_evaluation: dict[str, Any] | None,
    changed_controls: dict[str, Any],
) -> dict[str, Any]:
    evaluation = shadow_evaluation or {}
    key = _policy_key(changed_controls)
    aggregate = (
        evaluation.get("aggregate_5m_by_policy") or {}
    ).get(key)

    if not evaluation.get("ready") or aggregate is None:
        return {
            "quality": "INSUFFICIENT",
            "policy_key": key,
            "episode_count": 0,
            "supported": 0,
            "not_supported": 0,
            "mixed": 0,
            "insufficient_data": 0,
            "support_ratio": None,
            "interpretation": (
                "No matched 5-minute shadow-evaluation sample is available "
                "for this exact proposed change set."
            ),
        }

    episodes = int(aggregate.get("episode_count") or 0)
    supported = int(aggregate.get("supported") or 0)
    not_supported = int(aggregate.get("not_supported") or 0)
    mixed = int(aggregate.get("mixed") or 0)
    insufficient = int(aggregate.get("insufficient_data") or 0)

    usable = supported + not_supported + mixed
    support_ratio = (
        supported / usable
        if usable > 0
        else None
    )

    if usable >= 5 and support_ratio is not None and support_ratio >= 0.60:
        quality = "DIRECTIONALLY_SUPPORTED"
    elif usable >= 5 and support_ratio is not None and support_ratio <= 0.30:
        quality = "DIRECTIONALLY_NOT_SUPPORTED"
    elif usable >= 3:
        quality = "MIXED"
    else:
        quality = "INSUFFICIENT"

    return {
        "quality": quality,
        "policy_key": key,
        "episode_count": episodes,
        "usable_episode_count": usable,
        "supported": supported,
        "not_supported": not_supported,
        "mixed": mixed,
        "insufficient_data": insufficient,
        "support_ratio": (
            round(support_ratio, 4)
            if support_ratio is not None
            else None
        ),
        "interpretation": (
            "This is directional observational evidence only. It does not "
            "estimate counterfactual trading performance."
        ),
    }


def _replay_evidence(
    shadow_replay: dict[str, Any] | None,
) -> dict[str, Any]:
    replay = shadow_replay or {}
    coverage = replay.get("coverage") or {}
    confidence = coverage.get("decision_confidence") or {}

    replayed = int(coverage.get("replayed_fresh_trades") or 0)
    high = int(confidence.get("high") or 0)
    medium = int(confidence.get("medium") or 0)
    low = int(confidence.get("low") or 0)
    resolved = high + medium + low

    if not replay.get("ready") or replayed <= 0:
        quality = "INSUFFICIENT"
    elif high >= 5 or resolved >= 10:
        quality = "USEFUL_ENGINEERING_COVERAGE"
    elif resolved >= 3:
        quality = "LIMITED_ENGINEERING_COVERAGE"
    else:
        quality = "INSUFFICIENT"

    return {
        "quality": quality,
        "replayed_fresh_trades": replayed,
        "resolved_decision_count": resolved,
        "decision_confidence": {
            "high": high,
            "medium": medium,
            "low": low,
        },
        "warning": (
            "Replay coverage measures whether historical entry decisions can "
            "be reconstructed. It is not a profitability score and does not "
            "simulate alternate downstream hedge/management paths."
        ),
    }


def _candidate_score(
    intelligence: dict[str, Any],
    shadow_policy: dict[str, Any],
    evidence: dict[str, Any],
    replay_evidence: dict[str, Any],
) -> dict[str, Any]:
    confidence = float(intelligence.get("confidence") or 0.0)
    fit = str(intelligence.get("fit") or "NEUTRAL").upper()
    risk = intelligence.get("risk") or {}
    risk_state = str(risk.get("state") or "UNKNOWN").upper()
    veto = bool(risk.get("veto_new_risk"))

    changed = shadow_policy.get("changed_controls") or {}
    changed_count = len(changed)

    score = 50.0
    components: list[dict[str, Any]] = []

    confidence_component = max(-10.0, min(20.0, (confidence - 50.0) * 0.4))
    score += confidence_component
    components.append({
        "name": "intelligence_confidence",
        "value": round(confidence_component, 2),
        "detail": confidence,
    })

    fit_component = FIT_SCORE.get(fit, 0.0)
    score += fit_component
    components.append({
        "name": "fit",
        "value": fit_component,
        "detail": fit,
    })

    evidence_quality = evidence.get("quality")
    evidence_component = {
        "DIRECTIONALLY_SUPPORTED": 8.0,
        "DIRECTIONALLY_NOT_SUPPORTED": -10.0,
        "MIXED": -2.0,
        "INSUFFICIENT": 0.0,
    }.get(evidence_quality, 0.0)
    score += evidence_component
    components.append({
        "name": "shadow_evidence",
        "value": evidence_component,
        "detail": evidence_quality,
    })

    replay_quality = replay_evidence.get("quality")
    replay_component = {
        "USEFUL_ENGINEERING_COVERAGE": 4.0,
        "LIMITED_ENGINEERING_COVERAGE": 2.0,
        "INSUFFICIENT": 0.0,
    }.get(replay_quality, 0.0)
    score += replay_component
    components.append({
        "name": "replay_coverage",
        "value": replay_component,
        "detail": replay_quality,
    })

    # Penalize large simultaneous parameter jumps. Atlas eventually owns the
    # full runtime map, but early decisioning should prefer small attributable
    # changes while evidence is still being collected.
    change_penalty = -2.0 * max(0, changed_count - 3)
    score += change_penalty
    components.append({
        "name": "change_budget",
        "value": change_penalty,
        "detail": changed_count,
    })

    conceptual = shadow_policy.get("conceptual_controls") or {}
    risk_reducing = conceptual.get("new_risk_allowed") is False
    if veto:
        veto_component = 8.0 if risk_reducing else -20.0
        score += veto_component
        components.append({
            "name": "risk_veto_alignment",
            "value": veto_component,
            "detail": {
                "risk_state": risk_state,
                "risk_reducing": risk_reducing,
            },
        })

    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "components": components,
    }


def _build_policy_preference(
    status: dict[str, Any],
    intelligence: dict[str, Any],
    shadow_policy: dict[str, Any],
    shadow_evaluation: dict[str, Any] | None = None,
    shadow_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Atlas Policy Decision Engine v0.2.

    Selects between CURRENT_RUNTIME and ADVISOR_SHADOW as a SHADOW decision.
    It never writes commands.json and cannot auto-promote in v0.2.

    This is the first decision layer after Policy Epoch v3.3 proved that Nyao
    can preserve all 53 position-sensitive controls by entry policy epoch.
    """
    current_runtime = dict(shadow_policy.get("current_runtime") or {})
    advisor_runtime = dict(shadow_policy.get("shadow_runtime") or {})
    changed_controls = dict(shadow_policy.get("changed_controls") or {})

    evidence = _evidence_for_policy(
        shadow_evaluation,
        changed_controls,
    )
    replay = _replay_evidence(shadow_replay)

    current_candidate = {
        "name": "CURRENT_RUNTIME",
        "score": 50.0,
        "runtime": current_runtime,
        "fingerprint": _fingerprint(current_runtime),
        "changed_control_count": 0,
    }

    advisor_score = _candidate_score(
        intelligence,
        shadow_policy,
        evidence,
        replay,
    )
    advisor_candidate = {
        "name": "ADVISOR_SHADOW",
        "score": advisor_score["score"],
        "score_components": advisor_score["components"],
        "runtime": advisor_runtime,
        "fingerprint": _fingerprint(advisor_runtime),
        "changed_control_count": len(changed_controls),
        "changed_controls": changed_controls,
    }

    transition = shadow_policy.get("transition_plan") or {}
    transition_state = str(transition.get("apply_state") or "UNKNOWN")
    confidence = float(intelligence.get("confidence") or 0.0)
    veto = bool((intelligence.get("risk") or {}).get("veto_new_risk"))

    blockers: list[str] = ["SHADOW_ONLY_PHASE"]

    if confidence < 55.0:
        blockers.append("LOW_INTELLIGENCE_CONFIDENCE")

    if evidence.get("quality") in {
        "INSUFFICIENT",
        "MIXED",
        "DIRECTIONALLY_NOT_SUPPORTED",
    }:
        blockers.append(
            f"SHADOW_EVIDENCE_{evidence.get('quality')}"
        )

    if transition_state == "DEFER_OR_VERSION_LOCK":
        # This does not block shadow selection because v3.3 can preserve entry
        # policy, but it blocks future direct migration of existing positions.
        blockers.append("EXISTING_POSITIONS_REQUIRE_VERSION_LOCK")

    if len(changed_controls) > 3:
        blockers.append("CHANGE_BUDGET_EXCEEDED")

    score_margin = advisor_candidate["score"] - current_candidate["score"]

    if not changed_controls and not veto:
        selected = current_candidate
        decision_state = "HOLD_CURRENT"
        rationale = (
            "Advisor shadow runtime matches the current runtime and no fresh-risk "
            "veto is active."
        )
    elif advisor_candidate["score"] >= 55.0 and score_margin >= 5.0:
        selected = advisor_candidate
        decision_state = "SELECT_ADVISOR_SHADOW"
        rationale = (
            "Advisor shadow candidate cleared the v0.2 preference score "
            "margin. Selection is observational only and is not applied."
        )
    else:
        selected = current_candidate
        decision_state = "HOLD_CURRENT"
        rationale = (
            "Advisor shadow candidate did not clear the v0.2 preference score/margin gate. "
            "Atlas continues observing the current runtime."
        )

    current_epoch = int(status.get("policy_epoch") or 0)
    would_create_new_epoch = (
        selected["name"] == "ADVISOR_SHADOW"
        and bool(changed_controls)
    )

    decision_runtime = dict(selected["runtime"])

    promotion_eligible = False
    promotion_blockers = list(dict.fromkeys(blockers))

    return {
        "version": "0.2",
        "mode": "SHADOW_DECISION_STABILITY_GATED",
        "applied": False,
        "generated_at": _now_iso(),
        "decision_state": decision_state,
        "selected_candidate": selected["name"],
        "current_policy_epoch": current_epoch,
        "hypothetical_policy_epoch": (
            current_epoch + 1
            if would_create_new_epoch
            else current_epoch
        ),
        "would_create_new_policy_epoch": would_create_new_epoch,
        "current_runtime_fingerprint": current_candidate["fingerprint"],
        "decision_runtime_fingerprint": selected["fingerprint"],
        "decision_runtime_control_count": len(decision_runtime),
        "decision_runtime": decision_runtime,
        "selected_changed_controls": (
            changed_controls
            if selected["name"] == "ADVISOR_SHADOW"
            else {}
        ),
        "candidates": {
            "CURRENT_RUNTIME": {
                k: v
                for k, v in current_candidate.items()
                if k != "runtime"
            },
            "ADVISOR_SHADOW": {
                k: v
                for k, v in advisor_candidate.items()
                if k != "runtime"
            },
        },
        "decision_score_margin": round(score_margin, 2),
        "shadow_evidence": evidence,
        "shadow_replay_evidence": replay,
        "transition_plan": transition,
        "risk": {
            "state": (intelligence.get("risk") or {}).get("state"),
            "veto_new_risk": veto,
        },
        "regime": (intelligence.get("regime") or {}).get("regime"),
        "fit": intelligence.get("fit"),
        "confidence": confidence,
        "rationale": rationale,
        "promotion": {
            "eligible": promotion_eligible,
            "blockers": promotion_blockers,
            "next_mode_after_validation": "ADVISORY",
            "rule": (
                "v0.2 cannot write commands.json. Recommendation readiness is still ""non-executing; promotion requires a later "
                "explicitly enabled phase with a Risk Governor gate and "
                "Policy Epoch versioning."
            ),
        },
        "safety_contract": [
            "No commands.json write.",
            "No Nyao parameter mutation.",
            "No existing-position policy migration.",
            "All 53 position-sensitive controls remain governed by Nyao's entry-policy epoch lock.",
            "Fresh-risk veto remains conceptually distinct from recovery continuity.",
            "Decision scores are engineering heuristics, not expected-return or profitability estimates.",
        ],
    }


def build_policy_decision(
    status: dict[str, Any],
    intelligence: dict[str, Any],
    shadow_policy: dict[str, Any],
    shadow_evaluation: dict[str, Any] | None = None,
    shadow_replay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    preference = _build_policy_preference(
        status,
        intelligence,
        shadow_policy,
        shadow_evaluation=shadow_evaluation,
        shadow_replay=shadow_replay,
    )
    return finalize_policy_decision_v02(preference)


def _parse_dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _empty_stability_state() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "observed_candidate": None,
        "observed_fingerprint": None,
        "first_seen_at": None,
        "last_seen_at": None,
        "observation_count": 0,
        "candidate_switch_count_total": 0,
        "last_switch_at": None,
    }


def _read_stability_unlocked() -> dict[str, Any]:
    if not DECISION_STABILITY_FILE.exists():
        return _empty_stability_state()

    try:
        with DECISION_STABILITY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_stability_state()

    if not isinstance(data, dict):
        return _empty_stability_state()

    return data


def _recent_preference_churn(
    records: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    windows = {
        "15m": 15 * 60,
        "60m": 60 * 60,
    }

    results: dict[str, Any] = {}
    for label, seconds in windows.items():
        cutoff = now.timestamp() - seconds
        relevant: list[tuple[datetime, str | None, str | None]] = []

        for record in records:
            when = _parse_dt(record.get("recorded_at"))
            if when is None or when.timestamp() < cutoff:
                continue

            decision = record.get("decision") or {}
            relevant.append((
                when,
                decision.get("selected_candidate"),
                decision.get("decision_runtime_fingerprint"),
            ))

        relevant.sort(key=lambda item: item[0])

        switches = 0
        previous: tuple[str | None, str | None] | None = None
        unique_states: set[tuple[str | None, str | None]] = set()

        for _, candidate, fingerprint in relevant:
            state = (candidate, fingerprint)
            unique_states.add(state)
            if previous is not None and state != previous:
                switches += 1
            previous = state

        results[label] = {
            "record_count": len(relevant),
            "switch_count": switches,
            "unique_preference_states": len(unique_states),
        }

    results["within_limits"] = (
        results["15m"]["switch_count"] <= MAX_CHURN_15M
        and results["60m"]["switch_count"] <= MAX_CHURN_60M
    )
    return results


def observe_decision_stability(
    decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist continuous preference observation independently of decision-history
    deduplication.

    A repeated endpoint call can increase the observation count, but readiness
    also requires minimum elapsed dwell time, so request spamming cannot satisfy
    the stability gate by count alone.
    """
    now = datetime.now(timezone.utc)
    candidate = decision.get("selected_candidate")
    fingerprint = decision.get("decision_runtime_fingerprint")

    with _LOCK:
        state = _read_stability_unlocked()
        store = _read_store_unlocked()
        records = store.get("records") or []

        same_state = (
            state.get("observed_candidate") == candidate
            and state.get("observed_fingerprint") == fingerprint
        )

        if same_state:
            observation_count = int(state.get("observation_count") or 0) + 1
            first_seen_at = state.get("first_seen_at") or now.isoformat()
            switched = False
        else:
            observation_count = 1
            first_seen_at = now.isoformat()
            switched = state.get("observed_candidate") is not None

            if switched:
                state["candidate_switch_count_total"] = (
                    int(state.get("candidate_switch_count_total") or 0) + 1
                )
                state["last_switch_at"] = now.isoformat()

        state["observed_candidate"] = candidate
        state["observed_fingerprint"] = fingerprint
        state["first_seen_at"] = first_seen_at
        state["last_seen_at"] = now.isoformat()
        state["observation_count"] = observation_count
        state["updated_at"] = now.isoformat()

        first_seen = _parse_dt(first_seen_at) or now
        dwell_seconds = max(0.0, (now - first_seen).total_seconds())
        churn = _recent_preference_churn(records, now)

        _atomic_write(DECISION_STABILITY_FILE, state)

    stable_by_count = observation_count >= MIN_RECOMMENDATION_OBSERVATIONS
    stable_by_dwell = dwell_seconds >= MIN_RECOMMENDATION_DWELL_SECONDS
    stable_by_churn = bool(churn.get("within_limits"))

    return {
        "candidate": candidate,
        "fingerprint": fingerprint,
        "switched_this_observation": switched,
        "observation_count": observation_count,
        "first_seen_at": first_seen_at,
        "last_seen_at": now.isoformat(),
        "dwell_seconds": round(dwell_seconds, 2),
        "minimum_observations": MIN_RECOMMENDATION_OBSERVATIONS,
        "minimum_dwell_seconds": MIN_RECOMMENDATION_DWELL_SECONDS,
        "stable_by_observation_count": stable_by_count,
        "stable_by_dwell": stable_by_dwell,
        "churn": churn,
        "stable_by_churn": stable_by_churn,
        "stable": (
            stable_by_count
            and stable_by_dwell
            and stable_by_churn
        ),
        "candidate_switch_count_total": int(
            state.get("candidate_switch_count_total") or 0
        ),
        "last_switch_at": state.get("last_switch_at"),
        "state_file": str(DECISION_STABILITY_FILE),
    }


def build_recommendation_gate(
    decision: dict[str, Any],
    stability: dict[str, Any],
) -> dict[str, Any]:
    """
    Separate "Atlas prefers this policy" from "Atlas has enough evidence and
    stability to surface it as recommendation-ready."

    Even READY_FOR_ADVISORY remains non-executing in v0.2.
    """
    selected = decision.get("selected_candidate")
    evidence = decision.get("shadow_evidence") or {}
    replay = decision.get("shadow_replay_evidence") or {}
    confidence = float(decision.get("confidence") or 0.0)
    score_margin = float(decision.get("decision_score_margin") or 0.0)
    changed_controls = decision.get("selected_changed_controls") or {}

    usable = int(evidence.get("usable_episode_count") or 0)
    support_ratio = evidence.get("support_ratio")
    support_ratio_value = (
        float(support_ratio)
        if support_ratio is not None
        else None
    )

    gates = {
        "advisor_preferred": selected == "ADVISOR_SHADOW",
        "has_material_change": bool(changed_controls),
        "confidence": confidence >= MIN_RECOMMENDATION_CONFIDENCE,
        "score_margin": score_margin >= MIN_RECOMMENDATION_SCORE_MARGIN,
        "evidence_quality": (
            evidence.get("quality") == "DIRECTIONALLY_SUPPORTED"
        ),
        "evidence_sample_size": usable >= MIN_SUPPORTED_USABLE_EPISODES,
        "evidence_support_ratio": (
            support_ratio_value is not None
            and support_ratio_value >= MIN_SUPPORTED_RATIO
        ),
        "replay_coverage": replay.get("quality") in {
            "LIMITED_ENGINEERING_COVERAGE",
            "USEFUL_ENGINEERING_COVERAGE",
        },
        "candidate_observation_count": bool(
            stability.get("stable_by_observation_count")
        ),
        "candidate_dwell": bool(stability.get("stable_by_dwell")),
        "policy_churn": bool(stability.get("stable_by_churn")),
    }

    blockers: list[str] = []
    blocker_names = {
        "advisor_preferred": "CURRENT_RUNTIME_PREFERRED",
        "has_material_change": "NO_MATERIAL_POLICY_CHANGE",
        "confidence": "CONFIDENCE_BELOW_GATE",
        "score_margin": "SCORE_MARGIN_BELOW_HYSTERESIS_GATE",
        "evidence_quality": "EVIDENCE_NOT_DIRECTIONALLY_SUPPORTED",
        "evidence_sample_size": "EVIDENCE_SAMPLE_TOO_SMALL",
        "evidence_support_ratio": "SUPPORT_RATIO_BELOW_GATE",
        "replay_coverage": "REPLAY_COVERAGE_INSUFFICIENT",
        "candidate_observation_count": "CANDIDATE_STREAK_TOO_SHORT",
        "candidate_dwell": "CANDIDATE_DWELL_TOO_SHORT",
        "policy_churn": "POLICY_CHURN_TOO_HIGH",
    }

    for gate_name, passed in gates.items():
        if not passed:
            blockers.append(blocker_names[gate_name])

    ready = all(gates.values())

    if ready:
        state = "READY_FOR_ADVISORY"
        rationale = (
            "Atlas has a stable preferred shadow candidate with directionally "
            "supportive observational evidence and adequate engineering replay "
            "coverage. This is recommendation readiness only; nothing is applied."
        )
    else:
        state = "NOT_READY"
        rationale = (
            "Atlas may prefer a shadow candidate, but one or more stability, "
            "hysteresis, evidence, or coverage gates are not yet satisfied."
        )

    return {
        "recommendation_ready": ready,
        "recommendation_state": state,
        "candidate": selected if ready else None,
        "candidate_fingerprint": (
            decision.get("decision_runtime_fingerprint")
            if ready
            else None
        ),
        "gates": gates,
        "blockers": blockers,
        "thresholds": {
            "minimum_confidence": MIN_RECOMMENDATION_CONFIDENCE,
            "minimum_score_margin": MIN_RECOMMENDATION_SCORE_MARGIN,
            "minimum_dwell_seconds": MIN_RECOMMENDATION_DWELL_SECONDS,
            "minimum_observations": MIN_RECOMMENDATION_OBSERVATIONS,
            "minimum_supported_usable_episodes": MIN_SUPPORTED_USABLE_EPISODES,
            "minimum_support_ratio": MIN_SUPPORTED_RATIO,
            "maximum_churn_15m": MAX_CHURN_15M,
            "maximum_churn_60m": MAX_CHURN_60M,
        },
        "rationale": rationale,
        "execution": {
            "applied": False,
            "command_write_allowed": False,
            "next_possible_phase": "ADVISORY_PROPOSAL",
        },
    }


def finalize_policy_decision_v02(
    decision: dict[str, Any],
) -> dict[str, Any]:
    stability = observe_decision_stability(decision)
    recommendation = build_recommendation_gate(
        decision,
        stability,
    )

    decision = dict(decision)
    decision["version"] = "0.2"
    decision["mode"] = "SHADOW_DECISION_STABILITY_GATED"
    decision["preference"] = {
        "candidate": decision.get("selected_candidate"),
        "decision_state": decision.get("decision_state"),
        "score_margin": decision.get("decision_score_margin"),
        "fingerprint": decision.get("decision_runtime_fingerprint"),
        "interpretation": (
            "Preference is Atlas's current shadow choice. It is not the same "
            "as recommendation readiness."
        ),
    }
    decision["stability"] = stability
    decision["recommendation"] = recommendation

    # v0.2 remains hard shadow-only regardless of readiness.
    promotion = dict(decision.get("promotion") or {})
    promotion["eligible"] = False
    blockers = list(promotion.get("blockers") or [])
    if not recommendation["recommendation_ready"]:
        blockers.append("RECOMMENDATION_NOT_READY")
    blockers.append("V02_SHADOW_ONLY")
    promotion["blockers"] = list(dict.fromkeys(blockers))
    promotion["rule"] = (
        "v0.2 can declare recommendation readiness but cannot write commands. "
        "A later ADVISORY phase may package an explicit human-review proposal; "
        "execution remains disabled."
    )
    decision["promotion"] = promotion

    decision["safety_contract"] = [
        "No commands.json write.",
        "No Nyao parameter mutation.",
        "No existing-position policy migration.",
        "All 53 position-sensitive controls remain governed by Nyao's entry-policy epoch lock.",
        "Fresh-risk veto remains conceptually distinct from recovery continuity.",
        "Preference and recommendation readiness are separate states.",
        "Recommendation readiness is not an expected-return or profitability claim.",
        "v0.2 cannot auto-promote or auto-apply.",
    ]

    return decision


def get_policy_decision_stability() -> dict[str, Any]:
    with _LOCK:
        state = _read_stability_unlocked()
        store = _read_store_unlocked()

    now = datetime.now(timezone.utc)
    first_seen = _parse_dt(state.get("first_seen_at"))
    dwell = (
        max(0.0, (now - first_seen).total_seconds())
        if first_seen is not None
        else 0.0
    )
    churn = _recent_preference_churn(
        store.get("records") or [],
        now,
    )

    return {
        **state,
        "dwell_seconds": round(dwell, 2),
        "churn": churn,
        "thresholds": {
            "minimum_dwell_seconds": MIN_RECOMMENDATION_DWELL_SECONDS,
            "minimum_observations": MIN_RECOMMENDATION_OBSERVATIONS,
            "maximum_churn_15m": MAX_CHURN_15M,
            "maximum_churn_60m": MAX_CHURN_60M,
        },
        "state_file": str(DECISION_STABILITY_FILE),
    }


def _empty_store() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "record_count": 0,
        "records": [],
    }


def _read_store_unlocked() -> dict[str, Any]:
    if not DECISION_HISTORY_FILE.exists():
        return _empty_store()

    try:
        with DECISION_HISTORY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    records = data.get("records")
    if not isinstance(records, list):
        return _empty_store()

    return data


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _record_signature(decision: dict[str, Any]) -> tuple[Any, ...]:
    return (
        decision.get("decision_state"),
        decision.get("selected_candidate"),
        decision.get("current_policy_epoch"),
        decision.get("decision_runtime_fingerprint"),
        tuple(sorted(
            (decision.get("selected_changed_controls") or {}).keys()
        )),
        (decision.get("risk") or {}).get("state"),
        decision.get("regime"),
        (decision.get("recommendation") or {}).get("recommendation_state"),
    )


def record_policy_decision(
    decision: dict[str, Any],
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)

    with _LOCK:
        store = _read_store_unlocked()
        records = store.get("records") or []

        reason = "INITIAL"
        should_append = True

        if records:
            previous = records[-1]
            previous_decision = previous.get("decision") or {}
            if _record_signature(previous_decision) == _record_signature(decision):
                previous_when = previous.get("recorded_at")
                try:
                    previous_dt = datetime.fromisoformat(
                        str(previous_when).replace("Z", "+00:00")
                    )
                    age = (now - previous_dt.astimezone(timezone.utc)).total_seconds()
                except (TypeError, ValueError):
                    age = HEARTBEAT_SECONDS + 1

                if age < HEARTBEAT_SECONDS:
                    should_append = False
                    reason = "UNCHANGED"
                else:
                    reason = "HEARTBEAT"
            else:
                reason = "STATE_CHANGE"

        if should_append:
            records.append({
                "recorded_at": now.isoformat(),
                "reason": reason,
                "decision": decision,
            })
            if len(records) > MAX_RECORDS:
                records = records[-MAX_RECORDS:]

            store["records"] = records
            store["record_count"] = len(records)
            store["updated_at"] = now.isoformat()
            _atomic_write(DECISION_HISTORY_FILE, store)

        return {
            "recorded": should_append,
            "reason": reason,
            "record_count": len(records),
            "history_file": str(DECISION_HISTORY_FILE),
        }


def get_policy_decision_history(
    limit: int = 200,
) -> dict[str, Any]:
    with _LOCK:
        store = _read_store_unlocked()

    records = store.get("records") or []
    safe_limit = max(1, min(int(limit), 2000))

    return {
        "version": store.get("version", 1),
        "record_count": len(records),
        "records": records[-safe_limit:],
        "history_file": str(DECISION_HISTORY_FILE),
    }