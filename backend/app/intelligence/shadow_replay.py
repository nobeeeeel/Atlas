from __future__ import annotations

import json
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from backend.app.intelligence.account_identity import current_account_outcomes_file

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"

INTELLIGENCE_FILE = DATA_DIR / "intelligence_history.json"
OUTCOMES_FILE = DATA_DIR / "trade_outcomes.json"
SHADOW_FILE = DATA_DIR / "shadow_policy_history.json"

PRE_ENTRY_MAX_AGE_SECONDS = 120.0
HIGH_CONFIDENCE_PRE_ENTRY_SECONDS = 15.0
MEDIUM_CONFIDENCE_PRE_ENTRY_SECONDS = 60.0


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


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _estimate_entry_time(trade: dict[str, Any]) -> tuple[Optional[datetime], str]:
    first_seen = _dt(trade.get("first_seen_at"))
    if first_seen is None:
        return None, "MISSING"

    initial = trade.get("initial_position") or {}
    age_seconds = initial.get("age_seconds")

    if age_seconds is None:
        return first_seen, "FIRST_SEEN_PROXY"

    try:
        age = max(0.0, float(age_seconds))
    except (TypeError, ValueError):
        return first_seen, "FIRST_SEEN_PROXY"

    return first_seen - timedelta(seconds=age), "AGE_ADJUSTED"


def _indexed_records(
    records: list[dict[str, Any]],
    time_field: str,
) -> tuple[list[datetime], list[dict[str, Any]]]:
    pairs = []

    for record in records:
        when = _dt(record.get(time_field))
        if when is not None:
            pairs.append((when, record))

    pairs.sort(key=lambda item: item[0])
    return (
        [item[0] for item in pairs],
        [item[1] for item in pairs],
    )


def _latest_at_or_before(
    times: list[datetime],
    records: list[dict[str, Any]],
    when: datetime,
) -> tuple[Optional[dict[str, Any]], Optional[float]]:
    idx = bisect_right(times, when) - 1

    if idx < 0:
        return None, None

    age = (when - times[idx]).total_seconds()
    return records[idx], age


def _shadow_policy_records() -> list[dict[str, Any]]:
    store = _read_json(SHADOW_FILE, {"records": []})
    records = store.get("records") or []

    # Heartbeats represent the same active policy. They are still useful
    # for point-in-time lookup, but keeping all records is unnecessary.
    meaningful = [
        record
        for record in records
        if record.get("reason") in {
            "INITIAL",
            "STATE_CHANGE",
            "HEARTBEAT",
        }
    ]
    return meaningful


def _pre_entry_confidence(age_seconds: Optional[float]) -> str:
    if age_seconds is None:
        return "NONE"
    if age_seconds <= HIGH_CONFIDENCE_PRE_ENTRY_SECONDS:
        return "HIGH"
    if age_seconds <= MEDIUM_CONFIDENCE_PRE_ENTRY_SECONDS:
        return "MEDIUM"
    if age_seconds <= PRE_ENTRY_MAX_AGE_SECONDS:
        return "LOW"
    return "STALE"


def _runtime_value(
    mapping: dict[str, Any],
    name: str,
    default: Any = None,
) -> Any:
    if name in mapping:
        return mapping.get(name)

    runtime_name = f"runtime_{name}"
    if runtime_name in mapping:
        return mapping.get(runtime_name)

    return default


def _direction_fields(direction: str) -> dict[str, str]:
    side = str(direction or "").upper()

    if side == "BUY":
        return {
            "base_threshold": "min_buy_signal_score",
            "effective_threshold": "buy_effective_threshold",
            "duplicate_reference_active": "buy_reference_active",
            "duplicate_distance": "buy_distance_points",
            "duplicate_multiplier": "buy_duplicate_multiplier",
        }

    return {
        "base_threshold": "min_sell_signal_score",
        "effective_threshold": "sell_effective_threshold",
        "duplicate_reference_active": "sell_reference_active",
        "duplicate_distance": "sell_distance_points",
        "duplicate_multiplier": "sell_duplicate_multiplier",
    }


def _threshold_replay(
    trade: dict[str, Any],
    current_runtime: dict[str, Any],
    shadow_runtime: dict[str, Any],
) -> dict[str, Any]:
    fields = _direction_fields(str(trade.get("type")))
    entry_context = trade.get("entry_context") or {}
    signal = entry_context.get("signal") or {}

    score = trade.get("entry_signal_score")
    actual_effective = signal.get(fields["effective_threshold"])
    actual_base = _runtime_value(
        current_runtime,
        fields["base_threshold"],
    )
    shadow_base = _runtime_value(
        shadow_runtime,
        fields["base_threshold"],
        actual_base,
    )

    if (
        score is None
        or actual_effective is None
        or actual_base is None
        or shadow_base is None
    ):
        return {
            "replayable": False,
            "reason": "Missing entry score or threshold context.",
        }

    score_f = _f(score)
    actual_effective_f = _f(actual_effective)
    actual_base_f = _f(actual_base)
    shadow_base_f = _f(shadow_base)

    # Nyao can add threshold boosts/dampening. When Atlas changes only the
    # base threshold, preserve the observed additive adjustment.
    observed_adjustment = actual_effective_f - actual_base_f
    shadow_effective = shadow_base_f + observed_adjustment

    return {
        "replayable": True,
        "confidence": "MEDIUM",
        "entry_signal_score": round(score_f, 4),
        "actual_base_threshold": round(actual_base_f, 4),
        "shadow_base_threshold": round(shadow_base_f, 4),
        "observed_threshold_adjustment": round(observed_adjustment, 4),
        "shadow_effective_threshold_proxy": round(shadow_effective, 4),
        "shadow_pass": score_f >= shadow_effective,
        "method": (
            "Observed entry score compared with a locally adjusted shadow "
            "effective threshold. Existing observed threshold boosts are "
            "held constant."
        ),
    }


def _max_orders_replay(
    pre_entry: Optional[dict[str, Any]],
    shadow_runtime: dict[str, Any],
) -> dict[str, Any]:
    if pre_entry is None:
        return {
            "replayable": False,
            "reason": "No pre-entry intelligence snapshot.",
        }

    exposure = pre_entry.get("exposure") or {}
    open_positions = exposure.get("strategy_open_positions")
    shadow_max = _runtime_value(
        shadow_runtime,
        "max_open_orders",
    )

    if open_positions is None or shadow_max is None:
        return {
            "replayable": False,
            "reason": "Open-position count or shadow max-orders missing.",
        }

    return {
        "replayable": True,
        "confidence": "HIGH",
        "pre_entry_open_positions": _i(open_positions),
        "shadow_max_open_orders": _i(shadow_max),
        "shadow_pass": _i(open_positions) < _i(shadow_max),
    }


def _duplicate_replay(
    direction: str,
    pre_entry: Optional[dict[str, Any]],
    pre_entry_age_seconds: Optional[float],
    shadow_runtime: dict[str, Any],
) -> dict[str, Any]:
    if pre_entry is None:
        return {
            "replayable": False,
            "reason": "No pre-entry intelligence snapshot.",
        }

    confidence = _pre_entry_confidence(pre_entry_age_seconds)
    if confidence == "STALE":
        return {
            "replayable": False,
            "reason": "Nearest pre-entry duplicate snapshot is too stale.",
            "snapshot_age_seconds": pre_entry_age_seconds,
        }

    duplicate = pre_entry.get("duplicate_distance") or {}
    fields = _direction_fields(direction)

    enabled = bool(
        _runtime_value(
            shadow_runtime,
            "enable_duplicate_distance_filter",
            duplicate.get("enabled", False),
        )
    )

    if not enabled:
        return {
            "replayable": True,
            "confidence": confidence,
            "shadow_filter_enabled": False,
            "shadow_pass": True,
            "reason": "Shadow duplicate-distance filter is disabled.",
        }

    reference_active = duplicate.get(
        fields["duplicate_reference_active"]
    )

    if reference_active is None:
        return {
            "replayable": False,
            "reason": "Pre-entry duplicate reference state is missing.",
        }

    if reference_active is False:
        return {
            "replayable": True,
            "confidence": confidence,
            "shadow_filter_enabled": True,
            "reference_active": False,
            "shadow_pass": True,
            "reason": "No same-direction duplicate reference was active.",
        }

    distance = duplicate.get(fields["duplicate_distance"])
    zone = _runtime_value(
        shadow_runtime,
        "zone_points",
    )
    multiplier = _runtime_value(
        shadow_runtime,
        fields["duplicate_multiplier"],
    )

    if distance is None or zone is None or multiplier is None:
        return {
            "replayable": False,
            "reason": "Duplicate distance, zone or multiplier is missing.",
        }

    required = _f(zone) * _f(multiplier)

    return {
        "replayable": True,
        "confidence": confidence,
        "shadow_filter_enabled": True,
        "reference_active": True,
        "observed_pre_entry_distance_points": round(_f(distance), 2),
        "shadow_required_distance_points": round(required, 2),
        "shadow_pass": _f(distance) >= required,
        "snapshot_age_seconds": (
            round(pre_entry_age_seconds, 2)
            if pre_entry_age_seconds is not None
            else None
        ),
        "method": (
            "Uses the nearest intelligence snapshot before estimated entry "
            "time so the newly-opened ticket cannot become its own duplicate "
            "reference."
        ),
    }


def _size_replay(
    trade: dict[str, Any],
    current_runtime: dict[str, Any],
    shadow_runtime: dict[str, Any],
) -> dict[str, Any]:
    actual_volume = trade.get("initial_volume")
    current_base = _runtime_value(
        current_runtime,
        "base_lot_size",
    )
    shadow_base = _runtime_value(
        shadow_runtime,
        "base_lot_size",
        current_base,
    )

    if (
        actual_volume is None
        or current_base is None
        or shadow_base is None
        or _f(current_base) <= 0
    ):
        return {
            "replayable": False,
            "reason": "Volume or base-lot context is missing.",
        }

    ratio = _f(shadow_base) / _f(current_base)
    shadow_volume_proxy = max(
        0.0,
        _f(actual_volume) * ratio,
    )

    final_observed = trade.get(
        "final_observed_net_pl_before_disappearance"
    )

    scaled_pl = None
    if final_observed is not None:
        scaled_pl = _f(final_observed) * ratio

    return {
        "replayable": True,
        "confidence": "MEDIUM",
        "actual_initial_volume": round(_f(actual_volume), 4),
        "actual_base_lot_size": round(_f(current_base), 4),
        "shadow_base_lot_size": round(_f(shadow_base), 4),
        "size_ratio": round(ratio, 4),
        "shadow_volume_proxy": round(shadow_volume_proxy, 4),
        "observed_final_pl": (
            round(_f(final_observed), 2)
            if final_observed is not None
            else None
        ),
        "shadow_size_scaled_pl_proxy": (
            round(scaled_pl, 2)
            if scaled_pl is not None
            else None
        ),
        "method": (
            "Mechanical proportional sizing proxy only. It does not model "
            "subsequent path changes, dynamic-lot nonlinearities, margin, "
            "hedges, partial closes or later trade interactions."
        ),
    }


def _new_bar_replay(
    trade: dict[str, Any],
    current_runtime: dict[str, Any],
    shadow_runtime: dict[str, Any],
) -> dict[str, Any]:
    current = bool(
        _runtime_value(
            current_runtime,
            "enable_new_bar_entry_only",
            False,
        )
    )
    shadow = bool(
        _runtime_value(
            shadow_runtime,
            "enable_new_bar_entry_only",
            current,
        )
    )

    if current == shadow:
        return {
            "replayable": True,
            "confidence": "HIGH",
            "changed": False,
            "shadow_pass": True,
            "reason": "New-bar mode is unchanged.",
        }

    # If Shadow loosens NEW_BAR_ONLY -> intrabar allowed, any historical
    # entry that passed the stricter gate remains permitted.
    if current and not shadow:
        return {
            "replayable": True,
            "confidence": "HIGH",
            "changed": True,
            "shadow_pass": True,
            "reason": (
                "Shadow loosens the gate from NEW_BAR_ONLY to "
                "INTRABAR_ALLOWED."
            ),
        }

    event = (
        trade.get("entry_evaluation_event")
        or (trade.get("initial_position") or {}).get(
            "entry_evaluation_event"
        )
    )

    if event == "NEW_BAR":
        return {
            "replayable": True,
            "confidence": "HIGH",
            "changed": True,
            "entry_evaluation_event": event,
            "shadow_pass": True,
            "reason": (
                "Historical entry was evaluated on the first observed "
                "tick of a new bar."
            ),
        }

    if event == "INTRABAR":
        return {
            "replayable": True,
            "confidence": "HIGH",
            "changed": True,
            "entry_evaluation_event": event,
            "shadow_pass": False,
            "reason": (
                "Historical entry was evaluated intrabar, so NEW_BAR_ONLY "
                "would reject it."
            ),
        }

    return {
        "replayable": False,
        "changed": True,
        "reason": (
            "Authoritative entry_evaluation_event is missing for this "
            "historical trade."
        ),
    }


def _max_trades_per_candle_replay(
    trade: dict[str, Any],
    current_runtime: dict[str, Any],
    shadow_runtime: dict[str, Any],
) -> dict[str, Any]:
    current = _runtime_value(
        current_runtime,
        "max_trades_per_candle",
    )
    shadow = _runtime_value(
        shadow_runtime,
        "max_trades_per_candle",
        current,
    )

    if current is None or shadow is None:
        return {
            "replayable": False,
            "reason": "Max-trades-per-candle runtime context is missing.",
        }

    if _i(current) == _i(shadow):
        return {
            "replayable": True,
            "confidence": "HIGH",
            "changed": False,
            "shadow_pass": True,
            "reason": "Max-trades-per-candle is unchanged.",
        }

    before = trade.get(
        "trades_on_entry_candle_before_this_entry"
    )
    if before is None:
        before = (trade.get("initial_position") or {}).get(
            "trades_on_entry_candle_before_this_entry"
        )

    if before is None or _i(before, -1) < 0:
        return {
            "replayable": False,
            "changed": True,
            "reason": (
                "Authoritative same-direction entry count before this "
                "entry is missing."
            ),
        }

    shadow_limit = _i(shadow)

    # Nyao treats zero as unlimited.
    shadow_pass = (
        True
        if shadow_limit <= 0
        else _i(before) < shadow_limit
    )

    return {
        "replayable": True,
        "confidence": "HIGH",
        "changed": True,
        "same_direction_trades_before_entry": _i(before),
        "actual_max_trades_per_candle": _i(current),
        "shadow_max_trades_per_candle": shadow_limit,
        "shadow_pass": shadow_pass,
        "method": (
            "Uses Nyao's authoritative same-direction trade count captured "
            "before the historical entry decision."
        ),
    }

def _changed(
    current_runtime: dict[str, Any],
    shadow_runtime: dict[str, Any],
    name: str,
) -> bool:
    return _runtime_value(
        current_runtime,
        name,
    ) != _runtime_value(
        shadow_runtime,
        name,
    )


def _trade_replay(
    trade: dict[str, Any],
    policy_record: dict[str, Any],
    pre_entry: Optional[dict[str, Any]],
    pre_entry_age_seconds: Optional[float],
    entry_time: datetime,
    entry_time_method: str,
) -> dict[str, Any]:
    policy = policy_record.get("policy") or {}
    current_runtime = policy.get("current_runtime") or {}
    shadow_runtime = policy.get("shadow_runtime") or {}
    conceptual = policy.get("conceptual_controls") or {}

    direction = str(trade.get("type") or "").upper()
    fields = _direction_fields(direction)

    threshold = _threshold_replay(
        trade,
        current_runtime,
        shadow_runtime,
    )
    max_orders = _max_orders_replay(
        pre_entry,
        shadow_runtime,
    )
    duplicate = _duplicate_replay(
        direction,
        pre_entry,
        pre_entry_age_seconds,
        shadow_runtime,
    )
    new_bar = _new_bar_replay(
        trade,
        current_runtime,
        shadow_runtime,
    )
    max_trades_per_candle = _max_trades_per_candle_replay(
        trade,
        current_runtime,
        shadow_runtime,
    )
    sizing = _size_replay(
        trade,
        current_runtime,
        shadow_runtime,
    )

    # v0.2 critical rule:
    # An unchanged runtime gate cannot be allowed to create a shadow
    # divergence from a trade that actually occurred. If telemetry for an
    # unchanged gate disagrees with reality, that is evidence that the
    # snapshot/proxy is imperfect, not evidence that Shadow would skip.
    threshold_changed = _changed(
        current_runtime,
        shadow_runtime,
        fields["base_threshold"],
    )
    max_orders_changed = _changed(
        current_runtime,
        shadow_runtime,
        "max_open_orders",
    )
    duplicate_changed = any(
        _changed(
            current_runtime,
            shadow_runtime,
            name,
        )
        for name in (
            "enable_duplicate_distance_filter",
            "zone_points",
            fields["duplicate_multiplier"],
        )
    )
    new_bar_changed = _changed(
        current_runtime,
        shadow_runtime,
        "enable_new_bar_entry_only",
    )
    max_trades_per_candle_changed = _changed(
        current_runtime,
        shadow_runtime,
        "max_trades_per_candle",
    )
    sizing_changed = _changed(
        current_runtime,
        shadow_runtime,
        "base_lot_size",
    )

    threshold["decision_relevant"] = threshold_changed
    max_orders["decision_relevant"] = max_orders_changed
    duplicate["decision_relevant"] = duplicate_changed
    new_bar["decision_relevant"] = new_bar_changed
    sizing["decision_relevant"] = sizing_changed

    blockers = []
    passed_changed_checks = []
    unchanged_diagnostics = []
    unresolved = []

    for name, result in (
        ("threshold", threshold),
        ("max_open_orders", max_orders),
        ("duplicate_distance", duplicate),
        (
            "max_trades_per_candle",
            max_trades_per_candle,
        ),
    ):
        if not result.get("decision_relevant"):
            unchanged_diagnostics.append(name)
            continue

        if result.get("replayable") is not True:
            unresolved.append({
                "control": name,
                "reason": result.get(
                    "reason",
                    "Changed control is not replayable.",
                ),
            })
            continue

        if result.get("shadow_pass") is False:
            blockers.append({
                "control": name,
                "reason": "Changed shadow control would reject this entry.",
                "confidence": result.get("confidence", "MEDIUM"),
            })
        else:
            passed_changed_checks.append(name)

    if new_bar_changed:
        if new_bar.get("replayable") is not True:
            unresolved.append({
                "control": "enable_new_bar_entry_only",
                "reason": new_bar.get(
                    "reason",
                    "Changed new-bar gate is not replayable.",
                ),
            })
        elif new_bar.get("shadow_pass") is False:
            blockers.append({
                "control": "enable_new_bar_entry_only",
                "reason": (
                    "Changed shadow NEW_BAR_ONLY gate would reject "
                    "this intrabar entry."
                ),
                "confidence": new_bar.get(
                    "confidence",
                    "HIGH",
                ),
            })
        else:
            passed_changed_checks.append(
                "enable_new_bar_entry_only"
            )

    authoritative_origin = str(
        trade.get("order_origin")
        or (trade.get("initial_position") or {}).get(
            "order_origin"
        )
        or trade.get("origin_guess")
        or ""
    ).upper()

    fresh_origins = {
        "FRESH_MARKET",
        "FRESH_LIMIT",
    }
    recovery_origins = {
        "VIRTUAL_SL_REENTRY",
        "HEDGE_CHILD",
    }

    conceptual_veto_active = (
        conceptual.get("new_risk_allowed") is False
    )

    if conceptual_veto_active:
        if authoritative_origin in fresh_origins:
            blockers.append({
                "control": "conceptual_new_risk_allowed",
                "reason": (
                    "Atlas Risk Governor vetoed genuinely fresh risk."
                ),
                "confidence": "HIGH",
            })
        elif authoritative_origin in recovery_origins:
            passed_changed_checks.append(
                "conceptual_new_risk_allowed_recovery_exempt"
            )
        else:
            unresolved.append({
                "control": "conceptual_new_risk_allowed",
                "reason": (
                    "Risk Governor vetoes genuinely fresh risk, but this "
                    "historical trade lacks authoritative FRESH vs REENTRY "
                    "origin telemetry."
                ),
            })

    fresh_vs_reentry_ambiguous = (
        authoritative_origin in {
            "",
            "FRESH_OR_REENTRY",
            "UNKNOWN_RESTARTED",
        }
    )

    if blockers:
        shadow_decision = "SKIP"
        decision_confidence = (
            "HIGH"
            if any(
                blocker.get("confidence") == "HIGH"
                for blocker in blockers
            )
            else "MEDIUM"
        )
    elif unresolved:
        shadow_decision = "UNRESOLVED"
        decision_confidence = "LOW"
    else:
        shadow_decision = "TAKE"
        decision_confidence = "MEDIUM"

    return {
        "ticket": trade.get("ticket"),
        "symbol": trade.get("symbol"),
        "direction": direction,
        "origin_guess": trade.get("origin_guess"),
        "order_origin": trade.get("order_origin"),
        "origin_quality": trade.get("origin_quality"),
        "estimated_entry_time": entry_time.isoformat(),
        "entry_time_method": entry_time_method,
        "entry_context_quality": trade.get("entry_context_quality"),
        "shadow_policy_recorded_at": policy_record.get("recorded_at"),
        "regime": policy.get("regime"),
        "risk_state": policy.get("risk_state"),
        "fit": policy.get("fit"),
        "current_runtime_fingerprint": policy.get(
            "current_runtime_fingerprint"
        ),
        "shadow_runtime_fingerprint": policy.get(
            "shadow_runtime_fingerprint"
        ),
        "changed_controls": policy.get("changed_controls") or {},
        "pre_entry_snapshot_age_seconds": (
            round(pre_entry_age_seconds, 2)
            if pre_entry_age_seconds is not None
            else None
        ),
        "pre_entry_snapshot_confidence": _pre_entry_confidence(
            pre_entry_age_seconds
        ),
        "actual_decision": "TAKE",
        "shadow_decision": shadow_decision,
        "decision_confidence": decision_confidence,
        "blockers": blockers,
        "unresolved_constraints": unresolved,
        "passed_changed_replay_checks": passed_changed_checks,
        "unchanged_gate_diagnostics": unchanged_diagnostics,
        "fresh_vs_reentry_ambiguous": fresh_vs_reentry_ambiguous,
        "conceptual_fresh_risk_veto_active": conceptual_veto_active,
        "controls": {
            "threshold": threshold,
            "max_open_orders": max_orders,
            "duplicate_distance": duplicate,
            "new_bar_only": new_bar,
            "max_trades_per_candle": max_trades_per_candle,
            "sizing": sizing,
        },
        "observed_outcome": {
            "final_open_position_pl_before_disappearance": trade.get(
                "final_observed_net_pl_before_disappearance"
            ),
            "max_favorable_net_pl_observed": trade.get(
                "max_favorable_net_pl_observed"
            ),
            "max_adverse_net_pl_observed": trade.get(
                "max_adverse_net_pl_observed"
            ),
            "exact_realized_pl_available": bool(
                trade.get("exact_realized_pl_available", False)
            ),
        },
    }

def run_shadow_replay(
    recent_limit: int = 100,
) -> dict[str, Any]:
    intelligence_store = _read_json(
        INTELLIGENCE_FILE,
        {"records": []},
    )
    outcomes_store = _read_json(
        current_account_outcomes_file(OUTCOMES_FILE),
        {"closed": []},
    )

    intelligence_records = intelligence_store.get("records") or []
    shadow_records = _shadow_policy_records()
    closed = outcomes_store.get("closed") or []

    replay_candidates = {
        "FRESH_MARKET",
        "FRESH_LIMIT",
        "VIRTUAL_SL_REENTRY",
        "FRESH_OR_REENTRY",
    }

    fresh = [
        trade
        for trade in closed
        if str(
            trade.get("order_origin")
            or trade.get("origin_guess")
            or ""
        ).upper()
        in replay_candidates
    ]

    intel_times, intel_index = _indexed_records(
        intelligence_records,
        "recorded_at",
    )
    policy_times, policy_index = _indexed_records(
        shadow_records,
        "recorded_at",
    )

    replayed = []
    no_policy = 0
    no_entry_time = 0

    for trade in fresh:
        entry_time, entry_method = _estimate_entry_time(trade)

        if entry_time is None:
            no_entry_time += 1
            continue

        policy_record, _ = _latest_at_or_before(
            policy_times,
            policy_index,
            entry_time,
        )

        if policy_record is None:
            no_policy += 1
            continue

        pre_entry, pre_age = _latest_at_or_before(
            intel_times,
            intel_index,
            entry_time,
        )

        if (
            pre_age is not None
            and pre_age > PRE_ENTRY_MAX_AGE_SECONDS
        ):
            pre_entry_for_checks = None
        else:
            pre_entry_for_checks = pre_entry

        replayed.append(
            _trade_replay(
                trade,
                policy_record,
                pre_entry_for_checks,
                pre_age,
                entry_time,
                entry_method,
            )
        )

    takes = [
        row
        for row in replayed
        if row["shadow_decision"] == "TAKE"
    ]
    skips = [
        row
        for row in replayed
        if row["shadow_decision"] == "SKIP"
    ]
    unresolved_rows = [
        row
        for row in replayed
        if row["shadow_decision"] == "UNRESOLVED"
    ]

    high = sum(
        1
        for row in replayed
        if row["decision_confidence"] == "HIGH"
    )
    medium = sum(
        1
        for row in replayed
        if row["decision_confidence"] == "MEDIUM"
    )
    low = sum(
        1
        for row in replayed
        if row["decision_confidence"] == "LOW"
    )

    skip_observed_pl = sum(
        _f(
            row["observed_outcome"].get(
                "final_open_position_pl_before_disappearance"
            )
        )
        for row in skips
        if row["observed_outcome"].get(
            "final_open_position_pl_before_disappearance"
        )
        is not None
    )

    resized = [
        row
        for row in replayed
        if (
            row["shadow_decision"] != "SKIP"
            and row["controls"]["sizing"].get("replayable")
            and row["controls"]["sizing"].get("decision_relevant")
            and row["controls"]["sizing"].get("size_ratio") != 1.0
        )
    ]

    return {
        "version": "0.3",
        "ready": bool(replayed),
        "mode": "RESTRICTED_COUNTERFACTUAL_ENTRY_REPLAY_V03",
        "source_counts": {
            "intelligence_snapshots": len(intelligence_records),
            "shadow_policy_records": len(shadow_records),
            "closed_outcomes": len(closed),
            "fresh_or_reentry_closed": len(fresh),
        },
        "coverage": {
            "replayed_fresh_trades": len(replayed),
            "missing_policy_at_entry": no_policy,
            "missing_entry_time": no_entry_time,
            "shadow_take_count": len(takes),
            "shadow_skip_count": len(skips),
            "shadow_unresolved_count": len(unresolved_rows),
            "decision_confidence": {
                "high": high,
                "medium": medium,
                "low": low,
            },
        },
        "observational_diagnostics": {
            "observed_pl_of_trades_shadow_would_skip": round(
                skip_observed_pl,
                2,
            ),
            "shadow_take_with_size_change_count": len(resized),
            "warning": (
                "The skipped-trade P/L sum is descriptive only. It is NOT "
                "a profit estimate because skipping a trade changes later "
                "position capacity, duplicate references, hedges and account "
                "state."
            ),
        },
        "replayability_matrix": {
            "conceptual_new_risk_veto": "HIGH_WITH_AUTHORITATIVE_ORDER_ORIGIN",
            "min_buy_signal_score": "MEDIUM",
            "min_sell_signal_score": "MEDIUM",
            "base_lot_size": "MEDIUM_SIZE_PROXY",
            "max_open_orders": "HIGH_IF_PRE_ENTRY_SNAPSHOT",
            "enable_duplicate_distance_filter": (
                "MEDIUM_IF_FRESH_PRE_ENTRY_SNAPSHOT"
            ),
            "zone_points": "MEDIUM_IF_FRESH_PRE_ENTRY_SNAPSHOT",
            "buy_duplicate_multiplier": (
                "MEDIUM_IF_FRESH_PRE_ENTRY_SNAPSHOT"
            ),
            "sell_duplicate_multiplier": (
                "MEDIUM_IF_FRESH_PRE_ENTRY_SNAPSHOT"
            ),
            "enable_new_bar_entry_only": "HIGH_WITH_ENTRY_EVENT_TELEMETRY",
            "max_trades_per_candle": "HIGH_WITH_ENTRY_CANDLE_COUNT_TELEMETRY",
            "hedge_and_position_management_controls": (
                "NOT_REPLAYABLE_YET"
            ),
        },
        "recent_replays": replayed[
            -max(1, min(int(recent_limit), 500)):
        ],
        "interpretation_rules": [
            "Only controls that actually differ between current_runtime and shadow_runtime may create a replay decision divergence.",
            "If an unchanged historical gate appears to fail in telemetry even though the trade actually opened, that mismatch is treated as a telemetry/proxy limitation, not a Shadow SKIP.",
            "Shadow SKIP means at least one CHANGED and replayable Atlas runtime gate would reject the historical entry.",
            "UNRESOLVED means the available telemetry cannot determine the alternate decision safely.",
            "New records with authoritative Nyao order_origin allow deterministic fresh-risk veto replay; legacy FRESH_OR_REENTRY records remain unresolved.",
            "Threshold replay holds the observed Nyao threshold adjustment constant and changes only the Atlas-proposed base threshold.",
            "Duplicate-distance replay uses the nearest snapshot before estimated entry and only becomes decision-relevant when Atlas changed a duplicate-distance control.",
            "Sizing replay is a proportional exposure proxy, not a simulated portfolio outcome.",
            "Observed P/L values remain final open-position telemetry before disappearance and are not exact MT5 realised deal P/L.",
            "Replay v0.3 can replay authoritative fresh-risk origin, new-bar gates and max-trades-per-candle for newly collected records, but does not simulate alternate hedges, partial closes, trailing, TP/SL, recovery chains or downstream state divergence.",
            "This engine is for engineering evidence and decision-divergence analysis, not automatic optimization.",
        ],
        "files": {
            "intelligence_history": str(INTELLIGENCE_FILE),
            "trade_outcomes": str(current_account_outcomes_file(OUTCOMES_FILE)),
            "shadow_policy_history": str(SHADOW_FILE),
        },
    }
