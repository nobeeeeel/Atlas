from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from backend.app.intelligence.history import get_history


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _counter(records: list[dict], getter) -> dict[str, int]:
    counts = Counter()

    for record in records:
        key = getter(record)
        if key is None:
            key = "UNKNOWN"
        counts[str(key)] += 1

    return dict(counts.most_common())


def _pct(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total * 100.0, 2)


def _regime_runs(records: list[dict]) -> list[dict[str, Any]]:
    if not records:
        return []

    runs: list[dict[str, Any]] = []
    start_index = 0

    for index in range(1, len(records) + 1):
        current_regime = (
            (records[start_index].get("regime") or {}).get("regime")
            or "UNKNOWN"
        )

        if index < len(records):
            next_regime = (
                (records[index].get("regime") or {}).get("regime")
                or "UNKNOWN"
            )
        else:
            next_regime = None

        if index == len(records) or next_regime != current_regime:
            first = records[start_index]
            last = records[index - 1]

            start_time = _iso(first.get("recorded_at"))
            end_time = _iso(last.get("recorded_at"))

            duration_seconds = 0.0
            if start_time is not None and end_time is not None:
                duration_seconds = max(
                    0.0,
                    (end_time - start_time).total_seconds(),
                )

            first_equity = _f(
                (first.get("account") or {}).get("equity")
            )
            last_equity = _f(
                (last.get("account") or {}).get("equity")
            )

            first_balance = _f(
                (first.get("account") or {}).get("balance")
            )
            last_balance = _f(
                (last.get("account") or {}).get("balance")
            )

            first_bid = _f(
                (first.get("market") or {}).get("bid")
            )
            last_bid = _f(
                (last.get("market") or {}).get("bid")
            )

            runs.append(
                {
                    "regime": current_regime,
                    "start": first.get("recorded_at"),
                    "end": last.get("recorded_at"),
                    "snapshots": index - start_index,
                    "duration_seconds": round(duration_seconds, 1),
                    "duration_minutes": round(
                        duration_seconds / 60.0,
                        2,
                    ),
                    "equity_change": round(
                        last_equity - first_equity,
                        2,
                    ),
                    "balance_change": round(
                        last_balance - first_balance,
                        2,
                    ),
                    "bid_change": round(
                        last_bid - first_bid,
                        4,
                    ),
                }
            )

            start_index = index

    return runs


def analyze_history(limit: int = 20_000) -> dict[str, Any]:
    """
    Descriptive Atlas history analytics.

    Important:
    - Snapshots overlap in time.
    - They are saved on state change plus heartbeat.
    - This is not trade-level attribution and must not be treated as
      causal proof that a regime/advice is profitable.
    """
    history = get_history(limit=limit)
    records = history.get("records") or []
    total = len(records)

    if not records:
        return {
            "ready": False,
            "record_count": 0,
            "message": "No Atlas intelligence history is available yet.",
        }

    first = records[0]
    last = records[-1]

    first_time = _iso(first.get("recorded_at"))
    last_time = _iso(last.get("recorded_at"))

    duration_seconds = 0.0
    if first_time is not None and last_time is not None:
        duration_seconds = max(
            0.0,
            (last_time - first_time).total_seconds(),
        )

    balances = [
        _f((record.get("account") or {}).get("balance"))
        for record in records
    ]
    equities = [
        _f((record.get("account") or {}).get("equity"))
        for record in records
    ]
    drawdowns = [
        _f(
            (record.get("account") or {}).get(
                "equity_drawdown_pct"
            )
        )
        for record in records
    ]

    state_changes = sum(
        1
        for record in records
        if record.get("reason") == "STATE_CHANGE"
    )
    heartbeats = sum(
        1
        for record in records
        if record.get("reason") == "HEARTBEAT"
    )

    veto_count = sum(
        1
        for record in records
        if bool((record.get("risk") or {}).get("veto_new_risk"))
    )

    spread_blocked_count = sum(
        1
        for record in records
        if not bool(
            (record.get("market") or {}).get(
                "spread_within_limit",
                True,
            )
        )
    )

    hedge_active_count = sum(
        1
        for record in records
        if _i(
            (record.get("hedge") or {}).get(
                "active_hedge_chains"
            )
        )
        > 0
    )

    proposed_count = sum(
        1
        for record in records
        if bool(record.get("proposed_changes"))
    )

    buy_blocks = _counter(
        records,
        lambda r: (r.get("signal") or {}).get(
            "buy_block_reason",
            "UNKNOWN",
        ),
    )
    sell_blocks = _counter(
        records,
        lambda r: (r.get("signal") or {}).get(
            "sell_block_reason",
            "UNKNOWN",
        ),
    )

    proposal_patterns = Counter()
    for record in records:
        proposed = record.get("proposed_changes") or {}

        if not proposed:
            proposal_patterns["NO_CHANGE"] += 1
            continue

        pattern = ", ".join(
            f"{key}={proposed[key]}"
            for key in sorted(proposed)
        )
        proposal_patterns[pattern] += 1

    runs = _regime_runs(records)

    run_by_regime: dict[str, dict[str, Any]] = {}

    for run in runs:
        name = run["regime"]

        if name not in run_by_regime:
            run_by_regime[name] = {
                "runs": 0,
                "total_minutes": 0.0,
                "equity_change_sum": 0.0,
                "balance_change_sum": 0.0,
                "bid_change_sum": 0.0,
            }

        item = run_by_regime[name]
        item["runs"] += 1
        item["total_minutes"] += run["duration_minutes"]
        item["equity_change_sum"] += run["equity_change"]
        item["balance_change_sum"] += run["balance_change"]
        item["bid_change_sum"] += run["bid_change"]

    for item in run_by_regime.values():
        item["total_minutes"] = round(
            item["total_minutes"],
            2,
        )
        item["equity_change_sum"] = round(
            item["equity_change_sum"],
            2,
        )
        item["balance_change_sum"] = round(
            item["balance_change_sum"],
            2,
        )
        item["bid_change_sum"] = round(
            item["bid_change_sum"],
            4,
        )

    start_balance = balances[0]
    end_balance = balances[-1]
    start_equity = equities[0]
    end_equity = equities[-1]

    result = {
        "ready": True,
        "record_count": total,
        "period": {
            "start": first.get("recorded_at"),
            "end": last.get("recorded_at"),
            "duration_seconds": round(duration_seconds, 1),
            "duration_hours": round(
                duration_seconds / 3600.0,
                3,
            ),
        },
        "capture": {
            "state_change_records": state_changes,
            "heartbeat_records": heartbeats,
            "state_change_pct": _pct(
                state_changes,
                total,
            ),
        },
        "account": {
            "start_balance": round(start_balance, 2),
            "end_balance": round(end_balance, 2),
            "balance_change": round(
                end_balance - start_balance,
                2,
            ),
            "start_equity": round(start_equity, 2),
            "end_equity": round(end_equity, 2),
            "equity_change": round(
                end_equity - start_equity,
                2,
            ),
            "minimum_equity_seen": round(
                min(equities),
                2,
            ),
            "maximum_equity_seen": round(
                max(equities),
                2,
            ),
            "maximum_drawdown_pct_seen": round(
                max(drawdowns),
                4,
            ),
        },
        "counts": {
            "regimes": _counter(
                records,
                lambda r: (r.get("regime") or {}).get(
                    "regime"
                ),
            ),
            "risk_states": _counter(
                records,
                lambda r: (r.get("risk") or {}).get(
                    "state"
                ),
            ),
            "fit_states": _counter(
                records,
                lambda r: r.get("fit"),
            ),
            "exposure_biases": _counter(
                records,
                lambda r: (r.get("risk") or {}).get(
                    "exposure_bias"
                ),
            ),
            "volatility_states": _counter(
                records,
                lambda r: (r.get("regime") or {}).get(
                    "volatility"
                ),
            ),
        },
        "risk_activity": {
            "veto_records": veto_count,
            "veto_pct": _pct(veto_count, total),
            "spread_blocked_records": spread_blocked_count,
            "spread_blocked_pct": _pct(
                spread_blocked_count,
                total,
            ),
            "hedge_active_records": hedge_active_count,
            "hedge_active_pct": _pct(
                hedge_active_count,
                total,
            ),
            "records_with_proposed_changes": proposed_count,
            "proposed_change_pct": _pct(
                proposed_count,
                total,
            ),
        },
        "block_reasons": {
            "buy": buy_blocks,
            "sell": sell_blocks,
        },
        "proposal_patterns": dict(
            proposal_patterns.most_common()
        ),
        "regime_runs": {
            "run_count": len(runs),
            "by_regime": run_by_regime,
            "recent_runs": runs[-20:],
        },
        "limitations": [
            "Snapshots are not independent observations.",
            "Heartbeat records can overweight long-lasting states.",
            "Equity changes during a regime are descriptive only; they are not trade-level profit attribution.",
            "Closed-trade outcome tracking is still required before Atlas should learn autonomous parameter changes.",
        ],
    }

    return result
