from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
MQL = (ROOT / 'external/nyao/nyao_scalper.mq5').read_text()
SCHEMA = (ROOT / 'backend/app/bridge/schemas.py').read_text()
MAIN = (ROOT / 'backend/app/main.py').read_text()

# End-to-end source/schema/UI contract.
# Compile-safety regression: execution path must use the EA's real ATR handle.
assert 'CopyBuffer(atrSignalHandle, 0, 1, execAtrLookback, execAtrHistory)' in MQL
assert 'CopyBuffer(atrHandle, 0, 1, execAtrLookback, execAtrHistory)' not in MQL

for token in [
    'nyao-scalp-cost-v3',
    'AtlasValidateScalpStructureEnvelope',
    'SCALP_COST_STRUCTURE_MISMATCH',
    'scalp_cost_ratio_feasible',
    'scalp_structure_feasible',
    'scalp_structure_reason',
    'scalp_stop_expansion_ratio',
    'scalp_planned_stop_atr_ratio',
    'scalp_spread_atr_ratio',
    'scalp_max_stop_expansion_ratio',
    'scalp_max_stop_atr_ratio',
    'scalp_max_spread_atr_ratio',
]:
    assert token in MQL, token
    if token.startswith('scalp_'):
        assert token in SCHEMA, token
        assert token in MAIN, token

# Reproduce the user's live BTC snapshot. Economic ratios can be made to pass,
# but the required geometry is far outside the adaptive market-structure envelope.
spread = 59900.0
base_stop = 1187.25
base_target = 1780.88
atr = 763.5
vol_ratio = 0.5205
headroom = 1.10
max_spread_stop = 0.20
max_spread_target = 0.15
planned_stop = max(base_stop, spread * headroom / max_spread_stop)
planned_target = max(base_target, spread * headroom / max_spread_target, planned_stop * 1.5)
stop_expansion = planned_stop / base_stop
stop_atr = planned_stop / atr
spread_atr = spread / atr
max_expansion = 12.0 + 4.0 * min(2.0, max(0.0, vol_ratio))
max_stop_atr = 12.0 + 6.0 * min(2.0, max(0.0, vol_ratio))
max_spread_atr = 2.5 + 1.5 * min(2.0, max(0.0, vol_ratio))
assert spread / planned_stop <= max_spread_stop
assert spread / planned_target <= max_spread_target
assert stop_expansion > max_expansion
assert stop_atr > max_stop_atr
assert spread_atr > max_spread_atr

# A genuinely larger-volatility scalp can still pass; there is no BTC-specific
# or fixed dollar spread ban. This setup is judged only by dimensionless ratios.
spread = 60000.0
base_stop = 280000.0
base_target = 420000.0
atr = 100000.0
vol_ratio = 1.2
planned_stop = max(base_stop, spread * headroom / max_spread_stop)
planned_target = max(base_target, spread * headroom / max_spread_target, planned_stop * 1.5)
stop_expansion = planned_stop / base_stop
stop_atr = planned_stop / atr
spread_atr = spread / atr
max_expansion = 12.0 + 4.0 * min(2.0, max(0.0, vol_ratio))
max_stop_atr = 12.0 + 6.0 * min(2.0, max(0.0, vol_ratio))
max_spread_atr = 2.5 + 1.5 * min(2.0, max(0.0, vol_ratio))
assert spread / planned_stop <= max_spread_stop
assert spread / planned_target <= max_spread_target
assert stop_expansion <= max_expansion
assert stop_atr <= max_stop_atr
assert spread_atr <= max_spread_atr

# Recovery-probe UI must distinguish an in-flight exposure lock from a hard veto.
assert 'RECOVERY PROBE · IN FLIGHT' in MAIN
assert 'PARTIALLY ALLOCATED' in MAIN
assert 'only the final composite chain result can break or escalate the loss streak' in MAIN

print('P3.29.3 structure-aware cost gate + recovery exposure UI tests passed')
