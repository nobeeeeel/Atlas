from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.account_identity import (
    account_identity,
    current_account_fingerprint,
    current_account_outcomes_file,
)

_OUTCOME_LOCK = threading.Lock()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
OUTCOMES_FILE = DATA_DIR / "trade_outcomes.json"

OUTCOME_VERSION = 7
MAX_CLOSED_TRADES = 5_000
MAX_PROCESSED_EXIT_DEALS = 10_000
DISAPPEARANCE_GRACE_SECONDS = 30.0
IDENTITY_ENTRY_PRICE_TOLERANCE = 1e-6


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


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


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _earliest_iso(*values: Any) -> str | None:
    parsed = [(dt, raw) for raw in values if (dt := _parse_iso(raw)) is not None]
    if not parsed:
        return None
    return min(parsed, key=lambda item: item[0])[1]


def _latest_iso(*values: Any) -> str | None:
    parsed = [(dt, raw) for raw in values if (dt := _parse_iso(raw)) is not None]
    if not parsed:
        return None
    return max(parsed, key=lambda item: item[0])[1]


def _position_identity(position: dict[str, Any], symbol: Any = None) -> tuple[Any, ...]:
    return (
        _i(position.get("ticket")),
        str(symbol or position.get("symbol") or "").upper(),
        str(position.get("type") or "").upper(),
        _i(position.get("opened_at_epoch")),
        round(_f(position.get("entry_price")), 6),
    )


def _trade_identity(trade: dict[str, Any]) -> tuple[Any, ...]:
    initial = trade.get("initial_position") or {}
    return (
        _i(trade.get("ticket") or initial.get("ticket")),
        str(trade.get("symbol") or initial.get("symbol") or "").upper(),
        str(trade.get("type") or initial.get("type") or "").upper(),
        _i(trade.get("opened_at_epoch") or initial.get("opened_at_epoch")),
        round(_f(trade.get("entry_price") or initial.get("entry_price")), 6),
    )


def _same_trade_identity(
    trade: dict[str, Any],
    position: dict[str, Any],
    symbol: Any = None,
) -> bool:
    """Conservative identity match for lifecycle resurrection/de-duplication."""
    t_ticket, t_symbol, t_type, t_opened, t_price = _trade_identity(trade)
    p_ticket, p_symbol, p_type, p_opened, p_price = _position_identity(position, symbol)

    if not t_ticket or t_ticket != p_ticket:
        return False
    if t_symbol and p_symbol and t_symbol != p_symbol:
        return False
    if t_type and p_type and t_type != p_type:
        return False
    if t_opened and p_opened and t_opened != p_opened:
        return False
    if t_price and p_price and abs(t_price - p_price) > IDENTITY_ENTRY_PRICE_TOLERANCE:
        return False
    return True


def _merge_transition_lists(first: Any, second: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in (first, second):
        if not isinstance(source, list):
            continue
        for row in source:
            if isinstance(row, dict):
                rows.append(dict(row))

    def sort_key(row: dict[str, Any]) -> datetime:
        return _parse_iso(row.get("at")) or datetime.min.replace(tzinfo=timezone.utc)

    rows.sort(key=sort_key)
    merged: list[dict[str, Any]] = []
    for row in rows:
        if not merged or merged[-1].get("value") != row.get("value"):
            merged.append(row)
    return merged


def _merge_trade_segments(
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    reopen: bool = False,
) -> dict[str, Any]:
    """Merge two observations of the same MT5 position into one lifecycle."""
    first_dt = _parse_iso(first.get("first_seen_at"))
    second_dt = _parse_iso(second.get("first_seen_at"))
    if first_dt is None:
        earlier, later = second, first
    elif second_dt is None:
        earlier, later = first, second
    elif first_dt <= second_dt:
        earlier, later = first, second
    else:
        earlier, later = second, first

    merged = dict(earlier)

    # Prefer authoritative/filled identity and entry metadata from either segment.
    for key in (
        "ticket", "symbol", "type", "order_origin", "origin_guess", "origin_quality",
        "entry_gate_mode", "entry_evaluation_event", "entry_was_new_bar", "entry_policy_epoch",
        "trades_on_entry_candle_before_this_entry",
        "total_trades_on_entry_candle_before_this_entry", "opened_at_epoch",
        "entry_price", "entry_signal_score", "chain_id", "initial_hedge_level",
        "scalp_context_class", "scalp_context_zone_side", "scalp_context_pressure",
        "recovery_probe_entry", "recovery_probe_target_risk_pct",
        "recovery_probe_max_risk_pct", "recovery_probe_admission_risk_pct",
        "recovery_probe_admission_risk_amount", "recovery_probe_frozen_risk_amount",
    ):
        if merged.get(key) in (None, "", 0, "UNKNOWN") and later.get(key) not in (None, ""):
            merged[key] = later.get(key)

    merged["first_seen_at"] = _earliest_iso(
        earlier.get("first_seen_at"), later.get("first_seen_at")
    ) or earlier.get("first_seen_at") or later.get("first_seen_at")
    merged["last_seen_at"] = _latest_iso(
        earlier.get("last_seen_at"), later.get("last_seen_at")
    ) or later.get("last_seen_at") or earlier.get("last_seen_at")

    merged["initial_position"] = dict(
        earlier.get("initial_position") or later.get("initial_position") or {}
    )
    merged["latest_position"] = dict(
        later.get("latest_position") or earlier.get("latest_position") or {}
    )
    merged["entry_context"] = dict(
        earlier.get("entry_context") or later.get("entry_context") or {}
    )
    merged["entry_context_quality"] = (
        earlier.get("entry_context_quality") or later.get("entry_context_quality")
    )

    merged["observation_count"] = _i(earlier.get("observation_count")) + _i(later.get("observation_count"))
    merged["maximum_volume_observed"] = max(
        _f(earlier.get("maximum_volume_observed")), _f(later.get("maximum_volume_observed"))
    )
    positive_min_candidates = [
        _f(v) for v in (earlier.get("minimum_volume_observed"), later.get("minimum_volume_observed"))
        if _f(v) > 0
    ]
    merged["minimum_volume_observed"] = min(positive_min_candidates) if positive_min_candidates else 0.0
    merged["max_favorable_net_pl_observed"] = max(
        _f(earlier.get("max_favorable_net_pl_observed")),
        _f(later.get("max_favorable_net_pl_observed")),
    )
    merged["max_adverse_net_pl_observed"] = min(
        _f(earlier.get("max_adverse_net_pl_observed")),
        _f(later.get("max_adverse_net_pl_observed")),
    )
    merged["max_positive_distance_points_observed"] = max(
        _f(earlier.get("max_positive_distance_points_observed")),
        _f(later.get("max_positive_distance_points_observed")),
    )
    merged["max_negative_distance_points_observed"] = min(
        _f(earlier.get("max_negative_distance_points_observed")),
        _f(later.get("max_negative_distance_points_observed")),
    )
    merged["max_hedge_level_observed"] = max(
        _i(earlier.get("max_hedge_level_observed")), _i(later.get("max_hedge_level_observed"))
    )
    merged["max_cycle_observed"] = max(
        _i(earlier.get("max_cycle_observed")), _i(later.get("max_cycle_observed"))
    )
    merged["max_age_seconds_observed"] = max(
        _i(earlier.get("max_age_seconds_observed")), _i(later.get("max_age_seconds_observed"))
    )
    merged["break_even_ever_locked"] = bool(
        earlier.get("break_even_ever_locked") or later.get("break_even_ever_locked")
    )
    merged["partial_close_level_max_observed"] = max(
        _i(earlier.get("partial_close_level_max_observed")),
        _i(later.get("partial_close_level_max_observed")),
    )

    for field in ("regime", "risk_state", "fit"):
        merged[f"{field}_transitions"] = _merge_transition_lists(
            earlier.get(f"{field}_transitions"), later.get(f"{field}_transitions")
        )

    # Latest segment wins for terminal/last-observation fields.
    for key in (
        "last_observed_net_pl", "last_observed_distance_points", "disappeared_at",
        "observed_lifetime_seconds", "observed_lifetime_minutes", "outcome_quality",
        "exact_realized_pl_available", "final_observed_net_pl_before_disappearance",
        "balance_delta_near_disappearance", "balance_at_disappearance",
        "equity_at_disappearance", "observed_result_class",
        "exit_deals", "realized_profit", "realized_swap", "realized_commission",
        "realized_fee", "realized_net_pl", "final_exit_deal_ticket",
        "close_time_epoch", "close_time_msc", "close_price", "close_reason",
        "close_deal_type", "close_deal_entry",
    ):
        if later.get(key) is not None:
            merged[key] = later.get(key)

    merged["lifecycle_segments_merged"] = (
        _i(earlier.get("lifecycle_segments_merged"), 1)
        + _i(later.get("lifecycle_segments_merged"), 1)
    )
    merged["duplicate_repair_applied"] = True

    if reopen:
        merged["lifecycle_state"] = "ACTIVE"
        for key in (
            "disappeared_at", "observed_lifetime_seconds", "observed_lifetime_minutes",
            "outcome_quality", "final_observed_net_pl_before_disappearance",
            "balance_delta_near_disappearance", "balance_at_disappearance",
            "equity_at_disappearance", "observed_result_class",
            "missing_since", "missing_observation_count",
        ):
            merged.pop(key, None)
    return merged


def _repair_duplicate_closed_records(closed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Idempotently merge historical duplicate lifecycle records by MT5 position identity."""
    repaired: list[dict[str, Any]] = []
    identity_to_index: dict[tuple[Any, ...], int] = {}
    merged_count = 0

    for raw in closed:
        if not isinstance(raw, dict):
            continue
        trade = dict(raw)
        identity = _trade_identity(trade)
        # Require a real ticket and enough identity to avoid merging malformed records.
        if not identity[0]:
            repaired.append(trade)
            continue
        if identity in identity_to_index:
            idx = identity_to_index[identity]
            repaired[idx] = _merge_trade_segments(repaired[idx], trade)
            merged_count += 1
        else:
            identity_to_index[identity] = len(repaired)
            repaired.append(trade)

    return repaired, merged_count


def _find_matching_closed_index(
    closed: list[dict[str, Any]],
    position: dict[str, Any],
    symbol: Any,
) -> int | None:
    # Search newest first; a resurrected lifecycle should be recent.
    for idx in range(len(closed) - 1, -1, -1):
        trade = closed[idx]
        if isinstance(trade, dict) and _same_trade_identity(trade, position, symbol):
            return idx
    return None


def _empty_store() -> dict[str, Any]:
    now = _iso_now()
    return {
        "version": OUTCOME_VERSION,
        "created_at": now,
        "updated_at": now,
        "active_count": 0,
        "closed_count": 0,
        "active": {},
        "closed": [],
        "last_account": {},
        "processed_exit_deal_tickets": [],
        "processed_lifecycle_event_keys": [],
    }


def _normalize_closed_lifecycle_accounting(
    rows: list[dict[str, Any]],
) -> int:
    """Repair historical exact closes that still carry pre-close floating P/L."""
    repaired = 0
    for trade in rows:
        if not isinstance(trade, dict):
            continue
        if not trade.get("exact_realized_pl_available"):
            continue
        if not trade.get("final_exit_deal_ticket") and not trade.get("close_time_epoch"):
            continue
        realized = round(_f(trade.get("realized_net_pl")), 8)
        if (
            abs(_f(trade.get("floating_net_pl"))) > 1e-12
            or abs(_f(trade.get("lifecycle_net_pl")) - realized) > 1e-12
            or _f(trade.get("remaining_volume")) > 1e-12
        ):
            trade["remaining_volume"] = 0.0
            trade["floating_net_pl"] = 0.0
            trade["lifecycle_net_pl"] = realized
            repaired += 1
    return repaired


def _read_store_unlocked() -> dict[str, Any]:
    outcomes_file = current_account_outcomes_file(OUTCOMES_FILE)
    if not outcomes_file.exists():
        return _empty_store()

    try:
        with outcomes_file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    active = data.get("active")
    closed = data.get("closed")

    if not isinstance(active, dict):
        active = {}
    if not isinstance(closed, list):
        closed = []

    repaired_closed, repaired_count = _repair_duplicate_closed_records(closed)
    lifecycle_repaired_count = _normalize_closed_lifecycle_accounting(repaired_closed)
    data["version"] = OUTCOME_VERSION
    data["active"] = active
    data["closed"] = repaired_closed
    data["active_count"] = len(active)
    data["closed_count"] = len(repaired_closed)
    if repaired_count:
        data["historical_duplicate_segments_merged"] = (
            _i(data.get("historical_duplicate_segments_merged")) + repaired_count
        )
    if lifecycle_repaired_count:
        data["historical_closed_lifecycle_rows_repaired"] = (
            _i(data.get("historical_closed_lifecycle_rows_repaired"))
            + lifecycle_repaired_count
        )
    data.setdefault("last_account", {})
    if not isinstance(data.get("processed_exit_deal_tickets"), list):
        data["processed_exit_deal_tickets"] = []
    if not isinstance(data.get("processed_lifecycle_event_keys"), list):
        data["processed_lifecycle_event_keys"] = []
    data.setdefault("created_at", _iso_now())
    data.setdefault("updated_at", _iso_now())
    return data


def _atomic_write_unlocked(data: dict[str, Any]) -> None:
    outcomes_file = current_account_outcomes_file(OUTCOMES_FILE)
    outcomes_dir = outcomes_file.parent
    outcomes_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="atlas-outcomes-",
        suffix=".json",
        dir=str(outcomes_dir),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_name, outcomes_file)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _current_positions(status: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_positions = status.get("positions")
    if not isinstance(raw_positions, list):
        return {}

    positions: dict[str, dict[str, Any]] = {}

    for raw in raw_positions:
        if not isinstance(raw, dict):
            continue

        ticket = raw.get("ticket")
        if ticket in (None, "", 0):
            continue

        positions[str(ticket)] = raw

    return positions


def _current_exit_deals(status: dict[str, Any]) -> list[dict[str, Any]]:
    raw = status.get("recent_exit_deals")
    if not isinstance(raw, list):
        return []
    deals = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not _i(item.get("deal_ticket")) or not _i(item.get("position_id")):
            continue
        deals.append(dict(item))
    deals.sort(key=lambda d: (_i(d.get("time_msc")), _i(d.get("deal_ticket"))))
    return deals


def _current_lifecycle_events(status: dict[str, Any]) -> list[dict[str, Any]]:
    raw = status.get("recent_lifecycle_events")
    if not isinstance(raw, list):
        return []
    rows = [dict(x) for x in raw if isinstance(x, dict) and _i(x.get("sequence")) > 0]
    rows.sort(key=lambda x: _i(x.get("sequence")))
    return rows


def _attach_lifecycle_event(trade: dict[str, Any], event: dict[str, Any]) -> None:
    rows = trade.setdefault("lifecycle_events", [])
    seq = _i(event.get("sequence"))
    if any(_i(x.get("sequence")) == seq for x in rows if isinstance(x, dict)):
        return
    rows.append(dict(event))
    rows.sort(key=lambda x: _i(x.get("sequence")))
    result = str(event.get("result") or "").upper()
    action = str(event.get("action") or "UNKNOWN").upper()
    if result in {"FAILED", "REJECTED"}:
        issues = trade.setdefault("execution_integrity_issues", [])
        issues.append({
            "sequence": seq, "action": action, "result": result,
            "retcode": event.get("retcode"), "terminal_error": event.get("terminal_error"),
            "comment": event.get("comment"), "time_epoch": event.get("time_epoch"),
        })
        trade["execution_integrity"] = "IMPLEMENTATION_CONTAMINATED"
        trade["strategy_learning_eligible"] = False


def _finalize_execution_integrity(trade: dict[str, Any]) -> None:
    if trade.get("execution_integrity") == "IMPLEMENTATION_CONTAMINATED":
        trade["strategy_learning_eligible"] = False
        return
    if trade.get("lifecycle_contract_covered_from_entry"):
        trade["execution_integrity"] = "CLEAN"
        trade["strategy_learning_eligible"] = True
    else:
        trade["execution_integrity"] = "UNKNOWN"
        trade["strategy_learning_eligible"] = False


def _find_trade_for_position_id(
    active: dict[str, dict[str, Any]],
    closed: list[dict[str, Any]],
    position_id: int,
) -> tuple[str, str | int] | None:
    key = str(position_id)
    if key in active:
        return ("active", key)
    for idx in range(len(closed) - 1, -1, -1):
        if _i(closed[idx].get("ticket")) == position_id:
            return ("closed", idx)
    return None


def _attach_exit_deal(trade: dict[str, Any], deal: dict[str, Any]) -> None:
    deal_ticket = _i(deal.get("deal_ticket"))
    rows = trade.setdefault("exit_deals", [])
    if any(_i(row.get("deal_ticket")) == deal_ticket for row in rows if isinstance(row, dict)):
        return
    rows.append(dict(deal))
    rows.sort(key=lambda d: (_i(d.get("time_msc")), _i(d.get("deal_ticket"))))

    trade["realized_profit"] = round(sum(_f(d.get("profit")) for d in rows), 2)
    trade["realized_swap"] = round(sum(_f(d.get("swap")) for d in rows), 2)
    trade["realized_commission"] = round(sum(_f(d.get("commission")) for d in rows), 2)
    trade["realized_fee"] = round(sum(_f(d.get("fee")) for d in rows), 2)
    trade["realized_net_pl"] = round(sum(_f(d.get("net_pl")) for d in rows), 2)
    trade["closed_volume"] = round(sum(_f(d.get("volume")) for d in rows), 8)
    trade["partial_exit_count"] = sum(
        1 for d in rows if isinstance(d, dict) and not bool(d.get("full_close"))
    )
    trade["realized_pl_so_far_exact"] = True
    trade["remaining_volume"] = _f(
        (trade.get("latest_position") or {}).get("volume"),
        max(0.0, _f(trade.get("initial_volume")) - _f(trade.get("closed_volume"))),
    )
    trade["floating_net_pl"] = _f(
        (trade.get("latest_position") or {}).get("net_pl"),
        _f(trade.get("last_observed_net_pl")),
    )
    trade["lifecycle_net_pl"] = round(
        _f(trade.get("realized_net_pl")) + _f(trade.get("floating_net_pl")),
        8,
    )

    if bool(deal.get("full_close")):
        # Once MT5 supplies an authoritative full-close deal there is no live
        # floating component left. Preserve last_observed_net_pl separately as
        # diagnostic pre-close evidence, but never double-count it into the
        # closed lifecycle result.
        trade["remaining_volume"] = 0.0
        trade["floating_net_pl"] = 0.0
        trade["lifecycle_net_pl"] = round(_f(trade.get("realized_net_pl")), 8)
        trade["final_exit_deal_ticket"] = deal_ticket
        trade["close_time_epoch"] = _i(deal.get("time_epoch"))
        trade["close_time_msc"] = _i(deal.get("time_msc"))
        trade["close_price"] = _f(deal.get("price"))
        trade["close_reason"] = deal.get("reason")
        trade["close_deal_type"] = deal.get("deal_type")
        trade["close_deal_entry"] = deal.get("deal_entry")
        trade["exact_realized_pl_available"] = True
        trade["outcome_quality"] = "CONFIRMED_MT5_DEAL_TELEMETRY"


def _apply_realized_result_class(trade: dict[str, Any]) -> None:
    if not trade.get("exact_realized_pl_available"):
        return
    realized = _f(trade.get("realized_net_pl"))
    if realized > 0:
        trade["realized_result_class"] = "REALIZED_POSITIVE"
    elif realized < 0:
        trade["realized_result_class"] = "REALIZED_NEGATIVE"
    else:
        trade["realized_result_class"] = "REALIZED_FLAT"





def _parse_zone_entry_comment(comment: Any) -> tuple[str, int]:
    text = str(comment or "").strip()
    if not text.startswith("AZ|"):
        return "", 0
    parts = text.split("|")
    if len(parts) < 3:
        return "", 0
    plan_id = parts[1].strip()
    layer = 0
    token = parts[2].strip().upper()
    if token.startswith("L"):
        try:
            layer = int(token[1:])
        except ValueError:
            layer = 0
    return plan_id, layer


def _parse_scalp_context_comment(comment: Any) -> tuple[str, str, float]:
    text = str(comment or "").strip()
    parts = text.split("|")

    if len(parts) < 11 or not parts or parts[0] != "N":
        return "NEUTRAL_SCALP", "NONE", 0.0

    context_class = {
        "A": "ZONE_ALIGNED_SCALP",
        "C": "COUNTER_ZONE_SCALP",
        "N": "NEUTRAL_SCALP",
    }.get(parts[8].strip().upper(), "NEUTRAL_SCALP")

    zone_side = {
        "B": "BUY",
        "S": "SELL",
    }.get(parts[9].strip().upper(), "NONE")

    try:
        pressure = max(
            0.0,
            min(1.0, float(parts[10]) / 100.0),
        )
    except (TypeError, ValueError):
        pressure = 0.0

    return context_class, zone_side, pressure


def _position_type_from_exit_deal(deal: dict[str, Any]) -> str:
    explicit = str(deal.get("original_position_type") or "").strip().upper()
    if explicit in {"BUY", "SELL"}:
        return explicit
    exit_type = str(deal.get("deal_type") or "").strip().upper()
    if exit_type.endswith("SELL"):
        return "BUY"
    if exit_type.endswith("BUY"):
        return "SELL"
    return "UNKNOWN"


def _reconstruct_closed_trade_from_exit_deal(
    deal: dict[str, Any],
    status: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    """Create an auditable closed lifecycle when Atlas never observed it open."""
    position_id = _i(deal.get("position_id"))
    side = _position_type_from_exit_deal(deal)
    entry_price = _f(deal.get("entry_price"))
    entry_volume = _f(deal.get("entry_volume"), _f(deal.get("volume")))
    opened_at = _i(deal.get("entry_time_epoch"))
    entry_policy_epoch = _i(deal.get("entry_policy_epoch"))
    entry_order_origin = str(deal.get("entry_order_origin") or "RECONSTRUCTED_MT5_HISTORY")
    entry_chain_id = _i(deal.get("entry_chain_id"))
    entry_hedge_level = _i(deal.get("entry_hedge_level"))
    zone_plan_id = str(deal.get("entry_zone_plan_id") or "").strip()
    zone_layer = _i(deal.get("entry_zone_layer"))
    if not zone_plan_id:
        zone_plan_id, parsed_zone_layer = _parse_zone_entry_comment(deal.get("entry_comment"))
        if zone_layer <= 0:
            zone_layer = parsed_zone_layer
    close_epoch = _i(deal.get("time_epoch"))
    captured = _iso_now()
    context = _context_snapshot(status, intelligence)

    scalp_context_class, scalp_context_zone_side, scalp_context_pressure = (
        _parse_scalp_context_comment(deal.get("entry_comment"))
    )

    initial_position = {
        "ticket": position_id,
        "type": side,
        "volume": entry_volume,
        "entry_price": entry_price,
        "opened_at_epoch": opened_at,
        "entry_policy_epoch": entry_policy_epoch,
        "order_origin": entry_order_origin,
        "recovery_probe_entry": entry_order_origin.upper() == "RECOVERY_PROBE",
        "entry_comment": deal.get("entry_comment"),
        "scalp_context_class": scalp_context_class,
        "scalp_context_zone_side": scalp_context_zone_side,
        "scalp_context_pressure": scalp_context_pressure,
        "chain_id": entry_chain_id,
        "hedge_level": entry_hedge_level,
        "zone_plan_id": zone_plan_id,
        "zone_layer": zone_layer,
        "managed": True,
    }

    trade: dict[str, Any] = {
        "ticket": position_id,
        "symbol": status.get("symbol"),
        "type": side,
        "order_origin": entry_order_origin,
        "trading_mode": (
            "ZONE" if entry_order_origin.upper() == "ATLAS_ZONE"
            else ("RECOVERY_PROBE" if entry_order_origin.upper() == "RECOVERY_PROBE" else "SCALP")
        ),
        "origin_guess": entry_order_origin,
        "origin_quality": "AUTHORITATIVE_MT5_HISTORY_RECONSTRUCTION",
        "entry_gate_mode": "UNKNOWN_RECONSTRUCTED",
        "entry_evaluation_event": "UNKNOWN_RECONSTRUCTED",
        "entry_was_new_bar": False,
        "entry_policy_epoch": entry_policy_epoch,
        "scalp_context_class": scalp_context_class,
        "scalp_context_zone_side": scalp_context_zone_side,
        "scalp_context_pressure": scalp_context_pressure,
        "trades_on_entry_candle_before_this_entry": -1,
        "total_trades_on_entry_candle_before_this_entry": -1,
        "lifecycle_state": "CLOSED_OR_DISAPPEARED",
        "first_seen_at": captured,
        "last_seen_at": captured,
        "opened_at_epoch": opened_at,
        "entry_context_quality": "EXIT_ONLY_RECONSTRUCTED",
        "entry_context": context,
        "initial_position": initial_position,
        "latest_position": dict(initial_position),
        "entry_price": entry_price,
        "initial_volume": entry_volume,
        "maximum_volume_observed": entry_volume,
        "minimum_volume_observed": entry_volume,
        "entry_signal_score": 0.0,
        "chain_id": entry_chain_id,
        "zone_plan_id": zone_plan_id,
        "zone_layer": zone_layer,
        "initial_hedge_level": entry_hedge_level,
        "max_hedge_level_observed": entry_hedge_level,
        "max_cycle_observed": 0,
        "max_favorable_net_pl_observed": 0.0,
        "max_adverse_net_pl_observed": 0.0,
        "max_positive_distance_points_observed": 0.0,
        "max_negative_distance_points_observed": 0.0,
        "last_observed_net_pl": 0.0,
        "last_observed_distance_points": 0.0,
        "max_age_seconds_observed": max(0, close_epoch - opened_at) if opened_at else 0,
        "break_even_ever_locked": False,
        "partial_close_level_max_observed": 0,
        "regime_transitions": [],
        "risk_state_transitions": [],
        "fit_transitions": [],
        "observation_count": 0,
        "exit_deals": [],
        "exact_realized_pl_available": False,
        "reconstructed_from_exit_deal": True,
        "reconstruction_quality": (
            "ENTRY_AND_EXIT_MT5_HISTORY" if opened_at and entry_price > 0 else "EXIT_ONLY_MT5_HISTORY"
        ),
        "disappeared_at": captured,
        "observed_lifetime_seconds": 0.0,
        "observed_lifetime_minutes": 0.0,
        "final_observed_net_pl_before_disappearance": 0.0,
        "observed_result_class": "UNKNOWN_NOT_LIVE_OBSERVED",
        "closure_confirmation": {
            "method": "AUTHORITATIVE_MT5_FINAL_EXIT_DEAL_RECONSTRUCTION",
            "deal_ticket": _i(deal.get("deal_ticket")),
        },
    }
    _attach_exit_deal(trade, deal)
    _apply_realized_result_class(trade)
    return trade

def _origin_guess(position: dict[str, Any]) -> str:
    """
    Prefer Nyao's authoritative creation-origin telemetry when present.
    Fall back to the legacy chain heuristics for historical records.
    """
    authoritative = str(
        position.get("order_origin") or ""
    ).strip().upper()

    if authoritative in {
        "FRESH_MARKET",
        "FRESH_LIMIT",
        "VIRTUAL_SL_REENTRY",
        "HEDGE_CHILD",
        "ATLAS_ZONE",
        "RECOVERY_PROBE",
    }:
        return authoritative

    ticket = _i(position.get("ticket"))
    chain_id = _i(position.get("chain_id"))
    hedge_level = _i(position.get("hedge_level"))

    if hedge_level > 0:
        return "HEDGE_CHILD"
    if chain_id > 0 and chain_id == ticket:
        return "HEDGE_ROOT_OR_ORIGINAL"
    if chain_id > 0:
        return "CHAIN_MEMBER"
    return "FRESH_OR_REENTRY"


def _origin_quality(position: dict[str, Any]) -> str:
    authoritative = str(
        position.get("order_origin") or ""
    ).strip().upper()

    if authoritative in {
        "FRESH_MARKET",
        "FRESH_LIMIT",
        "VIRTUAL_SL_REENTRY",
        "HEDGE_CHILD",
        "ATLAS_ZONE",
        "RECOVERY_PROBE",
    }:
        return "AUTHORITATIVE_NYAO"

    return "INFERRED_LEGACY"


def _runtime_snapshot(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in status.items()
        if key.startswith("runtime_")
    }


def _context_snapshot(
    status: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    regime = intelligence.get("regime") or {}
    risk = intelligence.get("risk") or {}

    return {
        "captured_at": _iso_now(),
        "status_timestamp": status.get("timestamp"),
        "regime": regime.get("regime"),
        "direction": regime.get("direction"),
        "volatility": regime.get("volatility"),
        "execution_environment": regime.get(
            "execution_environment"
        ),
        "regime_confidence": regime.get("confidence"),
        "fit": intelligence.get("fit"),
        "advisor_confidence": intelligence.get("confidence"),
        "risk_state": risk.get("state"),
        "risk_score": risk.get("score"),
        "exposure_bias": risk.get("exposure_bias"),
        "veto_new_risk": risk.get("veto_new_risk"),
        "recommendations": intelligence.get(
            "recommendations"
        ) or [],
        "cautions": intelligence.get("cautions") or [],
        "proposed_changes": intelligence.get(
            "proposed_changes"
        ) or {},
        "market": {
            "symbol": status.get("symbol"),
            "bid": status.get("bid"),
            "ask": status.get("ask"),
            "spread_points": status.get("spread_points"),
            "effective_spread_cap_points": status.get(
                "effective_spread_cap_points"
            ),
            "spread_within_limit": status.get(
                "spread_within_limit"
            ),
            "current_atr": status.get("current_atr"),
            "average_atr": status.get("average_atr"),
            "volatility_ratio": status.get(
                "volatility_ratio"
            ),
        },
        "duplicate_distance": {
            "enabled": status.get(
                "runtime_enable_duplicate_distance_filter"
            ),
            "zone_points": status.get("runtime_zone_points"),
            "buy_multiplier": status.get(
                "runtime_buy_duplicate_multiplier"
            ),
            "sell_multiplier": status.get(
                "runtime_sell_duplicate_multiplier"
            ),
            "buy_reference_active": status.get(
                "buy_duplicate_reference_active"
            ),
            "sell_reference_active": status.get(
                "sell_duplicate_reference_active"
            ),
            "buy_blocked": status.get(
                "buy_duplicate_blocked"
            ),
            "sell_blocked": status.get(
                "sell_duplicate_blocked"
            ),
            "buy_distance_points": status.get(
                "buy_duplicate_distance_points"
            ),
            "sell_distance_points": status.get(
                "sell_duplicate_distance_points"
            ),
            "buy_required_distance_points": status.get(
                "buy_duplicate_required_distance_points"
            ),
            "sell_required_distance_points": status.get(
                "sell_duplicate_required_distance_points"
            ),
        },
        "signal": {
            "buy_score": status.get("buy_score"),
            "sell_score": status.get("sell_score"),
            "buy_adjusted_score": status.get(
                "buy_adjusted_score"
            ),
            "sell_adjusted_score": status.get(
                "sell_adjusted_score"
            ),
            "buy_effective_threshold": status.get(
                "buy_effective_threshold"
            ),
            "sell_effective_threshold": status.get(
                "sell_effective_threshold"
            ),
            "buy_entry_eligible": status.get(
                "buy_entry_eligible"
            ),
            "sell_entry_eligible": status.get(
                "sell_entry_eligible"
            ),
            "buy_block_reason": status.get(
                "buy_block_reason"
            ),
            "sell_block_reason": status.get(
                "sell_block_reason"
            ),
        },
        "zone": {
            "mode_active": status.get("zone_mode_active"),
            "plan_id": status.get("zone_plan_id"),
            "map_id": status.get("zone_map_id"),
            "side": status.get("zone_side"),
            "policy_epoch": status.get("zone_policy_epoch"),
            "policy_fingerprint": status.get("zone_policy_fingerprint"),
            "confirmation_score": status.get("zone_confirmation_score"),
            "confirmation_threshold": status.get("zone_confirmation_threshold"),
            "directional_score": status.get("zone_directional_score"),
        },
        "account": {
            "balance": status.get("balance"),
            "equity": status.get("equity"),
            "floating_profit": status.get(
                "floating_profit"
            ),
            "equity_drawdown_pct": status.get(
                "equity_drawdown_pct"
            ),
            "free_margin": status.get("free_margin"),
            "margin_level_pct": status.get(
                "margin_level_pct"
            ),
        },
        "exposure": {
            "strategy_open_positions": status.get(
                "strategy_open_positions"
            ),
            "buy_positions": status.get("buy_positions"),
            "sell_positions": status.get("sell_positions"),
            "total_lots": status.get("total_lots"),
            "buy_lots": status.get("buy_lots"),
            "sell_lots": status.get("sell_lots"),
            "active_hedge_chains": status.get(
                "active_hedge_chains"
            ),
            "max_active_hedge_level": status.get(
                "max_active_hedge_level"
            ),
        },
        "runtime": _runtime_snapshot(status),
        "command": {
            "applied_command_version": status.get(
                "applied_command_version"
            ),
            "atlas_enabled": status.get("atlas_enabled"),
            "atlas_buy_enabled": status.get(
                "atlas_buy_enabled"
            ),
            "atlas_sell_enabled": status.get(
                "atlas_sell_enabled"
            ),
        },
    }


def _transition_append(
    trade: dict[str, Any],
    field: str,
    value: Any,
    timestamp: str,
) -> None:
    key = f"{field}_transitions"
    transitions = trade.setdefault(key, [])

    if not transitions or transitions[-1].get("value") != value:
        transitions.append(
            {
                "at": timestamp,
                "value": value,
            }
        )


def _new_trade(
    position: dict[str, Any],
    status: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    now = _iso_now()
    net_pl = _f(position.get("net_pl"))
    distance = _f(position.get("signed_distance_points"))
    age_seconds = _i(position.get("age_seconds"))

    first_context = _context_snapshot(
        status,
        intelligence,
    )

    context_quality = (
        "NEAR_ENTRY"
        if age_seconds <= 10
        else "FIRST_OBSERVED"
    )

    regime_name = (
        (intelligence.get("regime") or {}).get("regime")
        or "UNKNOWN"
    )
    risk_state = (
        (intelligence.get("risk") or {}).get("state")
        or "UNKNOWN"
    )
    fit_state = intelligence.get("fit") or "UNKNOWN"

    return {
        "ticket": position.get("ticket"),
        "symbol": status.get("symbol"),
        "type": position.get("type"),
        "order_origin": position.get("order_origin"),
        "trading_mode": (
            "ZONE" if str(position.get("order_origin") or "").upper() == "ATLAS_ZONE"
            else ("RECOVERY_PROBE" if str(position.get("order_origin") or "").upper() == "RECOVERY_PROBE" else "SCALP")
        ),
        "recovery_probe_entry": bool(position.get("recovery_probe_entry")) or str(position.get("order_origin") or "").upper() == "RECOVERY_PROBE",
        "recovery_probe_target_risk_pct": _f(position.get("recovery_probe_target_risk_pct")),
        "recovery_probe_max_risk_pct": _f(position.get("recovery_probe_max_risk_pct")),
        "recovery_probe_admission_risk_pct": _f(position.get("recovery_probe_admission_risk_pct")),
        "recovery_probe_admission_risk_amount": _f(position.get("recovery_probe_admission_risk_amount")),
        "recovery_probe_frozen_risk_amount": _f(position.get("recovery_probe_frozen_risk_amount")),
        "origin_guess": _origin_guess(position),
        "origin_quality": _origin_quality(position),
        "entry_gate_mode": position.get("entry_gate_mode"),
        "entry_evaluation_event": position.get(
            "entry_evaluation_event"
        ),
        "entry_was_new_bar": position.get(
            "entry_was_new_bar"
        ),
        "entry_policy_epoch": _i(position.get("entry_policy_epoch")),
        "scalp_context_class": str(
            position.get("scalp_context_class") or "NEUTRAL_SCALP"
        ),
        "scalp_context_zone_side": str(
            position.get("scalp_context_zone_side") or "NONE"
        ),
        "scalp_context_pressure": _f(
            position.get("scalp_context_pressure")
        ),
        "zone_plan_id": str(position.get("zone_plan_id") or ""),
        "zone_layer": _i(position.get("zone_layer")),
        "trades_on_entry_candle_before_this_entry": position.get(
            "trades_on_entry_candle_before_this_entry"
        ),
        "total_trades_on_entry_candle_before_this_entry": position.get(
            "total_trades_on_entry_candle_before_this_entry"
        ),
        "lifecycle_state": "ACTIVE",
        "lifecycle_contract_version": status.get("lifecycle_contract_version"),
        "lifecycle_contract_started_at_epoch": _i(status.get("lifecycle_contract_started_at_epoch")),
        "lifecycle_contract_covered_from_entry": bool(
            status.get("lifecycle_contract_version") and
            _i(position.get("opened_at_epoch")) >= _i(status.get("lifecycle_contract_started_at_epoch")) > 0
        ),
        "execution_integrity": (
            "CLEAN_PENDING" if status.get("lifecycle_contract_version") and
            _i(position.get("opened_at_epoch")) >= _i(status.get("lifecycle_contract_started_at_epoch")) > 0
            else "UNKNOWN"
        ),
        "strategy_learning_eligible": False,
        "execution_integrity_issues": [],
        "lifecycle_events": [],
        "first_seen_at": now,
        "last_seen_at": now,
        "opened_at_epoch": position.get("opened_at_epoch"),
        "entry_context_quality": context_quality,
        "entry_context": first_context,
        "initial_position": dict(position),
        "latest_position": dict(position),
        "entry_price": position.get("entry_price"),
        "initial_volume": position.get("volume"),
        "remaining_volume": _f(position.get("volume")),
        "closed_volume": 0.0,
        "partial_exit_count": 0,
        "realized_profit": 0.0,
        "realized_swap": 0.0,
        "realized_commission": 0.0,
        "realized_fee": 0.0,
        "realized_net_pl": 0.0,
        "floating_net_pl": net_pl,
        "lifecycle_net_pl": net_pl,
        "realized_pl_so_far_exact": False,
        "maximum_volume_observed": _f(
            position.get("volume")
        ),
        "minimum_volume_observed": _f(
            position.get("volume")
        ),
        "entry_signal_score": position.get(
            "entry_signal_score"
        ),
        "chain_id": position.get("chain_id"),
        "initial_hedge_level": position.get(
            "hedge_level"
        ),
        "max_hedge_level_observed": _i(
            position.get("hedge_level")
        ),
        "max_cycle_observed": _i(
            position.get("cycle_num")
        ),
        "max_favorable_net_pl_observed": net_pl,
        "max_adverse_net_pl_observed": net_pl,
        "max_positive_distance_points_observed": distance,
        "max_negative_distance_points_observed": distance,
        "last_observed_net_pl": net_pl,
        "last_observed_distance_points": distance,
        "max_age_seconds_observed": age_seconds,
        "break_even_ever_locked": bool(
            position.get("break_even_locked", False)
        ),
        "partial_close_level_max_observed": _i(
            position.get("partial_close_level")
        ),
        "regime_transitions": [
            {"at": now, "value": regime_name}
        ],
        "risk_state_transitions": [
            {"at": now, "value": risk_state}
        ],
        "fit_transitions": [
            {"at": now, "value": fit_state}
        ],
        "observation_count": 1,
        "exit_deals": [],
        "exact_realized_pl_available": False,
    }


def _update_trade(
    trade: dict[str, Any],
    position: dict[str, Any],
    intelligence: dict[str, Any],
    status: dict[str, Any] | None = None,
) -> None:
    now = _iso_now()
    net_pl = _f(position.get("net_pl"))
    distance = _f(position.get("signed_distance_points"))
    volume = _f(position.get("volume"))

    status = status or {}
    current_contract_instance = _i(status.get("lifecycle_contract_started_at_epoch"))
    original_contract_instance = _i(trade.get("lifecycle_contract_started_at_epoch"))
    if (
        trade.get("lifecycle_contract_covered_from_entry")
        and current_contract_instance > 0
        and original_contract_instance > 0
        and current_contract_instance != original_contract_instance
    ):
        # The EA restarted while this lifecycle was active. The new contract
        # instance is authoritative from restart onward, but Atlas cannot prove
        # that no final event was lost from the prior in-memory ring during the
        # handoff. Preserve accounting, downgrade learning integrity to UNKNOWN.
        trade["lifecycle_contract_covered_from_entry"] = False
        if trade.get("execution_integrity") != "IMPLEMENTATION_CONTAMINATED":
            trade["execution_integrity"] = "UNKNOWN"
            trade["strategy_learning_eligible"] = False
        gaps = trade.setdefault("lifecycle_coverage_gaps", [])
        marker = {
            "reason": "EA_CONTRACT_INSTANCE_CHANGED_DURING_ACTIVE_LIFECYCLE",
            "from_instance": original_contract_instance,
            "to_instance": current_contract_instance,
            "observed_at": now,
        }
        if not any(g.get("to_instance") == current_contract_instance for g in gaps if isinstance(g, dict)):
            gaps.append(marker)

    trade["last_seen_at"] = now
    trade["lifecycle_state"] = "ACTIVE"
    trade.pop("missing_since", None)
    trade.pop("missing_observation_count", None)
    trade["latest_position"] = dict(position)
    if _i(trade.get("entry_policy_epoch")) <= 0 and _i(position.get("entry_policy_epoch")) > 0:
        trade["entry_policy_epoch"] = _i(position.get("entry_policy_epoch"))
    trade["last_observed_net_pl"] = net_pl
    trade["last_observed_distance_points"] = distance
    trade["remaining_volume"] = volume
    trade["floating_net_pl"] = net_pl
    trade["closed_volume"] = round(
        sum(
            _f(d.get("volume"))
            for d in (trade.get("exit_deals") or [])
            if isinstance(d, dict)
        ),
        8,
    )
    trade["partial_exit_count"] = sum(
        1
        for d in (trade.get("exit_deals") or [])
        if isinstance(d, dict) and not bool(d.get("full_close"))
    )
    trade["lifecycle_net_pl"] = round(
        _f(trade.get("realized_net_pl")) + net_pl,
        8,
    )
    trade["realized_pl_so_far_exact"] = bool(trade.get("exit_deals"))
    trade["observation_count"] = (
        _i(trade.get("observation_count")) + 1
    )

    trade["max_favorable_net_pl_observed"] = max(
        _f(trade.get("max_favorable_net_pl_observed"), net_pl),
        net_pl,
    )
    trade["max_adverse_net_pl_observed"] = min(
        _f(trade.get("max_adverse_net_pl_observed"), net_pl),
        net_pl,
    )
    trade["max_positive_distance_points_observed"] = max(
        _f(
            trade.get(
                "max_positive_distance_points_observed"
            ),
            distance,
        ),
        distance,
    )
    trade["max_negative_distance_points_observed"] = min(
        _f(
            trade.get(
                "max_negative_distance_points_observed"
            ),
            distance,
        ),
        distance,
    )
    trade["maximum_volume_observed"] = max(
        _f(trade.get("maximum_volume_observed"), volume),
        volume,
    )
    trade["minimum_volume_observed"] = min(
        _f(trade.get("minimum_volume_observed"), volume),
        volume,
    )
    trade["max_hedge_level_observed"] = max(
        _i(trade.get("max_hedge_level_observed")),
        _i(position.get("hedge_level")),
    )
    trade["max_cycle_observed"] = max(
        _i(trade.get("max_cycle_observed")),
        _i(position.get("cycle_num")),
    )
    trade["max_age_seconds_observed"] = max(
        _i(trade.get("max_age_seconds_observed")),
        _i(position.get("age_seconds")),
    )
    trade["break_even_ever_locked"] = bool(
        trade.get("break_even_ever_locked")
        or position.get("break_even_locked", False)
    )
    trade["partial_close_level_max_observed"] = max(
        _i(trade.get("partial_close_level_max_observed")),
        _i(position.get("partial_close_level")),
    )

    regime_name = (
        (intelligence.get("regime") or {}).get("regime")
        or "UNKNOWN"
    )
    risk_state = (
        (intelligence.get("risk") or {}).get("state")
        or "UNKNOWN"
    )
    fit_state = intelligence.get("fit") or "UNKNOWN"

    _transition_append(
        trade,
        "regime",
        regime_name,
        now,
    )
    _transition_append(
        trade,
        "risk_state",
        risk_state,
        now,
    )
    _transition_append(
        trade,
        "fit",
        fit_state,
        now,
    )


def _close_trade(
    trade: dict[str, Any],
    status: dict[str, Any],
    previous_account: dict[str, Any],
) -> dict[str, Any]:
    now = _iso_now()
    first_seen = _parse_iso(trade.get("first_seen_at"))
    last_seen = _parse_iso(trade.get("last_seen_at"))

    observed_seconds = 0.0
    if first_seen is not None and last_seen is not None:
        observed_seconds = max(
            0.0,
            (last_seen - first_seen).total_seconds(),
        )

    previous_balance = _f(
        previous_account.get("balance"),
        _f(status.get("balance")),
    )
    current_balance = _f(status.get("balance"))
    nearby_balance_delta = current_balance - previous_balance

    trade["lifecycle_state"] = "CLOSED_OR_DISAPPEARED"
    _finalize_execution_integrity(trade)
    trade["disappeared_at"] = now
    trade["observed_lifetime_seconds"] = round(
        observed_seconds,
        1,
    )
    trade["observed_lifetime_minutes"] = round(
        observed_seconds / 60.0,
        2,
    )

    # Prefer authoritative MT5 deal telemetry when the final exit deal was observed.
    # Legacy/historical trades without such telemetry remain explicitly inferred.
    if trade.get("exact_realized_pl_available"):
        trade["outcome_quality"] = "CONFIRMED_MT5_DEAL_TELEMETRY"
        _apply_realized_result_class(trade)
    else:
        trade["outcome_quality"] = "INFERRED_FROM_OPEN_POSITION_TELEMETRY"
        trade["exact_realized_pl_available"] = False
    trade["final_observed_net_pl_before_disappearance"] = _f(
        trade.get("last_observed_net_pl")
    )
    trade["balance_delta_near_disappearance"] = round(
        nearby_balance_delta,
        2,
    )
    trade["balance_at_disappearance"] = current_balance
    trade["equity_at_disappearance"] = _f(
        status.get("equity")
    )

    final_observed = _f(
        trade.get("final_observed_net_pl_before_disappearance")
    )
    if final_observed > 0:
        trade["observed_result_class"] = "POSITIVE_BEFORE_DISAPPEARANCE"
    elif final_observed < 0:
        trade["observed_result_class"] = "NEGATIVE_BEFORE_DISAPPEARANCE"
    else:
        trade["observed_result_class"] = "FLAT_BEFORE_DISAPPEARANCE"

    return trade


def track_trade_outcomes(
    status: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    """
    Observe position appearance, lifecycle, temporary disappearance, resurrection,
    and confirmed disappearance after a grace period.

    This function never changes commands.json and never controls Nyao.
    """
    identity = account_identity(status)
    outcomes_file = current_account_outcomes_file(OUTCOMES_FILE)
    if (
        not identity["ready"]
        or current_account_fingerprint() != identity["fingerprint"]
    ):
        return {
            "file": str(outcomes_file),
            "version": OUTCOME_VERSION,
            "state": (
                "WAITING_FOR_ACCOUNT_IDENTITY"
                if not identity["ready"]
                else "WAITING_FOR_ACCOUNT_SCOPE"
            ),
            "active_count": 0,
            "closed_count": 0,
            "account_identity": identity,
            "positions_snapshot_valid": isinstance(status.get("positions"), list),
        }

    with _OUTCOME_LOCK:
        store = _read_store_unlocked()

        # A malformed/missing positions array must never close the whole book.
        raw_positions = status.get("positions")
        positions_snapshot_valid = isinstance(raw_positions, list)
        current = _current_positions(status) if positions_snapshot_valid else {}
        active = store["active"]
        closed = store["closed"]
        previous_account = store.get("last_account") or {}
        now_dt = _utc_now()
        now_iso = now_dt.isoformat()

        new_tickets: list[str] = []
        resurrected_tickets: list[str] = []
        updated_tickets: list[str] = []
        pending_disappearance_tickets: list[str] = []
        disappeared_tickets: list[str] = []
        exact_closed_tickets: list[str] = []
        new_exit_deal_tickets: list[int] = []

        processed_list = store.get("processed_exit_deal_tickets") or []
        processed = {_i(x) for x in processed_list if _i(x)}
        exit_deals = _current_exit_deals(status)
        lifecycle_events = _current_lifecycle_events(status)
        processed_lifecycle = {str(x) for x in (store.get("processed_lifecycle_event_keys") or []) if str(x)}
        new_lifecycle_event_sequences: list[int] = []
        lifecycle_instance = _i(status.get("lifecycle_contract_started_at_epoch"))

        # P3.57: consume authoritative NYAO lifecycle events exactly once.
        for event in lifecycle_events:
            seq = _i(event.get("sequence"))
            event_instance = _i(event.get("contract_started_at_epoch"), lifecycle_instance)
            event_key = f"{event_instance}:{seq}"
            if not seq or event_key in processed_lifecycle:
                continue
            event["contract_started_at_epoch"] = event_instance
            ticket = _i(event.get("ticket"))
            chain_id = _i(event.get("chain_id"))
            target = _find_trade_for_position_id(active, closed, ticket) if ticket else None
            if target is None and chain_id:
                target = _find_trade_for_position_id(active, closed, chain_id)
            if target is None:
                # Position may have opened and closed between polls; defer until
                # authoritative exit-deal reconstruction creates the lifecycle row.
                continue
            kind, key_or_idx = target
            trade = active[key_or_idx] if kind == "active" else closed[key_or_idx]
            _attach_lifecycle_event(trade, event)
            processed_lifecycle.add(event_key)
            new_lifecycle_event_sequences.append(seq)

        # P3.28: consume every unseen authoritative exit deal exactly once. If a
        # position opened and closed between polls, reconstruct the closed lifecycle
        # directly from MT5 history instead of silently discarding the deal.
        reconstructed_closed_tickets: list[str] = []
        repaired_processed_orphan_tickets: list[str] = []
        deferred_exit_deal_tickets: list[int] = []
        for deal in exit_deals:
            deal_ticket = _i(deal.get("deal_ticket"))
            position_id = _i(deal.get("position_id"))
            if not deal_ticket:
                continue

            target = _find_trade_for_position_id(active, closed, position_id)

            # P3.28.1 migration repair: older ingestion could mark an exit deal as
            # processed even when no lifecycle row existed. If authoritative MT5
            # history still contains a full-close deal whose position is absent,
            # reconstruct it regardless of the old processed marker.
            if (
                target is None
                and bool(deal.get("full_close"))
                and position_id
            ):
                reconstructed = _reconstruct_closed_trade_from_exit_deal(
                    deal, status, intelligence
                )
                closed.append(reconstructed)
                reconstructed_closed_tickets.append(str(position_id))
                if deal_ticket in processed:
                    repaired_processed_orphan_tickets.append(str(position_id))
                exact_closed_tickets.append(str(position_id))
                processed.add(deal_ticket)
                new_exit_deal_tickets.append(deal_ticket)
                continue

            if deal_ticket in processed:
                continue

            consumed = False
            if target is not None:
                kind, key_or_idx = target
                trade = active[key_or_idx] if kind == "active" else closed[key_or_idx]
                _attach_exit_deal(trade, deal)
                if bool(deal.get("full_close")):
                    exact_closed_tickets.append(str(position_id))
                consumed = True
            else:
                # A partial exit with no lifecycle may correspond to a position that
                # becomes visible later in this same status pass. Do not mark it
                # processed; retry safely on the next poll.
                deferred_exit_deal_tickets.append(deal_ticket)

            if consumed:
                processed.add(deal_ticket)
                new_exit_deal_tickets.append(deal_ticket)

        # First process every currently visible MT5 position.
        for ticket, position in current.items():
            if ticket in active:
                _update_trade(active[ticket], position, intelligence, status)
                updated_tickets.append(ticket)
                continue

            # If the same MT5 position was previously closed only because telemetry
            # temporarily lost sight of it, resurrect and continue that lifecycle.
            matching_closed_idx = _find_matching_closed_index(
                closed, position, status.get("symbol")
            )
            if matching_closed_idx is not None:
                closed_segment = closed.pop(matching_closed_idx)
                fresh_segment = _new_trade(position, status, intelligence)
                active[ticket] = _merge_trade_segments(
                    closed_segment, fresh_segment, reopen=True
                )
                _update_trade(active[ticket], position, intelligence, status)
                active[ticket]["resurrection_count"] = (
                    _i(active[ticket].get("resurrection_count")) + 1
                )
                resurrected_tickets.append(ticket)
                continue

            active[ticket] = _new_trade(position, status, intelligence)
            new_tickets.append(ticket)

        # Invalid snapshot: preserve all active positions exactly as-is.
        if positions_snapshot_valid:
            for ticket in list(active.keys()):
                if ticket in current:
                    continue

                trade = active[ticket]

                # A final MT5 exit deal is authoritative closure evidence; no disappearance
                # grace is needed when the broker has explicitly confirmed the final exit.
                if trade.get("exact_realized_pl_available") and trade.get("final_exit_deal_ticket"):
                    trade = active.pop(ticket)
                    closed_trade = _close_trade(trade, status, previous_account)
                    closed_trade["closure_confirmation"] = {
                        "method": "AUTHORITATIVE_MT5_FINAL_EXIT_DEAL",
                        "deal_ticket": closed_trade.get("final_exit_deal_ticket"),
                    }
                    closed.append(closed_trade)
                    disappeared_tickets.append(ticket)
                    continue

                missing_since = _parse_iso(trade.get("missing_since"))
                if missing_since is None:
                    trade["lifecycle_state"] = "PENDING_DISAPPEARANCE"
                    trade["missing_since"] = now_iso
                    trade["missing_observation_count"] = 1
                    pending_disappearance_tickets.append(ticket)
                    continue

                trade["missing_observation_count"] = (
                    _i(trade.get("missing_observation_count")) + 1
                )
                missing_seconds = max(0.0, (now_dt - missing_since).total_seconds())
                trade["missing_duration_seconds"] = round(missing_seconds, 2)

                if missing_seconds < DISAPPEARANCE_GRACE_SECONDS:
                    trade["lifecycle_state"] = "PENDING_DISAPPEARANCE"
                    pending_disappearance_tickets.append(ticket)
                    continue

                trade = active.pop(ticket)
                trade.pop("missing_since", None)
                trade.pop("missing_observation_count", None)
                trade.pop("missing_duration_seconds", None)
                closed_trade = _close_trade(trade, status, previous_account)
                closed_trade["disappearance_confirmation"] = {
                    "grace_seconds": DISAPPEARANCE_GRACE_SECONDS,
                    "confirmed_after_seconds": round(missing_seconds, 2),
                }
                closed.append(closed_trade)
                disappeared_tickets.append(ticket)

        # Defensive de-duplication also repairs pre-v2 historical lifecycle splits.
        repaired_closed, repaired_count = _repair_duplicate_closed_records(closed)
        closed[:] = repaired_closed

        if len(closed) > MAX_CLOSED_TRADES:
            closed[:] = closed[-MAX_CLOSED_TRADES:]

        processed_sorted = sorted(processed)
        if len(processed_sorted) > MAX_PROCESSED_EXIT_DEALS:
            processed_sorted = processed_sorted[-MAX_PROCESSED_EXIT_DEALS:]
        store["processed_exit_deal_tickets"] = processed_sorted
        processed_lifecycle_sorted = sorted(processed_lifecycle)[-4096:]
        store["processed_lifecycle_event_keys"] = processed_lifecycle_sorted

        store["last_account"] = {
            "fingerprint": identity["fingerprint"],
            "login": identity["login"],
            "server": identity["server"],
            "balance": status.get("balance"),
            "equity": status.get("equity"),
            "timestamp": status.get("timestamp"),
            "captured_at": _iso_now(),
        }
        store["active_count"] = len(active)
        store["closed_count"] = len(closed)
        store["updated_at"] = _iso_now()
        store["disappearance_grace_seconds"] = DISAPPEARANCE_GRACE_SECONDS
        if repaired_count:
            store["historical_duplicate_segments_merged"] = (
                _i(store.get("historical_duplicate_segments_merged")) + repaired_count
            )

        _atomic_write_unlocked(store)

        return {
            "file": str(outcomes_file),
            "version": OUTCOME_VERSION,
            "state": "TRACKING_CURRENT_ACCOUNT",
            "account_identity": identity,
            "active_count": len(active),
            "closed_count": len(closed),
            "new_tickets": new_tickets,
            "resurrected_tickets": resurrected_tickets,
            "updated_count": len(updated_tickets),
            "pending_disappearance_tickets": pending_disappearance_tickets,
            "disappeared_tickets": disappeared_tickets,
            "historical_duplicate_segments_merged_this_pass": repaired_count,
            "positions_snapshot_valid": positions_snapshot_valid,
            "disappearance_grace_seconds": DISAPPEARANCE_GRACE_SECONDS,
            "new_exit_deal_tickets": new_exit_deal_tickets,
            "new_lifecycle_event_sequences": new_lifecycle_event_sequences,
            "reconstructed_closed_tickets": reconstructed_closed_tickets,
            "repaired_processed_orphan_tickets": repaired_processed_orphan_tickets,
            "deferred_exit_deal_tickets": deferred_exit_deal_tickets,
            "authoritative_final_exit_tickets_seen": exact_closed_tickets,
            "exact_realized_pl_available": any(
                bool(t.get("exact_realized_pl_available")) for t in closed
            ),
        }

def get_trade_outcomes(
    *,
    closed_limit: int = 200,
    include_active: bool = True,
) -> dict[str, Any]:
    closed_limit = max(
        1,
        min(int(closed_limit), 2_000),
    )

    with _OUTCOME_LOCK:
        store = _read_store_unlocked()
        outcomes_file = current_account_outcomes_file(OUTCOMES_FILE)
        closed = store["closed"][-closed_limit:]

        return {
            "version": store.get(
                "version",
                OUTCOME_VERSION,
            ),
            "file": str(outcomes_file),
            "account_fingerprint": (
                (store.get("last_account") or {}).get("fingerprint")
            ),
            "performance_scope": "CURRENT_MT5_ACCOUNT_ONLY",
            "active_count": len(store["active"]),
            "closed_count": len(store["closed"]),
            "active": (
                list(store["active"].values())
                if include_active
                else []
            ),
            "closed": closed,
            "disappearance_grace_seconds": DISAPPEARANCE_GRACE_SECONDS,
            "historical_duplicate_segments_merged": store.get(
                "historical_duplicate_segments_merged", 0
            ),
            "processed_exit_deal_count": len(store.get("processed_exit_deal_tickets") or []),
            "exact_realized_closed_count": sum(
                1 for t in store["closed"] if t.get("exact_realized_pl_available")
            ),
        }


def get_outcome_summary() -> dict[str, Any]:
    with _OUTCOME_LOCK:
        store = _read_store_unlocked()
        active = list(store["active"].values())
        closed = store["closed"]

        result_counts = Counter(
            trade.get(
                "observed_result_class",
                "UNKNOWN",
            )
            for trade in closed
        )

        origin_counts = Counter(
            trade.get("origin_guess", "UNKNOWN")
            for trade in closed
        )

        entry_regimes = Counter(
            (
                (trade.get("entry_context") or {}).get(
                    "regime"
                )
                or "UNKNOWN"
            )
            for trade in closed
        )

        entry_fit = Counter(
            (
                (trade.get("entry_context") or {}).get("fit")
                or "UNKNOWN"
            )
            for trade in closed
        )

        entry_risk = Counter(
            (
                (trade.get("entry_context") or {}).get(
                    "risk_state"
                )
                or "UNKNOWN"
            )
            for trade in closed
        )

        positive = result_counts.get(
            "POSITIVE_BEFORE_DISAPPEARANCE",
            0,
        )
        negative = result_counts.get(
            "NEGATIVE_BEFORE_DISAPPEARANCE",
            0,
        )
        flat = result_counts.get(
            "FLAT_BEFORE_DISAPPEARANCE",
            0,
        )

        exact_count = sum(1 for t in closed if t.get("exact_realized_pl_available"))
        inferred_count = len(closed) - exact_count

        return {
            "file": str(current_account_outcomes_file(OUTCOMES_FILE)),
            "active_count": len(active),
            "closed_count": len(closed),
            "outcome_quality": (
                "MIXED_CONFIRMED_AND_INFERRED" if exact_count and inferred_count
                else "CONFIRMED_MT5_DEAL_TELEMETRY" if exact_count
                else "INFERRED_FROM_OPEN_POSITION_TELEMETRY"
            ),
            "exact_realized_pl_available": exact_count > 0,
            "exact_realized_closed_count": exact_count,
            "inferred_closed_count": inferred_count,
            "observed_results": {
                "positive_before_disappearance": positive,
                "negative_before_disappearance": negative,
                "flat_before_disappearance": flat,
            },
            "entry_regime_counts": dict(
                entry_regimes.most_common()
            ),
            "entry_fit_counts": dict(
                entry_fit.most_common()
            ),
            "entry_risk_counts": dict(
                entry_risk.most_common()
            ),
            "origin_guess_counts": dict(
                origin_counts.most_common()
            ),
            "latest_closed_ticket": (
                closed[-1].get("ticket")
                if closed
                else None
            ),
            "limitations": [
                "Live-observed position disappearance uses a 30-second grace period unless an authoritative final MT5 exit deal is available.",
                "If the same MT5 position identity reappears, its lifecycle is resurrected/merged instead of counted as a new outcome.",
                "Trades that open and close between Atlas polls are reconstructed from authoritative MT5 deal history and marked as reconstructed rather than silently omitted.",
                "Legacy records collected before deal telemetry remain inferred from open-position observations.",
                "Exact realised P/L is the sum of authoritative MT5 exit deals (profit + swap + commission + fee).",
                "Balance movement near disappearance remains contextual and is not substituted for ticket-level realised P/L.",
            ],
        }
