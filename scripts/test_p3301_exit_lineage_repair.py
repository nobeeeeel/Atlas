from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.intelligence.risk_units import build_risk_units

mq5 = (ROOT / "external/nyao/nyao_scalper.mq5").read_text()
outcomes_src = (ROOT / "backend/app/intelligence/outcomes.py").read_text()

assert '#property version "44.3"' in mq5
assert "AtlasExitDealBelongsToNyao" in mq5
assert "HistorySelectByPosition(positionId)" in mq5
assert "AtlasBuildHedgeLineageComment" in mq5
assert 'return "H|"' in mq5
assert 'entry_chain_id' in mq5
assert 'entry_hedge_level' in mq5
assert 'entry_order_origin' in mq5
assert 'entry_chain_id = _i(deal.get("entry_chain_id"))' in outcomes_src

# Historical repair case matching the observed BTC recovery lifecycle:
# root opens first, hedge child opens while root is alive, root closes -1.59,
# child later closes +3.67. Old comments identify the child but have no chain id.
outcomes = {
    "closed": [
        {
            "ticket": 231325832,
            "order_origin": "RECONSTRUCTED_MT5_HISTORY",
            "origin_guess": "RECONSTRUCTED_MT5_HISTORY",
            "entry_policy_epoch": 35,
            "opened_at_epoch": 1786272556,
            "close_time_msc": 1786273482951,
            "exact_realized_pl_available": True,
            "realized_net_pl": -1.59,
            "trading_mode": "SCALP",
        },
        {
            "ticket": 231326411,
            "order_origin": "HEDGE_CHILD",
            "origin_guess": "HEDGE_CHILD",
            "entry_policy_epoch": 35,
            "opened_at_epoch": 1786273201,
            "close_time_msc": 1786273894000,
            "exact_realized_pl_available": True,
            "realized_net_pl": 3.67,
            "trading_mode": "SCALP",
            "chain_id": 0,
            "initial_hedge_level": 0,
        },
    ],
    "active": [],
}
report = build_risk_units(outcomes)
assert report["legacy_lineage_inference_count"] == 1, report
assert report["unit_count"] == 1, report
unit = report["units"][0]
assert unit["unit_type"] == "RECOVERY_CHAIN", unit
assert unit["root_ticket"] == 231325832, unit
assert unit["member_tickets"] == [231325832, 231326411], unit
assert abs(unit["realized_net_pl"] - 2.08) < 1e-9, unit
assert unit["result_class"] == "WIN", unit
assert report["consecutive_completed_loss_units"] == 0, report

print("P3.30.1 exit ownership + immutable lineage + legacy repair checks passed")
