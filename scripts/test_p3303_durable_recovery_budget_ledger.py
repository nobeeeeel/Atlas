from pathlib import Path
import tempfile

from backend.app.intelligence.recovery_risk import build_recovery_risk_ledger
from backend.app.intelligence.risk_units import build_risk_units

ROOT=Path(__file__).resolve().parents[1]
mq=(ROOT/'external/nyao/nyao_scalper.mq5').read_text()
main=(ROOT/'backend/app/main.py').read_text()
assert '#property version "44.3"' in mq
assert 'version="1.30.19"' in main
assert 'atlasRecoveryUnitBudgetMultiplier = 1.50' in mq
assert 'ORIGINAL_ENTRY_STOP_RISK' in mq
assert 'ANCHOR_LOSS_FALLBACK' in mq
assert 'FROZEN_RISK_UNIT_BUDGET' in mq
assert 'recovery_sizing_event_sequence' in mq
assert 'atlasRecoveryLastSizingReason' in mq
assert 'ATLAS_DURABLE_COMPOSITE_RECOVERY_RISK_LEDGER' in (ROOT/'backend/app/intelligence/recovery_risk.py').read_text()

# Zone campaigns must never pollute scalp-mode policy performance.
outcomes={"active":[],"closed":[{
    "ticket":1,"order_origin":"ATLAS_ZONE","trading_mode":"SCALP","entry_policy_epoch":5,
    "entry_comment":"AZ|abc123|L1|P5","exact_realized_pl_available":True,"realized_net_pl":2,
    "close_time_epoch":1000,
}]}
unit=build_risk_units(outcomes)["units"][0]
assert unit["unit_type"]=="ZONE_CAMPAIGN"
assert unit["trading_mode"]=="ZONE"

# Durable backend ledger retains a sizing decision even when the next status is NOT_EVALUATED.
with tempfile.TemporaryDirectory() as td:
    file=Path(td)/'trade_outcomes.json'; file.write_text('{}')
    o={"file":str(file),"active":[],"closed":[]}
    status={"equity":10000,"maximum_total_strategy_risk_pct":1,
      "recovery_sizing_version":"nyao-recovery-risk-v2","recovery_sizing_reason":"ATLAS_CHAIN_RISK_CAP",
      "recovery_sizing_chain_id":123,"recovery_sizing_event_sequence":1,"recovery_sizing_evaluated_at_epoch":99,
      "recovery_requested_lot":.2,"recovery_capital_capped_lot":.03,"recovery_final_lot":.03,
      "recovery_anchor_loss_usd":4,"recovery_original_unit_risk_usd":10,"recovery_unit_budget_multiplier":1.5,
      "recovery_portfolio_budget_usd":100,"recovery_budget_basis":"ORIGINAL_ENTRY_STOP_RISK",
      "recovery_chain_budget_usd":15,"recovery_remaining_budget_usd":11,"recovery_target_move_price":5,
      "recovery_estimated_adverse_risk_usd":10}
    first=build_recovery_risk_ledger(status,o)
    assert first['recovery_sizing_event_count']==1
    idle={"equity":10000,"maximum_total_strategy_risk_pct":1,"recovery_sizing_reason":"NOT_EVALUATED"}
    second=build_recovery_risk_ledger(idle,o)
    assert second['last_recovery_sizing']['chain_id']==123
    assert second['last_recovery_sizing']['final_lot']==.03
    assert second['last_recovery_sizing']['chain_budget_usd']==15
print('P3.30.3 durable recovery budget ledger tests passed')
