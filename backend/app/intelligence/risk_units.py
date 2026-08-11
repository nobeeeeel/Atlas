from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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


def _effective_chain_id(trade: dict[str, Any]) -> int:
    latest = trade.get("latest_position") or {}
    initial = trade.get("initial_position") or {}
    for candidate in (latest.get("chain_id"), trade.get("chain_id"), initial.get("chain_id"), trade.get("_inferred_chain_id")):
        value = _i(candidate)
        if value > 0:
            return value
    return 0


def _hedge_level(trade: dict[str, Any]) -> int:
    latest = trade.get("latest_position") or {}
    initial = trade.get("initial_position") or {}
    return max(
        _i(trade.get("max_hedge_level_observed")),
        _i(latest.get("hedge_level")),
        _i(initial.get("hedge_level")),
    )


def _is_hedge_child(trade: dict[str, Any]) -> bool:
    return str(trade.get("origin_guess") or trade.get("order_origin") or "").upper() == "HEDGE_CHILD" or _hedge_level(trade) > 0


def _is_chain_root(trade: dict[str, Any], chain_id: int) -> bool:
    if _is_hedge_child(trade):
        return False
    ticket = _i(trade.get("ticket"))
    origin = str(trade.get("origin_guess") or trade.get("order_origin") or "").upper()
    return (
        ticket == chain_id
        or origin in {"FRESH_MARKET", "FRESH_OR_REENTRY", "HEDGE_ROOT_OR_ORIGINAL", "RECONSTRUCTED_MT5_HISTORY"}
    )


def _parse_zone_comment(comment: Any) -> tuple[str, int]:
    text = str(comment or "").strip()
    if not text.startswith("AZ|"):
        return "", 0
    parts = text.split("|")
    if len(parts) < 3:
        return "", 0
    plan_id = parts[1].strip()
    layer = 0
    layer_token = parts[2].strip().upper()
    if layer_token.startswith("L"):
        try:
            layer = int(layer_token[1:])
        except ValueError:
            layer = 0
    return plan_id, layer


def _zone_lineage(trade: dict[str, Any]) -> tuple[str, int, str]:
    origin = str(trade.get("order_origin") or trade.get("origin_guess") or "").upper()
    mode = str(trade.get("trading_mode") or "").upper()
    if origin != "ATLAS_ZONE" and mode != "ZONE":
        return "", 0, "NONE"

    latest = trade.get("latest_position") or {}
    initial = trade.get("initial_position") or {}
    for source, quality in ((trade, "EXPLICIT_OUTCOME"), (latest, "EXPLICIT_LIVE"), (initial, "EXPLICIT_ENTRY")):
        plan_id = str(source.get("zone_plan_id") or "").strip()
        if plan_id:
            return plan_id, _i(source.get("zone_layer")), quality

    for source in (trade, latest, initial):
        plan_id, layer = _parse_zone_comment(source.get("entry_comment") or source.get("comment"))
        if plan_id:
            return plan_id, layer, "IMMUTABLE_ENTRY_COMMENT"

    # Live-observed zone trades can safely use the entry-context plan snapshot.
    # Exit-only reconstruction must not borrow the *current* zone plan because it
    # may be unrelated to the historical campaign being reconstructed.
    if str(trade.get("entry_context_quality") or "").upper() != "EXIT_ONLY_RECONSTRUCTED":
        ctx = trade.get("entry_context") or {}
        zone = ctx.get("zone") or {}
        plan_id = str(zone.get("plan_id") or "").strip()
        if plan_id:
            return plan_id, 0, "ENTRY_CONTEXT"
    return "", 0, "MISSING"


def _zone_plan_id(trade: dict[str, Any]) -> str:
    return _zone_lineage(trade)[0]


def _trade_result(trade: dict[str, Any]) -> tuple[float, bool]:
    if trade.get("exact_realized_pl_available"):
        return _f(trade.get("realized_net_pl")), True
    observed = trade.get("final_observed_net_pl_before_disappearance")
    if observed is not None:
        return _f(observed), False
    cls = str(trade.get("observed_result_class") or "").upper()
    if cls.startswith("NEGATIVE"):
        return -1.0, False
    if cls.startswith("POSITIVE"):
        return 1.0, False
    return 0.0, False


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _trade_close_time(trade: dict[str, Any]) -> datetime | None:
    for key, divisor in (("close_time_msc", 1000.0), ("close_time_epoch", 1.0)):
        raw = trade.get(key)
        try:
            if raw not in (None, "", 0):
                return datetime.fromtimestamp(float(raw) / divisor, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            pass
    for key in ("disappeared_at", "last_seen_at", "first_seen_at"):
        parsed = _parse_time(trade.get(key))
        if parsed is not None:
            return parsed
    return None



def _trade_open_time(trade: dict[str, Any]) -> datetime | None:
    opened = _i(trade.get("opened_at_epoch"))
    if opened > 0:
        try:
            return datetime.fromtimestamp(opened, tz=timezone.utc)
        except (ValueError, OSError):
            pass
    initial = trade.get("initial_position") or {}
    opened = _i(initial.get("opened_at_epoch"))
    if opened > 0:
        try:
            return datetime.fromtimestamp(opened, tz=timezone.utc)
        except (ValueError, OSError):
            pass
    return _parse_time(trade.get("first_seen_at"))


def _infer_legacy_hedge_lineage(rows: list[dict[str, Any]]) -> int:
    """Repair pre-P3.30.1 hedge children whose live chain_id was erased on graduation.

    A child is paired only when its entry occurred while a same-policy non-hedge
    position was demonstrably still alive. This avoids guessing from proximity alone.
    Future Nyao 44.0 hedge comments carry immutable chain IDs, so this path is
    strictly a backward-compatibility repair for existing MT5 history.
    """
    inferred = 0
    for child in rows:
        if not _is_hedge_child(child) or _effective_chain_id(child) > 0:
            continue
        child_open = _trade_open_time(child)
        if child_open is None:
            continue
        child_epoch = _i(child.get("entry_policy_epoch"))
        candidates: list[tuple[datetime, dict[str, Any]]] = []
        for root in rows:
            if root is child or _is_hedge_child(root):
                continue
            if child_epoch > 0 and _i(root.get("entry_policy_epoch")) != child_epoch:
                continue
            root_open = _trade_open_time(root)
            if root_open is None or root_open > child_open:
                continue
            root_close = _trade_close_time(root)
            if root_close is not None and root_close < child_open:
                continue
            candidates.append((root_open, root))
        if not candidates:
            continue
        candidates.sort(key=lambda item: item[0], reverse=True)
        root = candidates[0][1]
        chain_id = _i(root.get("ticket"))
        if chain_id <= 0:
            continue
        child["_inferred_chain_id"] = chain_id
        root["_inferred_chain_id"] = chain_id
        child["_lineage_quality"] = "INFERRED_FROM_OVERLAPPING_RECOVERY_LIFECYCLE"
        root["_lineage_quality"] = "INFERRED_FROM_OVERLAPPING_RECOVERY_LIFECYCLE"
        inferred += 1
    return inferred

def _unit_result_class(value: float) -> str:
    if value > 1e-9:
        return "WIN"
    if value < -1e-9:
        return "LOSS"
    return "FLAT"


def build_risk_units(outcomes: dict[str, Any] | None) -> dict[str, Any]:
    """Build composite strategic outcome units from ticket-level outcomes.

    Standalone positions count as one unit. Recovery chains and zone campaigns
    count as one unit and are not scoreable until every member is flat. This is
    the canonical input for loss-streak/probe logic and policy performance.
    """
    payload = outcomes or {}
    closed = [{**row, "_bucket": "CLOSED"} for row in (payload.get("closed") or [])]
    active = [{**row, "_bucket": "ACTIVE"} for row in (payload.get("active") or [])]
    rows = closed + active
    legacy_lineage_inference_count = _infer_legacy_hedge_lineage(rows)

    chain_groups: dict[int, list[dict[str, Any]]] = {}
    zone_groups: dict[str, list[dict[str, Any]]] = {}
    assigned: set[int] = set()

    for row in rows:
        chain_id = _effective_chain_id(row)
        if chain_id > 0:
            chain_groups.setdefault(chain_id, []).append(row)
            assigned.add(id(row))

    # P3.41 atomic recovery lineage: hedge comments carry the immutable root
    # ticket even when the root itself has chain_id=0. Attach that root to the
    # child-defined composite before standalone scoring, otherwise a root close
    # can be scored independently while its recovery children are still live.
    for chain_id, members in list(chain_groups.items()):
        for row in rows:
            if id(row) in assigned:
                continue
            if _i(row.get("ticket")) == chain_id and not _is_hedge_child(row):
                members.append(row)
                assigned.add(id(row))
                break

    for row in rows:
        if id(row) in assigned:
            continue
        plan_id = _zone_plan_id(row)
        if plan_id:
            zone_groups.setdefault(plan_id, []).append(row)
            assigned.add(id(row))

    units: list[dict[str, Any]] = []

    def composite(unit_type: str, unit_id: str, members: list[dict[str, Any]], *, chain_id: int = 0, plan_id: str = "") -> None:
        closed_members = [m for m in members if m.get("_bucket") == "CLOSED"]
        active_members = [m for m in members if m.get("_bucket") == "ACTIVE"]
        total = 0.0
        exact = True
        close_times: list[datetime] = []
        for member in closed_members:
            result, is_exact = _trade_result(member)
            total += result
            exact = exact and is_exact
            when = _trade_close_time(member)
            if when is not None:
                close_times.append(when)
        provisional_realized = 0.0
        provisional_floating = 0.0
        initial_volume = 0.0
        remaining_volume = 0.0
        closed_volume = 0.0
        for member in members:
            provisional_realized += _f(member.get("realized_net_pl"))
            latest = member.get("latest_position") or {}
            if member.get("_bucket") == "ACTIVE":
                provisional_floating += _f(
                    latest.get("net_pl"),
                    _f(member.get("last_observed_net_pl")),
                )
            initial_volume += _f(member.get("initial_volume"))
            remaining_volume += (
                _f(latest.get("volume"))
                if member.get("_bucket") == "ACTIVE"
                else 0.0
            )
            closed_volume += _f(member.get("closed_volume"))

        roots = [m for m in members if unit_type != "RECOVERY_CHAIN" or _is_chain_root(m, chain_id)]
        root = roots[0] if roots else None
        complete = not active_members and (unit_type != "RECOVERY_CHAIN" or root is not None)
        policy_epoch = _i((root or (members[0] if members else {})).get("entry_policy_epoch"))
        zone_layers = sorted({layer for m in members for _pid, layer, _q in [_zone_lineage(m)] if layer > 0}) if unit_type == "ZONE_CAMPAIGN" else []
        lineage_qualities = sorted({q for m in members for _pid, _layer, q in [_zone_lineage(m)] if q not in {"NONE", "MISSING"}}) if unit_type == "ZONE_CAMPAIGN" else []
        member_integrities = {str(m.get("execution_integrity") or "UNKNOWN") for m in members}
        contaminated = "IMPLEMENTATION_CONTAMINATED" in member_integrities
        all_clean = bool(members) and member_integrities == {"CLEAN"}
        strategy_learning_eligible = bool(complete and all_clean and not contaminated)
        unit_integrity = "IMPLEMENTATION_CONTAMINATED" if contaminated else ("CLEAN" if all_clean else "UNKNOWN")
        units.append({
            "unit_id": unit_id,
            "unit_type": unit_type,
            "state": "COMPLETE" if complete else ("ACTIVE" if active_members else "INCOMPLETE_HISTORY"),
            "eligible_for_loss_streak": complete and strategy_learning_eligible,
            "strategy_learning_eligible": strategy_learning_eligible,
            "execution_integrity": unit_integrity,
            "member_count": len(members),
            "closed_member_count": len(closed_members),
            "active_member_count": len(active_members),
            "member_tickets": [_i(m.get("ticket")) for m in members],
            "root_ticket": _i((root or {}).get("ticket")) or None,
            "chain_id": chain_id or None,
            "zone_plan_id": plan_id or None,
            "zone_layers": zone_layers,
            "zone_lineage_quality": lineage_qualities,
            "policy_epoch": policy_epoch,
            "trading_mode": "ZONE" if unit_type == "ZONE_CAMPAIGN" else str((root or (members[0] if members else {})).get("trading_mode") or "UNKNOWN"),
            "realized_net_pl": round(total, 8) if complete else None,
            "provisional_realized_net_pl": round(provisional_realized, 8),
            "provisional_floating_net_pl": round(provisional_floating, 8),
            "provisional_lifecycle_net_pl": round(
                provisional_realized + provisional_floating,
                8,
            ),
            "initial_volume": round(initial_volume, 8),
            "remaining_volume": round(remaining_volume, 8),
            "closed_volume": round(closed_volume, 8),
            "exact_realized_pl_available": bool(complete and exact),
            "result_class": _unit_result_class(total) if complete else "UNSCORED",
            "closed_at": max(close_times).isoformat() if complete and close_times else None,
        })

    for chain_id, members in chain_groups.items():
        has_hedge = any(_is_hedge_child(m) for m in members)
        if has_hedge:
            composite("RECOVERY_CHAIN", f"recovery:{chain_id}", members, chain_id=chain_id)
        else:
            # A root can carry chain metadata before any hedge actually existed.
            for member in members:
                assigned.discard(id(member))

    for plan_id, members in zone_groups.items():
        composite("ZONE_CAMPAIGN", f"zone:{plan_id}", members, plan_id=plan_id)

    composite_member_ids = set()
    for members in chain_groups.values():
        if any(_is_hedge_child(m) for m in members):
            composite_member_ids.update(id(m) for m in members)
    for members in zone_groups.values():
        composite_member_ids.update(id(m) for m in members)

    for row in rows:
        if id(row) in composite_member_ids:
            continue
        # Active standalone positions are useful for observability but not streaks.
        if row.get("_bucket") == "ACTIVE":
            units.append({
                "unit_id": f"trade:{_i(row.get('ticket'))}", "unit_type": "STANDALONE_TRADE",
                "state": "ACTIVE", "eligible_for_loss_streak": False, "strategy_learning_eligible": False,
                "execution_integrity": str(row.get("execution_integrity") or "UNKNOWN"), "member_count": 1,
                "closed_member_count": 0, "active_member_count": 1,
                "member_tickets": [_i(row.get("ticket"))], "root_ticket": _i(row.get("ticket")) or None,
                "chain_id": None, "zone_plan_id": None, "policy_epoch": _i(row.get("entry_policy_epoch")),
                "trading_mode": str(row.get("trading_mode") or "UNKNOWN"),
                "realized_net_pl": None,
                "provisional_realized_net_pl": round(_f(row.get("realized_net_pl")), 8),
                "provisional_floating_net_pl": round(
                    _f((row.get("latest_position") or {}).get("net_pl"),
                       _f(row.get("last_observed_net_pl"))),
                    8,
                ),
                "provisional_lifecycle_net_pl": round(
                    _f(row.get("realized_net_pl")) +
                    _f((row.get("latest_position") or {}).get("net_pl"),
                       _f(row.get("last_observed_net_pl"))),
                    8,
                ),
                "initial_volume": round(_f(row.get("initial_volume")), 8),
                "remaining_volume": round(
                    _f((row.get("latest_position") or {}).get("volume")),
                    8,
                ),
                "closed_volume": round(_f(row.get("closed_volume")), 8),
                "exact_realized_pl_available": False,
                "result_class": "UNSCORED", "closed_at": None,
            })
            continue
        result, exact = _trade_result(row)
        when = _trade_close_time(row)
        units.append({
            "unit_id": f"trade:{_i(row.get('ticket'))}", "unit_type": "STANDALONE_TRADE",
            "state": "COMPLETE", "eligible_for_loss_streak": bool(row.get("strategy_learning_eligible")),
            "strategy_learning_eligible": bool(row.get("strategy_learning_eligible")),
            "execution_integrity": str(row.get("execution_integrity") or "UNKNOWN"), "member_count": 1,
            "closed_member_count": 1, "active_member_count": 0,
            "member_tickets": [_i(row.get("ticket"))], "root_ticket": _i(row.get("ticket")) or None,
            "chain_id": None, "zone_plan_id": None, "policy_epoch": _i(row.get("entry_policy_epoch")),
            "trading_mode": str(row.get("trading_mode") or "UNKNOWN"),
            "realized_net_pl": round(result, 8), "exact_realized_pl_available": exact,
            "result_class": _unit_result_class(result), "closed_at": when.isoformat() if when else None,
        })

    def sort_key(unit: dict[str, Any]) -> tuple[int, str]:
        return (1 if unit.get("state") == "COMPLETE" else 2, str(unit.get("closed_at") or "9999"))
    units.sort(key=sort_key)

    completed = [u for u in units if u.get("eligible_for_loss_streak")]
    active_units = [u for u in units if u.get("state") == "ACTIVE"]
    streak = 0
    for unit in reversed(completed):
        cls = unit.get("result_class")
        if cls == "LOSS":
            streak += 1
        elif cls == "WIN":
            break
        # FLAT intentionally preserves the existing streak.

    latest_completed_loss = next((u for u in reversed(completed) if u.get("result_class") == "LOSS"), None)
    return {
        "version": 1,
        "ready": bool(rows),
        "unit_count": len(units),
        "completed_unit_count": len(completed),
        "active_unit_count": len(active_units),
        "consecutive_completed_loss_units": streak,
        "latest_completed_loss_at": (latest_completed_loss or {}).get("closed_at"),
        "legacy_lineage_inference_count": legacy_lineage_inference_count,
        "units": units,
        "rules": [
            "Standalone trades score individually.",
            "Recovery-chain members score only once, when the entire chain is flat.",
            "Zone-campaign members score only once, when the entire campaign is flat.",
            "Active composite units never increment a completed-loss streak.",
            "Only lifecycle-contract CLEAN completed units are eligible for loss-streak and strategy learning; contaminated or legacy UNKNOWN outcomes remain in account P/L but are excluded from policy evidence.",
            "Flat completed units preserve rather than reset the previous loss streak.",
            "Pre-P3.30.1 hedge children may be conservatively re-linked only when their entry overlaps a same-policy root lifecycle; Nyao 44.2+ carries immutable lineage in the hedge entry comment.",
            "Atlas zone layers sharing the same immutable AZ plan token score once as a completed ZONE_CAMPAIGN; individual layer exits are provisional while any campaign member remains active.",
        ],
    }
