from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.intelligence.account_identity import current_account_outcomes_file

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"

SHADOW_FILE = DATA_DIR / "shadow_policy_history.json"
INTELLIGENCE_FILE = DATA_DIR / "intelligence_history.json"
OUTCOMES_FILE = DATA_DIR / "trade_outcomes.json"

HORIZONS_MINUTES = (1, 5, 15)

RISK_RANK = {
    "LOW": 0,
    "MODERATE": 1,
    "ELEVATED": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def _read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _dt(value: Any) -> Optional[datetime]:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _load_shadow_records() -> list[dict[str, Any]]:
    store = _read_json(
        SHADOW_FILE,
        {"records": []},
    )
    records = store.get("records") or []

    # Evaluate meaningful policy episodes; heartbeats do not create a new
    # policy episode.
    return [
        record
        for record in records
        if record.get("reason") in {"INITIAL", "STATE_CHANGE"}
    ]


def _load_intelligence_records() -> list[dict[str, Any]]:
    store = _read_json(
        INTELLIGENCE_FILE,
        {"records": []},
    )
    records = store.get("records") or []

    cleaned = []
    for record in records:
        when = _dt(record.get("recorded_at"))
        if when is None:
            continue
        cleaned.append({
            "_when": when,
            **record,
        })

    cleaned.sort(key=lambda item: item["_when"])
    return cleaned


def _load_closed_outcomes() -> list[dict[str, Any]]:
    store = _read_json(
        current_account_outcomes_file(OUTCOMES_FILE),
        {"closed": []},
    )
    closed = [t for t in (store.get("closed") or []) if t.get("strategy_learning_eligible") and str(t.get("execution_integrity") or "").upper() == "CLEAN"]

    cleaned = []
    for trade in closed:
        when = _dt(trade.get("disappeared_at"))
        if when is None:
            continue
        cleaned.append({
            "_when": when,
            **trade,
        })

    cleaned.sort(key=lambda item: item["_when"])
    return cleaned


def _risk_rank(value: Any) -> int:
    return RISK_RANK.get(str(value or "").upper(), -1)


def _policy_direction(
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Describe the intended direction of the shadow recommendation without
    pretending to know the counterfactual trade result.
    """
    changed = policy.get("changed_controls") or {}
    conceptual = policy.get("conceptual_controls") or {}

    evidence = []
    risk_reducing = False
    selectivity_increasing = False

    for name, change in changed.items():
        current = change.get("current")
        shadow = change.get("shadow")

        if name in {
            "base_lot_size",
            "max_lot_size",
            "max_open_orders",
            "max_trades_per_candle",
        }:
            if (
                isinstance(current, (int, float))
                and isinstance(shadow, (int, float))
                and shadow < current
            ):
                risk_reducing = True
                evidence.append(f"{name} reduced")

        if name in {
            "min_buy_signal_score",
            "min_sell_signal_score",
        }:
            if (
                isinstance(current, (int, float))
                and isinstance(shadow, (int, float))
                and shadow > current
            ):
                selectivity_increasing = True
                evidence.append(f"{name} increased")

        if (
            name == "enable_new_bar_entry_only"
            and current is False
            and shadow is True
        ):
            selectivity_increasing = True
            evidence.append("new-bar-only enabled")

        if (
            name == "enable_duplicate_distance_filter"
            and current is False
            and shadow is True
        ):
            selectivity_increasing = True
            evidence.append("duplicate-distance protection restored")

    if conceptual.get("new_risk_allowed") is False:
        risk_reducing = True
        evidence.append("new risk vetoed")

    return {
        "risk_reducing": risk_reducing,
        "selectivity_increasing": selectivity_increasing,
        "evidence": evidence,
    }


def _baseline_snapshot(
    records: list[dict[str, Any]],
    start: datetime,
) -> Optional[dict[str, Any]]:
    # Prefer the latest snapshot at or before the policy episode start.
    previous = None
    for record in records:
        if record["_when"] <= start:
            previous = record
        else:
            break

    if previous is not None:
        return previous

    # Fall back to the first snapshot after the episode begins.
    for record in records:
        if record["_when"] >= start:
            return record

    return None


def _window_records(
    records: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if start <= record["_when"] <= end
    ]


def _snapshot_metrics(
    baseline: dict[str, Any],
    window: list[dict[str, Any]],
) -> dict[str, Any]:
    if not window:
        return {
            "snapshot_count": 0,
            "equity_change": None,
            "balance_change": None,
            "max_drawdown_pct": None,
            "drawdown_change_from_start": None,
            "risk_state_start": baseline.get("risk", {}).get("state"),
            "risk_state_end": None,
            "risk_worsened": None,
            "regime_start": baseline.get("regime", {}).get("regime"),
            "regime_end": None,
            "regime_changes": 0,
            "hedge_seen": False,
        }

    account0 = baseline.get("account") or {}
    risk0 = baseline.get("risk") or {}
    regime0 = baseline.get("regime") or {}

    last = window[-1]
    account1 = last.get("account") or {}
    risk1 = last.get("risk") or {}
    regime1 = last.get("regime") or {}

    equity0 = _f(account0.get("equity"))
    balance0 = _f(account0.get("balance"))
    dd0 = _f(account0.get("equity_drawdown_pct"))

    equity1 = _f(account1.get("equity"))
    balance1 = _f(account1.get("balance"))

    drawdowns = [
        _f(
            (record.get("account") or {}).get(
                "equity_drawdown_pct"
            )
        )
        for record in window
    ]

    max_dd = max(drawdowns) if drawdowns else dd0

    regimes = [
        (record.get("regime") or {}).get("regime")
        for record in window
    ]
    regime_changes = 0
    prev = regime0.get("regime")

    for value in regimes:
        if value and prev and value != prev:
            regime_changes += 1
        if value:
            prev = value

    hedge_seen = any(
        int(
            (record.get("hedge") or {}).get(
                "active_hedge_chains"
            )
            or 0
        )
        > 0
        for record in window
    )

    start_risk = risk0.get("state")
    end_risk = risk1.get("state")

    return {
        "snapshot_count": len(window),
        "equity_change": round(equity1 - equity0, 2),
        "balance_change": round(balance1 - balance0, 2),
        "max_drawdown_pct": round(max_dd, 4),
        "drawdown_change_from_start": round(max_dd - dd0, 4),
        "risk_state_start": start_risk,
        "risk_state_end": end_risk,
        "risk_worsened": (
            _risk_rank(end_risk) > _risk_rank(start_risk)
            if start_risk and end_risk
            else None
        ),
        "regime_start": regime0.get("regime"),
        "regime_end": regime1.get("regime"),
        "regime_changes": regime_changes,
        "hedge_seen": hedge_seen,
    }


def _outcome_metrics(
    outcomes: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    trades = [
        trade
        for trade in outcomes
        if start < trade["_when"] <= end
    ]

    observed = [
        _f(
            trade.get(
                "final_observed_net_pl_before_disappearance"
            )
        )
        for trade in trades
    ]

    fresh = [
        trade
        for trade in trades
        if trade.get("origin_guess") == "FRESH_OR_REENTRY"
    ]

    fresh_observed = [
        _f(
            trade.get(
                "final_observed_net_pl_before_disappearance"
            )
        )
        for trade in fresh
    ]

    return {
        "disappeared_ticket_count": len(trades),
        "observed_exit_pl_sum": round(sum(observed), 2),
        "fresh_exit_count": len(fresh),
        "fresh_observed_exit_pl_sum": round(
            sum(fresh_observed),
            2,
        ),
        "worst_observed_exit_pl": (
            round(min(observed), 2)
            if observed
            else None
        ),
    }


def _support_classification(
    direction: dict[str, Any],
    snapshot: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """
    Directional evidence only. This is NOT a counterfactual P/L estimate.
    """
    if snapshot.get("snapshot_count", 0) < 2:
        return {
            "classification": "INSUFFICIENT_DATA",
            "deterioration_score": 0,
            "improvement_score": 0,
            "reasons": ["Too few future intelligence snapshots."],
        }

    deterioration = 0
    improvement = 0
    reasons = []

    eq = snapshot.get("equity_change")
    dd = snapshot.get("drawdown_change_from_start")
    risk_worsened = snapshot.get("risk_worsened")
    fresh_pl = outcome.get("fresh_observed_exit_pl_sum")

    if eq is not None:
        if eq < -5:
            deterioration += 1
            reasons.append("equity declined")
        elif eq > 5:
            improvement += 1
            reasons.append("equity improved")

    if dd is not None:
        if dd >= 0.5:
            deterioration += 1
            reasons.append("drawdown expanded")
        elif dd <= -0.5:
            improvement += 1
            reasons.append("drawdown contracted")

    if risk_worsened is True:
        deterioration += 1
        reasons.append("risk state worsened")
    elif risk_worsened is False:
        # Only count a genuine rank improvement, not unchanged.
        start_rank = _risk_rank(snapshot.get("risk_state_start"))
        end_rank = _risk_rank(snapshot.get("risk_state_end"))
        if end_rank >= 0 and start_rank >= 0 and end_rank < start_rank:
            improvement += 1
            reasons.append("risk state improved")

    if fresh_pl is not None and outcome.get("fresh_exit_count", 0) > 0:
        if fresh_pl < 0:
            deterioration += 1
            reasons.append("fresh observed exits were net negative")
        elif fresh_pl > 0:
            improvement += 1
            reasons.append("fresh observed exits were net positive")

    cautious_policy = (
        direction.get("risk_reducing")
        or direction.get("selectivity_increasing")
    )

    if not cautious_policy:
        classification = "MIXED"
        reasons.append(
            "Policy direction is not clearly risk-reducing/selectivity-increasing."
        )
    elif deterioration >= 2 and deterioration > improvement:
        classification = "SUPPORTED"
    elif improvement >= 2 and improvement > deterioration:
        classification = "NOT_SUPPORTED"
    else:
        classification = "MIXED"

    return {
        "classification": classification,
        "deterioration_score": deterioration,
        "improvement_score": improvement,
        "reasons": reasons,
    }


def _episode_key(policy: dict[str, Any]) -> str:
    changes = policy.get("changed_controls") or {}
    if not changes:
        return "NO_RUNTIME_CHANGE"

    parts = []
    for name in sorted(changes):
        change = changes[name]
        parts.append(
            f"{name}:{change.get('current')}->{change.get('shadow')}"
        )
    return " | ".join(parts)


def evaluate_shadow_policies(
    recent_limit: int = 50,
) -> dict[str, Any]:
    shadow_records = _load_shadow_records()
    intelligence = _load_intelligence_records()
    outcomes = _load_closed_outcomes()

    if not shadow_records or not intelligence:
        return {
            "ready": False,
            "message": (
                "Shadow policy history and intelligence history are required."
            ),
            "shadow_episode_count": len(shadow_records),
        }

    episodes = []

    for index, record in enumerate(shadow_records):
        start = _dt(record.get("recorded_at"))
        policy = record.get("policy") or {}

        if start is None:
            continue

        next_change = None
        if index + 1 < len(shadow_records):
            next_change = _dt(
                shadow_records[index + 1].get("recorded_at")
            )

        baseline = _baseline_snapshot(
            intelligence,
            start,
        )
        if baseline is None:
            continue

        direction = _policy_direction(policy)
        horizons = {}

        for minutes in HORIZONS_MINUTES:
            nominal_end = start.timestamp() + minutes * 60
            end = datetime.fromtimestamp(
                nominal_end,
                tz=timezone.utc,
            )

            intel_window = _window_records(
                intelligence,
                start,
                end,
            )
            snapshot = _snapshot_metrics(
                baseline,
                intel_window,
            )
            outcome = _outcome_metrics(
                outcomes,
                start,
                end,
            )
            support = _support_classification(
                direction,
                snapshot,
                outcome,
            )

            horizons[f"{minutes}m"] = {
                "window_end": end.isoformat(),
                "snapshot": snapshot,
                "outcomes": outcome,
                "directional_support": support,
            }

        # Also evaluate until the next meaningful policy change.
        if next_change and next_change > start:
            intel_window = _window_records(
                intelligence,
                start,
                next_change,
            )
            snapshot = _snapshot_metrics(
                baseline,
                intel_window,
            )
            outcome = _outcome_metrics(
                outcomes,
                start,
                next_change,
            )
            support = _support_classification(
                direction,
                snapshot,
                outcome,
            )
            until_change = {
                "window_end": next_change.isoformat(),
                "duration_seconds": round(
                    (next_change - start).total_seconds(),
                    1,
                ),
                "snapshot": snapshot,
                "outcomes": outcome,
                "directional_support": support,
            }
        else:
            until_change = None

        episodes.append({
            "started_at": start.isoformat(),
            "reason": record.get("reason"),
            "regime": policy.get("regime"),
            "risk_state": policy.get("risk_state"),
            "fit": policy.get("fit"),
            "confidence": policy.get("confidence"),
            "current_runtime_fingerprint": policy.get(
                "current_runtime_fingerprint"
            ),
            "shadow_runtime_fingerprint": policy.get(
                "shadow_runtime_fingerprint"
            ),
            "changed_controls": policy.get(
                "changed_controls"
            ) or {},
            "conceptual_controls": policy.get(
                "conceptual_controls"
            ) or {},
            "transition_plan": policy.get(
                "transition_plan"
            ),
            "policy_direction": direction,
            "policy_key": _episode_key(policy),
            "horizons": horizons,
            "until_next_policy_change": until_change,
        })

    # Aggregate the 5-minute directional classifications by recommendation.
    aggregates: dict[str, dict[str, Any]] = {}

    for episode in episodes:
        key = episode["policy_key"]
        support = (
            episode.get("horizons", {})
            .get("5m", {})
            .get("directional_support", {})
            .get("classification")
        )

        row = aggregates.setdefault(
            key,
            {
                "episode_count": 0,
                "supported": 0,
                "not_supported": 0,
                "mixed": 0,
                "insufficient_data": 0,
            },
        )
        row["episode_count"] += 1

        if support == "SUPPORTED":
            row["supported"] += 1
        elif support == "NOT_SUPPORTED":
            row["not_supported"] += 1
        elif support == "INSUFFICIENT_DATA":
            row["insufficient_data"] += 1
        else:
            row["mixed"] += 1

    return {
        "version": "0.1",
        "ready": True,
        "shadow_episode_count": len(episodes),
        "intelligence_snapshot_count": len(intelligence),
        "closed_outcome_count": len(outcomes),
        "evaluation_horizons_minutes": list(HORIZONS_MINUTES),
        "aggregate_5m_by_policy": aggregates,
        "recent_episodes": episodes[-max(1, min(recent_limit, 200)):],
        "interpretation_rules": [
            "SUPPORTED means subsequent observations were directionally consistent with Atlas's more cautious/selective recommendation.",
            "NOT_SUPPORTED means subsequent observations directionally improved despite Atlas's more cautious/selective recommendation.",
            "Neither label proves the shadow configuration would have produced the observed result.",
            "True A-versus-B performance requires a future replay/shadow execution engine using the alternate parameter configuration.",
            "Outcome monetary values remain inferred from last open-position telemetry before disappearance.",
        ],
        "files": {
            "shadow_policy_history": str(SHADOW_FILE),
            "intelligence_history": str(INTELLIGENCE_FILE),
            "trade_outcomes": str(current_account_outcomes_file(OUTCOMES_FILE)),
        },
    }
