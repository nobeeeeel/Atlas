from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agents.policy_proposal import (
    GemmaPolicyProposal,
    run_policy_proposal,
    validate_policy_proposal,
)


class FakeProvider:
    def __init__(self, response: dict):
        self.response = response

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        assert "required_output_schema" in user_prompt
        return json.dumps(self.response)


def test_multi_parameter_policy_contract() -> None:
    policy_input = {
        "purpose": "MULTI_PARAMETER_POLICY_PROPOSAL",
        "execution_authority": "PROPOSAL_ONLY",
        "symbol": "#BTCUSD",
        "performance_context": {
            "closed_count": 11,
            "current_consecutive_loss_streak": 11,
        },
        "budget": {
            "max_changes": 12,
            "strategy_open_positions": 0,
            "position_sensitive_changes_allowed": True,
        },
        "control_catalog": [{
            "parameter": "min_buy_signal_score",
            "current": 4.5,
        }],
    }
    analyst = FakeProvider({
        "bundle_name": "HIGH_VOL_ENTRY_SELECTIVITY",
        "market_regime": "HIGH_VOLATILITY",
        "market_summary": "Entry selectivity should increase.",
        "policy_thesis": "Reduce low-quality BUY entries.",
        "past_performance_used": True,
        "performance_diagnosis": ["The current policy lost all 11 observed outcomes."],
        "weaknesses_targeted": ["Low-quality entries"],
        "reviewed_parameters": ["min_buy_signal_score"],
        "changes": [{
            "parameter": "min_buy_signal_score",
            "proposed": 5.0,
            "rationale": "Require stronger signals.",
            "expected_effect": "Fewer BUY entries.",
            "evidence_used": ["High volatility"],
            "confidence": 70,
        }],
        "expected_behavior": ["Lower trade frequency"],
        "risks_and_tradeoffs": ["May miss some valid entries"],
        "revert_conditions": ["No improvement after 30 closed outcomes"],
        "observation_window": "30 closed outcomes",
        "overall_confidence": 70,
    })
    critic = FakeProvider({
        "verdict": "ACCEPT_FOR_SUPERVISED_REVIEW",
        "summary": "The proposal is internally coherent.",
        "approved_parameters": ["min_buy_signal_score"],
        "rejected_changes": [],
        "interaction_warnings": [],
        "required_revisions": [],
        "confirms_no_direct_execution": True,
    })

    result = run_policy_proposal(policy_input, analyst, critic)
    assert result["state"] == "READY_FOR_RAPID_SUPERVISED_REVIEW"
    assert result["runtime_patch"] == {"min_buy_signal_score": 5.0}
    assert result["eligible_for_rapid_supervised_review"] is True
    assert result["eligible_for_direct_execution"] is False


def test_past_performance_cannot_be_ignored() -> None:
    policy_input = {
        "purpose": "MULTI_PARAMETER_POLICY_PROPOSAL",
        "execution_authority": "PROPOSAL_ONLY",
        "symbol": "#BTCUSD",
        "performance_context": {"closed_count": 12},
        "budget": {
            "max_changes": 1,
            "strategy_open_positions": 0,
            "position_sensitive_changes_allowed": True,
        },
        "control_catalog": [{
            "parameter": "min_buy_signal_score",
            "current": 4.5,
        }],
    }
    analyst = FakeProvider({
        "bundle_name": "IGNORES_HISTORY",
        "market_regime": "UNKNOWN",
        "market_summary": "No diagnosis.",
        "policy_thesis": "Keep the policy.",
        "past_performance_used": False,
        "performance_diagnosis": [],
        "weaknesses_targeted": [],
        "reviewed_parameters": ["min_buy_signal_score"],
        "changes": [],
        "expected_behavior": [],
        "risks_and_tradeoffs": [],
        "revert_conditions": ["Revert if losses continue"],
        "observation_window": "10 closed outcomes",
        "overall_confidence": 20,
    })
    critic = FakeProvider({
        "verdict": "REJECT",
        "summary": "History was ignored.",
        "approved_parameters": [],
        "rejected_changes": [],
        "interaction_warnings": [],
        "required_revisions": [],
        "confirms_no_direct_execution": True,
    })

    try:
        run_policy_proposal(policy_input, analyst, critic)
    except ValueError as exc:
        assert "ignored available past performance" in str(exc)
    else:
        raise AssertionError("A proposal that ignores performance must be rejected.")


def test_genuine_agreement_does_not_require_invented_disagreement() -> None:
    proposal = GemmaPolicyProposal.model_validate({
        "bundle_name": "ATLAS_ANALYSIS_AGREEMENT",
        "market_regime": "RANGE",
        "market_summary": "Atlas and Gemini reach the same conclusion.",
        "policy_thesis": "Keep the current control.",
        "past_performance_used": False,
        "atlas_prior_analysis_used": True,
        "atlas_analysis_agreements": [
            "Both analyses identify range-bound conditions from the supplied evidence."
        ],
        "atlas_analysis_disagreements": [],
        "reviewed_parameters": ["min_buy_signal_score"],
        "changes": [],
        "revert_conditions": ["Reassess when the regime changes."],
        "observation_window": "Next policy cycle",
        "overall_confidence": 75,
    })
    validated = validate_policy_proposal(proposal, {
        "atlas_prior_analysis": {"current_shadow_policy": {"fit": "RANGE"}},
        "performance_context": {"closed_count": 0},
        "budget": {"max_changes": 1, "strategy_open_positions": 0},
        "control_catalog": [{
            "parameter": "min_buy_signal_score",
            "current": 4.5,
        }],
    })
    assert validated == []


def test_catalog_scope_does_not_require_echoing_every_unchanged_name() -> None:
    policy_input = {
        "purpose": "MULTI_PARAMETER_POLICY_PROPOSAL",
        "execution_authority": "PROPOSAL_ONLY",
        "symbol": "#BTCUSD",
        "performance_context": {"closed_count": 0},
        "budget": {
            "max_changes": 2,
            "strategy_open_positions": 0,
            "position_sensitive_changes_allowed": True,
        },
        "control_catalog": [
            {"parameter": "min_buy_signal_score", "current": 4.5},
            {"parameter": "atr_period", "current": 14},
        ],
    }
    analyst = FakeProvider({
        "bundle_name": "KEEP_COHERENT_BASELINE",
        "market_regime": "RANGE",
        "market_summary": "No supported change is required.",
        "policy_thesis": "Keep the complete supplied catalog unchanged.",
        "past_performance_used": False,
        "reviewed_parameters": ["min_buy_signal_score"],
        "changes": [],
        "revert_conditions": ["Reassess on a material regime change."],
        "observation_window": "Next policy cycle",
        "overall_confidence": 70,
    })
    critic = FakeProvider({
        "verdict": "ACCEPT_FOR_SUPERVISED_REVIEW",
        "summary": "Keeping the catalog is coherent.",
        "approved_parameters": ["min_buy_signal_score", "atr_period"],
        "rejected_changes": [],
        "interaction_warnings": [],
        "required_revisions": [],
        "confirms_no_direct_execution": True,
    })
    result = run_policy_proposal(policy_input, analyst, critic)
    assert result["full_policy_decision"]["reviewed_control_count"] == 2
    assert result["full_policy_decision"]["model_reported_reviewed_count"] == 1
    assert result["bundle"]["reviewed_parameters"] == [
        "min_buy_signal_score",
        "atr_period",
    ]
    assert result["critic"]["approved_parameters"] == []
    assert result["critic"]["ignored_non_change_approvals"] == [
        "atr_period",
        "min_buy_signal_score",
    ]
    assert result["eligible_for_rapid_supervised_review"] is True


def test_incomplete_critic_change_coverage_blocks_without_crashing() -> None:
    policy_input = {
        "purpose": "MULTI_PARAMETER_POLICY_PROPOSAL",
        "execution_authority": "PROPOSAL_ONLY",
        "symbol": "#BTCUSD",
        "performance_context": {"closed_count": 0},
        "budget": {"max_changes": 1, "strategy_open_positions": 0},
        "control_catalog": [{
            "parameter": "min_buy_signal_score",
            "current": 4.5,
        }],
    }
    analyst = FakeProvider({
        "bundle_name": "SELECTIVE_ENTRY",
        "market_regime": "VOLATILE",
        "market_summary": "Require a stronger entry.",
        "policy_thesis": "Raise selectivity.",
        "past_performance_used": False,
        "reviewed_parameters": ["min_buy_signal_score"],
        "changes": [{
            "parameter": "min_buy_signal_score",
            "proposed": 5.0,
            "rationale": "Require stronger evidence.",
            "expected_effect": "Fewer weak entries.",
            "evidence_used": ["Volatility"],
            "confidence": 75,
        }],
        "revert_conditions": ["Revert if opportunity loss rises."],
        "observation_window": "Next 20 signals",
        "overall_confidence": 75,
    })
    critic = FakeProvider({
        "verdict": "ACCEPT_FOR_SUPERVISED_REVIEW",
        "summary": "Review was incomplete.",
        "approved_parameters": ["atr_period"],
        "rejected_changes": [],
        "interaction_warnings": [],
        "required_revisions": [],
        "confirms_no_direct_execution": True,
    })
    result = run_policy_proposal(policy_input, analyst, critic)
    assert result["state"] == "BLOCKED_BY_LLM_CRITIC"
    assert result["eligible_for_rapid_supervised_review"] is False
    assert result["critic"]["effective_verdict"] == "REVISE"
    assert result["critic"]["unreviewed_proposed_changes"] == [
        "min_buy_signal_score"
    ]


if __name__ == "__main__":
    test_multi_parameter_policy_contract()
    test_past_performance_cannot_be_ignored()
    test_genuine_agreement_does_not_require_invented_disagreement()
    test_catalog_scope_does_not_require_echoing_every_unchanged_name()
    test_incomplete_critic_change_coverage_blocks_without_crashing()
    print("P3.4 performance-learning policy checks passed.")
