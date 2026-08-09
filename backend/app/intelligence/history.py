from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HISTORY_LOCK = threading.Lock()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
HISTORY_FILE = DATA_DIR / "intelligence_history.json"

HISTORY_VERSION = 1
MAX_RECORDS = 20_000
HEARTBEAT_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _empty_store() -> dict[str, Any]:
    return {
        "version": HISTORY_VERSION,
        "created_at": _utc_now().isoformat(),
        "updated_at": _utc_now().isoformat(),
        "record_count": 0,
        "records": [],
    }


def _read_store_unlocked() -> dict[str, Any]:
    if not HISTORY_FILE.exists():
        return _empty_store()

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    records = data.get("records")
    if not isinstance(records, list):
        records = []

    data["version"] = HISTORY_VERSION
    data["records"] = records
    data["record_count"] = len(records)
    data.setdefault("created_at", _utc_now().isoformat())
    data.setdefault("updated_at", _utc_now().isoformat())
    return data


def _atomic_write_unlocked(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
        separators=(",", ": "),
    )

    fd, temp_name = tempfile.mkstemp(
        prefix="atlas-history-",
        suffix=".json",
        dir=str(DATA_DIR),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_name, HISTORY_FILE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _position_digest(status: dict[str, Any]) -> list[dict[str, Any]]:
    positions = status.get("positions")
    if not isinstance(positions, list):
        return []

    digest: list[dict[str, Any]] = []

    for position in positions:
        if not isinstance(position, dict):
            continue

        digest.append(
            {
                "ticket": position.get("ticket"),
                "type": position.get("type"),
                "volume": position.get("volume"),
                "net_pl": position.get("net_pl"),
                "entry_signal_score": position.get("entry_signal_score"),
                "chain_id": position.get("chain_id"),
                "hedge_level": position.get("hedge_level"),
                "cycle_num": position.get("cycle_num"),
            }
        )

    return digest


def _signature(status: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
    regime = intelligence.get("regime") or {}
    risk = intelligence.get("risk") or {}

    return {
        "regime": regime.get("regime"),
        "direction": regime.get("direction"),
        "volatility": regime.get("volatility"),
        "execution_environment": regime.get("execution_environment"),
        "fit": intelligence.get("fit"),
        "risk_state": risk.get("state"),
        "risk_score": risk.get("score"),
        "exposure_bias": risk.get("exposure_bias"),
        "veto_new_risk": risk.get("veto_new_risk"),
        "proposed_changes": intelligence.get("proposed_changes") or {},
        "atlas_enabled": status.get("atlas_enabled"),
        "atlas_buy_enabled": status.get("atlas_buy_enabled"),
        "atlas_sell_enabled": status.get("atlas_sell_enabled"),
        "applied_command_version": status.get("applied_command_version"),
        "strategy_open_positions": status.get("strategy_open_positions"),
        "active_hedge_chains": status.get("active_hedge_chains"),
        "max_active_hedge_level": status.get("max_active_hedge_level"),
        "trading_paused": status.get("trading_paused"),
        "spread_within_limit": status.get("spread_within_limit"),
        "buy_block_reason": status.get("buy_block_reason"),
        "sell_block_reason": status.get("sell_block_reason"),
        "duplicate_filter_enabled": status.get(
            "runtime_enable_duplicate_distance_filter"
        ),
        "buy_duplicate_blocked": status.get(
            "buy_duplicate_blocked"
        ),
        "sell_duplicate_blocked": status.get(
            "sell_duplicate_blocked"
        ),
        "buy_duplicate_reference_ticket": status.get(
            "buy_duplicate_reference_ticket"
        ),
        "sell_duplicate_reference_ticket": status.get(
            "sell_duplicate_reference_ticket"
        ),
    }


def _build_record(
    status: dict[str, Any],
    intelligence: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    regime = intelligence.get("regime") or {}
    risk = intelligence.get("risk") or {}

    return {
        "recorded_at": _utc_now().isoformat(),
        "reason": reason,
        "mode": intelligence.get("mode", "ADVISORY"),
        "summary": intelligence.get("summary"),
        "fit": intelligence.get("fit"),
        "confidence": intelligence.get("confidence"),
        "recommendations": intelligence.get("recommendations") or [],
        "cautions": intelligence.get("cautions") or [],
        "proposed_changes": intelligence.get("proposed_changes") or {},
        "auto_apply_allowed": bool(
            intelligence.get("auto_apply_allowed", False)
        ),
        "regime": regime,
        "risk": risk,
        "market": {
            "symbol": status.get("symbol"),
            "bid": status.get("bid"),
            "ask": status.get("ask"),
            "spread_points": status.get("spread_points"),
            "effective_spread_cap_points": status.get(
                "effective_spread_cap_points"
            ),
            "spread_within_limit": status.get("spread_within_limit"),
            "current_atr": status.get("current_atr"),
            "average_atr": status.get("average_atr"),
            "volatility_ratio": status.get("volatility_ratio"),
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
            "buy_reference_ticket": status.get(
                "buy_duplicate_reference_ticket"
            ),
            "sell_reference_ticket": status.get(
                "sell_duplicate_reference_ticket"
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
        "account": {
            "balance": status.get("balance"),
            "equity": status.get("equity"),
            "floating_profit": status.get("floating_profit"),
            "equity_drawdown_usd": status.get("equity_drawdown_usd"),
            "equity_drawdown_pct": status.get("equity_drawdown_pct"),
            "account_margin": status.get("account_margin"),
            "free_margin": status.get("free_margin"),
            "margin_level_pct": status.get("margin_level_pct"),
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
            "strategy_floating_pl": status.get("strategy_floating_pl"),
            "gross_notional_exposure": status.get(
                "gross_notional_exposure"
            ),
            "basket_loss_pct": status.get("basket_loss_pct"),
            "basket_risk_remaining_pct": status.get(
                "basket_risk_remaining_pct"
            ),
        },
        "hedge": {
            "active_hedge_chains": status.get("active_hedge_chains"),
            "hedge_chain_positions": status.get(
                "hedge_chain_positions"
            ),
            "hedge_chain_lots": status.get("hedge_chain_lots"),
            "hedge_chain_floating_pl": status.get(
                "hedge_chain_floating_pl"
            ),
            "hedge_chain_loss_pct": status.get("hedge_chain_loss_pct"),
            "max_active_hedge_level": status.get(
                "max_active_hedge_level"
            ),
            "max_active_hedge_cycle": status.get(
                "max_active_hedge_cycle"
            ),
        },
        "signal": {
            "buy_score": status.get("buy_score"),
            "sell_score": status.get("sell_score"),
            "buy_adjusted_score": status.get("buy_adjusted_score"),
            "sell_adjusted_score": status.get("sell_adjusted_score"),
            "buy_effective_threshold": status.get(
                "buy_effective_threshold"
            ),
            "sell_effective_threshold": status.get(
                "sell_effective_threshold"
            ),
            "buy_entry_eligible": status.get("buy_entry_eligible"),
            "sell_entry_eligible": status.get("sell_entry_eligible"),
            "buy_block_reason": status.get("buy_block_reason"),
            "sell_block_reason": status.get("sell_block_reason"),
            "buy_trend_score": status.get("buy_trend_score"),
            "sell_trend_score": status.get("sell_trend_score"),
            "buy_momentum_score": status.get("buy_momentum_score"),
            "sell_momentum_score": status.get("sell_momentum_score"),
            "buy_chop_score": status.get("buy_chop_score"),
            "sell_chop_score": status.get("sell_chop_score"),
            "buy_impulse_strength": status.get(
                "buy_impulse_strength"
            ),
            "sell_impulse_strength": status.get(
                "sell_impulse_strength"
            ),
            "buy_signal_reasoning": status.get(
                "buy_signal_reasoning"
            ),
            "sell_signal_reasoning": status.get(
                "sell_signal_reasoning"
            ),
        },
        "runtime": {
            key: value
            for key, value in status.items()
            if key.startswith("runtime_")
        },
        "positions": _position_digest(status),
        "command": {
            "applied_command_version": status.get(
                "applied_command_version"
            ),
            "atlas_enabled": status.get("atlas_enabled"),
            "atlas_buy_enabled": status.get("atlas_buy_enabled"),
            "atlas_sell_enabled": status.get("atlas_sell_enabled"),
        },
        "status_timestamp": status.get("timestamp"),
    }


def record_intelligence_snapshot(
    status: dict[str, Any],
    intelligence: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Persist an Atlas intelligence snapshot.

    To prevent the JSON file from exploding while the dashboard polls every
    two seconds, a new record is saved when the meaningful state changes or
    when the heartbeat interval expires.
    """
    with _HISTORY_LOCK:
        store = _read_store_unlocked()
        records = store["records"]
        new_signature = _signature(status, intelligence)

        reason = "INITIAL"
        should_write = True

        if records:
            last = records[-1]
            previous_signature = last.get("signature") or {}
            last_time = _parse_iso(last.get("recorded_at"))
            elapsed = (
                (_utc_now() - last_time).total_seconds()
                if last_time is not None
                else HEARTBEAT_SECONDS
            )

            if force:
                reason = "FORCED"
            elif previous_signature != new_signature:
                reason = "STATE_CHANGE"
            elif elapsed >= HEARTBEAT_SECONDS:
                reason = "HEARTBEAT"
            else:
                should_write = False
                reason = "UNCHANGED"

        if not should_write:
            return {
                "written": False,
                "reason": reason,
                "record_count": len(records),
                "path": str(HISTORY_FILE),
            }

        record = _build_record(status, intelligence, reason)
        record["signature"] = new_signature
        records.append(record)

        if len(records) > MAX_RECORDS:
            records[:] = records[-MAX_RECORDS:]

        store["updated_at"] = _utc_now().isoformat()
        store["record_count"] = len(records)
        _atomic_write_unlocked(store)

        return {
            "written": True,
            "reason": reason,
            "record_count": len(records),
            "path": str(HISTORY_FILE),
        }


def get_history(
    *,
    limit: int = 200,
    regime: str | None = None,
    risk_state: str | None = None,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 2000))

    with _HISTORY_LOCK:
        store = _read_store_unlocked()
        records = store["records"]

        filtered = records

        if regime:
            wanted = regime.upper()
            filtered = [
                item
                for item in filtered
                if str(
                    (item.get("regime") or {}).get("regime", "")
                ).upper()
                == wanted
            ]

        if risk_state:
            wanted = risk_state.upper()
            filtered = [
                item
                for item in filtered
                if str(
                    (item.get("risk") or {}).get("state", "")
                ).upper()
                == wanted
            ]

        selected = filtered[-limit:]

        return {
            "version": store.get("version", HISTORY_VERSION),
            "file": str(HISTORY_FILE),
            "total_records": len(records),
            "matching_records": len(filtered),
            "returned_records": len(selected),
            "records": selected,
        }


def get_history_summary() -> dict[str, Any]:
    with _HISTORY_LOCK:
        store = _read_store_unlocked()
        records = store["records"]

        regimes: dict[str, int] = {}
        risk_states: dict[str, int] = {}
        fit_states: dict[str, int] = {}

        for item in records:
            regime = str(
                (item.get("regime") or {}).get("regime", "UNKNOWN")
            )
            risk = str(
                (item.get("risk") or {}).get("state", "UNKNOWN")
            )
            fit = str(item.get("fit", "UNKNOWN"))

            regimes[regime] = regimes.get(regime, 0) + 1
            risk_states[risk] = risk_states.get(risk, 0) + 1
            fit_states[fit] = fit_states.get(fit, 0) + 1

        latest = records[-1] if records else None

        return {
            "file": str(HISTORY_FILE),
            "record_count": len(records),
            "created_at": store.get("created_at"),
            "updated_at": store.get("updated_at"),
            "heartbeat_seconds": HEARTBEAT_SECONDS,
            "max_records": MAX_RECORDS,
            "regime_counts": regimes,
            "risk_state_counts": risk_states,
            "fit_counts": fit_states,
            "latest_recorded_at": (
                latest.get("recorded_at")
                if latest
                else None
            ),
            "latest_reason": (
                latest.get("reason")
                if latest
                else None
            ),
        }
