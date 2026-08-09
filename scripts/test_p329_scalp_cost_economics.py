from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
nyao = (ROOT / 'external/nyao/nyao_scalper.mq5').read_text(encoding='utf-8')
main = (ROOT / 'backend/app/main.py').read_text(encoding='utf-8')

assert '#property version "44.3"' in nyao
assert 'ATLAS_SCALP_MAX_SPREAD_STOP_RATIO 0.20' in nyao
assert 'ATLAS_SCALP_MAX_SPREAD_TARGET_RATIO 0.15' in nyao
assert 'ATLAS_SCALP_SPREAD_HEADROOM_MULTIPLIER 1.10' in nyao
assert 'bool AtlasBuildScalpEconomicStructure' in nyao
assert 'SCALP_COST_RISK_BUDGET_INFEASIBLE' in nyao
assert 'nyao-scalp-cost-v3' in nyao
assert 'double AtlasScalpCostCapPoints' in nyao
assert 'if(!hasStructure && fallbackAtrPoints > 0.0 && MaxSpreadATRRatio > 0.0)' in nyao
assert 'SCALP_COST_INFEASIBLE' in nyao
assert 'scalp_cost_gate_version' in nyao
assert 'scalp_planned_stop_points' in nyao
assert 'scalp_planned_target_points' in nyao
assert 'scalp_spread_to_stop_ratio' in nyao
assert 'scalp_spread_to_target_ratio' in nyao

assert 'version="1.30.19"' in main
assert 'Economic spread cap' in main
assert 'Spread / cap' in main
assert 'scalp_planned_stop_points' in main
assert 'scalp_spread_to_target_ratio' in main

print('P3.29 scalp transaction-cost economics tests passed')
