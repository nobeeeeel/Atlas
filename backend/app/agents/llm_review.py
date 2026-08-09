from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.agents.llm_provider import LlmProvider


class InvestigationPriority(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameter: str
    rationale: str
    supporting_evidence: list[str] = Field(default_factory=list, max_length=8)
    contradicting_evidence: list[str] = Field(default_factory=list, max_length=8)
    next_evidence_needed: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=100)


class AnalystReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    priorities: list[InvestigationPriority] = Field(default_factory=list, max_length=5)
    abstain_from_numeric_change: bool
    limitations: list[str] = Field(default_factory=list, max_length=10)


class CriticReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["ACCEPT_FOR_HUMAN_REVIEW", "REVISE", "REJECT"]
    summary: str
    unsupported_claims: list[str] = Field(default_factory=list, max_length=10)
    missing_risks: list[str] = Field(default_factory=list, max_length=10)
    required_revisions: list[str] = Field(default_factory=list, max_length=10)
    confirms_no_execution_authority: bool


ANALYST_SYSTEM_PROMPT = """You are the Atlas trading-research Analyst.
Use only the supplied evidence packet. Historical associations are descriptive,
not causal. CONFOUNDED evidence must never be attributed to one parameter.
Rank investigation priorities only; do not invent parameter values, commands,
orders, trades, or execution instructions. Return strict JSON matching the schema.
"""

CRITIC_SYSTEM_PROMPT = """You are the independent Atlas safety Critic.
Audit the Analyst against the supplied evidence. Reject causal overclaiming,
confounded attribution, invented facts, numeric parameter changes, and any implied
execution authority. Return strict JSON matching the schema.
"""


def _parse_json(raw: str) -> dict[str, Any]:
    """Extract one JSON object from a model response.

    Google JSON mode can still wrap the object in a markdown fence or append a
    second explanatory block. Decode the first complete object and let the
    strict Pydantic schema reject missing, extra, or invalid policy fields.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    object_start = text.find("{")
    if object_start < 0:
        raise ValueError("LLM response does not contain a JSON object.")
    value, _end = json.JSONDecoder().raw_decode(text[object_start:])
    if not isinstance(value, dict):
        raise ValueError("LLM response must be a JSON object.")
    return value


def _schema_prompt(schema: type[BaseModel], payload: dict[str, Any]) -> str:
    return json.dumps({
        "required_output_schema": schema.model_json_schema(),
        "input": payload,
    }, separators=(",", ":"), default=str)


def run_analyst_critic_review(
    packet: dict[str, Any],
    analyst_provider: LlmProvider,
    critic_provider: LlmProvider | None = None,
) -> dict[str, Any]:
    if packet.get("purpose") != "ANALYST_CRITIC_INPUT_ONLY":
        raise ValueError("Unsupported evidence packet purpose.")
    if packet.get("execution_authority") != "NONE":
        raise ValueError("Evidence packet must have execution_authority NONE.")

    packet_hash = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    allowed_parameters = {
        str(row.get("parameter"))
        for row in packet.get("top_parameters_for_reasoning", [])
        if isinstance(row, dict) and row.get("parameter")
    }

    analyst_raw = analyst_provider.complete(
        system_prompt=ANALYST_SYSTEM_PROMPT,
        user_prompt=_schema_prompt(AnalystReview, packet),
    )
    analyst = AnalystReview.model_validate(_parse_json(analyst_raw))
    if not analyst.abstain_from_numeric_change:
        raise ValueError("Analyst failed the no-numeric-change safety contract.")
    unknown = sorted({p.parameter for p in analyst.priorities} - allowed_parameters)
    if unknown:
        raise ValueError(f"Analyst introduced parameters outside the packet: {unknown}")

    critic: CriticReview | None = None
    if critic_provider is not None:
        critic_input = {"evidence_packet": packet, "analyst_review": analyst.model_dump()}
        critic_raw = critic_provider.complete(
            system_prompt=CRITIC_SYSTEM_PROMPT,
            user_prompt=_schema_prompt(CriticReview, critic_input),
        )
        critic = CriticReview.model_validate(_parse_json(critic_raw))
        if not critic.confirms_no_execution_authority:
            raise ValueError("Critic did not confirm the execution-authority boundary.")

    return {
        "review_version": "1.0",
        "mode": "SUPERVISED_RESEARCH_ONLY",
        "execution_authority": "NONE",
        "human_review_required": True,
        "packet_hash": packet_hash,
        "symbol": packet.get("symbol"),
        "analyst": analyst.model_dump(),
        "critic": critic.model_dump() if critic else None,
        "eligible_for_execution": False,
    }
