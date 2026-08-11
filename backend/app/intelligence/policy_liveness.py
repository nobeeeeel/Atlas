from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MIN_ATTRIBUTABLE_UNITS_FOR_RETIGHTEN = 5
MIN_EVALUATIONS_FOR_LIVENESS = 120
STARVED_ELIGIBLE_RATE_PCT = 3.0
DORMANT_ELIGIBLE_RATE_PCT = 1.0
STARVED_POLICY_BLOCK_SHARE_PCT = 70.0
DORMANT_POLICY_BLOCK_SHARE_PCT = 82.0
WAITING_RELEASE_SHARE_PCT = 40.0
MIN_ATTRIBUTABLE_UNITS_FOR_RELAX = 2
NEAR_THRESHOLD_GAP_POINTS = 1.0
MIN_NEAR_THRESHOLD_SHARE_FOR_RELAX_PCT = 3.0
STARVED_THRESHOLD_RELAX_STEP = 0.20
DORMANT_THRESHOLD_RELAX_STEP = 0.30
MIN_AUTONOMOUS_SIGNAL_THRESHOLD = 4.50

ENTRY_THRESHOLD_CONTROLS = {
    "min_buy_signal_score",
    "min_sell_signal_score",
}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _dominant_share(responsiveness: dict[str, Any], reason: str) -> float:
    target = reason.upper()
    rows = (
        (responsiveness.get("entry_observations") or {})
        .get("dominant_block_reasons")
        or []
    )
    for row in rows:
        if str(row.get("reason") or "").upper() == target:
            return _f(row.get("share_pct"))
    return 0.0


def _current_epoch_performance(
    policy_performance: dict[str, Any] | None,
    current_epoch: int,
) -> dict[str, Any]:
    for row in list((policy_performance or {}).get("by_policy_epoch") or []):
        if str(row.get("policy_epoch")) == str(current_epoch):
            return dict(row)
    return {
        "policy_epoch": str(current_epoch),
        "closed_risk_units": 0,
        "sample_state": "INSUFFICIENT",
        "net_pl": 0.0,
        "expectancy": 0.0,
    }


def assess_policy_liveness(
    status: dict[str, Any],
    current_command: dict[str, Any],
    responsiveness: dict[str, Any],
    *,
    policy_performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure whether Atlas policy itself is starving otherwise-healthy execution.

    This is deliberately not a trades-per-hour target. It only classifies policy
    starvation when deterministic execution/risk authority is healthy enough that
    threshold/new-bar selectivity is the dominant reason opportunities disappear.
    """
    entry = responsiveness.get("entry_observations") or {}
    evaluations = _i(entry.get("side_evaluation_count"))
    eligible_rate = _f(entry.get("eligible_rate_pct"), 0.0)
    score_share = _dominant_share(responsiveness, "SCORE_BELOW_THRESHOLD")
    waiting_share = _dominant_share(responsiveness, "WAITING_FOR_NEW_BAR")
    new_bar_only = bool(current_command.get("enable_new_bar_entry_only", True))
    # Historical WAITING_FOR_NEW_BAR observations must not keep suppressing a
    # policy after the live temporal gate has already been released.
    effective_waiting_share = waiting_share if new_bar_only else 0.0
    policy_block_share = min(100.0, score_share + effective_waiting_share)

    entry_obs = responsiveness.get("entry_observations") or {}
    near_buy = _i(entry_obs.get("near_threshold_buy_block_count"))
    near_sell = _i(entry_obs.get("near_threshold_sell_block_count"))
    near_share = _f(entry_obs.get("near_threshold_block_share_pct"))
    avg_buy_gap = _f(entry_obs.get("average_buy_score_deficit_when_blocked"), 999.0)
    avg_sell_gap = _f(entry_obs.get("average_sell_score_deficit_when_blocked"), 999.0)

    current_epoch = _i(current_command.get("policy_epoch"))
    epoch_perf = _current_epoch_performance(policy_performance, current_epoch)
    attributable_units = _i(epoch_perf.get("closed_risk_units"))

    protection = dict(status.get("_atlas_capital_protection") or {})
    capital_or_risk_veto = bool(
        protection.get("active")
        or status.get("trading_paused")
        or not bool(status.get("session_open", True))
    )
    execution_healthy = bool(
        status.get("market_quote_fresh", status.get("quote_fresh", True))
        and status.get("scalp_structure_feasible", True)
        and status.get("scalp_cost_ratio_feasible", True)
        and not capital_or_risk_veto
    )

    intrabar_safety_ready = bool(
        _i(current_command.get("max_trades_per_candle"), 1) <= 1
        and current_command.get("enable_duplicate_distance_filter", True) is True
    )

    state = "ACTIVE"
    reason = "Policy selectivity is not starving the strategy."
    if execution_healthy and evaluations >= MIN_EVALUATIONS_FOR_LIVENESS:
        if (
            eligible_rate <= DORMANT_ELIGIBLE_RATE_PCT
            and policy_block_share >= DORMANT_POLICY_BLOCK_SHARE_PCT
        ):
            state = "DORMANT"
            reason = "Policy gates dominate healthy execution and almost no side evaluations remain eligible."
        elif (
            eligible_rate <= STARVED_ELIGIBLE_RATE_PCT
            and policy_block_share >= STARVED_POLICY_BLOCK_SHARE_PCT
        ):
            state = "STARVED"
            reason = "Policy gates dominate healthy execution and eligible opportunities are scarce."
        elif str(responsiveness.get("profile") or "").upper() == "SELECTIVE":
            state = "SELECTIVE"
            reason = "Policy is selective but has not crossed the starvation threshold."

    return {
        "version": "atlas-policy-liveness-v1",
        "state": state,
        "reason": reason,
        "execution_healthy": execution_healthy,
        "evaluation_count": evaluations,
        "eligible_rate_pct": round(eligible_rate, 3),
        "score_block_share_pct": round(score_share, 3),
        "waiting_for_new_bar_share_pct": round(waiting_share, 3),
        "effective_waiting_for_new_bar_share_pct": round(effective_waiting_share, 3),
        "policy_block_share_pct": round(policy_block_share, 3),
        "near_threshold_block_share_pct": round(near_share, 3),
        "near_threshold_buy_block_count": near_buy,
        "near_threshold_sell_block_count": near_sell,
        "average_buy_score_deficit_when_blocked": None if avg_buy_gap >= 999.0 else round(avg_buy_gap, 3),
        "average_sell_score_deficit_when_blocked": None if avg_sell_gap >= 999.0 else round(avg_sell_gap, 3),
        "enable_new_bar_entry_only": new_bar_only,
        "intrabar_safety_ready": intrabar_safety_ready,
        "current_policy_epoch": current_epoch,
        "current_epoch_closed_risk_units": attributable_units,
        "current_epoch_sample_state": epoch_perf.get("sample_state"),
        "current_epoch_net_pl": epoch_perf.get("net_pl"),
        "current_epoch_expectancy": epoch_perf.get("expectancy"),
        "minimum_attributable_units_before_retighten": MIN_ATTRIBUTABLE_UNITS_FOR_RETIGHTEN,
        "retighten_evidence_ready": attributable_units >= MIN_ATTRIBUTABLE_UNITS_FOR_RETIGHTEN,
        "threshold_relax_evidence_ready": attributable_units >= MIN_ATTRIBUTABLE_UNITS_FOR_RELAX,
        "threshold_relaxation_eligible": bool(
            execution_healthy
            and state in {"STARVED", "DORMANT"}
            and attributable_units >= MIN_ATTRIBUTABLE_UNITS_FOR_RELAX
            and near_share >= MIN_NEAR_THRESHOLD_SHARE_FOR_RELAX_PCT
        ),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "rules": [
            "Do not optimize raw trade count; only detect policy-caused starvation when execution authority is otherwise healthy.",
            "A new policy epoch must accumulate attributable completed risk units before entry thresholds may tighten again.",
            "Do not simultaneously raise entry thresholds and enable new-bar-only gating in one autonomous activation.",
            "When policy is STARVED or DORMANT, autonomous entry-selectivity changes may only hold or loosen until liveness recovers.",
            "Intrabar release is permitted only with max_trades_per_candle <= 1 and duplicate-distance protection enabled.",
            "Threshold starvation recovery is incremental, one direction at a time, and requires near-threshold evidence from the current operating window.",
        ],
    }


def guard_autonomous_patch(
    patch: dict[str, Any],
    current_command: dict[str, Any],
    liveness: dict[str, Any],
) -> dict[str, Any]:
    """Fail safe against self-throttling autonomous entry-policy ratchets.

    The guard preserves unrelated policy changes. It blocks only entry-selectivity
    mutations that would compound starvation or re-tighten before the current epoch
    has generated enough attributable outcomes. When new-bar-only itself is the
    dominant starvation source and intrabar safety prerequisites remain intact, the
    guard performs a one-dimensional temporal-gate release rather than lowering
    thresholds at the same time.
    """
    original = dict(patch or {})
    guarded = dict(original)
    blocked: dict[str, str] = {}
    injected: dict[str, Any] = {}

    state = str(liveness.get("state") or "ACTIVE").upper()
    evidence_ready = bool(liveness.get("retighten_evidence_ready"))

    threshold_increases: list[str] = []
    for name in ENTRY_THRESHOLD_CONTROLS:
        if name not in guarded:
            continue
        current = _f(current_command.get(name))
        proposed = _f(guarded.get(name), current)
        if proposed > current:
            threshold_increases.append(name)
            if not evidence_ready:
                guarded.pop(name, None)
                blocked[name] = "CURRENT_POLICY_EPOCH_HAS_INSUFFICIENT_ATTRIBUTABLE_OUTCOMES"
            elif state in {"STARVED", "DORMANT"}:
                guarded.pop(name, None)
                blocked[name] = f"POLICY_LIVENESS_{state}_NO_FURTHER_TIGHTENING"

    # A policy cycle must not stack a temporal gate on top of threshold tightening.
    enabling_new_bar = (
        guarded.get("enable_new_bar_entry_only") is True
        and current_command.get("enable_new_bar_entry_only") is not True
    )
    remaining_threshold_increase = any(
        name in guarded and _f(guarded[name]) > _f(current_command.get(name))
        for name in ENTRY_THRESHOLD_CONTROLS
    )
    if enabling_new_bar and remaining_threshold_increase:
        guarded.pop("enable_new_bar_entry_only", None)
        blocked["enable_new_bar_entry_only"] = "COMPOUND_ENTRY_SUPPRESSION_WITH_THRESHOLD_TIGHTENING"

    if state in {"STARVED", "DORMANT"}:
        # Never make the temporal gate more restrictive while starved.
        if guarded.get("enable_new_bar_entry_only") is True:
            guarded.pop("enable_new_bar_entry_only", None)
            blocked["enable_new_bar_entry_only"] = f"POLICY_LIVENESS_{state}_NO_TEMPORAL_TIGHTENING"

        waiting_share = _f(liveness.get("waiting_for_new_bar_share_pct"))
        if (
            current_command.get("enable_new_bar_entry_only") is True
            and waiting_share >= WAITING_RELEASE_SHARE_PCT
            and bool(liveness.get("intrabar_safety_ready"))
        ):
            guarded["enable_new_bar_entry_only"] = False
            injected["enable_new_bar_entry_only"] = False

    # If the temporal gate is already open and the policy remains genuinely
    # starved by near-threshold score suppression, relax one directional
    # threshold incrementally. Never lower both directions in one corrective
    # action, and never chase signals that are many score points away.
    if (
        state in {"STARVED", "DORMANT"}
        and current_command.get("enable_new_bar_entry_only") is not True
        and bool(liveness.get("threshold_relaxation_eligible"))
    ):
        buy_count = _i(liveness.get("near_threshold_buy_block_count"))
        sell_count = _i(liveness.get("near_threshold_sell_block_count"))
        buy_gap = _f(liveness.get("average_buy_score_deficit_when_blocked"), 999.0)
        sell_gap = _f(liveness.get("average_sell_score_deficit_when_blocked"), 999.0)
        # Prefer the side with more near-threshold misses; tie-break toward the
        # side whose average deficit is smaller (more likely to be restored by
        # a modest threshold change).
        side = "buy"
        if sell_count > buy_count or (sell_count == buy_count and sell_gap < buy_gap):
            side = "sell"
        name = f"min_{side}_signal_score"
        current = _f(current_command.get(name), MIN_AUTONOMOUS_SIGNAL_THRESHOLD)
        step = DORMANT_THRESHOLD_RELAX_STEP if state == "DORMANT" else STARVED_THRESHOLD_RELAX_STEP
        proposed = max(MIN_AUTONOMOUS_SIGNAL_THRESHOLD, round(current - step, 2))
        if proposed < current and name not in guarded:
            guarded[name] = proposed
            injected[name] = proposed

    changed = guarded != original
    return {
        "patch": guarded,
        "changed": changed,
        "blocked_changes": blocked,
        "injected_changes": injected,
        "liveness_state": state,
        "retighten_evidence_ready": evidence_ready,
        "original_patch": original,
    }
