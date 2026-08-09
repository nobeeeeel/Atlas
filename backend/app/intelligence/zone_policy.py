from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
ZONE_POLICY_FILE = DATA_DIR / "zone_policy.json"
_LOCK = threading.RLock()


class ZonePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    confirmation_threshold: float = Field(default=52.0, ge=0.0, le=100.0)
    minimum_directional_score: float = Field(default=3.5, ge=0.0, le=10.0)
    zone_quality_weight: float = Field(default=0.40, ge=0.0, le=1.0)
    directional_signal_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    location_depth_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    timeframe_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    structure_alignment_weight: float = Field(default=0.05, ge=0.0, le=1.0)
    confluence_bonus_per_item: float = Field(default=2.0, ge=0.0, le=10.0)
    maximum_confluence_bonus: float = Field(default=10.0, ge=0.0, le=25.0)
    countertrend_penalty: float = Field(default=8.0, ge=0.0, le=30.0)
    account_risk_pct: float = Field(default=0.50, ge=0.05, le=2.0)
    entry_allocations: list[float] = Field(default_factory=lambda: [40.0, 35.0, 25.0])
    entry_depths: list[float] = Field(default_factory=lambda: [0.20, 0.50, 0.80])
    take_profit_allocations: list[float] = Field(default_factory=lambda: [40.0, 35.0, 25.0])
    take_profit_reward_multiples: list[float] = Field(default_factory=lambda: [1.0, 1.5, 2.0])
    stop_zone_width_buffer: float = Field(default=0.20, ge=0.0, le=2.0)
    stop_m30_atr_buffer: float = Field(default=0.25, ge=0.0, le=5.0)
    stop_spread_buffer: float = Field(default=3.0, ge=0.0, le=20.0)
    enable_zone_spread_filter: bool = True
    zone_market_spread_atr_ratio: float = Field(default=0.75, ge=0.0, le=5.0)
    zone_max_spread_stop_ratio: float = Field(default=0.10, ge=0.0, le=1.0)
    zone_max_spread_target_ratio: float = Field(default=0.15, ge=0.0, le=1.0)
    virtual_layer_activation_atr_ratio: float = Field(default=0.25, ge=0.01, le=2.0)

    @model_validator(mode="after")
    def validate_bundle(self) -> "ZonePolicy":
        vectors = (
            self.entry_allocations,
            self.entry_depths,
            self.take_profit_allocations,
            self.take_profit_reward_multiples,
        )
        if any(len(values) != 3 for values in vectors):
            raise ValueError("Zone execution requires exactly three entries and targets.")
        if abs(sum(self.entry_allocations) - 100.0) > 1e-6:
            raise ValueError("entry_allocations must total 100%.")
        if abs(sum(self.take_profit_allocations) - 100.0) > 1e-6:
            raise ValueError("take_profit_allocations must total 100%.")
        if any(value <= 0 for value in self.entry_allocations + self.take_profit_allocations):
            raise ValueError("Zone allocations must be positive.")
        if any(value < 0 or value > 1 for value in self.entry_depths):
            raise ValueError("entry_depths must stay inside the source zone.")
        if self.entry_depths != sorted(self.entry_depths):
            raise ValueError("entry_depths must be ordered from shallow to deep.")
        if any(value <= 0 for value in self.take_profit_reward_multiples):
            raise ValueError("take-profit reward multiples must be positive.")
        if self.enable_zone_spread_filter and not any((
            self.zone_market_spread_atr_ratio,
            self.zone_max_spread_stop_ratio,
            self.zone_max_spread_target_ratio,
        )):
            raise ValueError("At least one zone spread cap must be positive when filtering is enabled.")
        weight_total = sum((
            self.zone_quality_weight,
            self.directional_signal_weight,
            self.location_depth_weight,
            self.timeframe_weight,
            self.structure_alignment_weight,
        ))
        if abs(weight_total - 1.0) > 1e-6:
            raise ValueError("Zone confirmation weights must total 1.0.")
        return self


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(policy: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()[:16]


def _atomic_write(payload: dict[str, Any]) -> None:
    ZONE_POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(ZONE_POLICY_FILE.parent), prefix=".zone_policy.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, ZONE_POLICY_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def get_zone_policy() -> dict[str, Any]:
    with _LOCK:
        try:
            stored = json.loads(ZONE_POLICY_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
    raw_policy = stored.get("policy") if isinstance(stored, dict) else None
    policy = ZonePolicy.model_validate(raw_policy or {}).model_dump(mode="json")
    return {
        "schema_version": "1.0",
        "policy_epoch": int((stored or {}).get("policy_epoch") or 1),
        "source": (stored or {}).get("source") or "ATLAS_DEFAULT",
        "updated_at": (stored or {}).get("updated_at"),
        "fingerprint": _fingerprint(policy),
        "policy": policy,
        "path": str(ZONE_POLICY_FILE),
    }


def apply_zone_policy(
    policy: dict[str, Any],
    *,
    source: str,
    expected_current_epoch: int | None = None,
) -> dict[str, Any]:
    validated = ZonePolicy.model_validate(policy).model_dump(mode="json")
    with _LOCK:
        current = get_zone_policy()
        if expected_current_epoch is not None and int(expected_current_epoch) != int(current["policy_epoch"]):
            raise ValueError("Zone policy epoch changed before activation.")
        unchanged = validated == current["policy"]
        payload = {
            "schema_version": "1.0",
            "policy_epoch": int(current["policy_epoch"]) + (0 if unchanged else 1),
            "source": source,
            "updated_at": _now_iso(),
            "fingerprint": _fingerprint(validated),
            "policy": validated,
        }
        _atomic_write(payload)
    return {**payload, "changed": not unchanged, "path": str(ZONE_POLICY_FILE)}


def zone_policy_catalog() -> list[dict[str, Any]]:
    schema = ZonePolicy.model_json_schema().get("properties") or {}
    current = get_zone_policy()["policy"]
    return [
        {
            "parameter": name,
            "current": current.get(name),
            "description": row.get("description"),
            "minimum": row.get("minimum"),
            "maximum": row.get("maximum"),
            "type": row.get("type"),
        }
        for name, row in schema.items()
    ]
