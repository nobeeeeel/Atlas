from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.market_candles import (  # noqa: E402
    REQUIRED_TIMEFRAMES,
    build_market_candle_report,
)
from backend.app.main import DASHBOARD_TEMPLATE  # noqa: E402


def _bars(*, count: int, period: int, now_epoch: int) -> list[dict]:
    first = now_epoch - count * period
    return [
        {
            "time_epoch": first + index * period,
            "open": 100.0 + index,
            "high": 101.0 + index,
            "low": 99.0 + index,
            "close": 100.5 + index,
            "tick_volume": 1000 + index,
            "spread": 25,
            "real_volume": 0,
        }
        for index in range(count)
    ]


def _payload(now_epoch: int = 2_000_000_000) -> dict:
    return {
        "schema_version": "1.0",
        "symbol": "#BTCUSD",
        "generated_at_epoch": now_epoch,
        "closed_bars_only": True,
        "timeframes": {
            timeframe: {
                "period_seconds": requirement["period_seconds"],
                "requested_count": 160,
                "bar_count": 160,
                "bars": _bars(
                    count=160,
                    period=requirement["period_seconds"],
                    now_epoch=now_epoch,
                ),
            }
            for timeframe, requirement in REQUIRED_TIMEFRAMES.items()
        },
    }


def test_valid_export_is_ready() -> None:
    now_epoch = 2_000_000_000
    report = build_market_candle_report(
        _payload(now_epoch),
        source_path=Path("candles.json"),
        expected_symbol="#BTCUSD",
        now_epoch=now_epoch,
    )
    assert report["state"] == "READY"
    assert report["ready_for_zone_analysis"] is True
    assert report["blockers"] == []
    assert all(
        report["timeframes"][timeframe]["state"] == "READY"
        for timeframe in REQUIRED_TIMEFRAMES
    )


def test_invalid_ohlc_and_symbol_are_rejected() -> None:
    now_epoch = 2_000_000_000
    invalid = _payload(now_epoch)
    invalid["timeframes"]["M30"]["bars"][0]["high"] = 98.0
    report = build_market_candle_report(
        invalid,
        source_path=Path("candles.json"),
        expected_symbol="XAUUSD",
        now_epoch=now_epoch,
    )
    assert report["state"] == "INVALID"
    assert report["ready_for_zone_analysis"] is False
    assert any("OHLC validation" in item for item in report["blockers"])


def test_stale_or_incomplete_export_is_not_ready() -> None:
    now_epoch = 2_000_000_000
    incomplete = _payload(now_epoch - 600)
    incomplete["timeframes"].pop("H4")
    report = build_market_candle_report(
        incomplete,
        source_path=Path("candles.json"),
        expected_symbol="#BTCUSD",
        now_epoch=now_epoch,
    )
    assert report["state"] == "INCOMPLETE"
    assert report["ready_for_zone_analysis"] is False
    assert any("stale" in item.lower() for item in report["blockers"])
    assert any("H4" in item for item in report["blockers"])


def test_dashboard_and_nyao_export_contract() -> None:
    dashboard_markers = (
        'id="an-mtf-grid"',
        'id="an-stage-candles"',
        'id="an-stage-zone-engine"',
        "function loadMarketCandles()",
        'api("/api/v1/atlas/market-candles")',
        "CANDLES VALIDATED",
    )
    for marker in dashboard_markers:
        assert marker in DASHBOARD_TEMPLATE, marker

    nyao_source = (PROJECT_ROOT / "external/nyao/nyao_scalper.mq5").read_text(
        encoding="utf-8"
    )
    for marker in (
        "WriteAtlasMarketCandles()",
        "CopyRates(_Symbol, timeframe, 1, requestedCount, rates)",
        'atlasCandlesFile = atlasBridgeRoot + "\\\\candles.json"',
        "PERIOD_M30",
        "PERIOD_H1",
        "PERIOD_H4",
    ):
        assert marker in nyao_source, marker


if __name__ == "__main__":
    test_valid_export_is_ready()
    test_invalid_ohlc_and_symbol_are_rejected()
    test_stale_or_incomplete_export_is_not_ready()
    test_dashboard_and_nyao_export_contract()
    print("P3.10 multi-timeframe candle foundation checks passed.")
