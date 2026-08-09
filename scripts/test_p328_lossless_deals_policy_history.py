from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
outcomes = (ROOT / "backend/app/intelligence/outcomes.py").read_text(encoding="utf-8")
auto = (ROOT / "backend/app/intelligence/autonomous_policy.py").read_text(encoding="utf-8")
mql = (ROOT / "external/nyao/nyao_scalper.mq5").read_text(encoding="utf-8")

ast.parse(main)
ast.parse(outcomes)
ast.parse(auto)

required_outcomes = [
    "OUTCOME_VERSION = 5",
    "_reconstruct_closed_trade_from_exit_deal",
    "reconstructed_closed_tickets",
    "deferred_exit_deal_tickets",
    "AUTHORITATIVE_MT5_FINAL_EXIT_DEAL_RECONSTRUCTION",
]
for marker in required_outcomes:
    assert marker in outcomes, marker

required_mql = [
    '#property version "44.3"',
    "AtlasRefreshRecentExitDealsFromHistory",
    "AtlasPopulateExitEntryMetadata",
    "entry_policy_epoch",
    "original_position_type",
]
for marker in required_mql:
    assert marker in mql, marker

required_policy = [
    "baseline_command_version",
    "baseline_policy_epoch",
    "command_readback_patch",
]
for marker in required_policy:
    assert marker in auto, marker

required_main = [
    'version="1.30.19"',
    "/api/v1/atlas/autonomous-policy-applications",
    "Current active policy",
    "Applied policy history",
    "RUNTIME_CONFIRMED",
    "RUNTIME_MISMATCH",
]
for marker in required_main:
    assert marker in main, marker

# The embedded dashboard JavaScript should remain syntactically extractable.
module = ast.parse(main)
template = None
for node in module.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "DASHBOARD_TEMPLATE"
        for target in node.targets
    ):
        template = ast.literal_eval(node.value)
        break
assert template and "applied-policy-history" in template
assert re.search(r"function\s+renderAtlas\s*\(", template)

print("P3.28 lossless deals + applied policy history static tests passed")
