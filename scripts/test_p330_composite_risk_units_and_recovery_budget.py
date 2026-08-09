from __future__ import annotations

from pathlib import Path

from backend.app.intelligence.risk_units import build_risk_units
from backend.app.intelligence.capital_sizing import _consecutive_losses
import backend.app.intelligence.recovery_attribution as recovery


def trade(ticket, pl, *, chain=0, origin="FRESH_MARKET", level=0, active=False, epoch=35, t=1):
    row = {
        "ticket": ticket,
        "origin_guess": origin,
        "order_origin": origin,
        "entry_policy_epoch": epoch,
        "trading_mode": "SCALP",
        "max_hedge_level_observed": level,
        "chain_id": chain,
        "latest_position": {"chain_id": chain, "hedge_level": level},
        "initial_position": {"chain_id": chain, "hedge_level": level},
        "exact_realized_pl_available": not active,
        "realized_net_pl": pl if not active else None,
        "final_observed_net_pl_before_disappearance": pl if not active else None,
        "last_observed_net_pl": pl if active else None,
        "close_time_epoch": t if not active else 0,
    }
    return row


# Four genuine completed standalone losses already exist.
prior = [trade(100+i, -1.0, t=10+i) for i in range(4)]
root = trade(200, -1.59, chain=200, origin="FRESH_MARKET", level=0, t=20)
child_active = trade(201, 3.0, chain=200, origin="HEDGE_CHILD", level=1, active=True)
payload_active = {"closed": prior + [root], "active": [child_active]}
report = build_risk_units(payload_active)
chain = next(u for u in report["units"] if u["unit_type"] == "RECOVERY_CHAIN")
assert chain["state"] == "ACTIVE"
assert chain["root_ticket"] == 200
assert chain["eligible_for_loss_streak"] is False
assert report["consecutive_completed_loss_units"] == 4
assert _consecutive_losses(payload_active) == 4

# When the child eventually wins enough to recover the root, the whole chain is
# ONE win and resets the streak; the root loss never became a fifth loss.
child_win = trade(201, 4.00, chain=200, origin="HEDGE_CHILD", level=1, t=30)
payload_win = {"closed": prior + [root, child_win], "active": []}
report_win = build_risk_units(payload_win)
chain_win = next(u for u in report_win["units"] if u["unit_type"] == "RECOVERY_CHAIN")
assert chain_win["state"] == "COMPLETE"
assert chain_win["result_class"] == "WIN"
assert abs(chain_win["realized_net_pl"] - 2.41) < 1e-9
assert report_win["consecutive_completed_loss_units"] == 0

# If instead the final chain sum is negative, the chain contributes exactly one
# completed loss, so four earlier losses become a five-unit streak, not six.
child_loss = trade(201, 0.50, chain=200, origin="HEDGE_CHILD", level=1, t=30)
payload_loss = {"closed": prior + [root, child_loss], "active": []}
report_loss = build_risk_units(payload_loss)
chain_loss = next(u for u in report_loss["units"] if u["unit_type"] == "RECOVERY_CHAIN")
assert chain_loss["result_class"] == "LOSS"
assert report_loss["consecutive_completed_loss_units"] == 5

# Recovery attribution must recognize a normal FRESH_MARKET root whose ticket is
# the chain id, and must prefer authoritative realized P/L where available.
old_get = recovery.get_trade_outcomes
try:
    recovery.get_trade_outcomes = lambda **kwargs: payload_active
    attr = recovery.analyze_recovery_chains()
finally:
    recovery.get_trade_outcomes = old_get
assert attr["chains"][0]["root_ticket"] == 200
assert attr["chains"][0]["root_state"] == "CLOSED"
assert attr["chains"][0]["observed_closed_member_pl_sum"] == -1.59

mq5 = Path("external/nyao/nyao_scalper.mq5").read_text()
for required in (
    'nyao-recovery-risk-v2',
    'ComputeAtlasRecoveryChainBudgetUsd',
    'RECOVERY_RISK_BUDGET_EXHAUSTED',
    'RECOVERY_RISK_BUDGET_INFEASIBLE',
    'ATLAS_CHAIN_RISK_CAP',
    'return ComputeAtlasRecoveryChainBudgetUsd(chainId, recoveryPolicy, anchorLoss);',
    'recovery_chain_budget_usd',
    'recovery_estimated_adverse_risk_usd',
):
    assert required in mq5, required
assert '#property version "44.3"' in mq5

main = Path("backend/app/main.py").read_text()
assert '/api/v1/atlas/risk-units' in main
assert 'Risk-unit streak' in main
assert 'Recovery sizing' in main
assert 'only the final composite chain result can break or escalate the loss streak' in main

print("P3.30 composite risk-unit + recovery budget regression: PASS")
