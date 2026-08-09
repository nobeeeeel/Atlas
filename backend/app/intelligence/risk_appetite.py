from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from backend.app.intelligence.account_identity import current_account_fingerprint


DATA_DIR = Path(__file__).resolve().parents[3] / "data"
RISK_APPETITE_FILE = DATA_DIR / "risk_appetite.json"

RISK_APPETITE_VERSION = 1
DEFAULT_PORTFOLIO_HARD_RISK_PCT = 1.0
MIN_PORTFOLIO_HARD_RISK_PCT = 1.0
MAX_PORTFOLIO_HARD_RISK_PCT = 20.0


def _file() -> Path:
    fingerprint = current_account_fingerprint() or "UNIDENTIFIED_ACCOUNT"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in fingerprint)
    return RISK_APPETITE_FILE.parent / "accounts" / safe / "risk_appetite.json"


def _normalize(value: Any) -> float:
    try:
        pct = float(value)
    except (TypeError, ValueError):
        pct = DEFAULT_PORTFOLIO_HARD_RISK_PCT
    return min(MAX_PORTFOLIO_HARD_RISK_PCT, max(MIN_PORTFOLIO_HARD_RISK_PCT, pct))


def get_risk_appetite() -> dict[str, Any]:
    path = _file()
    data: dict[str, Any] = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except (OSError, json.JSONDecodeError):
        pass

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
        "rules": [
            "This operator-owned percentage is the absolute aggregate Atlas portfolio risk ceiling, not per-trade risk.",
            "Atlas may reduce the effective operating ceiling for drawdown, loss protection, market risk, volatility, concentration, or capacity constraints.",
            "Atlas and Gemini cannot increase the operator-owned ceiling; only an explicit operator settings update may do so.",
            "Individual scalp, zone, and recovery risk-unit limits remain independently enforced beneath this ceiling.",
        ],
    }


def update_risk_appetite(portfolio_hard_risk_pct: float, *, actor: str = "human_operator") -> dict[str, Any]:
    requested = float(portfolio_hard_risk_pct)
    if requested < MIN_PORTFOLIO_HARD_RISK_PCT or requested > MAX_PORTFOLIO_HARD_RISK_PCT:
        raise ValueError(
            f"Portfolio hard risk must be between {MIN_PORTFOLIO_HARD_RISK_PCT:.0f}% and {MAX_PORTFOLIO_HARD_RISK_PCT:.0f}%."
        )

    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": RISK_APPETITE_VERSION,
        "portfolio_hard_risk_pct": round(requested, 4),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": str(actor or "human_operator")[:120],
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return get_risk_appetite()
