from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from backend.app.bridge.protocol import BRIDGE_DIR
from backend.app.intelligence.account_identity import current_account_fingerprint


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
LEGACY_RISK_APPETITE_FILE = DATA_DIR / "risk_appetite.json"
# Operator-owned state must survive replacing/upgrading the Atlas source tree.
# MT5's shared Atlas bridge is outside the release package and is therefore the
# durable home for this configuration.
PERSISTENT_OPERATOR_STATE_DIR = BRIDGE_DIR / "_operator_state"
# Compatibility/configuration anchor. Tests and advanced deployments may override this.
RISK_APPETITE_FILE = PERSISTENT_OPERATOR_STATE_DIR / "risk_appetite.json"

RISK_APPETITE_VERSION = 2
DEFAULT_PORTFOLIO_HARD_RISK_PCT = 1.0
MIN_PORTFOLIO_HARD_RISK_PCT = 1.0
MAX_PORTFOLIO_HARD_RISK_PCT = 20.0


def _safe_fingerprint() -> str:
    fingerprint = current_account_fingerprint() or "UNIDENTIFIED_ACCOUNT"
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in fingerprint)


def _file() -> Path:
    return RISK_APPETITE_FILE.parent / "accounts" / _safe_fingerprint() / "risk_appetite.json"


def _legacy_file() -> Path:
    return LEGACY_RISK_APPETITE_FILE.parent / "accounts" / _safe_fingerprint() / "risk_appetite.json"


def _normalize(value: Any) -> float:
    try:
        pct = float(value)
    except (TypeError, ValueError):
        pct = DEFAULT_PORTFOLIO_HARD_RISK_PCT
    return min(MAX_PORTFOLIO_HARD_RISK_PCT, max(MIN_PORTFOLIO_HARD_RISK_PCT, pct))


def _read(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _migrate_legacy_if_needed() -> tuple[dict[str, Any], str]:
    persistent = _file()
    data = _read(persistent)
    if data:
        return data, "PERSISTENT_BRIDGE_STATE"

    legacy = _legacy_file()
    legacy_data = _read(legacy)
    if legacy_data:
        migrated = dict(legacy_data)
        migrated["version"] = RISK_APPETITE_VERSION
        migrated["migrated_at"] = datetime.now(timezone.utc).isoformat()
        migrated["migrated_from"] = str(legacy)
        _atomic_write(persistent, migrated)
        return migrated, "MIGRATED_LEGACY_RELEASE_STATE"

    return {}, "DEFAULT_NO_PERSISTED_OPERATOR_STATE"


def get_risk_appetite() -> dict[str, Any]:
    path = _file()
    data, persistence_state = _migrate_legacy_if_needed()
    configured = _normalize(data.get("portfolio_hard_risk_pct"))
    return {
        "version": RISK_APPETITE_VERSION,
        "authority": "ATLAS_OPERATOR_RISK_APPETITE",
        "portfolio_hard_risk_pct": configured,
        "default_portfolio_hard_risk_pct": DEFAULT_PORTFOLIO_HARD_RISK_PCT,
        "minimum_portfolio_hard_risk_pct": MIN_PORTFOLIO_HARD_RISK_PCT,
        "maximum_portfolio_hard_risk_pct": MAX_PORTFOLIO_HARD_RISK_PCT,
        "updated_at": data.get("updated_at"),
        "updated_by": data.get("updated_by") or "DEFAULT",
        "file": str(path),
        "persistent_outside_release_tree": True,
        "persistence_state": persistence_state,
        "legacy_file": str(_legacy_file()),
        "rules": [
            "This operator-owned percentage is the absolute aggregate Atlas portfolio risk ceiling, not per-trade risk.",
            "Atlas may reduce the effective operating ceiling for drawdown, loss protection, market risk, volatility, concentration, or capacity constraints.",
            "Atlas and Gemini cannot increase the operator-owned ceiling; only an explicit operator settings update may do so.",
            "Individual scalp, zone, and recovery risk-unit limits remain independently enforced beneath this ceiling.",
            "Operator risk appetite is persisted outside the Atlas release tree so source upgrades cannot silently reset it.",
        ],
    }


def update_risk_appetite(portfolio_hard_risk_pct: float, *, actor: str = "human_operator") -> dict[str, Any]:
    requested = float(portfolio_hard_risk_pct)
    if requested < MIN_PORTFOLIO_HARD_RISK_PCT or requested > MAX_PORTFOLIO_HARD_RISK_PCT:
        raise ValueError(
            f"Portfolio hard risk must be between {MIN_PORTFOLIO_HARD_RISK_PCT:.0f}% and {MAX_PORTFOLIO_HARD_RISK_PCT:.0f}%."
        )

    path = _file()
    payload = {
        "version": RISK_APPETITE_VERSION,
        "portfolio_hard_risk_pct": round(requested, 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": str(actor or "human_operator")[:120],
    }
    _atomic_write(path, payload)
    return get_risk_appetite()
