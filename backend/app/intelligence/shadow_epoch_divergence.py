from __future__ import annotations

from typing import Any

from backend.app.intelligence.policy_epoch import get_policy_epoch_registry
from backend.app.intelligence.position_policy_resolver import (
    POSITION_SCOPED_CONTROLS,
)

VERSION = 1
MODE = "SHADOW_EPOCH_DIVERGENCE_V21"


def _runtime_from_status(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key.removeprefix("runtime_"): value
        for key, value in status.items()
        if key.startswith("runtime_")
    }


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


def _values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) is bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-9
    return a == b


def coerce_shadow_test_value(raw: str, current_value: Any) -> Any:
    """Coerce a URL query value to the current runtime control's type."""
    if isinstance(current_value, bool):
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        raise ValueError("Boolean test values must be true/false, 1/0, yes/no, or on/off.")

    if isinstance(current_value, int) and not isinstance(current_value, bool):
        value = float(raw)
        if not value.is_integer():
            raise ValueError("This control requires an integer test value.")
        return int(value)

    if isinstance(current_value, float):
        return float(raw)

    return raw


def build_shadow_epoch_divergence(
    status: dict[str, Any],
    shadow_policy: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    test_control: str | None = None,
    test_value: Any = None,
) -> dict[str, Any]:
    """
    Compare each live position's entry-policy snapshot with a hypothetical
    next policy. This function is pure diagnostics: it does not write
    commands.json, does not register a new epoch, and does not alter Nyao.
    """
    if registry is None:
        registry = get_policy_epoch_registry(limit=2000)

    symbol = str(status.get("symbol") or "")
    current_epoch = int(status.get("policy_epoch") or 0)
    current_runtime = _runtime_from_status(status)
    hypothetical_runtime = dict(shadow_policy.get("shadow_runtime") or current_runtime)

    source = "ADVISOR_SHADOW_POLICY"
    controlled_override = None

    if test_control is not None:
        if test_control not in POSITION_SCOPED_CONTROLS:
            raise ValueError(
                f"{test_control!r} is not one of the {len(POSITION_SCOPED_CONTROLS)} "
                "position-scoped controls allowed in the v2.1 dry-run test."
            )
        if test_control not in current_runtime:
            raise ValueError(f"{test_control!r} is not present in the current Nyao runtime.")
        hypothetical_runtime = dict(current_runtime)
        hypothetical_runtime[test_control] = test_value
        source = "CONTROLLED_SINGLE_CONTROL_OVERRIDE"
        controlled_override = {
            "control": test_control,
            "current_runtime_value": current_runtime.get(test_control),
            "hypothetical_value": test_value,
        }

    changed_from_current = {
        key: {
            "current": current_runtime.get(key),
            "hypothetical": hypothetical_runtime.get(key),
        }
        for key in hypothetical_runtime
        if key in current_runtime
        and not _values_equal(current_runtime.get(key), hypothetical_runtime.get(key))
    }

    material_change = bool(changed_from_current)
    hypothetical_epoch = current_epoch + 1 if material_change else current_epoch

    epochs = _registry_map(registry)
    results: list[dict[str, Any]] = []
    divergent_positions = 0
    resolvable_positions = 0

    for position in status.get("positions") or []:
        if not isinstance(position, dict):
            continue

        entry_epoch = int(position.get("entry_policy_epoch") or 0)
        record = epochs.get(entry_epoch) if entry_epoch > 0 else None
        entry_runtime = (
            record.get("runtime")
            if isinstance(record, dict) and isinstance(record.get("runtime"), dict)
            else None
        )

        if entry_epoch <= 0:
            quality = "LEGACY_UNKNOWN_EPOCH"
            reason = "Epoch 0 is intentionally unresolved; historical policy is not invented."
        elif record is None:
            quality = "MISSING_EPOCH_SNAPSHOT"
            reason = f"Epoch {entry_epoch} is not present in the policy registry."
        elif record.get("symbol") not in (None, "", symbol):
            quality = "SYMBOL_MISMATCH"
            reason = f"Epoch {entry_epoch} belongs to {record.get('symbol')}, not {symbol}."
            entry_runtime = None
        elif entry_runtime is None:
            quality = "INVALID_EPOCH_SNAPSHOT"
            reason = f"Epoch {entry_epoch} has no usable runtime snapshot."
        else:
            quality = "RESOLVED_AUTHORITATIVE_EPOCH"
            reason = "Exact entry-policy runtime resolved from the Atlas epoch registry."
            resolvable_positions += 1

        differences: list[dict[str, Any]] = []
        if entry_runtime is not None:
            for control in POSITION_SCOPED_CONTROLS:
                if control not in entry_runtime or control not in hypothetical_runtime:
                    continue
                entry_value = entry_runtime.get(control)
                hypothetical_value = hypothetical_runtime.get(control)
                if not _values_equal(entry_value, hypothetical_value):
                    differences.append({
                        "control": control,
                        "entry_policy_value": entry_value,
                        "hypothetical_policy_value": hypothetical_value,
                    })

        if differences:
            divergent_positions += 1

        results.append({
            "ticket": int(position.get("ticket") or 0),
            "type": position.get("type"),
            "order_origin": position.get("order_origin"),
            "chain_id": int(position.get("chain_id") or 0),
            "hedge_level": int(position.get("hedge_level") or 0),
            "entry_policy_epoch": entry_epoch,
            "current_policy_epoch": current_epoch,
            "hypothetical_policy_epoch": hypothetical_epoch,
            "resolution_quality": quality,
            "resolution_reason": reason,
            "actual_execution_source": "V33_ENTRY_POLICY_EPOCH_ALL_53_POSITION_SENSITIVE",
            "actual_execution_epoch": current_epoch,
            "hypothetical_execution_source": "SHADOW_ONLY",
            "execution_changed": False,
            "would_differ_control_count": len(differences),
            "would_differ_controls": [item["control"] for item in differences],
            "differences": differences,
        })

    return {
        "version": VERSION,
        "mode": MODE,
        "ready": True,
        "symbol": symbol,
        "source": source,
        "current_policy_epoch": current_epoch,
        "hypothetical_policy_epoch": hypothetical_epoch,
        "hypothetical_epoch_is_new": material_change,
        "controlled_override": controlled_override,
        "current_to_hypothetical_changed_control_count": len(changed_from_current),
        "current_to_hypothetical_changed_controls": changed_from_current,
        "position_count": len(results),
        "resolvable_position_count": resolvable_positions,
        "divergent_position_count": divergent_positions,
        "actual_execution_unchanged": True,
        "command_file_write_performed": False,
        "policy_epoch_registered": False,
        "positions": results,
        "safety_notes": [
            "This endpoint is a pure dry-run and never writes commands.json.",
            "The hypothetical epoch number is informational only and is not registered in policy_epoch_registry.json.",
            "The endpoint itself changes nothing. Nyao v3.3 executes all 53 position-sensitive controls from entry policy epoch when the required snapshots are available.",
            "Controlled overrides are restricted to the 53 position-scoped management/recovery controls.",
        ],
    }