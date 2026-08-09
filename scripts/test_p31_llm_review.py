from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agents.llm_review import _parse_json, run_analyst_critic_review


class FakeProvider:
    def __init__(self, response: dict):
        self.response = response

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        assert "execution" in system_prompt.lower()
        assert "required_output_schema" in user_prompt
        return json.dumps(self.response)


def test_supervised_analyst_critic_contract() -> None:
    packet = {
        "purpose": "ANALYST_CRITIC_INPUT_ONLY",
        "execution_authority": "NONE",
        "symbol": "#BTCUSD",
        "top_parameters_for_reasoning": [{"parameter": "max_open_orders"}],
    }
    analyst = FakeProvider({
        "summary": "Investigate only.",
        "priorities": [{
            "parameter": "max_open_orders",
            "rationale": "Evidence is confounded.",
            "supporting_evidence": [],
            "contradicting_evidence": ["Shared policy cohort"],
            "next_evidence_needed": ["Isolated observations"],
            "confidence": 35,
        }],
        "abstain_from_numeric_change": True,
        "limitations": ["No causal evidence"],
    })
    critic = FakeProvider({
        "verdict": "ACCEPT_FOR_HUMAN_REVIEW",
        "summary": "The analysis preserves the boundary.",
        "unsupported_claims": [],
        "missing_risks": [],
        "required_revisions": [],
        "confirms_no_execution_authority": True,
    })
    result = run_analyst_critic_review(packet, analyst, critic)
    assert result["execution_authority"] == "NONE"
    assert result["eligible_for_execution"] is False
    assert result["human_review_required"] is True


def test_model_json_with_trailing_content() -> None:
    assert _parse_json('{"summary":"valid"}\nAdditional explanation.') == {
        "summary": "valid"
    }
    assert _parse_json(
        '```json\n{"summary":"first"}\n```\n{"summary":"duplicate"}'
    ) == {"summary": "first"}


if __name__ == "__main__":
    test_supervised_analyst_critic_contract()
    test_model_json_with_trailing_content()
    print("P3.1 Analyst/Critic contract checks passed.")
