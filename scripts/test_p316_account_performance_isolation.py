from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence import outcomes
from backend.app.intelligence.account_identity import (
    account_identity,
    current_account_outcomes_file,
    scoped_account_performance,
)


def _status(login: int) -> dict:
    return {
        "account_login": login,
        "account_server": "Atlas-Demo",
        "symbol": "#BTCUSD",
        "balance": 5000.0,
        "equity": 5000.0,
        "positions": [],
    }


def test_account_ledgers_are_isolated() -> None:
    with tempfile.TemporaryDirectory(prefix="atlas-account-isolation-") as raw:
        original_data = outcomes.DATA_DIR
        original_file = outcomes.OUTCOMES_FILE
        outcomes.DATA_DIR = Path(raw)
        outcomes.OUTCOMES_FILE = Path(raw) / "trade_outcomes.json"
        try:
            first = _status(111)
            second = _status(222)
            with scoped_account_performance(first):
                first_path = current_account_outcomes_file(outcomes.OUTCOMES_FILE)
                first_path.parent.mkdir(parents=True, exist_ok=True)
                first_path.write_text(json.dumps({
                    "version": 4,
                    "active": {},
                    "closed": [{"observed_result_class": "NEGATIVE_BEFORE_DISAPPEARANCE"}],
                    "last_account": {
                        "fingerprint": account_identity(first)["fingerprint"]
                    },
                    "processed_exit_deal_tickets": [],
                }), encoding="utf-8")
                assert outcomes.get_trade_outcomes()["closed_count"] == 1

            with scoped_account_performance(second):
                second_result = outcomes.get_trade_outcomes()
                assert second_result["closed_count"] == 0
                assert second_result["closed"] == []
                tracked = outcomes.track_trade_outcomes(second, {})
                assert tracked["state"] == "TRACKING_CURRENT_ACCOUNT"
                assert tracked["closed_count"] == 0
                assert first_path != current_account_outcomes_file(outcomes.OUTCOMES_FILE)

            with scoped_account_performance({}):
                blocked = outcomes.track_trade_outcomes({"positions": []}, {})
                assert blocked["state"] == "WAITING_FOR_ACCOUNT_IDENTITY"
        finally:
            outcomes.DATA_DIR = original_data
            outcomes.OUTCOMES_FILE = original_file


if __name__ == "__main__":
    test_account_ledgers_are_isolated()
    print("P3.16 account performance isolation checks passed.")
