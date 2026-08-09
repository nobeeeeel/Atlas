from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import DASHBOARD_TEMPLATE  # noqa: E402


def main() -> None:
    required = (
        'data-view="analysis"',
        'data-view="market"',
        'id="view-market"',
        'id="view-analysis"',
        'id="an-cost-badge"',
        'id="an-zone-status"',
        'id="an-scenarios"',
        'id="an-gemini-thesis"',
        'market:["Market Analysis"',
        'analysis:["Zone Analysis"',
        "Market Analysis",
        "Zone Analysis",
        'id="market-live-slot"',
        "LIVE ZONE WORKSPACE",
        "function renderAnalysis()",
        "renderAnalysis();renderPositions()",
        "TOO NARROW AFTER COSTS",
        "ORDINARY SCALP SUSPENDED",
        "Zone authority: ${esc(authority)}",
    )
    for marker in required:
        assert marker in DASHBOARD_TEMPLATE, marker
    assert DASHBOARD_TEMPLATE.count('id="view-analysis"') == 1
    assert DASHBOARD_TEMPLATE.count('id="view-market"') == 1
    assert 'id="analysis-live-slot"' not in DASHBOARD_TEMPLATE
    assert "Zone authority: NOT ACTIVE" not in DASHBOARD_TEMPLATE
    print("P3.9 analysis dashboard checks passed.")


if __name__ == "__main__":
    main()
