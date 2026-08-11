from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.app.intelligence.parameter_registry import all_parameters
from backend.app.intelligence.account_identity import current_account_outcomes_file

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"

OUTCOMES_FILE = DATA_DIR / "trade_outcomes.json"
INTELLIGENCE_FILE = DATA_DIR / "intelligence_history.json"
DECISION_FILE = DATA_DIR / "policy_decision_history.json"
SHADOW_FILE = DATA_DIR / "shadow_policy_history.json"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _records(data: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def _norm(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 10)
    return value


def _runtime_value(runtime: dict[str, Any], parameter: dict[str, Any]) -> Any:
    if not isinstance(runtime, dict):
        return None
    status_key = parameter["status_key"]
    if status_key in runtime:
        return runtime.get(status_key)
    return runtime.get(parameter["name"])


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _outcome_pl(row: dict[str, Any]) -> float | None:
    for key in (
        "realized_net_pl",
        "realized_profit",
        "final_observed_net_pl_before_disappearance",
        "last_observed_net_pl",
    ):
        value = _finite_number(row.get(key))
        if value is not None:
            return value
    return None


def _outcome_class(row: dict[str, Any]) -> str:
    value = str(
        row.get("realized_result_class")
        or row.get("observed_result_class")
        or ""
    ).upper()
    if "WIN" in value or "PROFIT" in value:
        return "WIN"
    if "LOSS" in value:
        return "LOSS"
    pl = _outcome_pl(row)
    if pl is None:
        return "UNKNOWN"
    if pl > 0:
        return "WIN"
    if pl < 0:
        return "LOSS"
    return "FLAT"


def _distinct_sequence(values: list[Any]) -> tuple[int, int]:
    clean = [_norm(v) for v in values if v is not None]
    if not clean:
        return 0, 0
    distinct = len({repr(v) for v in clean})
    transitions = 0
    previous = clean[0]
    for value in clean[1:]:
        if value != previous:
            transitions += 1
            previous = value
    return distinct, transitions


def _value_groups(
    rows: list[dict[str, Any]],
    parameter: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = defaultdict(list)
    classes: dict[str, Counter[str]] = defaultdict(Counter)
    raw_values: dict[str, Any] = {}

    for row in rows:
        runtime = ((row.get("entry_context") or {}).get("runtime") or {})
        value = _runtime_value(runtime, parameter)
        if value is None:
            continue
        key = repr(_norm(value))
        raw_values[key] = _norm(value)
        pl = _outcome_pl(row)
        if pl is not None:
            groups[key].append(pl)
        classes[key][_outcome_class(row)] += 1

    result: dict[str, dict[str, Any]] = {}
    for key in sorted(set(groups) | set(classes)):
        pls = groups.get(key, [])
        total = sum(classes[key].values())
        wins = classes[key].get("WIN", 0)
        losses = classes[key].get("LOSS", 0)
        result[key] = {
            "value": raw_values.get(key),
            "outcome_count": total,
            "mean_pl": round(sum(pls) / len(pls), 4) if pls else None,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(100.0 * wins / total, 1) if total else None,
        }
    return result


def _association(
    groups: dict[str, dict[str, Any]],
    confounded_with: list[str] | None = None,
) -> dict[str, Any]:
    qualified = [
        row for row in groups.values()
        if int(row.get("outcome_count") or 0) >= 3
        and row.get("mean_pl") is not None
    ]
    if len(qualified) < 2:
        return {
            "available": False,
            "strength": "NONE",
            "best_observed_value": None,
            "worst_observed_value": None,
            "mean_pl_gap": None,
            "note": "Not enough outcome coverage across at least two observed parameter values.",
        }

    ordered = sorted(qualified, key=lambda x: float(x["mean_pl"]))
    worst = ordered[0]
    best = ordered[-1]
    gap = float(best["mean_pl"]) - float(worst["mean_pl"])
    abs_gap = abs(gap)

    if abs_gap < 0.25:
        strength = "WEAK"
    elif abs_gap < 1.0:
        strength = "MODEST"
    elif abs_gap < 3.0:
        strength = "MATERIAL"
    else:
        strength = "STRONG"

    confounded_with = confounded_with or []
    if confounded_with:
        return {
            "available": False,
            "strength": "CONFOUNDED",
            "raw_strength": strength,
            "best_observed_value": best["value"],
            "worst_observed_value": worst["value"],
            "mean_pl_gap": round(gap, 4),
            "confounded_with": confounded_with,
            "note": (
                "The outcome split is shared with other parameters that changed in "
                "the same policy cohort. The observed gap cannot be attributed to "
                "this parameter independently."
            ),
        }

    return {
        "available": True,
        "strength": strength,
        "best_observed_value": best["value"],
        "worst_observed_value": worst["value"],
        "mean_pl_gap": round(gap, 4),
        "note": "Descriptive historical association only; this is not causal proof that the parameter value caused the outcome.",
    }


def _outcome_partition_signature(
    rows: list[dict[str, Any]],
    parameter: dict[str, Any],
) -> tuple[int, ...] | None:
    """Describe how a parameter partitions outcomes, independent of its values.

    Parameters changed together can have different raw values but create the exact
    same outcome cohorts. Treating each cohort split as independent evidence would
    multiply one historical comparison across many controls.
    """
    group_ids: dict[str, int] = {}
    signature: list[int] = []
    for row in rows:
        runtime = ((row.get("entry_context") or {}).get("runtime") or {})
        value = _runtime_value(runtime, parameter)
        if value is None:
            signature.append(-1)
            continue
        key = repr(_norm(value))
        if key not in group_ids:
            group_ids[key] = len(group_ids)
        signature.append(group_ids[key])
    if len(group_ids) < 2:
        return None
    return tuple(signature)


def _family_signals(
    parameter: dict[str, Any],
    status: dict[str, Any],
    intel_records: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    family = str(parameter.get("family") or "")
    recent = intel_records[-300:]
    counts = Counter()

    for rec in recent:
        market = rec.get("market") or {}
        signal = rec.get("signal") or {}
        duplicate = rec.get("duplicate_distance") or {}
        exposure = rec.get("exposure") or {}
        hedge = rec.get("hedge") or {}
        risk = rec.get("risk") or {}

        if market.get("spread_within_limit") is False:
            counts["spread_block_snapshots"] += 1
        if duplicate.get("buy_blocked"):
            counts["buy_duplicate_blocks"] += 1
        if duplicate.get("sell_blocked"):
            counts["sell_duplicate_blocks"] += 1
        if exposure.get("strategy_open_positions", 0):
            counts["open_position_snapshots"] += 1
        if hedge.get("active_hedge_chains", 0):
            counts["hedge_active_snapshots"] += 1
        if str(risk.get("state") or "").upper() in {"ELEVATED", "HIGH", "CRITICAL"}:
            counts["elevated_risk_snapshots"] += 1
        if signal.get("buy_entry_eligible"):
            counts["buy_eligible_snapshots"] += 1
        if signal.get("sell_entry_eligible"):
            counts["sell_eligible_snapshots"] += 1

    new_bar_entries = 0
    intrabar_entries = 0
    hedge_outcomes = 0
    reentry_outcomes = 0
    managed_outcomes = 0
    partial_close_outcomes = 0
    be_outcomes = 0
    for row in outcomes:
        if row.get("entry_was_new_bar") is True:
            new_bar_entries += 1
        if str(row.get("entry_evaluation_event") or "").upper() == "INTRABAR":
            intrabar_entries += 1
        origin = str(row.get("order_origin") or row.get("origin_guess") or "").upper()
        if origin == "HEDGE_CHILD" or int(row.get("max_hedge_level_observed") or 0) > 0:
            hedge_outcomes += 1
        if origin == "VIRTUAL_SL_REENTRY":
            reentry_outcomes += 1
        if int(row.get("observation_count") or 0) > 1:
            managed_outcomes += 1
        if int(row.get("partial_close_level_max_observed") or 0) > 0:
            partial_close_outcomes += 1
        if row.get("break_even_ever_locked") is True:
            be_outcomes += 1

    direct_units = 0
    trigger_summary: list[str] = []

    if family == "SPREAD_FILTER":
        direct_units = counts["spread_block_snapshots"]
        trigger_summary.append(f'{direct_units} recent spread-block snapshots')
    elif family == "DUPLICATE_DISTANCE":
        direct_units = counts["buy_duplicate_blocks"] + counts["sell_duplicate_blocks"]
        trigger_summary.append(
            f'{counts["buy_duplicate_blocks"]} BUY + {counts["sell_duplicate_blocks"]} SELL duplicate-block snapshots'
        )
    elif family == "ENTRY_FREQUENCY":
        direct_units = new_bar_entries + intrabar_entries
        trigger_summary.append(f'{new_bar_entries} new-bar and {intrabar_entries} intrabar outcomes')
    elif family == "RECOVERY_REENTRY":
        direct_units = reentry_outcomes
        trigger_summary.append(f'{reentry_outcomes} virtual-SL re-entry outcomes')
    elif family == "HEDGE_RECOVERY":
        direct_units = hedge_outcomes
        trigger_summary.append(f'{hedge_outcomes} hedge/recovery outcomes')
    elif family in {"POSITION_HEALTH", "SL_MANAGEMENT", "TRAILING_EXIT"}:
        direct_units = managed_outcomes
        trigger_summary.append(f'{managed_outcomes} managed outcomes')
    elif family == "PARTIAL_CLOSE":
        direct_units = partial_close_outcomes
        trigger_summary.append(f'{partial_close_outcomes} outcomes with partial-close activity')
    elif family == "POSITION_SIZING":
        direct_units = len(outcomes)
        trigger_summary.append(f'{len(outcomes)} closed outcomes with sizing context')
    elif family == "ACCOUNT_RISK":
        direct_units = counts["elevated_risk_snapshots"]
        trigger_summary.append(f'{direct_units} recent elevated-risk snapshots')
    elif family == "ENTRY_DIRECTION":
        direct_units = len(outcomes)
        trigger_summary.append(f'{len(outcomes)} closed directional outcomes')
    elif family == "SIGNAL_MODEL":
        direct_units = len(outcomes)
        trigger_summary.append(f'{len(outcomes)} closed outcomes with entry signal context')
    elif family in {"STATIC_EXIT"}:
        direct_units = len(outcomes)
        trigger_summary.append(f'{len(outcomes)} closed outcomes')
    elif family == "LIMIT_ENTRY":
        limit_count = sum(
            1 for row in outcomes
            if "LIMIT" in str(row.get("order_origin") or row.get("origin_guess") or "").upper()
        )
        direct_units = limit_count
        trigger_summary.append(f'{limit_count} limit-entry outcomes')
    else:
        direct_units = min(len(recent), 40)
        trigger_summary.append(f'{direct_units} recent operational observations')

    return {
        "direct_evidence_units": int(direct_units),
        "trigger_summary": trigger_summary,
        "recent_signals": dict(counts),
        "managed_outcomes": managed_outcomes,
        "hedge_outcomes": hedge_outcomes,
        "reentry_outcomes": reentry_outcomes,
        "partial_close_outcomes": partial_close_outcomes,
        "break_even_outcomes": be_outcomes,
    }


def _maturity(
    snapshot_count: int,
    distinct_values: int,
    transitions: int,
    outcome_count: int,
    value_groups: dict[str, dict[str, Any]],
    direct_units: int,
    association_independent: bool,
) -> tuple[str, int, list[str]]:
    comparable_groups = sum(
        1 for row in value_groups.values()
        if int(row.get("outcome_count") or 0) >= 3
    )

    score = 0
    reasons: list[str] = []

    if snapshot_count >= 25:
        score += 1
        reasons.append("runtime observed repeatedly")
    if snapshot_count >= 150:
        score += 1
    if direct_units >= 5:
        score += 1
        reasons.append("direct family evidence exists")
    if direct_units >= 20:
        score += 1
    if outcome_count >= 5:
        score += 1
        reasons.append("closed outcomes carry this runtime value")
    if outcome_count >= 20:
        score += 1
    if distinct_values >= 2:
        score += 2
        reasons.append("more than one parameter value has been observed")
    if transitions >= 2:
        score += 1
        reasons.append("runtime has changed across observations")
    if comparable_groups >= 2 and association_independent:
        score += 3
        reasons.append("at least two values have comparable outcome samples")

    if score <= 1:
        level = "NEW"
    elif score <= 3:
        level = "INSUFFICIENT"
    elif score <= 6:
        level = "DEVELOPING"
    elif score <= 9:
        level = "MODERATE"
    else:
        level = "MATURE"

    return level, score, reasons


def build_parameter_evidence(
    status: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    intel_data = _load(INTELLIGENCE_FILE) or {}
    outcomes_data = _load(current_account_outcomes_file(OUTCOMES_FILE)) or {}

    intel_records = _records(intel_data, "records", "history", "snapshots")
    outcomes = [row for row in _records(outcomes_data, "closed", "outcomes") if row.get("strategy_learning_eligible") and str(row.get("execution_integrity") or "").upper() == "CLEAN"]

    parameters = all_parameters()
    signatures: dict[str, tuple[int, ...]] = {}
    signature_members: dict[tuple[int, ...], list[str]] = defaultdict(list)
    for parameter in parameters:
        signature = _outcome_partition_signature(outcomes, parameter)
        if signature is not None:
            signatures[parameter["name"]] = signature
            signature_members[signature].append(parameter["name"])

    result: dict[str, dict[str, Any]] = {}

    for parameter in parameters:
        values: list[Any] = []
        for record in intel_records:
            value = _runtime_value(record.get("runtime") or {}, parameter)
            if value is not None:
                values.append(value)

        distinct_values, transitions = _distinct_sequence(values)

        outcome_values = []
        for row in outcomes:
            runtime = ((row.get("entry_context") or {}).get("runtime") or {})
            value = _runtime_value(runtime, parameter)
            if value is not None:
                outcome_values.append(value)

        groups = _value_groups(outcomes, parameter)
        signature = signatures.get(parameter["name"])
        confounded_with = [
            name
            for name in signature_members.get(signature, [])
            if name != parameter["name"]
        ] if signature is not None else []
        association = _association(groups, confounded_with=confounded_with)
        family = _family_signals(parameter, status, intel_records, outcomes)

        level, maturity_score, maturity_reasons = _maturity(
            snapshot_count=len(values),
            distinct_values=distinct_values,
            transitions=transitions,
            outcome_count=len(outcome_values),
            value_groups=groups,
            direct_units=family["direct_evidence_units"],
            association_independent=not confounded_with,
        )

        supporting: list[str] = []
        contradicting: list[str] = []

        if family["direct_evidence_units"] > 0:
            supporting.extend(family["trigger_summary"])

        if distinct_values >= 2:
            supporting.append(
                f"{distinct_values} distinct historical values observed with {transitions} transitions"
            )
        else:
            contradicting.append(
                "Only one historical value is represented; Atlas cannot compare parameter settings yet."
            )

        if len(outcome_values) >= 5:
            supporting.append(
                f"{len(outcome_values)} closed outcomes contain this parameter at entry"
            )
        else:
            contradicting.append(
                f"Only {len(outcome_values)} closed outcomes contain this parameter at entry"
            )

        if confounded_with:
            sample = ", ".join(confounded_with[:4])
            suffix = "" if len(confounded_with) <= 4 else f" and {len(confounded_with) - 4} more"
            contradicting.append(
                "Outcome association is confounded by the same historical cohort "
                f"split as {sample}{suffix}."
            )

        comparable_groups = sum(
            1 for row in groups.values()
            if int(row.get("outcome_count") or 0) >= 3
        )
        if comparable_groups >= 2:
            supporting.append(
                f"{comparable_groups} parameter values have at least 3 outcome observations each"
            )
        else:
            contradicting.append(
                "No robust A/B-style historical comparison exists across parameter values."
            )

        if association["available"]:
            supporting.append(
                "Observed values show a descriptive performance separation; treat it as association, not causation."
            )
        else:
            contradicting.append(association["note"])

        current = status.get(parameter["status_key"])
        result[parameter["name"]] = {
            "parameter": parameter["name"],
            "label": parameter["label"],
            "domain": parameter["domain"],
            "family": parameter.get("family"),
            "current": current,
            "position_sensitive": parameter["position_sensitive"],
            "risk_direction": parameter["risk_direction"],
            "meaning": parameter["meaning"],
            "parameter_maturity": {
                "level": level,
                "score": maturity_score,
                "snapshot_observations": len(values),
                "distinct_values": distinct_values,
                "runtime_transitions": transitions,
                "outcomes_with_value": len(outcome_values),
                "direct_evidence_units": family["direct_evidence_units"],
                "reasons": maturity_reasons,
            },
            "outcome_by_observed_value": list(groups.values())[:12],
            "descriptive_association": association,
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "family_evidence": family,
            "causal_warning": (
                "Historical associations can rank investigation priorities, "
                "but do not prove that changing this parameter will improve performance."
            ),
        }

    return result
