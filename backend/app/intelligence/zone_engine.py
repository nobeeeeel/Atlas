from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any


ENGINE_VERSION = "deterministic-zone-v0.2"
TIMEFRAME_WEIGHT = {"M30": 15.0, "H1": 25.0, "H4": 35.0}
KIND_WEIGHT = {"FVG": 18.0, "ORDER_BLOCK": 20.0, "SUPPORT_RESISTANCE": 16.0}

# P3.24A zone-quality guardrails. A zone that spans too much of its local ATR
# stops being a useful location hypothesis and becomes a broad price region.
# Reject it rather than silently shrinking its technical boundaries.
MAX_WIDTH_ATR = {
    "FVG": 1.25,
    "ORDER_BLOCK": 1.35,
    "SUPPORT_RESISTANCE": 0.80,
}
SAME_SIDE_OVERLAP_COLLAPSE_RATIO = 0.68


def _true_range(current: dict[str, Any], previous_close: float | None) -> float:
    high = float(current["high"])
    low = float(current["low"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def _atr(bars: list[dict[str, Any]], end: int | None = None, period: int = 14) -> float:
    stop = len(bars) if end is None else max(1, min(len(bars), end + 1))
    start = max(0, stop - period)
    values: list[float] = []
    for index in range(start, stop):
        previous_close = float(bars[index - 1]["close"]) if index > 0 else None
        values.append(_true_range(bars[index], previous_close))
    return sum(values) / len(values) if values else 0.0


def _swings(bars: list[dict[str, Any]], window: int = 2) -> tuple[list[dict], list[dict]]:
    highs: list[dict] = []
    lows: list[dict] = []
    for index in range(window, len(bars) - window):
        bar = bars[index]
        neighbours = bars[index - window:index] + bars[index + 1:index + window + 1]
        high = float(bar["high"])
        low = float(bar["low"])
        if all(high > float(item["high"]) for item in neighbours):
            highs.append({"index": index, "price": high, "time_epoch": int(bar["time_epoch"])})
        if all(low < float(item["low"]) for item in neighbours):
            lows.append({"index": index, "price": low, "time_epoch": int(bar["time_epoch"])})
    return highs, lows


def _market_structure(bars: list[dict[str, Any]]) -> dict[str, Any]:
    swing_highs, swing_lows = _swings(bars)
    recent_highs = swing_highs[-2:]
    recent_lows = swing_lows[-2:]
    direction = "RANGE_OR_UNCLEAR"
    if len(recent_highs) == 2 and len(recent_lows) == 2:
        higher_high = recent_highs[-1]["price"] > recent_highs[-2]["price"]
        higher_low = recent_lows[-1]["price"] > recent_lows[-2]["price"]
        lower_high = recent_highs[-1]["price"] < recent_highs[-2]["price"]
        lower_low = recent_lows[-1]["price"] < recent_lows[-2]["price"]
        if higher_high and higher_low:
            direction = "BULLISH"
        elif lower_high and lower_low:
            direction = "BEARISH"

    close = float(bars[-1]["close"])
    event = "NONE"
    reference_price: float | None = None
    if swing_highs and close > swing_highs[-1]["price"]:
        event = "BULLISH_BREAK_OF_STRUCTURE"
        reference_price = swing_highs[-1]["price"]
    elif swing_lows and close < swing_lows[-1]["price"]:
        event = "BEARISH_BREAK_OF_STRUCTURE"
        reference_price = swing_lows[-1]["price"]

    return {
        "direction": direction,
        "event": event,
        "reference_price": reference_price,
        "last_close": close,
        "recent_swing_highs": recent_highs,
        "recent_swing_lows": recent_lows,
    }


def _zone_status(
    bars: list[dict[str, Any]],
    *,
    created_index: int,
    side: str,
    low: float,
    high: float,
) -> str:
    touched = False
    for bar in bars[created_index + 1:]:
        close = float(bar["close"])
        if side == "DEMAND" and close < low:
            return "INVALIDATED"
        if side == "SUPPLY" and close > high:
            return "INVALIDATED"
        if float(bar["low"]) <= high and float(bar["high"]) >= low:
            touched = True
    return "MITIGATED" if touched else "FRESH"


def _candidate(
    *,
    timeframe: str,
    kind: str,
    side: str,
    low: float,
    high: float,
    created_index: int,
    bars: list[dict[str, Any]],
    atr: float,
    evidence: list[str],
) -> dict[str, Any] | None:
    if not all(math.isfinite(value) for value in (low, high)) or low <= 0 or high <= low:
        return None
    status = _zone_status(
        bars,
        created_index=created_index,
        side=side,
        low=low,
        high=high,
    )
    if status == "INVALIDATED":
        return None

    age_bars = len(bars) - 1 - created_index
    width_atr = (high - low) / atr if atr > 0 else None
    max_width_atr = MAX_WIDTH_ATR.get(kind, 1.25)
    if width_atr is not None and width_atr > max_width_atr:
        return None

    score = TIMEFRAME_WEIGHT[timeframe] + KIND_WEIGHT[kind]
    score += max(0.0, 15.0 - age_bars * 0.18)
    score += 7.0 if status == "FRESH" else 2.0
    # Narrower zones are more actionable locations. Penalize broad-but-still-valid
    # zones before they reach the hard rejection boundary.
    if width_atr is not None and width_atr > 0.70:
        score -= min(10.0, (width_atr - 0.70) * 8.0)

    raw_id = f"{timeframe}|{kind}|{side}|{low:.8f}|{high:.8f}|{bars[created_index]['time_epoch']}"
    return {
        "zone_id": hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:16],
        "timeframe": timeframe,
        "kind": kind,
        "side": side,
        "low": round(low, 8),
        "high": round(high, 8),
        "mid": round((low + high) / 2.0, 8),
        "created_at_epoch": int(bars[created_index]["time_epoch"]),
        "age_bars": age_bars,
        "status": status,
        "score": round(max(0.0, min(100.0, score)), 1),
        "width_atr": round(width_atr, 3) if width_atr is not None else None,
        "max_width_atr": max_width_atr,
        "width_quality": (
            "TIGHT" if width_atr is not None and width_atr <= 0.70
            else "ACCEPTABLE"
        ),
        "confluence": [],
        "absorbed_zone_count": 0,
        "evidence": evidence,
    }


def _detect_fvgs(timeframe: str, bars: list[dict[str, Any]], atr: float) -> list[dict]:
    zones: list[dict] = []
    for index in range(max(2, len(bars) - 100), len(bars)):
        left = bars[index - 2]
        current = bars[index]
        local_atr = _atr(bars, index) or atr
        minimum_gap = local_atr * 0.08
        bullish_gap = float(current["low"]) - float(left["high"])
        bearish_gap = float(left["low"]) - float(current["high"])
        if bullish_gap >= minimum_gap:
            zone = _candidate(
                timeframe=timeframe,
                kind="FVG",
                side="DEMAND",
                low=float(left["high"]),
                high=float(current["low"]),
                created_index=index,
                bars=bars,
                atr=local_atr,
                evidence=[
                    "Three-candle bullish fair-value gap.",
                    f"Gap size {bullish_gap / local_atr:.2f} ATR.",
                ],
            )
            if zone:
                zones.append(zone)
        if bearish_gap >= minimum_gap:
            zone = _candidate(
                timeframe=timeframe,
                kind="FVG",
                side="SUPPLY",
                low=float(current["high"]),
                high=float(left["low"]),
                created_index=index,
                bars=bars,
                atr=local_atr,
                evidence=[
                    "Three-candle bearish fair-value gap.",
                    f"Gap size {bearish_gap / local_atr:.2f} ATR.",
                ],
            )
            if zone:
                zones.append(zone)
    return zones


def _detect_order_blocks(timeframe: str, bars: list[dict[str, Any]], atr: float) -> list[dict]:
    zones: list[dict] = []
    for index in range(max(7, len(bars) - 100), len(bars)):
        bar = bars[index]
        open_price = float(bar["open"])
        close = float(bar["close"])
        local_atr = _atr(bars, index) or atr
        body = abs(close - open_price)
        previous = bars[index - 6:index]
        bullish_break = close > open_price and close > max(float(item["high"]) for item in previous)
        bearish_break = close < open_price and close < min(float(item["low"]) for item in previous)
        if body < local_atr * 0.9:
            continue

        if bullish_break:
            for source_index in range(index - 1, max(-1, index - 6), -1):
                source = bars[source_index]
                if float(source["close"]) < float(source["open"]):
                    zone = _candidate(
                        timeframe=timeframe,
                        kind="ORDER_BLOCK",
                        side="DEMAND",
                        low=float(source["low"]),
                        high=float(source["open"]),
                        created_index=source_index,
                        bars=bars,
                        atr=local_atr,
                        evidence=[
                            "Last bearish candle before bullish displacement.",
                            "Displacement closed above the prior six-bar high.",
                        ],
                    )
                    if zone:
                        zones.append(zone)
                    break
        elif bearish_break:
            for source_index in range(index - 1, max(-1, index - 6), -1):
                source = bars[source_index]
                if float(source["close"]) > float(source["open"]):
                    zone = _candidate(
                        timeframe=timeframe,
                        kind="ORDER_BLOCK",
                        side="SUPPLY",
                        low=float(source["open"]),
                        high=float(source["high"]),
                        created_index=source_index,
                        bars=bars,
                        atr=local_atr,
                        evidence=[
                            "Last bullish candle before bearish displacement.",
                            "Displacement closed below the prior six-bar low.",
                        ],
                    )
                    if zone:
                        zones.append(zone)
                    break
    return zones


def _cluster_levels(points: list[dict], tolerance: float) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for point in sorted(points, key=lambda item: item["price"]):
        if clusters:
            mean = sum(item["price"] for item in clusters[-1]) / len(clusters[-1])
            if abs(point["price"] - mean) <= tolerance:
                clusters[-1].append(point)
                continue
        clusters.append([point])
    return clusters


def _detect_support_resistance(
    timeframe: str,
    bars: list[dict[str, Any]],
    atr: float,
) -> list[dict]:
    zones: list[dict] = []
    swing_highs, swing_lows = _swings(bars)
    tolerance = max(atr * 0.18, float(bars[-1]["close"]) * 0.0002)
    for side, points in (("SUPPLY", swing_highs), ("DEMAND", swing_lows)):
        for cluster in _cluster_levels(points[-30:], tolerance):
            if len(cluster) < 2:
                continue
            level = sum(item["price"] for item in cluster) / len(cluster)
            created_index = max(item["index"] for item in cluster)
            zone = _candidate(
                timeframe=timeframe,
                kind="SUPPORT_RESISTANCE",
                side=side,
                low=level - tolerance,
                high=level + tolerance,
                created_index=created_index,
                bars=bars,
                atr=atr,
                evidence=[
                    f"{len(cluster)} confirmed pivot reactions clustered within {tolerance:.5f}.",
                    "Level is derived from repeated closed-candle structure.",
                ],
            )
            if zone:
                zone["touch_count"] = len(cluster)
                zone["score"] = round(min(100.0, zone["score"] + min(10, len(cluster) * 2)), 1)
                zones.append(zone)
    return zones


def _overlap(first: dict, second: dict) -> bool:
    return min(first["high"], second["high"]) >= max(first["low"], second["low"])


def _overlap_ratio(first: dict, second: dict) -> float:
    intersection = max(
        0.0,
        min(float(first["high"]), float(second["high"]))
        - max(float(first["low"]), float(second["low"])),
    )
    first_width = max(0.0, float(first["high"]) - float(first["low"]))
    second_width = max(0.0, float(second["high"]) - float(second["low"]))
    smaller = min(first_width, second_width)
    if smaller <= 0:
        return 0.0
    return intersection / smaller


def _rank_and_deduplicate(zones: list[dict], current_price: float) -> list[dict]:
    for zone in zones:
        confluence = sorted({
            f"{other['timeframe']} {other['kind']}"
            for other in zones
            if other["zone_id"] != zone["zone_id"]
            and other["side"] == zone["side"]
            and _overlap(zone, other)
        })
        zone["confluence"] = confluence
        zone["score"] = round(min(100.0, zone["score"] + min(18, len(confluence) * 6)), 1)
        zone["distance_from_price"] = round(
            0.0
            if zone["low"] <= current_price <= zone["high"]
            else min(abs(current_price - zone["low"]), abs(current_price - zone["high"])),
            8,
        )
        zone["price_relation"] = (
            "INSIDE"
            if zone["low"] <= current_price <= zone["high"]
            else "ABOVE"
            if current_price > zone["high"]
            else "BELOW"
        )

    ranked = sorted(
        zones,
        key=lambda item: (-item["score"], item["distance_from_price"], -item["created_at_epoch"]),
    )
    selected: list[dict] = []
    for zone in ranked:
        absorbed_by: dict | None = None
        for existing in selected:
            if existing["side"] != zone["side"]:
                continue
            same_detector = (
                existing["timeframe"] == zone["timeframe"]
                and existing["kind"] == zone["kind"]
                and _overlap(existing, zone)
            )
            strongly_redundant = (
                _overlap_ratio(existing, zone) >= SAME_SIDE_OVERLAP_COLLAPSE_RATIO
            )
            if same_detector or strongly_redundant:
                absorbed_by = existing
                break

        if absorbed_by is None:
            selected.append(zone)
            continue

        # The ranked zone remains the technical representative. Preserve the fact
        # that another detector/timeframe agreed without drawing another giant box.
        absorbed_by["absorbed_zone_count"] = int(
            absorbed_by.get("absorbed_zone_count") or 0
        ) + 1
        absorbed_label = f"{zone['timeframe']} {zone['kind']}"
        absorbed_by["confluence"] = sorted(
            set(absorbed_by.get("confluence") or []) | {absorbed_label}
        )

    demand = [item for item in selected if item["side"] == "DEMAND"][:4]
    supply = [item for item in selected if item["side"] == "SUPPLY"][:4]
    return sorted(demand + supply, key=lambda item: item["low"], reverse=True)


def _nearest(zones: list[dict], current_price: float, side: str) -> dict | None:
    candidates = [zone for zone in zones if zone["side"] == side]
    if side == "DEMAND":
        preferred = [zone for zone in candidates if zone["low"] <= current_price]
    else:
        preferred = [zone for zone in candidates if zone["high"] >= current_price]
    pool = preferred or candidates
    return min(pool, key=lambda item: item["distance_from_price"], default=None)


def _scenario(
    zone: dict | None,
    side: str,
    opposing: dict | None,
    current_price: float,
) -> dict[str, Any]:
    if zone is None:
        return {
            "side": side,
            "state": "NO_QUALIFIED_ZONE",
            "price_basis": "LATEST_CLOSED_M30",
            "reference_price": round(current_price, 8),
            "zone_id": None,
            "conditions": [],
            "invalidation": None,
            "first_opposing_zone": None,
        }
    demand = side == "BUY"
    at_zone = zone["low"] <= current_price <= zone["high"]
    return {
        "side": side,
        "state": "AT_ZONE_WAIT_FOR_CONFIRMATION" if at_zone else "WAIT_FOR_LOCATION_AND_CONFIRMATION",
        "price_basis": "LATEST_CLOSED_M30",
        "reference_price": round(current_price, 8),
        "zone_id": zone["zone_id"],
        "zone_low": zone["low"],
        "zone_high": zone["high"],
        "conditions": [
            (
                f"Price is inside the {zone['timeframe']} {zone['kind']} zone; do not enter without confirmation."
                if at_zone
                else f"Price trades into the {zone['timeframe']} {zone['kind']} zone."
            ),
            "Closed-candle rejection or lower-timeframe structure shift confirms direction.",
            "Spread and expected movement remain economically viable at entry time.",
        ],
        "invalidation": {
            "rule": "CLOSE_BELOW_ZONE" if demand else "CLOSE_ABOVE_ZONE",
            "price": zone["low"] if demand else zone["high"],
        },
        "first_opposing_zone": (
            {"zone_id": opposing["zone_id"], "low": opposing["low"], "high": opposing["high"]}
            if opposing is not None
            else None
        ),
    }


def build_zone_map(candle_report: dict[str, Any]) -> dict[str, Any]:
    if not candle_report.get("ready_for_zone_analysis"):
        return {
            "engine_version": ENGINE_VERSION,
            "state": "WAITING_FOR_VALIDATED_CANDLES",
            "zone_authority_active": False,
            "symbol": candle_report.get("symbol"),
            "map_id": None,
            "zones": [],
            "blockers": candle_report.get("blockers") or ["Validated candles are required."],
        }

    structures: dict[str, Any] = {}
    candidates: list[dict] = []
    source_signature: dict[str, Any] = {
        "symbol": candle_report.get("symbol"),
        "engine": ENGINE_VERSION,
        "timeframes": {},
    }
    current_price = 0.0
    chart_bars: list[dict[str, Any]] = []

    for timeframe in ("M30", "H1", "H4"):
        series = candle_report["timeframes"][timeframe]
        bars = series.get("bars") or []
        if not bars:
            continue
        timeframe_atr = _atr(bars)
        structures[timeframe] = {
            **_market_structure(bars),
            "atr": round(timeframe_atr, 8),
        }
        current_price = float(candle_report["timeframes"]["M30"]["bars"][-1]["close"])
        if timeframe == "M30":
            chart_bars = bars[-96:]
        candidates.extend(_detect_fvgs(timeframe, bars, timeframe_atr))
        candidates.extend(_detect_order_blocks(timeframe, bars, timeframe_atr))
        candidates.extend(_detect_support_resistance(timeframe, bars, timeframe_atr))
        source_signature["timeframes"][timeframe] = {
            "last_time": bars[-1]["time_epoch"],
            "last_close": bars[-1]["close"],
            "count": len(bars),
        }

    zones = _rank_and_deduplicate(candidates, current_price)
    direction_counts = Counter(
        item["direction"] for item in structures.values() if item["direction"] != "RANGE_OR_UNCLEAR"
    )
    composite_bias = direction_counts.most_common(1)[0][0] if direction_counts else "NEUTRAL"
    nearest_demand = _nearest(zones, current_price, "DEMAND")
    nearest_supply = _nearest(zones, current_price, "SUPPLY")
    map_id = hashlib.sha256(
        json.dumps(source_signature, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]

    return {
        "schema_version": "1.0",
        "engine_version": ENGINE_VERSION,
        "state": "DETECTED_NOT_ACTIVATED",
        "zone_authority_active": False,
        "symbol": candle_report.get("symbol"),
        "map_id": map_id,
        "as_of_epoch": candle_report.get("generated_at_epoch"),
        "current_price": round(current_price, 8),
        "current_price_basis": "LATEST_CLOSED_M30",
        "current_price_is_live": False,
        "chart": {
            "timeframe": "M30",
            "bars": chart_bars,
            "bar_count": len(chart_bars),
        },
        "composite_bias": composite_bias,
        "market_structure": structures,
        "zone_count": len(zones),
        "zones": zones,
        "nearest_demand": nearest_demand,
        "nearest_supply": nearest_supply,
        "scenarios": [
            _scenario(nearest_demand, "BUY", nearest_supply, current_price),
            _scenario(nearest_supply, "SELL", nearest_demand, current_price),
        ],
        "detector_counts": dict(Counter(zone["kind"] for zone in zones)),
        "quality": {
            "max_width_atr": MAX_WIDTH_ATR,
            "same_side_overlap_collapse_ratio": SAME_SIDE_OVERLAP_COLLAPSE_RATIO,
            "absorbed_overlap_count": sum(
                int(zone.get("absorbed_zone_count") or 0) for zone in zones
            ),
            "policy": "REJECT_OVERBROAD_AND_COLLAPSE_REDUNDANT_SAME_SIDE_ZONES",
        },
        "blockers": [
            "Zone map is analysis-only and has not been activated for Nyao execution."
        ],
        "limitations": [
            "Detections use closed OHLC bars only; no order-book or external-news context is included.",
            "A detected zone is a location hypothesis, not an instruction to trade.",
            "Entry still requires confirmation and a viable spread-to-movement relationship.",
        ],
    }
