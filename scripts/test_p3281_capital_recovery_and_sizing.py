from __future__ import annotations

import json
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence import capital_sizing
from backend.app.intelligence.capital_sizing import build_capital_sizing_plan


def _status() -> dict:
    return {
        "connected": True,
        "symbol": "#BTCUSD",
        "balance": 10000.0,
        "equity": 10000.0,
        "equity_drawdown_pct": 0.0,
        "strategy_open_positions": 0,
        "working_limit_orders": 0,
        "volatility_ratio": 1.0,
        "spread_within_limit": True,
        "zone_spread_within_limit": True,
        "positions": [],
        "account_trade_mode": 0,
        "policy_epoch": 28,
        "applied_command_version": 30,
    }


def _outcomes(root: Path, closed: list[dict]) -> dict:
    file = root / "trade_outcomes.json"
    file.write_text("{}", encoding="utf-8")
    return {
        "file": str(file),
        "account_fingerprint": "test-account",
        "closed_count": len(closed),
        "closed": closed,
    }


def _trade(pl: float, close_epoch: float, ticket: int) -> dict:
    return {
        "ticket": ticket,
        "exact_realized_pl_available": True,
        "realized_net_pl": pl,
        "close_time_msc": int(close_epoch * 1000),
    }


capital_sizing.assess_risk = lambda status: {
    "state": "LOW",
    "veto_new_risk": False,
    "veto_reasons": [],
}

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    normal = build_capital_sizing_plan(_status(), _outcomes(root, []))
    assert normal["version"] == "atlas-capital-regime-v2.0"
    assert normal["capital_regime"] == "CAPITAL"
    assert abs(normal["base_risk_pct"]["scalp"] - 0.30) < 1e-9
    assert abs(normal["base_risk_pct"]["zone"] - 0.45) < 1e-9
    assert abs(normal["base_risk_pct"]["maximum_total"] - 1.00) < 1e-9

    now = datetime.now(timezone.utc).timestamp()
    losses8 = [_trade(-1, now - (80 - i), 100 + i) for i in range(8)]
    hard = build_capital_sizing_plan(_status(), _outcomes(root, losses8))
    # P3.28.2: historical streak length does not jump straight to 60m.
    assert hard["loss_protection"]["state"] == "HARD_VETO", hard["loss_protection"]
    assert hard["loss_protection"]["timeout_minutes"] == 15
    assert hard["loss_protection"]["escalation_level"] == 1
    assert hard["veto_new_risk"] is True
    assert hard["approved_scalp_risk_pct"] == 0.0

project = Path(__file__).resolve().parents[1]
mql = (project / "external/nyao/nyao_scalper.mq5").read_text(encoding="utf-8")
assert '#property version "44.3"' in mql
assert "const double ATLAS_HARD_MAX_LOT = 1.0;" in mql
assert "atlasCapitalSizingActive\n        ? MathMin(maxLot, ATLAS_HARD_MAX_LOT)" in mql
assert 'AtlasSetDecisionReason(dir, "ATLAS_CAPITAL_RISK_VETO")' in mql

auto = (project / "backend/app/intelligence/autonomous_policy.py").read_text(encoding="utf-8")
assert "AUTO_DWELL_OVERRIDE_LOSS_PROTECTION" in auto
assert "apply_ready_loss_protection_consensus" in auto
assert "produced_policy_epoch" in auto

outcomes = (project / "backend/app/intelligence/outcomes.py").read_text(encoding="utf-8")
assert "repaired_processed_orphan_tickets" in outcomes

main = (project / "backend/app/main.py").read_text(encoding="utf-8")
assert 'version="1.30.19"' in main
assert "POLICY-ADAPTED RECOVERY" in main
assert "Baseline Epoch" in main and "Produced Epoch" in main

print("P3.28.1/P3.28.2 capital sizing baseline tests passed")
