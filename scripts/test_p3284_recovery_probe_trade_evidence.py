from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence import capital_sizing as cs


def _status(epoch: int = 32) -> dict:
    return {
        "symbol": "#BTCUSD",
        "policy_epoch": epoch,
        "applied_command_version": epoch + 2,
        "balance": 10968.40,
        "equity": 10968.40,
        "equity_drawdown_pct": 0.0,
        "volatility_ratio": 1.0,
        "strategy_open_positions": 0,
        "working_limit_orders": 0,
    }


def _outcomes(streak: int, path: Path) -> dict:
    closed = []
    for i in range(streak):
        closed.append({
            "ticket": 1000 + i,
            "exact_realized_pl_available": True,
            "realized_net_pl": -1.0,
            # Deliberately far-future relative to Atlas wall clock. This must
            # NOT be treated as a new loss after the probe is armed.
            "close_time_epoch": 4102444800,
        })
    return {
        "account_fingerprint": "test-account",
        "file": str(path),
        "closed_count": len(closed),
        "closed": closed,
    }


def run() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "trade_outcomes.json"
        outcomes = _outcomes(8, base)
        status = _status()

        # Force the material-policy lookup to emulate a runtime-confirmed new
        # policy and therefore arm a recovery probe.
        material = {
            "policy_epoch": 33,
            "command_version": 35,
            "applied_at": "2099-01-01T00:00:00+00:00",
            "material_controls": ["min_buy_signal_score"],
            "material_patch": {"min_buy_signal_score": 5.5},
            "runtime_confirmed": True,
        }
        with patch.object(cs, "_latest_runtime_confirmed_material_policy_after_protection", return_value=material):
            first = cs._loss_protection_state(status, outcomes, 8)
            assert first["state"] == "RECOVERY_PROBE", first
            assert first["escalation_level"] == 1, first
            assert first["streak_at_probe_start"] == 8, first

        # Same 8-loss history on the next poll must remain a probe even though
        # the broker close timestamp is in the future. P3.28.3 incorrectly
        # escalated here.
        second = cs._loss_protection_state(status, outcomes, 8)
        assert second["state"] == "RECOVERY_PROBE", second
        assert second["escalation_level"] == 1, second
        assert second["failed_recovery_probes"] == 0, second

        # Only a genuinely NEW losing close, represented by streak 8 -> 9,
        # escalates to the 30-minute stage.
        outcomes9 = _outcomes(9, base)
        third = cs._loss_protection_state(status, outcomes9, 9)
        assert third["state"] == "HARD_VETO", third
        assert third["escalation_level"] == 2, third
        assert third["failed_recovery_probes"] == 1, third
        assert third["timeout_minutes"] == 30, third

    print("P3.28.4 recovery probe trade-evidence regression tests passed")


if __name__ == "__main__":
    run()
