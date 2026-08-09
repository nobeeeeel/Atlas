from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.outcome_analytics import _performance_summary  # noqa: E402


def main() -> None:
    trades = [
        {"exact_realized_pl_available": True, "realized_net_pl": 12.0, "close_time_epoch": 1},
        {"exact_realized_pl_available": True, "realized_net_pl": -4.0, "close_time_epoch": 2},
        {"exact_realized_pl_available": False, "final_observed_net_pl_before_disappearance": 2.0, "close_time_epoch": 3},
    ]
    result = _performance_summary(trades)
    assert result["closed_trades"] == 3
    assert result["exact_realized_count"] == 2
    assert result["net_pl"] == 10.0
    assert result["expectancy"] == 3.33
    assert result["profit_factor"] == 3.5
    assert result["maximum_closed_trade_drawdown"] == 4.0
    assert result["sample_state"] == "INSUFFICIENT"
    print("P3.19 policy performance checks passed.")


if __name__ == "__main__":
    main()
