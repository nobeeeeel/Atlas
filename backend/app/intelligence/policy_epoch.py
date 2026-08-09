from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
POLICY_EPOCH_FILE = DATA_DIR / "policy_epoch_registry.json"
_LOCK = threading.Lock()
MAX_EPOCHS = 10_000

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _runtime_config(status: dict[str, Any]) -> dict[str, Any]:
    return {k.removeprefix("runtime_"): v for k, v in status.items() if k.startswith("runtime_")}

def _empty() -> dict[str, Any]:
    now = _now_iso()
    return {"version": 1, "created_at": now, "updated_at": now, "epochs": {}}

def _read_unlocked() -> dict[str, Any]:
    if not POLICY_EPOCH_FILE.exists():
        return _empty()
    try:
        data = json.loads(POLICY_EPOCH_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    if not isinstance(data.get("epochs"), dict):
        data["epochs"] = {}
    data["version"] = 1
    data.setdefault("created_at", _now_iso())
    data.setdefault("updated_at", _now_iso())
    return data

def _write_unlocked(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="atlas-policy-epoch-", suffix=".json", dir=str(DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp_name, POLICY_EPOCH_FILE)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)

def register_runtime_policy_epoch(status: dict[str, Any]) -> dict[str, Any]:
    epoch = int(status.get("policy_epoch") or 0)
    if epoch <= 0:
        return {"written": False, "reason": "NO_POLICY_EPOCH", "path": str(POLICY_EPOCH_FILE)}
    runtime = _runtime_config(status)
    key = str(epoch)
    with _LOCK:
        store = _read_unlocked()
        existing = store["epochs"].get(key)
        comparable = {
            "symbol": status.get("symbol"),
            "applied_command_version": status.get("applied_command_version"),
            "runtime": runtime,
            "runtime_control_count": len(runtime),
        }
        if existing and all(existing.get(k) == v for k, v in comparable.items()):
            return {
                "written": False,
                "reason": "UNCHANGED",
                "policy_epoch": epoch,
                "path": str(POLICY_EPOCH_FILE),
                "runtime_control_count": len(runtime),
            }

        record = {
            "policy_epoch": epoch,
            **comparable,
            "first_captured_at": (existing or {}).get("first_captured_at", _now_iso()),
            "last_captured_at": _now_iso(),
        }
        store["epochs"][key] = record
        # Retain newest numeric epochs.
        keys = sorted(store["epochs"], key=lambda v: int(v) if str(v).isdigit() else -1)
        for old_key in keys[:-MAX_EPOCHS]:
            store["epochs"].pop(old_key, None)
        store["updated_at"] = _now_iso()
        _write_unlocked(store)
        return {"written": True, "reason": "REGISTERED" if existing is None else "REFRESHED", "policy_epoch": epoch, "path": str(POLICY_EPOCH_FILE), "runtime_control_count": len(runtime)}

def get_policy_epoch_registry(limit: int = 200) -> dict[str, Any]:
    limit = max(1, min(int(limit), 2000))
    with _LOCK:
        store = _read_unlocked()
        keys = sorted(store["epochs"], key=lambda v: int(v) if str(v).isdigit() else -1)
        selected = keys[-limit:]
        return {
            "version": store.get("version", 1),
            "file": str(POLICY_EPOCH_FILE),
            "epoch_count": len(keys),
            "epochs": [store["epochs"][k] for k in selected],
        }
