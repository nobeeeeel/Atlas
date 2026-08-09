from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence.advisory_policy_proposal import (
    build_llm_policy_advisory_proposal,
    llm_advisory_context_status,
    reissue_llm_advisory_proposal,
)
from backend.app.intelligence.parameter_registry import all_parameters
from backend.app.intelligence.account_identity import account_identity


def _current_value(parameter: dict) -> object:
    if parameter["kind"] == "bool":
        return False
    if parameter["kind"] == "time":
        return "00:00"
    if parameter["kind"] == "select":
        return (parameter.get("options") or [{}])[0].get("value")
    if parameter["kind"] == "number":
        return parameter.get("min") if parameter.get("min") is not None else 0
    return ""


def test_llm_policy_enters_existing_review_contract() -> None:
    parameters = all_parameters()
    runtime = {row["name"]: _current_value(row) for row in parameters}
    status = {
        "policy_epoch": 7,
        "strategy_open_positions": 0,
        "account_login": 123456,
        "account_server": "Atlas-Demo",
        **{row["status_key"]: runtime[row["name"]] for row in parameters},
    }
    command = {"policy_epoch": 7, "command_version": 7, **runtime}
    policy_input = {
        "symbol": "#BTCUSD",
        "account_identity": account_identity(status),
        "market_context": {"risk_state": "MODERATE"},
        "control_catalog": [
            {"parameter": row["name"], "current": runtime[row["name"]]}
            for row in parameters
        ],
    }
    result = {
        "proposal_id": "gemini-test-policy",
        "symbol": "#BTCUSD",
        "state": "READY_FOR_RAPID_SUPERVISED_REVIEW",
        "eligible_for_rapid_supervised_review": True,
        "runtime_patch": {"enable_buy_orders": True},
        "full_policy_decision": {
            "reviewed_control_count": 157,
            "changed_control_count": 1,
            "kept_control_count": 156,
        },
        "bundle": {
            "bundle_name": "TEST_POLICY",
            "market_regime": "BULLISH_TREND",
            "overall_confidence": 80,
            "performance_diagnosis": ["Baseline is losing."],
            "weaknesses_targeted": ["Entry quality"],
            "observation_window": "10 closed trades",
            "changes": [{
                "parameter": "enable_buy_orders",
                "current": False,
                "proposed": True,
                "rationale": "Contract test",
                "expected_effect": "Contract test",
                "confidence": 80,
            }],
        },
        "critic": {
            "verdict": "ACCEPT_FOR_SUPERVISED_REVIEW",
            "summary": "Accepted",
        },
    }

    proposal = build_llm_policy_advisory_proposal(
        result,
        policy_input,
        current_status=status,
        current_command=command,
    )
    assert proposal["mode"] == "LLM_POLICY_PROPOSAL"
    assert proposal["review_state"] == "READY_FOR_HUMAN_REVIEW"
    assert proposal["recommendation_ready"] is True
    assert proposal["current_policy_epoch"] == 7
    assert proposal["proposed_policy_epoch"] == 8
    assert len(proposal["proposed_runtime"]) == 157
    assert proposal["proposed_runtime"]["enable_buy_orders"] is True
    assert proposal["changed_controls"]["enable_buy_orders"]["shadow"] is True

    autonomous_input = {**policy_input, "application_mode": "AUTONOMOUS"}
    autonomous_proposal = build_llm_policy_advisory_proposal(
        result,
        autonomous_input,
        current_status=status,
        current_command=command,
    )
    assert autonomous_proposal["review_state"] == "READY_FOR_AUTONOMOUS_APPLY"
    assert (
        autonomous_proposal["transition_plan"]["apply_state"]
        == "READY_FOR_AUTONOMOUS_VALIDATION"
    )

    context = llm_advisory_context_status(
        proposal,
        current_status=status,
        current_command=command,
    )
    assert context["current"] is True
    assert context["phase"] == "PRE_APPLY"

    changed_status = dict(status)
    changed_status[parameters[1]["status_key"]] = not bool(
        changed_status[parameters[1]["status_key"]]
    )
    stale = llm_advisory_context_status(
        proposal,
        current_status=changed_status,
        current_command=command,
    )
    assert stale["current"] is False
    assert stale["phase"] == "STALE"

    proposal["approval"]["status"] = "INVALIDATED_STALE_CONTEXT"
    reissued = reissue_llm_advisory_proposal(
        proposal,
        reason="Contract-test workflow correction",
    )
    assert reissued["proposal_id"] != proposal["proposal_id"]
    assert reissued["supersedes_proposal_id"] == proposal["proposal_id"]
    assert reissued["approval"]["status"] == "NOT_REQUESTED"
    assert reissued["runtime_fingerprint"] == proposal["runtime_fingerprint"]


if __name__ == "__main__":
    test_llm_policy_enters_existing_review_contract()
    print("P3.5 LLM advisory workflow checks passed.")
