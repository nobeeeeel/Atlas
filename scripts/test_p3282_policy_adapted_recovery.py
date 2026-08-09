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


def status(epoch=28, command=30):
    return {
        "connected": True, "symbol": "#BTCUSD", "account_fingerprint": "acct",
        "balance": 10000.0, "equity": 10000.0, "equity_drawdown_pct": 0.0,
        "strategy_open_positions": 0, "working_limit_orders": 0,
        "volatility_ratio": 1.0, "spread_within_limit": True,
        "zone_spread_within_limit": True, "positions": [], "account_trade_mode": 0,
        "policy_epoch": epoch, "applied_command_version": command,
    }


def trade(pl, when, ticket):
    return {
        "ticket": ticket, "exact_realized_pl_available": True,
        "realized_net_pl": pl, "close_time_msc": int(when.timestamp() * 1000),
    }


def outcomes(root, rows):
    p = root / "trade_outcomes.json"
    p.write_text("{}", encoding="utf-8")
    return {"file": str(p), "account_fingerprint": "acct", "closed_count": len(rows), "closed": rows}


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    events = root / "autonomous_policy_events.json"
    capital_sizing.AUTONOMOUS_EVENT_FILE = events
    now = datetime.now(timezone.utc)
    losses = [trade(-1, now - timedelta(minutes=8-i), 100+i) for i in range(8)]
    book = outcomes(root, losses)

    # First activation with 8 historical losses is stage 1 / 15m, never retroactive stage 3.
    p1 = build_capital_sizing_plan(status(28, 30), book)
    assert p1["loss_protection"]["state"] == "HARD_VETO"
    assert p1["loss_protection"]["timeout_minutes"] == 15
    assert p1["loss_protection"]["failed_recovery_probes"] == 0

    protection_started = datetime.fromisoformat(
        p1["loss_protection"]["protection_started_at"].replace("Z", "+00:00")
    )
    applied = protection_started + timedelta(milliseconds=1)
    events.write_text(json.dumps({"version": 1, "events": [{
        "sequence": 1,
        "timestamp": applied.isoformat(),
        "action": "AUTO_POLICY_APPLIED",
        "baseline_policy_epoch": 28,
        "policy_epoch": 29,
        "command_version": 31,
        "consensus_patch": {"min_buy_signal_score": 5.0, "min_sell_signal_score": 5.0},
    }]}), encoding="utf-8")

    # Command write alone is not enough: runtime must ACK epoch 29.
    waiting = build_capital_sizing_plan(status(28, 30), book)
    assert waiting["loss_protection"]["state"] == "HARD_VETO"

    # Runtime-confirmed material policy immediately releases only the loss timer.
    released = build_capital_sizing_plan(status(29, 31), book)
    lp = released["loss_protection"]
    assert lp["state"] == "RECOVERY_PROBE", lp
    assert lp["release_reason"] == "MATERIAL_POLICY_RUNTIME_CONFIRMED"
    assert lp["released_by_policy_epoch"] == 29
    assert set(lp["policy_release"]["material_controls"]) == {"min_buy_signal_score", "min_sell_signal_score"}
    assert abs(released["approved_scalp_risk_pct"] - 0.05) < 1e-9
    assert released["approved_zone_risk_pct"] == 0.0
    assert released["veto_new_risk"] is False
    assert released["consecutive_losses"] == 8  # evidence is preserved, not reset

    # Historical/backfilled losses do not count as a failed probe. Only a loss that
    # closes after recovery_probe_started_at escalates to 30m.
    probe_started = datetime.fromisoformat(lp["recovery_probe_started_at"].replace("Z", "+00:00"))
    losses2 = losses + [trade(-1, probe_started + timedelta(seconds=2), 999)]
    book2 = outcomes(root, losses2)
    failed = build_capital_sizing_plan(status(29, 31), book2)
    flp = failed["loss_protection"]
    assert flp["state"] == "HARD_VETO", flp
    assert flp["timeout_minutes"] == 30
    assert flp["escalation_level"] == 2
    assert flp["failed_recovery_probes"] == 1

    # A win breaks the streak and resets durable protection state.
    book3 = outcomes(root, losses2 + [trade(2, probe_started + timedelta(seconds=4), 1000)])
    won = build_capital_sizing_plan(status(29, 31), book3)
    assert won["consecutive_losses"] == 0
    assert won["loss_protection"]["state"] == "INACTIVE"
    assert abs(won["approved_scalp_risk_pct"] - 0.30) < 1e-9

print("P3.28.2 policy-adapted recovery tests passed")
