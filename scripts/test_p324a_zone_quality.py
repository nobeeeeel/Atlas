from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.intelligence.zone_engine import (  # noqa: E402
    ENGINE_VERSION,
    MAX_WIDTH_ATR,
    SAME_SIDE_OVERLAP_COLLAPSE_RATIO,
    _candidate,
    _rank_and_deduplicate,
)


def bars() -> list[dict]:
    return [
        {
            "time_epoch": 1_000 + i * 60,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
        }
        for i in range(20)
    ]


def test_overbroad_zone_is_rejected_without_shrinking() -> None:
    result = _candidate(
        timeframe="H4",
        kind="ORDER_BLOCK",
        side="SUPPLY",
        low=100.0,
        high=115.0,
        created_index=10,
        bars=bars(),
        atr=10.0,
        evidence=["synthetic"],
    )
    assert result is None
    assert MAX_WIDTH_ATR["ORDER_BLOCK"] == 1.35


def test_valid_zone_keeps_original_geometry() -> None:
    result = _candidate(
        timeframe="H4",
        kind="ORDER_BLOCK",
        side="SUPPLY",
        low=100.0,
        high=110.0,
        created_index=10,
        bars=bars(),
        atr=10.0,
        evidence=["synthetic"],
    )
    assert result is not None
    assert result["low"] == 100.0
    assert result["high"] == 110.0
    assert result["width_atr"] == 1.0


def zone(zone_id: str, low: float, high: float, score: float, *, tf: str, kind: str) -> dict:
    return {
        "zone_id": zone_id,
        "timeframe": tf,
        "kind": kind,
        "side": "SUPPLY",
        "low": low,
        "high": high,
        "mid": (low + high) / 2,
        "created_at_epoch": 2_000,
        "age_bars": 1,
        "status": "FRESH",
        "score": score,
        "width_atr": 0.5,
        "confluence": [],
        "absorbed_zone_count": 0,
        "evidence": ["synthetic"],
    }


def test_redundant_same_side_overlap_collapses_to_best_representative() -> None:
    primary = zone("primary", 100.0, 110.0, 90.0, tf="H4", kind="ORDER_BLOCK")
    redundant = zone("redundant", 102.0, 109.0, 80.0, tf="H1", kind="FVG")
    result = _rank_and_deduplicate([primary, redundant], current_price=105.0)
    assert len(result) == 1
    assert result[0]["zone_id"] == "primary"
    assert result[0]["absorbed_zone_count"] == 1
    assert "H1 FVG" in result[0]["confluence"]
    assert SAME_SIDE_OVERLAP_COLLAPSE_RATIO == 0.68


if __name__ == "__main__":
    assert ENGINE_VERSION == "deterministic-zone-v0.2"
    test_overbroad_zone_is_rejected_without_shrinking()
    test_valid_zone_keeps_original_geometry()
    test_redundant_same_side_overlap_collapses_to_best_representative()
    print("P3.24A zone-quality checks passed.")
