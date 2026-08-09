from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agents.policy_proposal import (  # noqa: E402
    GemmaPolicyProposal,
    validate_policy_proposal,
)
from backend.app.intelligence.scalping_responsiveness import (  # noqa: E402
    analyze_scalping_responsiveness,
)


def _change(parameter: str, proposed: object) -> dict:
    return {
        "parameter": parameter,
        "proposed": proposed,
        "rationale": "Reduce measured scalping latency coherently.",
        "expected_effect": "Faster qualified entries.",
        "evidence_used": ["responsiveness analysis"],
        "confidence": 70,
    }


def _proposal(changes: list[dict]) -> GemmaPolicyProposal:
    return GemmaPolicyProposal.model_validate({
        "bundle_name": "FAST_INTRABAR_TEST",
        "market_regime": "MOMENTUM",
        "market_summary": "Measured entry latency is excessive.",
        "policy_thesis": "Reduce latency while retaining repetition guards.",
        "past_performance_used": False,
        "atlas_prior_analysis_used": False,
        "responsiveness_analysis_used": True,
        "responsiveness_profile": "FAST",
        "responsiveness_diagnosis": ["New-bar gating is the largest static delay."],
        "performance_diagnosis": [],
        "weaknesses_targeted": ["Entry latency"],
        "reviewed_parameters": [
            "enable_new_bar_entry_only",
            "max_trades_per_candle",
            "enable_duplicate_distance_filter",
        ],
        "changes": changes,
        "expected_behavior": ["Qualified intrabar evaluation"],
        "risks_and_tradeoffs": ["More intrabar signal noise"],
        "revert_conditions": ["Net expectancy deteriorates after 20 outcomes"],
        "observation_window": "20 closed outcomes",
        "overall_confidence": 70,
    })


def _policy_input() -> dict:
    return {
        "budget": {"max_changes": 3, "strategy_open_positions": 0},
        "performance_context": {"closed_count": 0},
        "scalping_responsiveness": {"profile": "SELECTIVE"},
        "control_catalog": [
            {"parameter": "enable_new_bar_entry_only", "current": True},
            {"parameter": "max_trades_per_candle", "current": 3},
            {"parameter": "enable_duplicate_distance_filter", "current": True},
        ],
    }


def test_responsiveness_metrics() -> None:
    records = []
    for _ in range(60):
        records.append({
            "signal": {
                "buy_entry_eligible": False,
                "sell_entry_eligible": False,
                "buy_block_reason": "NEW_BAR_GATE",
                "sell_block_reason": "SCORE_BELOW_THRESHOLD",
                "buy_adjusted_score": 4.0,
                "sell_adjusted_score": 3.5,
                "buy_effective_threshold": 5.0,
                "sell_effective_threshold": 5.0,
            }
        })
    closed = [{
        "origin_guess": "FRESH_OR_REENTRY",
        "observed_lifetime_minutes": 8,
        "max_favorable_net_pl_observed": 10,
        "final_observed_net_pl_before_disappearance": 4,
    } for _ in range(20)]
    result = analyze_scalping_responsiveness(
        {"symbol": "#BTCUSD", "positions": []},
        {
            "enable_new_bar_entry_only": True,
            "signal_smoothing_candles": 2,
            "enable_limit_entry": True,
            "max_trades_per_candle": 3,
            "enable_duplicate_distance_filter": True,
            "health_grace_bars": 2,
            "min_buy_signal_score": 5.0,
            "min_sell_signal_score": 5.0,
        },
        history={"records": records},
        trade_outcomes={"closed": closed},
    )
    assert result["profile"] == "SELECTIVE"
    assert result["evidence_quality"] == "MODERATE"
    assert result["entry_observations"]["eligible_rate_pct"] == 0.0
    assert result["exit_observations"]["average_mfe_capture_ratio"] == 0.4


def test_intrabar_bundle_requires_repetition_guards() -> None:
    try:
        validate_policy_proposal(
            _proposal([_change("enable_new_bar_entry_only", False)]),
            _policy_input(),
        )
    except ValueError as exc:
        assert "max_trades_per_candle <= 1" in str(exc)
    else:
        raise AssertionError("Unsafe intrabar policy was accepted.")

    validated = validate_policy_proposal(
        _proposal([
            _change("enable_new_bar_entry_only", False),
            _change("max_trades_per_candle", 1),
        ]),
        _policy_input(),
    )
    assert len(validated) == 2


if __name__ == "__main__":
    test_responsiveness_metrics()
    test_intrabar_bundle_requires_repetition_guards()
    print("P3.7 scalping responsiveness checks passed.")
