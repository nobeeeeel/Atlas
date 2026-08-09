from pathlib import Path
import tempfile

from backend.app.intelligence import risk_appetite as ra
from backend.app.intelligence.capital_sizing import build_capital_sizing_plan


def status():
    return {
        "balance": 500.0, "equity": 500.0, "account_trade_mode": 0,
        "equity_drawdown_pct": 0.0, "volatility_ratio": 1.0,
        "strategy_open_positions": 0, "working_limit_orders": 0,
        "spread_within_limit": True, "zone_spread_within_limit": True,
        "account_login": 1, "account_server": "test",
    }


def main():
    with tempfile.TemporaryDirectory() as td:
        old = ra.RISK_APPETITE_FILE
        ra.RISK_APPETITE_FILE = Path(td) / "risk_appetite.json"
        try:
            assert ra.get_risk_appetite()["portfolio_hard_risk_pct"] == 1.0
            ra.update_risk_appetite(5.0, actor="test")
            plan = build_capital_sizing_plan(status(), {"closed": [], "closed_count": 0})
            assert plan["risk_appetite"]["portfolio_hard_risk_pct"] == 5.0
            assert plan["maximum_total_strategy_risk_amount"] == 25.0
            assert plan["maximum_total_strategy_risk_pct"] == 5.0
            try:
                ra.update_risk_appetite(20.1)
                raise AssertionError("20.1 must fail")
            except ValueError:
                pass
            ra.update_risk_appetite(20.0)
            plan = build_capital_sizing_plan(status(), {"closed": [], "closed_count": 0})
            assert plan["maximum_total_strategy_risk_amount"] == 100.0
            print("P3.31.1 configurable risk appetite: PASS")
        finally:
            ra.RISK_APPETITE_FILE = old

if __name__ == "__main__":
    main()
