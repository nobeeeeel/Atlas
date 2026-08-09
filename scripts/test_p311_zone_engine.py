from __future__ import annotations

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.zone_engine import build_zone_map  # noqa: E402
from backend.app.main import DASHBOARD_TEMPLATE  # noqa: E402


def _bars(period: int, count: int = 160) -> list[dict]:
    start = 2_000_000_000 - count * period
    bars: list[dict] = []
    for index in range(count):
        center = 100.0 + math.sin(index / 3.0) * 2.0 + index * 0.01
        open_price = center - 0.3
        close = center + 0.3
        bars.append({
            "time_epoch": start + index * period,
            "open": open_price,
            "high": center + 1.0,
            "low": center - 1.0,
            "close": close,
            "tick_volume": 1000 + index,
            "spread": 20,
            "real_volume": 0,
        })

    # Closed-candle bullish displacement and an unfilled bullish FVG.
    bars[150].update(open=103.0, high=103.5, low=101.5, close=102.0)
    bars[151].update(open=102.0, high=110.0, low=101.8, close=109.5)
    bars[152].update(open=111.0, high=112.0, low=110.5, close=111.5)
    for index in range(153, count):
        base = 112.0 + (index - 153) * 0.2
        bars[index].update(open=base, high=base + 1.0, low=base - 0.5, close=base + 0.4)
    return bars


def _report() -> dict:
    periods = {"M30": 1800, "H1": 3600, "H4": 14400}
    timeframes = {}
    for timeframe, period in periods.items():
        bars = _bars(period)
        timeframes[timeframe] = {
            "state": "READY",
            "bar_count": len(bars),
            "minimum_bars": 90,
            "period_seconds": period,
            "bars": bars,
        }
    return {
        "state": "READY",
        "ready_for_zone_analysis": True,
        "symbol": "TESTUSD",
        "generated_at_epoch": 2_000_000_000,
        "timeframes": timeframes,
        "blockers": [],
    }


def test_zone_map_is_deterministic_and_analysis_only() -> None:
    first = build_zone_map(_report())
    second = build_zone_map(_report())
    assert first["state"] == "DETECTED_NOT_ACTIVATED"
    assert first["zone_authority_active"] is False
    assert first["map_id"] == second["map_id"]
    assert first["zone_count"] > 0
    assert any(zone["kind"] == "FVG" for zone in first["zones"])
    assert any(zone["side"] == "DEMAND" for zone in first["zones"])
    assert len(first["scenarios"]) == 2
    assert all(item["price_basis"] == "LATEST_CLOSED_M30" for item in first["scenarios"])
    assert first["chart"]["timeframe"] == "M30"
    assert first["chart"]["bar_count"] == 96
    assert first["current_price_basis"] == "LATEST_CLOSED_M30"
    assert first["current_price_is_live"] is False
    assert len(first["chart"]["bars"]) == 96
    assert all("conditions" in scenario for scenario in first["scenarios"])
    assert all(
        zone["price_relation"] in {"ABOVE", "INSIDE", "BELOW"}
        for zone in first["zones"]
    )


def test_zone_map_waits_for_validated_candles() -> None:
    result = build_zone_map({
        "ready_for_zone_analysis": False,
        "symbol": "TESTUSD",
        "blockers": ["H4 missing"],
    })
    assert result["state"] == "WAITING_FOR_VALIDATED_CANDLES"
    assert result["zones"] == []
    assert result["zone_authority_active"] is False


def test_dashboard_zone_map_contract() -> None:
    for marker in (
        'id="an-zone-list"',
        'id="an-zone-scenario-list"',
        'id="an-zone-stats"',
        'id="an-zone-chart"',
        "function renderZoneChart(zoneMap,livePrice=null)",
        "M30 PRICE · PRIORITY MTF ZONES",
        "function loadZoneMap()",
        'api("/api/v1/atlas/zone-map")',
        "ZONE MAP DETECTED",
        "Live MT5 bid",
    ):
        assert marker in DASHBOARD_TEMPLATE, marker


if __name__ == "__main__":
    test_zone_map_is_deterministic_and_analysis_only()
    test_zone_map_waits_for_validated_candles()
    test_dashboard_zone_map_contract()
    print("P3.11 deterministic zone engine checks passed.")
