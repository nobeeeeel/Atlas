from __future__ import annotations

from typing import Any

from backend.app.intelligence.parameter_evidence import build_parameter_evidence
from backend.app.intelligence.parameter_registry import (
    CHANGE_BUDGET,
    DOMAIN_ORDER,
    all_parameters,
    registry_summary,
)


def _same_value(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    try:
        return abs(float(a) - float(b)) <= 1e-12
    except (TypeError, ValueError):
        return a == b


def _domain_summary(
    parameter_evidence: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    levels = {"NEW": 0, "INSUFFICIENT": 1, "DEVELOPING": 2, "MODERATE": 3, "MATURE": 4}
    result: dict[str, dict[str, Any]] = {}

    for domain in DOMAIN_ORDER:
        rows = [x for x in parameter_evidence.values() if x["domain"] == domain]
        distribution = {name: 0 for name in levels}
        for row in rows:
            distribution[row["parameter_maturity"]["level"]] += 1

        mature_or_moderate = sum(
            1 for row in rows
            if levels[row["parameter_maturity"]["level"]] >= levels["MODERATE"]
        )
        developing_or_better = sum(
            1 for row in rows
            if levels[row["parameter_maturity"]["level"]] >= levels["DEVELOPING"]
        )

        # Domain maturity now reflects the parameter distribution, not merely
        # a large general history count.
        ratio = (mature_or_moderate / len(rows)) if rows else 0.0
        dev_ratio = (developing_or_better / len(rows)) if rows else 0.0

        if ratio >= 0.70:
            level = "MATURE"
        elif ratio >= 0.40:
            level = "MODERATE"
        elif dev_ratio >= 0.40:
            level = "DEVELOPING"
        elif rows:
            level = "INSUFFICIENT"
        else:
            level = "NEW"

        result[domain] = {
            "level": level,
            "parameter_count": len(rows),
            "mature_or_moderate_parameters": mature_or_moderate,
            "developing_or_better_parameters": developing_or_better,
            "distribution": distribution,
            "eligible_for_broad_optimization": ratio >= 0.40,
            "note": (
                "Domain maturity is derived from parameter-specific evidence "
                "coverage and is not a profitability claim."
            ),
        }
    return result


def _context_relevance(
    parameter: dict[str, Any],
    evidence: dict[str, Any],
    status: dict[str, Any],
    intelligence: dict[str, Any],
) -> tuple[float, list[str]]:
    family = str(parameter.get("family") or "")
    reasons: list[str] = []
    score = 5.0

    maturity = evidence["parameter_maturity"]
    score += {
        "NEW": 0,
        "INSUFFICIENT": 5,
        "DEVELOPING": 12,
        "MODERATE": 20,
        "MATURE": 28,
    }.get(maturity["level"], 0)

    direct = int(maturity.get("direct_evidence_units") or 0)
    if direct:
        score += min(25.0, 5.0 + direct / 4.0)
        reasons.append(f"{direct} direct evidence units for this parameter family")

    if int(maturity.get("distinct_values") or 0) >= 2:
        score += 12
        reasons.append("historical runtime variation exists")

    assoc = evidence.get("descriptive_association") or {}
    if assoc.get("available"):
        score += {"WEAK": 3, "MODEST": 7, "MATERIAL": 14, "STRONG": 20}.get(
            str(assoc.get("strength") or ""), 0
        )
        reasons.append(
            f'{assoc.get("strength")} descriptive outcome association across observed values'
        )

    regime = str((intelligence.get("regime") or {}).get("regime") or "UNKNOWN").upper()
    risk = str((intelligence.get("risk") or {}).get("state") or "UNKNOWN").upper()

    if family == "SPREAD_FILTER" and status.get("spread_within_limit") is False:
        score += 35
        reasons.append("spread gate is currently blocking")
    if family == "DUPLICATE_DISTANCE" and (
        status.get("buy_duplicate_blocked") or status.get("sell_duplicate_blocked")
    ):
        score += 35
        reasons.append("duplicate-distance gate is currently blocking")
    if family in {"POSITION_HEALTH", "SL_MANAGEMENT", "TRAILING_EXIT", "PARTIAL_CLOSE"} and int(status.get("strategy_open_positions") or 0) > 0:
        score += 18
        reasons.append("open positions make management behavior currently relevant")
    if family in {"HEDGE_RECOVERY", "RECOVERY_REENTRY"} and (
        int(status.get("active_hedge_chains") or 0) > 0
        or int(status.get("hedge_chain_positions") or 0) > 0
    ):
        score += 35
        reasons.append("recovery/hedge activity is currently active")
    if family in {"POSITION_SIZING", "ACCOUNT_RISK"} and risk in {"ELEVATED", "HIGH", "CRITICAL"}:
        score += 30
        reasons.append(f"current risk state is {risk}")
    if family in {"ENTRY_DIRECTION", "ENTRY_FREQUENCY", "SIGNAL_DAMPENING", "SIGNAL_MODEL"} and regime in {"RANGE_CHOP", "LOW_VOL_COMPRESSION", "TRANSITION"}:
        score += 18
        reasons.append(f"current regime {regime} increases entry/signal relevance")

    if parameter["position_sensitive"] and int(status.get("strategy_open_positions") or 0) > 0:
        score -= 8
        reasons.append("existing positions require entry-policy lock preservation")

    return max(0.0, score), reasons


def build_parameter_intelligence(
    status: dict[str, Any],
    intelligence: dict[str, Any],
    current_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameter_evidence = build_parameter_evidence(status)
    domain_maturity = _domain_summary(parameter_evidence)

    raw_proposed = intelligence.get("proposed_changes") or {}
    proposed: dict[str, Any] = {}

    # P2.2 fix: a current==proposed value is not a change.
    for name, value in raw_proposed.items():
        evidence = parameter_evidence.get(name)
        if evidence is None:
            continue
        current = evidence.get("current")
        if current is None:
            current = (current_command or {}).get(name)
        if _same_value(current, value):
            continue
        proposed[name] = value

    by_name = {p["name"]: p for p in all_parameters()}
    candidates: list[dict[str, Any]] = []

    for name, evidence in parameter_evidence.items():
        p = by_name[name]
        score, relevance_reasons = _context_relevance(
            p, evidence, status, intelligence
        )

        if name in proposed:
            action = "CURRENT_ADVISOR_PROPOSAL"
            proposed_value = proposed[name]
            score += 100
        else:
            action = "INVESTIGATE_ONLY"
            proposed_value = None

        maturity_level = evidence["parameter_maturity"]["level"]

        # Do not treat insufficient evidence as recommendation-ready.
        if action == "INVESTIGATE_ONLY" and maturity_level in {"NEW", "INSUFFICIENT"}:
            readiness = "WAIT_FOR_EVIDENCE"
        elif action == "INVESTIGATE_ONLY":
            readiness = "INVESTIGATE"
        else:
            readiness = "SUPERVISED_PROPOSAL"

        why_relevant = relevance_reasons + evidence["supporting_evidence"][:3]
        why_not_change = evidence["contradicting_evidence"][:4]
        if action == "INVESTIGATE_ONLY":
            why_not_change = [
                "No validated numeric recommendation has been generated for this parameter."
            ] + why_not_change

        candidates.append({
            "parameter": name,
            "label": p["label"],
            "domain": p["domain"],
            "family": p.get("family"),
            "current": evidence.get("current"),
            "proposed": proposed_value,
            "action": action,
            "readiness": readiness,
            "relevance_score": round(score, 1),
            "parameter_maturity": evidence["parameter_maturity"],
            "evidence_maturity": maturity_level,
            "position_sensitive": p["position_sensitive"],
            "risk_direction": p["risk_direction"],
            "meaning": p["meaning"],
            "why_relevant": why_relevant,
            "why_not_change": why_not_change,
            "supporting_evidence": evidence["supporting_evidence"],
            "contradicting_evidence": evidence["contradicting_evidence"],
            "descriptive_association": evidence["descriptive_association"],
            "outcome_by_observed_value": evidence["outcome_by_observed_value"],
            "causal_warning": evidence["causal_warning"],
        })

    candidates.sort(key=lambda x: (-x["relevance_score"], x["parameter"]))

    supervised = [
        c for c in candidates
        if c["action"] == "CURRENT_ADVISOR_PROPOSAL"
    ][:CHANGE_BUDGET]

    investigations = [
        c for c in candidates
        if c["action"] == "INVESTIGATE_ONLY"
    ][:15]

    spread_points = status.get("spread_points")
    spread_cap_points = status.get("effective_spread_cap_points")
    try:
        measured_spread_within_cap = (
            float(spread_points) <= float(spread_cap_points)
            if float(spread_cap_points) > 0
            else None
        )
    except (TypeError, ValueError):
        measured_spread_within_cap = None

    packet_warnings: list[str] = []
    if (
        measured_spread_within_cap is False
        and status.get("spread_within_limit") is True
    ):
        packet_warnings.append(
            "Observed spread exceeds the calculated cap, but the runtime spread "
            "gate is passing (for example because the spread filter is disabled)."
        )

    llm_packet = {
        "packet_version": "1.1",
        "purpose": "ANALYST_CRITIC_INPUT_ONLY",
        "execution_authority": "NONE",
        "symbol": status.get("symbol"),
        "market_context": {
            "regime": intelligence.get("regime"),
            "risk": intelligence.get("risk"),
            "confidence": intelligence.get("confidence"),
            "summary": intelligence.get("summary"),
            "spread_gate_passed": status.get("spread_within_limit"),
            "spread_filter_enabled": status.get("runtime_enable_max_spread_filter"),
            "spread_points": spread_points,
            "effective_spread_cap_points": spread_cap_points,
            "observed_spread_within_cap": measured_spread_within_cap,
            "current_atr": status.get("current_atr"),
            "average_atr": status.get("average_atr"),
            "volatility_ratio": status.get("volatility_ratio"),
            "strategy_open_positions": status.get("strategy_open_positions"),
            "strategy_floating_pl": status.get("strategy_floating_pl"),
        },
        "data_quality_warnings": packet_warnings,
        "current_validated_advisor_proposals": [
            {
                "parameter": c["parameter"],
                "current": c["current"],
                "proposed": c["proposed"],
                "maturity": c["evidence_maturity"],
                "supporting_evidence": c["supporting_evidence"][:5],
                "contradicting_evidence": c["contradicting_evidence"][:5],
            }
            for c in supervised
        ],
        "top_parameters_for_reasoning": [
            {
                "parameter": c["parameter"],
                "domain": c["domain"],
                "family": c["family"],
                "current": c["current"],
                "maturity": c["evidence_maturity"],
                "relevance_score": c["relevance_score"],
                "risk_direction": c["risk_direction"],
                "position_sensitive": c["position_sensitive"],
                "meaning": c["meaning"],
                "why_relevant": c["why_relevant"][:5],
                "why_not_change": c["why_not_change"][:5],
                "descriptive_association": c["descriptive_association"],
            }
            for c in investigations[:8]
        ],
        "rules": [
            "Treat historical associations as descriptive evidence, not causal proof.",
            "Do not invent an executable numeric change unless Atlas later validates it.",
            "Respect the three-control change budget.",
            "Existing-position policy locks cannot be bypassed.",
            "Human review remains mandatory.",
        ],
    }

    return {
        "version": "2.2",
        "mode": "SUPERVISED_PARAMETER_INTELLIGENCE",
        "registry": registry_summary(),
        "domain_maturity": domain_maturity,
        "raw_advisor_change_count": len(raw_proposed),
        "current_advisor_change_count": len(proposed),
        "no_op_advisor_changes_filtered": len(raw_proposed) - len(proposed),
        "change_budget": CHANGE_BUDGET,
        "supervised_candidates": supervised,
        "top_investigation_candidates": investigations,
        "parameter_evidence": parameter_evidence,
        "llm_evidence_packet": llm_packet,
        "safety": {
            "direct_execution_allowed": False,
            "llm_execution_allowed": False,
            "human_review_required": True,
            "position_policy_lock_preserved": True,
            "causal_claims_allowed": False,
            "note": (
                "P2.2 ranks parameters using parameter-specific historical coverage, "
                "runtime variation and descriptive outcome associations. It does not "
                "autonomously invent new numeric parameter values."
            ),
        },
    }
