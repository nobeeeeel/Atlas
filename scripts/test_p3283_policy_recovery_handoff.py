from __future__ import annotations

import json
import tempfile
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence import capital_sizing
from backend.app.intelligence.capital_sizing import build_capital_sizing_plan

capital_sizing.assess_risk = lambda status: {
    "state": "LOW", "veto_new_risk": False, "veto_reasons": []
}


def status(epoch=29, command=31, threshold=5.0):
    return {
        "connected": True,
        "symbol": "#BTCUSD",
        "account_fingerprint": "acct",
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
        "policy_epoch": epoch,
        "applied_command_version": command,
        "runtime_min_buy_signal_score": threshold,
        "runtime_min_sell_signal_score": threshold,
    }


def trade(pl, *, ticket, broker_close_msc, observed_at):
    return {
        "ticket": ticket,
        "exact_realized_pl_available": True,
        "realized_net_pl": pl,
        # Deliberately broker/server-clock shifted into the future relative to Atlas UTC.
        "close_time_msc": broker_close_msc,
        "disappeared_at": observed_at.isoformat(),
    }


def outcomes(root: Path, rows):
    p = root / "trade_outcomes.json"
    p.write_text("{}", encoding="utf-8")
    return {
        "file": str(p),
        "account_fingerprint": "acct",
        "closed_count": len(rows),
        "closed": rows,
    }


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    events = root / "autonomous_policy_events.json"
    capital_sizing.AUTONOMOUS_EVENT_FILE = events
    now = datetime.now(timezone.utc)

    # Broker clock is two hours ahead. This reproduces the P3.28.2 bug where
    # comparing policy UTC timestamps against DEAL_TIME blocked valid releases.
    broker_future = int((now + timedelta(hours=2)).timestamp() * 1000)
    rows = [
        trade(-1, ticket=100 + i, broker_close_msc=broker_future + i, observed_at=now - timedelta(minutes=10-i))
        for i in range(8)
    ]
    book = outcomes(root, rows)

    first = build_capital_sizing_plan(status(29, 31, 5.0), book)
    assert first["loss_protection"]["state"] == "HARD_VETO"
    assert first["loss_protection"]["timeout_minutes"] == 15

    # Policy is applied after the Atlas protection stage begins, despite the MT5
    # broker close timestamp appearing later on the wall clock.
    event_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    events.write_text(json.dumps({"version": 1, "events": [{
        "sequence": 1,
        "timestamp": event_at.isoformat(),
        "action": "AUTO_POLICY_APPLIED",
        "baseline_policy_epoch": 29,
        "policy_epoch": 30,
        "command_version": 32,
        "consensus_patch": {
            "min_buy_signal_score": 5.5,
            "min_sell_signal_score": 5.5,
        },
    }]}), encoding="utf-8")

    # Command/epoch ACK plus matching runtime controls releases only the loss timer.
    released = build_capital_sizing_plan(status(30, 32, 5.5), book)
    lp = released["loss_protection"]
    assert lp["state"] == "RECOVERY_PROBE", lp
    assert lp["released_by_policy_epoch"] == 30
    assert lp["release_reason"] == "MATERIAL_POLICY_RUNTIME_CONFIRMED"
    assert abs(released["approved_scalp_risk_pct"] - 0.05) < 1e-9
    assert released["approved_zone_risk_pct"] == 0.0
    assert released["veto_new_risk"] is False

    # If live runtime controls do not match the patch, epoch ACK alone cannot release.
    state_file = root / "capital_recovery.json"
    stored = json.loads(state_file.read_text(encoding="utf-8"))
    stored.update({
        "state": "HARD_VETO",
        "protected_policy_epoch": 30,
        "released_by_policy_epoch": None,
        "stage_started_at": datetime.now(timezone.utc).isoformat(),
        "recovery_probe_started_at": None,
    })
    state_file.write_text(json.dumps(stored), encoding="utf-8")
    events.write_text(json.dumps({"version": 1, "events": [{
        "sequence": 2,
        "timestamp": (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
        "action": "AUTO_POLICY_APPLIED",
        "baseline_policy_epoch": 30,
        "policy_epoch": 31,
        "command_version": 33,
        "consensus_patch": {
            "min_buy_signal_score": 6.0,
            "min_sell_signal_score": 6.0,
        },
    }]}), encoding="utf-8")
    mismatch = build_capital_sizing_plan(status(31, 33, 5.5), book)
    assert mismatch["loss_protection"]["state"] == "HARD_VETO"

    # Matching runtime values now release epoch 31.
    matched = build_capital_sizing_plan(status(31, 33, 6.0), book)
    assert matched["loss_protection"]["state"] == "RECOVERY_PROBE"
    assert matched["loss_protection"]["released_by_policy_epoch"] == 31

print("P3.28.3 policy recovery handoff tests passed")
