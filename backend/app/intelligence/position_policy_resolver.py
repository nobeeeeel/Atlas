from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.intelligence.policy_epoch import get_policy_epoch_registry

RESOLVER_VERSION = 1
RESOLVER_MODE = "LIVE_POSITION_POLICY_DIAGNOSTIC"

# These controls are the first position-scoped candidates. Nothing in this
# module writes commands.json or changes Nyao execution.
MANAGEMENT_SENSITIVE_CONTROLS = (
    "enable_loss_management",
    "max_holding_loss_positions",
    "min_health_score",
    "max_adverse_atr",
    "health_trend_weight",
    "health_rsi_weight",
    "health_atr_weight",
    "health_swing_weight",
    "health_rsi_buy_min",
    "health_rsi_sell_max",
    "health_swing_lookback",
    "health_grace_bars",
    "enable_partial_close",
    "partial_close75_pct",
    "partial_close50_pct",
    "partial_close25_pct",
    "enable_health_sl_tightening",
    "sl_tighten_atr_multiplier",
    "sl_tighten_min_health_pct",
    "enable_break_even_on_spread",
    "break_even_spread_multiplier",
    "enable_profit_offset_sl",
    "consecutive_wins_required",
    "min_offset_profit",
    "enable_trailing",
    "trailing_enable_break_even_lock",
    "trailing_sl_on_profitable_only",
    "enable_adaptive_tp",
    "enable_adaptive_sl",
    "ts_input_type",
    "trailing_distance_value",
    "trailing_value_multiplier",
)

RECOVERY_SENSITIVE_CONTROLS = (
    "enable_virtual_sl_reentry",
    "reentry_respects_new_bar_gate",
    "reentry_min_signal_pct",
    "enable_hedge_chain",
    "hedge_trigger_atr",
    "hedge_require_signal",
    "hedge_min_signal_score",
    "hedge_auto_lot",
    "hedge_recovery_atr",
    "hedge_lot_multiplier",
    "hedge_max_lot",
    "hedge_recovery_pct",
    "hedge_roll_min_profit",
    "hedge_cycle_levels",
    "enable_hedge_cycle_reset",
    "hedge_cycle_partial_pct",
    "hedge_max_cycles",
    "hedge_max_chain_loss_usd",
    "hedge_max_chain_loss_pct",
    "hedge_clear_root_sl",
    "hedge_trail_atr",
)

POSITION_SCOPED_CONTROLS = MANAGEMENT_SENSITIVE_CONTROLS + RECOVERY_SENSITIVE_CONTROLS

POSITION_EXECUTION_LOCKED_CONTROLS = POSITION_SCOPED_CONTROLS


def _runtime_from_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key.removeprefix("runtime_"): value
        for key, value in status.items()
        if key.startswith("runtime_")
    }


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) is bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9
    return a == b


def _registry_map(registry: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for record in registry.get("epochs") or []:
        if not isinstance(record, dict):
            continue
        try:
            epoch = int(record.get("policy_epoch") or 0)
        except (TypeError, ValueError):
            continue
        if epoch > 0:
            result[epoch] = record
    return result


def _control_rows(
    current_runtime: dict[str, Any],
    entry_runtime: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    changed: list[str] = []
    management = set(MANAGEMENT_SENSITIVE_CONTROLS)

    for control in POSITION_SCOPED_CONTROLS:
        current_present = control in current_runtime
        entry_present = entry_runtime is not None and control in entry_runtime
        current_value = current_runtime.get(control)
        entry_value = entry_runtime.get(control) if entry_present else None
        differs = bool(current_present and entry_present and not _values_equal(current_value, entry_value))
        if differs:
            changed.append(control)
        rows.append({
            "control": control,
            "family": "MANAGEMENT_SENSITIVE" if control in management else "RECOVERY_SENSITIVE",
            "current_runtime_value": current_value if current_present else None,
            "entry_policy_value": entry_value if entry_present else None,
            "entry_policy_value_available": bool(entry_present),
            "would_differ_if_locked": differs,
        })
    return rows, changed


def build_position_management_policy_diagnostics(
    status: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve every live position's entry policy without changing execution.

    `actual_execution_source` is deliberately CURRENT_RUNTIME in v1. This is a
    shadow resolver only. It tells us what Nyao would use after true
    position-scoped management is enabled, and where that would differ from
    today's global runtime.
    """
    if registry is None:
        registry = get_policy_epoch_registry(limit=2000)

    current_epoch = int(status.get("policy_epoch") or 0)
    current_runtime = _runtime_from_status(status)
    epochs = _registry_map(registry)
    symbol = str(status.get("symbol") or "")
    positions = status.get("positions") or []

    results: list[dict[str, Any]] = []
    quality_counts: Counter[str] = Counter()
    divergent_position_count = 0
    resolved_position_count = 0
    unresolved_position_count = 0

    for position in positions:
        if not isinstance(position, dict):
            continue
        ticket = int(position.get("ticket") or 0)
        entry_epoch = int(position.get("entry_policy_epoch") or 0)
        record = epochs.get(entry_epoch) if entry_epoch > 0 else None
        entry_runtime: dict[str, Any] | None = None
        quality: str
        reason: str

        if entry_epoch <= 0:
            quality = "LEGACY_UNKNOWN_EPOCH"
            reason = "Position predates authoritative policy epochs or its historical policy is unknown."
        elif record is None:
            quality = "MISSING_EPOCH_SNAPSHOT"
            reason = f"Policy epoch {entry_epoch} is not present in the Atlas registry."
        elif record.get("symbol") not in (None, "", symbol):
            quality = "SYMBOL_MISMATCH"
            reason = f"Epoch {entry_epoch} belongs to {record.get('symbol')}, not {symbol}."
        elif not isinstance(record.get("runtime"), dict):
            quality = "INVALID_EPOCH_SNAPSHOT"
            reason = f"Policy epoch {entry_epoch} does not contain a runtime snapshot."
        else:
            quality = "RESOLVED_AUTHORITATIVE_EPOCH"
            reason = "Entry policy snapshot resolved from the Atlas policy-epoch registry."
            entry_runtime = record["runtime"]
            resolved_position_count += 1

        rows, changed = _control_rows(current_runtime, entry_runtime)
        if entry_runtime is None:
            unresolved_position_count += 1
        if changed:
            divergent_position_count += 1
        quality_counts[quality] += 1

        results.append({
            "ticket": ticket,
            "symbol": symbol,
            "type": position.get("type"),
            "order_origin": position.get("order_origin"),
            "chain_id": int(position.get("chain_id") or 0),
            "hedge_level": int(position.get("hedge_level") or 0),
            "entry_policy_epoch": entry_epoch,
            "current_policy_epoch": current_epoch,
            "same_as_current_epoch": entry_epoch > 0 and entry_epoch == current_epoch,
            "resolution_quality": quality,
            "resolution_reason": reason,
            "actual_execution_source": ("ENTRY_POLICY_EPOCH_ALL_53_POSITION_SENSITIVE" if entry_runtime is not None else "CURRENT_RUNTIME_FALLBACK"),
            "shadow_locked_execution_source": (
                "ENTRY_POLICY_EPOCH" if entry_runtime is not None else "UNRESOLVED_LEGACY_FALLBACK"
            ),
            "execution_changed": bool(entry_runtime is not None and entry_epoch != current_epoch),
            "position_scoped_control_count": len(POSITION_SCOPED_CONTROLS),
            "would_differ_control_count": len(changed),
            "would_differ_controls": changed,
            "controls": rows,
        })

    return {
        "version": RESOLVER_VERSION,
        "mode": RESOLVER_MODE,
        "ready": True,
        "symbol": symbol,
        "current_policy_epoch": current_epoch,
        "position_count": len(results),
        "resolved_position_count": resolved_position_count,
        "unresolved_position_count": unresolved_position_count,
        "divergent_position_count": divergent_position_count,
        "position_scoped_control_count": len(POSITION_SCOPED_CONTROLS),
        "management_sensitive_control_count": len(MANAGEMENT_SENSITIVE_CONTROLS),
        "recovery_sensitive_control_count": len(RECOVERY_SENSITIVE_CONTROLS),
        "resolution_quality_counts": dict(quality_counts),
        "actual_execution_unchanged": True,
        "positions": results,
        "safety_notes": [
            "This resolver is diagnostic only and does not write commands.json.",
            "Nyao now executes all 53 position-sensitive controls (32 management + 21 recovery) from the entry epoch when snapshots are available.",
            "Epoch 0 is intentionally unresolved; Atlas does not invent a historical policy for legacy positions.",
            "Only a later explicitly enabled phase may substitute entry-policy values into Nyao position management.",
        ],
    }