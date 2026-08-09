from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


SCHEMA_VERSION = "1.0"
REQUIRED_TIMEFRAMES: dict[str, dict[str, int]] = {
    "M30": {"period_seconds": 30 * 60, "minimum_bars": 100},
    "H1": {"period_seconds": 60 * 60, "minimum_bars": 100},
    "H4": {"period_seconds": 4 * 60 * 60, "minimum_bars": 90},
}
MAX_EXPORT_AGE_SECONDS = 180


class CandleBar(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    time_epoch: int = Field(gt=0)
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    tick_volume: int = Field(default=0, ge=0)
    spread: int = Field(default=0, ge=0)
    real_volume: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "CandleBar":
        values = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("OHLC values must be finite.")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("High must be greater than or equal to O/L/C.")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Low must be less than or equal to O/H/C.")
        return self


class CandleSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_seconds: int = Field(gt=0)
    requested_count: int = Field(gt=0, le=1000)
    bar_count: int = Field(ge=0, le=1000)
    bars: list[CandleBar] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_count_and_order(self) -> "CandleSeries":
        if self.bar_count != len(self.bars):
            raise ValueError("bar_count must equal the number of bars.")
        times = [bar.time_epoch for bar in self.bars]
        if any(current <= previous for previous, current in zip(times, times[1:])):
            raise ValueError("Bars must be strictly ordered oldest to newest.")
        return self


class MarketCandleExport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    symbol: str = Field(min_length=1, max_length=120)
    generated_at_epoch: int = Field(gt=0)
    closed_bars_only: bool
    timeframes: dict[str, CandleSeries]


def _waiting_report(source_path: Path) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "WAITING_FOR_NYAO_EXPORT",
        "ready_for_zone_analysis": False,
        "source_path": str(source_path),
        "symbol": None,
        "generated_at_epoch": None,
        "export_age_seconds": None,
        "required_timeframes": list(REQUIRED_TIMEFRAMES),
        "timeframes": {
            timeframe: {
                "state": "WAITING",
                "bar_count": 0,
                "minimum_bars": requirement["minimum_bars"],
                "period_seconds": requirement["period_seconds"],
                "latest_closed_at_epoch": None,
                "latest_bar_age_seconds": None,
            }
            for timeframe, requirement in REQUIRED_TIMEFRAMES.items()
        },
        "blockers": [
            "Nyao has not exported symbol-scoped multi-timeframe candles yet."
        ],
        "warnings": [],
    }


def load_market_candle_export(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "Candle export root must be a JSON object."
    return payload, None


def build_market_candle_report(
    payload: dict[str, Any] | None,
    *,
    source_path: Path,
    expected_symbol: str | None = None,
    now_epoch: int | None = None,
    include_bars: bool = False,
    read_error: str | None = None,
) -> dict[str, Any]:
    if payload is None and read_error is None:
        return _waiting_report(source_path)

    if read_error is not None:
        return {
            **_waiting_report(source_path),
            "state": "INVALID",
            "blockers": [f"Candle export could not be read: {read_error}"],
        }

    try:
        export = MarketCandleExport.model_validate(payload)
    except ValidationError as exc:
        return {
            **_waiting_report(source_path),
            "state": "INVALID",
            "blockers": [
                "Candle export failed schema or OHLC validation.",
                *[
                    f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                    for error in exc.errors()[:12]
                ],
            ],
        }

    current_epoch = int(now_epoch if now_epoch is not None else time.time())
    export_age = max(0, current_epoch - export.generated_at_epoch)
    blockers: list[str] = []
    warnings: list[str] = []
    summaries: dict[str, Any] = {}

    if export.schema_version != SCHEMA_VERSION:
        blockers.append(
            f"Unsupported candle schema {export.schema_version}; expected {SCHEMA_VERSION}."
        )
    if expected_symbol and export.symbol != expected_symbol:
        blockers.append(
            f"Candle symbol {export.symbol} does not match selected symbol {expected_symbol}."
        )
    if not export.closed_bars_only:
        blockers.append("Candle export includes an open/incomplete bar.")
    if export_age > MAX_EXPORT_AGE_SECONDS:
        blockers.append(
            f"Candle export is stale ({export_age}s old; maximum {MAX_EXPORT_AGE_SECONDS}s)."
        )

    for timeframe, requirement in REQUIRED_TIMEFRAMES.items():
        series = export.timeframes.get(timeframe)
        if series is None:
            blockers.append(f"Required timeframe {timeframe} is missing.")
            summaries[timeframe] = {
                "state": "MISSING",
                "bar_count": 0,
                "minimum_bars": requirement["minimum_bars"],
                "period_seconds": requirement["period_seconds"],
                "latest_closed_at_epoch": None,
                "latest_bar_age_seconds": None,
            }
            continue

        tf_blockers: list[str] = []
        if series.period_seconds != requirement["period_seconds"]:
            tf_blockers.append(
                f"period is {series.period_seconds}s, expected {requirement['period_seconds']}s"
            )
        if series.bar_count < requirement["minimum_bars"]:
            tf_blockers.append(
                f"only {series.bar_count} bars, need {requirement['minimum_bars']}"
            )

        latest = series.bars[-1] if series.bars else None
        latest_closed_at = (
            latest.time_epoch + series.period_seconds if latest is not None else None
        )
        latest_age = (
            max(0, current_epoch - latest_closed_at)
            if latest_closed_at is not None
            else None
        )
        if latest_closed_at is not None and latest_closed_at > export.generated_at_epoch:
            tf_blockers.append("latest bar was not closed when the export was generated")

        if latest_age is not None:
            allowed_history_lag = max(6 * 60 * 60, series.period_seconds * 3)
            if latest_age > allowed_history_lag:
                warnings.append(
                    f"{timeframe} latest closed bar is {latest_age}s old; market may be closed or history stale."
                )

        if tf_blockers:
            blockers.extend(f"{timeframe}: {message}." for message in tf_blockers)

        summary: dict[str, Any] = {
            "state": "READY" if not tf_blockers else "INCOMPLETE",
            "bar_count": series.bar_count,
            "minimum_bars": requirement["minimum_bars"],
            "period_seconds": series.period_seconds,
            "first_bar_epoch": series.bars[0].time_epoch if series.bars else None,
            "last_bar_epoch": latest.time_epoch if latest is not None else None,
            "latest_closed_at_epoch": latest_closed_at,
            "latest_bar_age_seconds": latest_age,
        }
        if include_bars:
            summary["bars"] = [bar.model_dump(mode="json") for bar in series.bars]
        summaries[timeframe] = summary

    ready = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "READY" if ready else "INCOMPLETE",
        "ready_for_zone_analysis": ready,
        "source_path": str(source_path),
        "symbol": export.symbol,
        "generated_at_epoch": export.generated_at_epoch,
        "export_age_seconds": export_age,
        "closed_bars_only": export.closed_bars_only,
        "required_timeframes": list(REQUIRED_TIMEFRAMES),
        "timeframes": summaries,
        "blockers": blockers,
        "warnings": warnings,
    }
