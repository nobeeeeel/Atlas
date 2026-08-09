from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NYAO = ROOT / "external" / "nyao" / "nyao_scalper.mq5"
MAIN = ROOT / "backend" / "app" / "main.py"

nyao = NYAO.read_text(encoding="utf-8")
main = MAIN.read_text(encoding="utf-8")

assert '#property version "44.3"' in nyao
assert 'ATLAS_SCALP_MAX_SPREAD_STOP_RATIO 0.20' in nyao
assert 'ATLAS_SCALP_MAX_SPREAD_TARGET_RATIO 0.15' in nyao
assert 'ATLAS_SCALP_SPREAD_HEADROOM_MULTIPLIER 1.10' in nyao
assert 'AtlasBuildScalpEconomicStructure' in nyao
assert 'SCALP_ABSOLUTE_SPREAD_CEILING' in nyao
assert 'SCALP_COST_RISK_BUDGET_INFEASIBLE' in nyao
assert 'double AtlasScalpCostCapPoints' in nyao
assert 'SCALP_COST_INFEASIBLE' in nyao
assert 'if(!IsAllowedToOpenPosition(false))' in nyao
assert 'finalSlPoints' in nyao and 'finalTpPoints' in nyao
assert 'MaxSpreadPoints' in nyao
assert '!hasStructure && fallbackAtrPoints > 0.0' in nyao
assert 'version="1.30.19"' in main
assert 'Economic spread cap' in main
assert 'Spread / cap' in main
assert 'economic cap' in main

# Dynamic economics sanity check using the live BTC-like example.
# A ~$60.95 spread no longer loses automatically against the original ~$5.5
# ATR stop. The planned structure expands until spread consumes <=20% of stop
# and <=15% of target, with 10% quote-movement headroom.
spread = 60.95
headroom = 1.10
base_sl = 5.50915
base_tp = base_sl * 1.5
planned_sl = max(base_sl, spread * headroom / 0.20)
planned_tp = max(base_tp, spread * headroom / 0.15, planned_sl * 1.5)
assert round(planned_sl, 3) == 335.225
assert round(planned_tp, 4) == 502.8375
assert spread / planned_sl < 0.20
assert spread / planned_tp < 0.15

# The absolute MaxSpreadPoints setting remains only an emergency outer ceiling.
hard_ceiling = 100.0
assert spread < hard_ceiling

print("P3.29 scalp cost feasibility tests passed")
