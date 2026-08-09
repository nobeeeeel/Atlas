from __future__ import annotations

import hashlib
import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.parameter_registry import all_parameters
from backend.app.intelligence.account_identity import account_identity

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
PROPOSAL_STORE_FILE = DATA_DIR / "advisory_policy_proposals.json"

_LOCK = threading.Lock()
MAX_PROPOSALS = 10_000


TEST_FORCE_ENV = "ATLAS_TEST_FORCE_RECOMMENDATION_READY"
TEST_BASE_LOT_ENV = "ATLAS_TEST_FORCE_BASE_LOT_SIZE"
TEST_PROPOSAL_NONCE_ENV = "ATLAS_TEST_PROPOSAL_NONCE"


def _env_true(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {
        "1", "true", "yes", "on"
    }


def _test_override_enabled() -> bool:
    return _env_true(TEST_FORCE_ENV)


def _test_proposal_nonce() -> str:
    return str(os.getenv(TEST_PROPOSAL_NONCE_ENV, "")).strip()


def _test_override_base_lot() -> float:
    raw = str(os.getenv(TEST_BASE_LOT_ENV, "0.02")).strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.02
    # Proposal-only test value. This never reaches commands.json in v0.4.2.
    return max(0.01, min(value, 0.05))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _empty_store() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "proposal_count": 0,
        "proposals": [],
    }


def _read_store_unlocked() -> dict[str, Any]:
    if not PROPOSAL_STORE_FILE.exists():
        return _empty_store()

    try:
        with PROPOSAL_STORE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    proposals = data.get("proposals")
    if not isinstance(proposals, list):
        return _empty_store()

    return data


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _proposal_identity(decision: dict[str, Any]) -> dict[str, Any]:
    recommendation = decision.get("recommendation") or {}
    selected_changes = decision.get("selected_changed_controls") or {}

    return {
        "candidate": decision.get("selected_candidate"),
        "runtime_fingerprint": decision.get("decision_runtime_fingerprint"),
        "current_policy_epoch": decision.get("current_policy_epoch"),
        "hypothetical_policy_epoch": decision.get("hypothetical_policy_epoch"),
        "changed_controls": selected_changes,
        "recommendation_state": recommendation.get("recommendation_state"),
    }


def _build_review_summary(decision: dict[str, Any]) -> dict[str, Any]:
    recommendation = decision.get("recommendation") or {}
    stability = decision.get("stability") or {}
    evidence = decision.get("shadow_evidence") or {}
    replay = decision.get("shadow_replay_evidence") or {}
    transition = decision.get("transition_plan") or {}
    risk = decision.get("risk") or {}

    return {
        "preference": decision.get("selected_candidate"),
        "recommendation_ready": recommendation.get("recommendation_ready"),
        "recommendation_state": recommendation.get("recommendation_state"),
        "score_margin": decision.get("decision_score_margin"),
        "confidence": decision.get("confidence"),
        "fit": decision.get("fit"),
        "regime": decision.get("regime"),
        "risk_state": risk.get("state"),
        "veto_new_risk": risk.get("veto_new_risk"),
        "stability": {
            "stable": stability.get("stable"),
            "observation_count": stability.get("observation_count"),
            "dwell_seconds": stability.get("dwell_seconds"),
            "churn": stability.get("churn"),
        },
        "shadow_evidence": {
            "quality": evidence.get("quality"),
            "usable_episode_count": evidence.get("usable_episode_count"),
            "supported": evidence.get("supported"),
            "not_supported": evidence.get("not_supported"),
            "mixed": evidence.get("mixed"),
            "support_ratio": evidence.get("support_ratio"),
        },
        "replay_evidence": {
            "quality": replay.get("quality"),
            "replayed_fresh_trades": replay.get("replayed_fresh_trades"),
            "resolved_decision_count": replay.get("resolved_decision_count"),
            "decision_confidence": replay.get("decision_confidence"),
        },
        "transition": {
            "apply_state": transition.get("apply_state"),
            "existing_position_action": transition.get("existing_position_action"),
            "existing_position_policy_lock_required": (
                transition.get("existing_position_policy_lock_required")
            ),
            "open_positions": transition.get("open_positions"),
            "active_hedge_chains": transition.get("active_hedge_chains"),
        },
    }


def build_advisory_policy_proposal(
    decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Package a v0.2 decision into a formal human-review proposal.

    This function NEVER writes commands.json and NEVER changes Nyao.
    A proposal can exist in BLOCKED state when recommendation readiness has not
    yet been achieved. That preserves auditability without pretending Atlas has
    enough evidence to recommend execution.
    """
    recommendation = decision.get("recommendation") or {}
    natural_ready = bool(recommendation.get("recommendation_ready"))
    natural_selected = decision.get("selected_candidate")
    natural_changes = dict(decision.get("selected_changed_controls") or {})
    runtime = dict(decision.get("decision_runtime") or {})

    test_override_active = _test_override_enabled()
    test_proposal_nonce = _test_proposal_nonce()
    selected = natural_selected
    selected_changes = dict(natural_changes)
    ready = natural_ready
    readiness_source = "NATURAL_GATES"

    # TEST-ONLY path:
    # If Atlas is naturally blocked, create an unmistakably synthetic proposal
    # so the v0.4 human-review state machine can be validated without weakening
    # real evidence thresholds or changing Nyao.
    if test_override_active and not natural_ready:
        readiness_source = "TEST_OVERRIDE"
        ready = True
        selected = "TEST_OVERRIDE_PROPOSAL"

        # If there is already a material advisor change, preserve it.
        # Otherwise create one proposal-only delta from the current runtime.
        if not selected_changes:
            current_base_lot = float(runtime.get("base_lot_size") or 0.05)
            forced_base_lot = _test_override_base_lot()
            if abs(forced_base_lot - current_base_lot) < 1e-12:
                forced_base_lot = 0.01 if current_base_lot > 0.01 else 0.02

            runtime["base_lot_size"] = forced_base_lot
            selected_changes = {
                "base_lot_size": {
                    "current": current_base_lot,
                    "shadow": forced_base_lot,
                }
            }

    review_state = "READY_FOR_HUMAN_REVIEW" if ready else "BLOCKED_NOT_READY"

    proposal_core = {
        "proposal_version": "0.4.3",
        "mode": "ADVISORY_PROPOSAL",
        "execution_allowed": False,
        "selected_candidate": selected,
        "natural_selected_candidate": natural_selected,
        "runtime_fingerprint": _fingerprint(runtime),
        "natural_runtime_fingerprint": decision.get("decision_runtime_fingerprint"),
        "current_policy_epoch": decision.get("current_policy_epoch"),
        "proposed_policy_epoch": (
            int(decision.get("current_policy_epoch") or 0) + 1
            if test_override_active and not natural_ready and bool(selected_changes)
            else decision.get("hypothetical_policy_epoch")
        ),
        "would_create_new_policy_epoch": (
            True
            if test_override_active and not natural_ready and bool(selected_changes)
            else decision.get("would_create_new_policy_epoch")
        ),
        "runtime_control_count": len(runtime),
        "proposed_runtime": runtime,
        "changed_controls": selected_changes,
        "review_state": review_state,
        "recommendation_ready": ready,
        "natural_recommendation_ready": natural_ready,
        "readiness_source": readiness_source,
        "test_override_active": test_override_active,
        "test_override": {
            "environment_variable": TEST_FORCE_ENV,
            "base_lot_environment_variable": TEST_BASE_LOT_ENV,
            "proposal_nonce_environment_variable": TEST_PROPOSAL_NONCE_ENV,
            "proposal_nonce": test_proposal_nonce or None,
            "synthetic": bool(test_override_active and not natural_ready),
            "natural_blockers": recommendation.get("blockers") or [],
            "warning": (
                "TEST_OVERRIDE is for demo workflow validation only. "
                "It is not a natural Atlas recommendation."
            ),
        },
        "recommendation_blockers": (
            []
            if test_override_active and not natural_ready
            else recommendation.get("blockers") or []
        ),
        "natural_recommendation_blockers": recommendation.get("blockers") or [],
        "review_summary": _build_review_summary(decision),
        "transition_plan": decision.get("transition_plan") or {},
        "risk": decision.get("risk") or {},
        "safety_contract": [
            "Proposal packaging + human-review workflow only.",
            "No commands.json write.",
            "No Nyao parameter mutation.",
            "No existing-position policy migration.",
            "Human review is required before any future proposal can become executable.",
            "Policy Epoch protection remains mandatory for all 53 position-sensitive controls.",
            "Proposal readiness is not a profitability or expected-return claim.",
        ],
    }

    proposal_id = _fingerprint({
        "proposal_version": "0.4.3",
        "selected_candidate": selected,
        "natural_selected_candidate": natural_selected,
        "runtime_fingerprint": proposal_core.get("runtime_fingerprint"),
        "current_policy_epoch": proposal_core.get("current_policy_epoch"),
        "proposed_policy_epoch": proposal_core.get("proposed_policy_epoch"),
        "changed_controls": selected_changes,
        "recommendation_ready": ready,
        "natural_recommendation_ready": natural_ready,
        "readiness_source": readiness_source,
        "test_override_active": test_override_active,
        "test_proposal_nonce": (
            test_proposal_nonce if test_override_active else ""
        ),
    })

    return {
        **proposal_core,
        "proposal_id": proposal_id,
        "generated_at": _now_iso(),
        "approval": {
            "status": "NOT_REQUESTED",
            "human_approval_required": True,
            "approved": False,
            "requested_at": None,
            "requested_by": None,
            "approved_at": None,
            "approved_by": None,
            "rejected_at": None,
            "rejected_by": None,
            "expired_at": None,
            "invalidated_at": None,
            "approval_note": None,
            "review_snapshot_hash": None,
        },
        "execution": {
            "eligible": False,
            "allowed": False,
            "reason": (
                "v0.4.2 is review/approval-only. Even an APPROVED proposal "
                "cannot write commands or mutate Nyao."
            ),
        },
    }


def _status_runtime(status: dict[str, Any]) -> dict[str, Any]:
    return {
        parameter["name"]: status.get(parameter["status_key"])
        for parameter in all_parameters()
    }


def _command_runtime(command: dict[str, Any]) -> dict[str, Any]:
    return {
        parameter["name"]: command.get(parameter["name"])
        for parameter in all_parameters()
    }


def build_llm_policy_advisory_proposal(
    llm_result: dict[str, Any],
    policy_input: dict[str, Any],
    *,
    current_status: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any]:
    """Translate an accepted full-registry LLM policy into the review workflow."""
    if not bool(llm_result.get("eligible_for_rapid_supervised_review")):
        raise ValueError("Only a critic-accepted LLM policy can enter human review.")

    catalog = policy_input.get("control_catalog") or []
    current_runtime = {
        str(row.get("parameter")): row.get("current")
        for row in catalog
        if row.get("parameter")
    }
    expected_count = len(all_parameters())
    if len(current_runtime) != expected_count or any(
        value is None for value in current_runtime.values()
    ):
        raise ValueError(
            "LLM policy input does not contain a complete current 157-control runtime."
        )

    runtime_patch = dict(llm_result.get("runtime_patch") or {})
    proposed_runtime = {**current_runtime, **runtime_patch}
    if len(proposed_runtime) != expected_count:
        raise ValueError("LLM proposed runtime is not a complete 157-control policy.")

    bundle = llm_result.get("bundle") or {}
    critic = llm_result.get("critic") or {}
    changes = {
        row["parameter"]: {
            "current": row.get("current"),
            "shadow": row.get("proposed"),
            "rationale": row.get("rationale"),
            "expected_effect": row.get("expected_effect"),
            "confidence": row.get("confidence"),
        }
        for row in (bundle.get("changes") or [])
    }
    current_epoch = int(
        current_command.get("policy_epoch")
        or current_status.get("policy_epoch")
        or 0
    )
    proposed_epoch = current_epoch + 1
    runtime_fingerprint = _fingerprint(proposed_runtime)
    baseline_fingerprint = _fingerprint(current_runtime)
    proposal_id = _fingerprint({
        "mode": "LLM_POLICY_PROPOSAL",
        "source_llm_proposal_id": llm_result.get("proposal_id"),
        "baseline_runtime_fingerprint": baseline_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
        "current_policy_epoch": current_epoch,
        "proposed_policy_epoch": proposed_epoch,
        "account_fingerprint": (
            (policy_input.get("account_identity") or {}).get("fingerprint")
        ),
    })
    now = _now_iso()
    autonomous = str(policy_input.get("application_mode") or "SUPERVISED").upper() == "AUTONOMOUS"
    return {
        "proposal_version": "1.0",
        "proposal_id": proposal_id,
        "generated_at": now,
        "mode": "LLM_POLICY_PROPOSAL",
        "execution_allowed": False,
        "selected_candidate": "GEMINI_3_6_FULL_NYAO_SCALP_POLICY",
        "natural_selected_candidate": "GEMINI_3_6_FULL_NYAO_SCALP_POLICY",
        "source_llm_proposal_id": llm_result.get("proposal_id"),
        "symbol": llm_result.get("symbol") or policy_input.get("symbol"),
        "account_fingerprint": (
            (policy_input.get("account_identity") or {}).get("fingerprint")
        ),
        "runtime_fingerprint": runtime_fingerprint,
        "baseline_runtime_fingerprint": baseline_fingerprint,
        "natural_runtime_fingerprint": baseline_fingerprint,
        "current_policy_epoch": current_epoch,
        "proposed_policy_epoch": proposed_epoch,
        "would_create_new_policy_epoch": True,
        "runtime_control_count": len(proposed_runtime),
        "proposed_runtime": proposed_runtime,
        "changed_controls": changes,
        "review_state": (
            "READY_FOR_AUTONOMOUS_APPLY" if autonomous
            else "READY_FOR_HUMAN_REVIEW"
        ),
        "recommendation_ready": True,
        "natural_recommendation_ready": True,
        "readiness_source": "GEMINI_ANALYST_CRITIC_ACCEPTED",
        "test_override_active": False,
        "test_override": {"synthetic": False},
        "recommendation_blockers": [],
        "natural_recommendation_blockers": [],
        "review_summary": {
            "preference": bundle.get("bundle_name"),
            "recommendation_ready": True,
            "recommendation_state": llm_result.get("state"),
            "confidence": bundle.get("overall_confidence"),
            "regime": bundle.get("market_regime"),
            "risk_state": (policy_input.get("market_context") or {}).get(
                "risk_state"
            ),
            "performance_diagnosis": bundle.get("performance_diagnosis") or [],
            "weaknesses_targeted": bundle.get("weaknesses_targeted") or [],
            "responsiveness_profile": bundle.get("responsiveness_profile"),
            "responsiveness_diagnosis": (
                bundle.get("responsiveness_diagnosis") or []
            ),
            "observation_window": bundle.get("observation_window"),
            "critic_verdict": critic.get("verdict"),
            "critic_summary": critic.get("summary"),
        },
        "transition_plan": {
            "apply_state": (
                "READY_FOR_AUTONOMOUS_VALIDATION" if autonomous
                else "READY_AFTER_HUMAN_APPROVAL"
            ),
            "existing_position_action": "PRESERVE_ENTRY_POLICY_EPOCH",
            "existing_position_policy_lock_required": True,
            "open_positions": current_status.get("strategy_open_positions"),
        },
        "risk": {
            "state": (policy_input.get("market_context") or {}).get("risk_state"),
            "veto_new_risk": False,
        },
        "llm_policy": {
            "provider": "GOOGLE_GEMINI_API",
            "model": "gemini-3.6-flash",
            "proposal_id": llm_result.get("proposal_id"),
            "bundle": bundle,
            "critic": critic,
            "full_policy_decision": llm_result.get("full_policy_decision"),
            "zone_context_assessment": llm_result.get("zone_context_assessment"),
        },
        "safety_contract": [
            "Gemini analyst and critic acceptance must pass the configured application mode gates.",
            (
                "Validated autonomous mode may write only after confidence, dwell, risk, epoch, account, and mode-boundary checks."
                if autonomous else
                "Human review and a separately armed execution action are required before commands.json write."
            ),
            "The complete 157-control Nyao scalp runtime is fingerprint-bound and eligible for policy optimization subject to validation and existing-position locks.",
            "Policy Epoch protection remains mandatory for existing positions; deterministic zone/capital/risk authority is outside Gemini mutation scope.",
        ],
        "approval": {
            "status": "NOT_REQUESTED",
            "human_approval_required": True,
            "approved": False,
            "requested_at": None,
            "requested_by": None,
            "approved_at": None,
            "approved_by": None,
            "rejected_at": None,
            "rejected_by": None,
            "expired_at": None,
            "invalidated_at": None,
            "approval_note": None,
            "review_snapshot_hash": None,
        },
        "execution": {
            "eligible": False,
            "allowed": False,
            "reason": "Awaiting human review and supervised execution workflow.",
        },
    }


def llm_advisory_context_status(
    proposal: dict[str, Any],
    *,
    current_status: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any]:
    """Check whether an LLM proposal still matches the live pre/post-apply context."""
    if proposal.get("mode") != "LLM_POLICY_PROPOSAL":
        return {"current": False, "reason": "NOT_LLM_POLICY"}

    status_runtime = _status_runtime(current_status)
    command_runtime = _command_runtime(current_command)
    status_fp = _fingerprint(status_runtime)
    command_fp = _fingerprint(command_runtime)
    baseline_epoch = int(proposal.get("current_policy_epoch") or 0)
    target_epoch = int(proposal.get("proposed_policy_epoch") or 0)
    status_epoch = int(current_status.get("policy_epoch") or 0)
    command_epoch = int(current_command.get("policy_epoch") or 0)
    proposal_account = str(proposal.get("account_fingerprint") or "")
    live_account = str(account_identity(current_status).get("fingerprint") or "")

    if not proposal_account or proposal_account != live_account:
        return {
            "current": False,
            "phase": "STALE",
            "reason": "ACCOUNT_CONTEXT_CHANGED",
            "proposal_account_fingerprint": proposal_account or None,
            "live_account_fingerprint": live_account or None,
        }

    pre_apply = (
        status_fp == proposal.get("baseline_runtime_fingerprint")
        and status_epoch == baseline_epoch
        and command_epoch == baseline_epoch
    )
    applying_or_applied = (
        command_fp == proposal.get("runtime_fingerprint")
        and command_epoch == target_epoch
        and status_epoch in {baseline_epoch, target_epoch}
    )
    return {
        "current": bool(pre_apply or applying_or_applied),
        "phase": (
            "PRE_APPLY" if pre_apply
            else "APPLYING_OR_APPLIED" if applying_or_applied
            else "STALE"
        ),
        "status_runtime_fingerprint": status_fp,
        "command_runtime_fingerprint": command_fp,
        "status_policy_epoch": status_epoch,
        "command_policy_epoch": command_epoch,
    }


def reissue_llm_advisory_proposal(
    proposal: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    """Create a fresh review identity without erasing a prior terminal audit trail."""
    if proposal.get("mode") != "LLM_POLICY_PROPOSAL":
        raise ValueError("Only LLM policy proposals can be reissued by this helper.")
    now = _now_iso()
    reissued = copy.deepcopy(proposal)
    old_id = str(proposal.get("proposal_id") or "")
    reissued["proposal_id"] = _fingerprint({
        "mode": "LLM_POLICY_PROPOSAL_REISSUE",
        "supersedes_proposal_id": old_id,
        "runtime_fingerprint": proposal.get("runtime_fingerprint"),
        "proposed_policy_epoch": proposal.get("proposed_policy_epoch"),
        "reissued_at": now,
    })
    reissued["generated_at"] = now
    reissued["supersedes_proposal_id"] = old_id
    reissued["reissue_reason"] = reason
    reissued["review_state"] = "READY_FOR_HUMAN_REVIEW"
    reissued["approval"] = {
        "status": "NOT_REQUESTED",
        "human_approval_required": True,
        "approved": False,
        "requested_at": None,
        "requested_by": None,
        "approved_at": None,
        "approved_by": None,
        "rejected_at": None,
        "rejected_by": None,
        "expired_at": None,
        "invalidated_at": None,
        "approval_note": None,
        "review_snapshot_hash": None,
    }
    reissued["execution"] = {
        "eligible": False,
        "allowed": False,
        "reason": "Reissued after workflow correction; awaiting fresh approval.",
    }
    return reissued


def persist_advisory_policy_proposal(
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """
    Idempotently persist the proposal by proposal_id.

    Repeated generation of the same proposal updates last_seen_at/seen_count
    rather than creating duplicate proposal rows.
    """
    proposal_id = proposal.get("proposal_id")
    now = _now_iso()

    with _LOCK:
        store = _read_store_unlocked()
        proposals = store.get("proposals") or []

        existing_index = -1
        for i, item in enumerate(proposals):
            if item.get("proposal_id") == proposal_id:
                existing_index = i
                break

        if existing_index >= 0:
            existing = proposals[existing_index]
            first_seen_at = existing.get("first_seen_at") or now
            seen_count = int(existing.get("seen_count") or 0) + 1

            # Preserve any future approval metadata if another phase extends it.
            approval = existing.get("approval") or proposal.get("approval")
            execution = existing.get("execution") or proposal.get("execution")

            proposals[existing_index] = {
                **proposal,
                "first_seen_at": first_seen_at,
                "last_seen_at": now,
                "seen_count": seen_count,
                "approval": approval,
                "execution": execution,
            }
            action = "UPDATED_EXISTING"
        else:
            proposals.append({
                **proposal,
                "first_seen_at": now,
                "last_seen_at": now,
                "seen_count": 1,
            })
            if len(proposals) > MAX_PROPOSALS:
                proposals = proposals[-MAX_PROPOSALS:]
            action = "CREATED"

        store["proposals"] = proposals
        store["proposal_count"] = len(proposals)
        store["updated_at"] = now
        _atomic_write(PROPOSAL_STORE_FILE, store)

    return {
        "persisted": True,
        "action": action,
        "proposal_id": proposal_id,
        "proposal_count": len(proposals),
        "store_file": str(PROPOSAL_STORE_FILE),
    }


def update_advisory_policy_proposal(
    proposal_id: str,
    updater,
) -> dict[str, Any] | None:
    """
    Atomically update one persisted proposal.

    `updater` receives a copy of the proposal and must return the replacement
    proposal. This helper is used by the v0.4 review workflow so all proposal
    mutations share the same file lock and atomic writer.
    """
    now = _now_iso()

    with _LOCK:
        store = _read_store_unlocked()
        proposals = store.get("proposals") or []

        index = -1
        for i, item in enumerate(proposals):
            if item.get("proposal_id") == proposal_id:
                index = i
                break

        if index < 0:
            return None

        original = dict(proposals[index])
        updated = updater(dict(original))
        if not isinstance(updated, dict):
            raise ValueError("Proposal updater must return a dict.")

        updated["proposal_id"] = proposal_id
        updated["last_review_update_at"] = now
        proposals[index] = updated

        store["proposals"] = proposals
        store["proposal_count"] = len(proposals)
        store["updated_at"] = now
        _atomic_write(PROPOSAL_STORE_FILE, store)

        return dict(updated)


def get_all_advisory_policy_proposals() -> list[dict[str, Any]]:
    with _LOCK:
        store = _read_store_unlocked()
    return [
        dict(item)
        for item in (store.get("proposals") or [])
        if isinstance(item, dict)
    ]


def get_advisory_policy_proposals(
    limit: int = 100,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 1000))
    with _LOCK:
        store = _read_store_unlocked()

    proposals = store.get("proposals") or []
    return {
        "version": store.get("version", 1),
        "proposal_count": len(proposals),
        "proposals": proposals[-safe_limit:],
        "store_file": str(PROPOSAL_STORE_FILE),
    }


def get_advisory_policy_proposal(
    proposal_id: str,
) -> dict[str, Any] | None:
    with _LOCK:
        store = _read_store_unlocked()

    for proposal in store.get("proposals") or []:
        if proposal.get("proposal_id") == proposal_id:
            return proposal
    return None
