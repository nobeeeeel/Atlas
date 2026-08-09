from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.policy_transition import build_transition_plan
from backend.app.intelligence.policy_epoch import register_runtime_policy_epoch

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SHADOW_HISTORY_FILE = DATA_DIR / "shadow_policy_history.json"

_LOCK = threading.Lock()
MAX_RECORDS = 20_000
HEARTBEAT_SECONDS = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_config(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key.removeprefix("runtime_"): value
        for key, value in status.items()
        if key.startswith("runtime_")
    }


def _fingerprint(config: dict[str, Any]) -> str:
    payload = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_shadow_policy(
    status: dict[str, Any],
    intelligence: dict[str, Any],
) -> dict[str, Any]:
    """
    Build Atlas's full shadow configuration without applying it.

    The desired runtime map begins as the full currently-applied Nyao
    runtime configuration, then overlays only the advisor's proposed
    changes. This means Atlas emits a complete policy while remaining
    explicit about which parameters it would actually change.
    """
    current = _runtime_config(status)
    desired = dict(current)
    current_policy_epoch = int(status.get("policy_epoch") or 0)
    epoch_registry = register_runtime_policy_epoch(status)

    proposed = dict(
        intelligence.get("proposed_changes") or {}
    )

    changed: dict[str, dict[str, Any]] = {}

    for key, value in proposed.items():
        if key not in desired:
            # Conceptual or non-runtime recommendations are preserved
            # separately and never silently invented as Nyao controls.
            continue

        if desired.get(key) != value:
            changed[key] = {
                "current": desired.get(key),
                "shadow": value,
            }
            desired[key] = value

    risk = intelligence.get("risk") or {}
    veto = bool(risk.get("veto_new_risk"))

    conceptual_controls = {
        "new_risk_allowed": not veto,
        "risk_veto_active": veto,
        "auto_apply_allowed": False,
    }

    reasons = [
        intelligence.get("summary", ""),
        *list(intelligence.get("recommendations") or []),
    ]
    reasons = [reason for reason in reasons if reason]

    transition_plan = build_transition_plan(
        status,
        changed,
    )

    policy = {
        "mode": "SHADOW",
        "applied": False,
        "generated_at": _now_iso(),
        "policy_epoch": current_policy_epoch,
        "policy_epoch_registry": epoch_registry,
        "runtime_control_count": len(desired),
        "current_runtime_fingerprint": _fingerprint(current),
        "shadow_runtime_fingerprint": _fingerprint(desired),
        "changed_control_count": len(changed),
        "changed_controls": changed,
        "current_runtime": current,
        "shadow_runtime": desired,
        "conceptual_controls": conceptual_controls,
        "transition_plan": transition_plan,
        "regime": (intelligence.get("regime") or {}).get("regime"),
        "risk_state": risk.get("state"),
        "risk_score": risk.get("score"),
        "fit": intelligence.get("fit"),
        "confidence": intelligence.get("confidence"),
        "rationale": reasons,
        "safety_notes": [
            "Shadow policy does not write commands.json.",
            "Risk-veto state is represented conceptually and is not automatically translated into a Nyao entry-disable control yet because recovery paths must remain distinguishable from fresh-risk paths.",
            "Unchanged controls remain in the full shadow runtime map so Atlas always expresses a complete configuration.",
            "Policy Epoch v1 records the active runtime epoch and locks that epoch ID onto each new position/recovery lineage. Management-setting enforcement by snapshot is intentionally not enabled yet.",
        ],
    }

    return policy


def _empty_store() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 2,
        "created_at": now,
        "updated_at": now,
        "record_count": 0,
        "records": [],
    }


def _read_store_unlocked() -> dict[str, Any]:
    if not SHADOW_HISTORY_FILE.exists():
        return _empty_store()

    try:
        with SHADOW_HISTORY_FILE.open(
            "r",
            encoding="utf-8",
        ) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    records = data.get("records")
    if not isinstance(records, list):
        records = []

    data["records"] = records
    data["record_count"] = len(records)
    data.setdefault("created_at", _now_iso())
    data.setdefault("updated_at", _now_iso())
    data["version"] = 2
    return data


def _write_store_unlocked(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(
        prefix="atlas-shadow-",
        suffix=".json",
        dir=str(DATA_DIR),
    )

    try:
        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                store,
                handle,
                indent=2,
                ensure_ascii=False,
            )
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temp_name, SHADOW_HISTORY_FILE)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _signature(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "regime": policy.get("regime"),
        "risk_state": policy.get("risk_state"),
        "fit": policy.get("fit"),
        "current_runtime_fingerprint": policy.get(
            "current_runtime_fingerprint"
        ),
        "shadow_runtime_fingerprint": policy.get(
            "shadow_runtime_fingerprint"
        ),
        "changed_controls": policy.get("changed_controls"),
        "conceptual_controls": policy.get(
            "conceptual_controls"
        ),
        "policy_epoch": policy.get("policy_epoch"),
        "transition_apply_state": (
            policy.get("transition_plan") or {}
        ).get("apply_state"),
    }


def record_shadow_policy(
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Persist meaningful shadow-policy changes plus a 60-second heartbeat.
    """
    with _LOCK:
        store = _read_store_unlocked()
        records = store["records"]
        now = datetime.now(timezone.utc)

        current_signature = _signature(policy)
        reason = "INITIAL"

        if records:
            previous = records[-1]
            previous_signature = previous.get("signature")

            if previous_signature != current_signature:
                reason = "STATE_CHANGE"
            else:
                previous_time_raw = previous.get("recorded_at")
                try:
                    previous_time = datetime.fromisoformat(
                        str(previous_time_raw).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                except (TypeError, ValueError):
                    previous_time = None

                if (
                    previous_time is not None
                    and (now - previous_time).total_seconds()
                    < HEARTBEAT_SECONDS
                ):
                    return {
                        "written": False,
                        "reason": "UNCHANGED",
                        "record_count": len(records),
                        "path": str(SHADOW_HISTORY_FILE),
                    }

                reason = "HEARTBEAT"

        record = {
            "recorded_at": now.isoformat(),
            "reason": reason,
            "signature": current_signature,
            "policy": policy,
        }

        records.append(record)

        if len(records) > MAX_RECORDS:
            del records[:-MAX_RECORDS]

        store["record_count"] = len(records)
        store["updated_at"] = now.isoformat()

        _write_store_unlocked(store)

        return {
            "written": True,
            "reason": reason,
            "record_count": len(records),
            "path": str(SHADOW_HISTORY_FILE),
        }


def get_shadow_history(
    limit: int = 200,
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 2_000))

    with _LOCK:
        store = _read_store_unlocked()
        records = store["records"][-limit:]

        return {
            "version": store.get("version", 2),
            "file": str(SHADOW_HISTORY_FILE),
            "record_count": len(store["records"]),
            "records": records,
        }