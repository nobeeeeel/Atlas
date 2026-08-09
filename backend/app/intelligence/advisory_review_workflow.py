from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.intelligence.advisory_policy_proposal import (
    get_advisory_policy_proposal,
    get_all_advisory_policy_proposals,
    update_advisory_policy_proposal,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
REVIEW_EVENT_FILE = DATA_DIR / "advisory_review_events.json"

_EVENT_LOCK = threading.Lock()

PENDING_REVIEW_TTL_SECONDS = 15 * 60
APPROVED_TTL_SECONDS = 10 * 60
MAX_EVENTS = 50_000

ACTIVE_REVIEW_STATUSES = {
    "PENDING_APPROVAL",
    "APPROVED",
}

TERMINAL_REVIEW_STATUSES = {
    "REJECTED",
    "EXPIRED",
    "INVALIDATED_SUPERSEDED",
    "INVALIDATED_STALE_CONTEXT",
}


class ReviewWorkflowError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 409,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or {}

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _review_identity(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": proposal.get("proposal_id"),
        "runtime_fingerprint": proposal.get("runtime_fingerprint"),
        "current_policy_epoch": proposal.get("current_policy_epoch"),
        "proposed_policy_epoch": proposal.get("proposed_policy_epoch"),
        "changed_controls": proposal.get("changed_controls") or {},
        "runtime_control_count": proposal.get("runtime_control_count"),
        "recommendation_ready": proposal.get("recommendation_ready"),
        "natural_recommendation_ready": proposal.get("natural_recommendation_ready"),
        "readiness_source": proposal.get("readiness_source"),
        "test_override_active": proposal.get("test_override_active"),
        "test_proposal_nonce": (
            (proposal.get("test_override") or {}).get("proposal_nonce")
        ),
        "review_state": proposal.get("review_state"),
    }


def _review_snapshot_hash(proposal: dict[str, Any]) -> str:
    return _canonical_hash(_review_identity(proposal))[:24]


def _empty_event_store() -> dict[str, Any]:
    now = _now_iso()
    return {
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "event_count": 0,
        "events": [],
        "chain_head": None,
    }


def _read_events_unlocked() -> dict[str, Any]:
    if not REVIEW_EVENT_FILE.exists():
        return _empty_event_store()

    try:
        with REVIEW_EVENT_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_event_store()

    if not isinstance(data, dict):
        return _empty_event_store()
    if not isinstance(data.get("events"), list):
        return _empty_event_store()
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


def _append_event(
    *,
    action: str,
    proposal: dict[str, Any],
    actor: str,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append-only event ledger with a SHA-256 hash chain.

    This is tamper-evident at the application-data level, not a cryptographic
    signature or external immutable log.
    """
    now = _now_iso()

    with _EVENT_LOCK:
        store = _read_events_unlocked()
        events = store.get("events") or []
        previous_hash = (
            events[-1].get("event_hash")
            if events
            else None
        )

        event_core = {
            "sequence": len(events) + 1,
            "timestamp": now,
            "action": action,
            "proposal_id": proposal.get("proposal_id"),
            "runtime_fingerprint": proposal.get("runtime_fingerprint"),
            "proposed_policy_epoch": proposal.get("proposed_policy_epoch"),
            "review_snapshot_hash": _review_snapshot_hash(proposal),
            "actor": actor or "human_operator",
            "note": note,
            "metadata": metadata or {},
            "previous_hash": previous_hash,
        }

        event_hash = _canonical_hash(event_core)
        event = {
            **event_core,
            "event_hash": event_hash,
        }

        events.append(event)
        if len(events) > MAX_EVENTS:
            # Keep the full logical sequence number even if very old rows are
            # trimmed from this local convenience store.
            events = events[-MAX_EVENTS:]

        store["events"] = events
        store["event_count"] = int(store.get("event_count") or 0) + 1
        store["updated_at"] = now
        store["chain_head"] = event_hash
        _atomic_write(REVIEW_EVENT_FILE, store)

    return event


def verify_review_event_chain() -> dict[str, Any]:
    with _EVENT_LOCK:
        store = _read_events_unlocked()
        events = store.get("events") or []

    previous_hash = None
    broken_at = None

    for event in events:
        event_core = {
            key: event.get(key)
            for key in (
                "sequence",
                "timestamp",
                "action",
                "proposal_id",
                "runtime_fingerprint",
                "proposed_policy_epoch",
                "review_snapshot_hash",
                "actor",
                "note",
                "metadata",
                "previous_hash",
            )
        }

        if event.get("previous_hash") != previous_hash:
            broken_at = event.get("sequence")
            break

        expected = _canonical_hash(event_core)
        if expected != event.get("event_hash"):
            broken_at = event.get("sequence")
            break

        previous_hash = event.get("event_hash")

    return {
        "valid": broken_at is None,
        "checked_event_count": len(events),
        "broken_at_sequence": broken_at,
        "chain_head": previous_hash,
        "event_file": str(REVIEW_EVENT_FILE),
        "interpretation": (
            "Hash-chain verification is tamper-evident for the local event file. "
            "It is not an external signature or immutable ledger."
        ),
    }


def get_review_events(
    limit: int = 100,
    proposal_id: str | None = None,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 2000))

    with _EVENT_LOCK:
        store = _read_events_unlocked()
        events = store.get("events") or []

    if proposal_id:
        events = [
            event
            for event in events
            if event.get("proposal_id") == proposal_id
        ]

    return {
        "event_count": len(events),
        "events": events[-safe_limit:],
        "chain_verification": verify_review_event_chain(),
        "event_file": str(REVIEW_EVENT_FILE),
    }


def _normalize_approval(proposal: dict[str, Any]) -> dict[str, Any]:
    approval = dict(proposal.get("approval") or {})
    approval.setdefault("status", "NOT_REQUESTED")
    approval.setdefault("human_approval_required", True)
    approval.setdefault("approved", False)
    approval.setdefault("requested_at", None)
    approval.setdefault("requested_by", None)
    approval.setdefault("approved_at", None)
    approval.setdefault("approved_by", None)
    approval.setdefault("rejected_at", None)
    approval.setdefault("rejected_by", None)
    approval.setdefault("expired_at", None)
    approval.setdefault("invalidated_at", None)
    approval.setdefault("approval_note", None)
    approval.setdefault("review_snapshot_hash", None)
    return approval


def _validate_expected_identity(
    proposal: dict[str, Any],
    *,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
) -> None:
    actual_fp = str(proposal.get("runtime_fingerprint") or "")
    actual_epoch = int(proposal.get("proposed_policy_epoch") or 0)

    if expected_runtime_fingerprint != actual_fp:
        raise ReviewWorkflowError(
            "RUNTIME_FINGERPRINT_MISMATCH",
            "The proposal runtime fingerprint does not match the value the reviewer expected.",
            409,
            {
                "expected": expected_runtime_fingerprint,
                "actual": actual_fp,
            },
        )

    if int(expected_proposed_policy_epoch) != actual_epoch:
        raise ReviewWorkflowError(
            "PROPOSED_EPOCH_MISMATCH",
            "The proposal policy epoch does not match the value the reviewer expected.",
            409,
            {
                "expected": int(expected_proposed_policy_epoch),
                "actual": actual_epoch,
            },
        )


def _set_approval_state(
    proposal_id: str,
    *,
    status: str,
    actor: str,
    note: str | None,
    timestamp_field: str,
    actor_field: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_iso()

    def updater(proposal: dict[str, Any]) -> dict[str, Any]:
        approval = _normalize_approval(proposal)
        approval["status"] = status
        approval["approved"] = status == "APPROVED"
        approval[timestamp_field] = now
        approval[actor_field] = actor or "human_operator"
        approval["approval_note"] = note
        if extra:
            approval.update(extra)
        proposal["approval"] = approval
        proposal["execution"] = {
            "eligible": False,
            "allowed": False,
            "reason": (
                "v0.4 review/approval state is non-executing. "
                "No approval state can write commands.json or mutate Nyao."
            ),
        }
        return proposal

    updated = update_advisory_policy_proposal(
        proposal_id,
        updater,
    )
    if updated is None:
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_FOUND",
            "Advisory proposal not found.",
            404,
        )
    return updated


def refresh_review_expirations() -> dict[str, Any]:
    """
    Expire stale PENDING_APPROVAL and APPROVED records when the workflow is
    observed. No background scheduler is required.
    """
    now = _now()
    changed: list[dict[str, Any]] = []

    for proposal in get_all_advisory_policy_proposals():
        approval = _normalize_approval(proposal)
        status = approval.get("status")

        if status == "PENDING_APPROVAL":
            since = _parse_dt(approval.get("requested_at"))
            ttl = PENDING_REVIEW_TTL_SECONDS
        elif status == "APPROVED":
            since = _parse_dt(approval.get("approved_at"))
            ttl = APPROVED_TTL_SECONDS
        else:
            continue

        if since is None:
            continue

        age = (now - since).total_seconds()
        if age <= ttl:
            continue

        updated = _set_approval_state(
            proposal["proposal_id"],
            status="EXPIRED",
            actor="ATLAS_SYSTEM",
            note=f"{status} exceeded its v0.4 TTL.",
            timestamp_field="expired_at",
            actor_field="expired_by",
            extra={
                "approved": False,
                "expired_from_status": status,
            },
        )
        _append_event(
            action="EXPIRED",
            proposal=updated,
            actor="ATLAS_SYSTEM",
            note=f"{status} exceeded its v0.4 TTL.",
            metadata={
                "expired_from_status": status,
                "age_seconds": round(age, 2),
                "ttl_seconds": ttl,
            },
        )
        changed.append({
            "proposal_id": proposal["proposal_id"],
            "from_status": status,
            "to_status": "EXPIRED",
        })

    return {
        "expired_count": len(changed),
        "expired": changed,
    }


def _ensure_test_override_audit_event(
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    if not bool(proposal.get("test_override_active")):
        return None
    if proposal.get("readiness_source") != "TEST_OVERRIDE":
        return None

    existing = get_review_events(
        limit=2000,
        proposal_id=proposal.get("proposal_id"),
    ).get("events") or []

    for event in existing:
        if event.get("action") == "TEST_READINESS_OVERRIDE":
            return event

    return _append_event(
        action="TEST_READINESS_OVERRIDE",
        proposal=proposal,
        actor="ATLAS_TEST_SYSTEM",
        note=(
            "Recommendation readiness was forced for demo workflow validation. "
            "Natural Atlas readiness remains preserved separately."
        ),
        metadata={
            "natural_recommendation_ready": proposal.get(
                "natural_recommendation_ready"
            ),
            "natural_recommendation_blockers": proposal.get(
                "natural_recommendation_blockers"
            ) or [],
            "readiness_source": proposal.get("readiness_source"),
            "test_proposal_nonce": (
                (proposal.get("test_override") or {}).get("proposal_nonce")
            ),
            "execution_allowed": False,
        },
    )


def reconcile_advisory_review_state(
    current_proposal: dict[str, Any],
) -> dict[str, Any]:
    """
    Automatically invalidate active review/approval records when Atlas's latest
    proposal identity changes.

    This is the core stale-approval defense: approval is bound to exact
    proposal_id + runtime fingerprint + proposed epoch.
    """
    refresh = refresh_review_expirations()
    override_event = _ensure_test_override_audit_event(
        current_proposal,
    )
    current_id = current_proposal.get("proposal_id")
    current_fp = current_proposal.get("runtime_fingerprint")
    current_epoch = current_proposal.get("proposed_policy_epoch")

    invalidated: list[dict[str, Any]] = []

    for proposal in get_all_advisory_policy_proposals():
        if proposal.get("proposal_id") == current_id:
            continue

        approval = _normalize_approval(proposal)
        status = approval.get("status")
        if status not in ACTIVE_REVIEW_STATUSES:
            continue

        stale_context = (
            proposal.get("runtime_fingerprint") != current_fp
            or proposal.get("proposed_policy_epoch") != current_epoch
        )
        if not stale_context:
            # Different proposal_id with the same exact runtime/epoch can happen
            # if recommendation metadata changed. The review identity is still
            # stale because the human approved/requested a different proposal.
            invalidation_status = "INVALIDATED_SUPERSEDED"
        else:
            invalidation_status = "INVALIDATED_STALE_CONTEXT"

        updated = _set_approval_state(
            proposal["proposal_id"],
            status=invalidation_status,
            actor="ATLAS_SYSTEM",
            note="A newer Atlas advisory proposal superseded this review context.",
            timestamp_field="invalidated_at",
            actor_field="invalidated_by",
            extra={
                "approved": False,
                "superseded_by_proposal_id": current_id,
                "superseded_by_runtime_fingerprint": current_fp,
                "superseded_by_proposed_policy_epoch": current_epoch,
                "invalidated_from_status": status,
            },
        )
        _append_event(
            action=invalidation_status,
            proposal=updated,
            actor="ATLAS_SYSTEM",
            note="A newer Atlas advisory proposal superseded this review context.",
            metadata={
                "previous_status": status,
                "current_proposal_id": current_id,
                "current_runtime_fingerprint": current_fp,
                "current_proposed_policy_epoch": current_epoch,
            },
        )
        invalidated.append({
            "proposal_id": proposal.get("proposal_id"),
            "from_status": status,
            "to_status": invalidation_status,
        })

    return {
        "current_proposal_id": current_id,
        "invalidated_count": len(invalidated),
        "invalidated": invalidated,
        "expiration_refresh": refresh,
        "test_override_event": override_event,
    }


def request_human_review(
    proposal_id: str,
    *,
    reviewer: str,
    note: str | None,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
) -> dict[str, Any]:
    refresh_review_expirations()
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_FOUND",
            "Advisory proposal not found.",
            404,
        )

    _validate_expected_identity(
        proposal,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        expected_proposed_policy_epoch=expected_proposed_policy_epoch,
    )

    if not bool(proposal.get("recommendation_ready")):
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_READY",
            "Atlas has not marked this proposal recommendation-ready.",
            409,
            {
                "review_state": proposal.get("review_state"),
                "recommendation_blockers": (
                    proposal.get("recommendation_blockers") or []
                ),
            },
        )

    if proposal.get("review_state") != "READY_FOR_HUMAN_REVIEW":
        raise ReviewWorkflowError(
            "REVIEW_STATE_NOT_READY",
            "Proposal is not in READY_FOR_HUMAN_REVIEW state.",
            409,
            {"review_state": proposal.get("review_state")},
        )

    approval = _normalize_approval(proposal)
    if approval.get("status") != "NOT_REQUESTED":
        raise ReviewWorkflowError(
            "REVIEW_ALREADY_STARTED",
            "This exact proposal already has a review lifecycle.",
            409,
            {"status": approval.get("status")},
        )

    snapshot_hash = _review_snapshot_hash(proposal)
    updated = _set_approval_state(
        proposal_id,
        status="PENDING_APPROVAL",
        actor=reviewer,
        note=note,
        timestamp_field="requested_at",
        actor_field="requested_by",
        extra={
            "review_snapshot_hash": snapshot_hash,
            "expected_runtime_fingerprint": expected_runtime_fingerprint,
            "expected_proposed_policy_epoch": int(expected_proposed_policy_epoch),
        },
    )

    event = _append_event(
        action="REVIEW_REQUESTED",
        proposal=updated,
        actor=reviewer,
        note=note,
        metadata={
            "review_snapshot_hash": snapshot_hash,
        },
    )

    return {
        "proposal": updated,
        "event": event,
        "workflow_state": "PENDING_APPROVAL",
        "execution_allowed": False,
    }


def approve_proposal(
    proposal_id: str,
    *,
    reviewer: str,
    note: str | None,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
) -> dict[str, Any]:
    refresh_review_expirations()
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_FOUND",
            "Advisory proposal not found.",
            404,
        )

    _validate_expected_identity(
        proposal,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        expected_proposed_policy_epoch=expected_proposed_policy_epoch,
    )

    approval = _normalize_approval(proposal)
    if approval.get("status") != "PENDING_APPROVAL":
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_PENDING_APPROVAL",
            "Only PENDING_APPROVAL proposals can be approved.",
            409,
            {"status": approval.get("status")},
        )

    if not bool(proposal.get("recommendation_ready")):
        raise ReviewWorkflowError(
            "READINESS_REVOKED",
            "Recommendation readiness is no longer present.",
            409,
        )

    expected_snapshot = approval.get("review_snapshot_hash")
    actual_snapshot = _review_snapshot_hash(proposal)
    if not expected_snapshot or expected_snapshot != actual_snapshot:
        raise ReviewWorkflowError(
            "REVIEW_SNAPSHOT_CHANGED",
            "The exact proposal identity changed after review was requested.",
            409,
            {
                "expected_review_snapshot_hash": expected_snapshot,
                "actual_review_snapshot_hash": actual_snapshot,
            },
        )

    updated = _set_approval_state(
        proposal_id,
        status="APPROVED",
        actor=reviewer,
        note=note,
        timestamp_field="approved_at",
        actor_field="approved_by",
        extra={
            "approved": True,
            "approval_runtime_fingerprint": expected_runtime_fingerprint,
            "approval_proposed_policy_epoch": int(expected_proposed_policy_epoch),
            "approval_snapshot_hash": actual_snapshot,
        },
    )

    event = _append_event(
        action="APPROVED",
        proposal=updated,
        actor=reviewer,
        note=note,
        metadata={
            "approval_snapshot_hash": actual_snapshot,
            "execution_allowed": False,
        },
    )

    return {
        "proposal": updated,
        "event": event,
        "workflow_state": "APPROVED",
        "execution_allowed": False,
        "warning": (
            "APPROVED in v0.5 means human review approval only. "
            "It does not apply the policy or write a Nyao command."
        ),
    }


def restore_system_invalidated_approval(
    proposal_id: str,
    *,
    actor: str,
    note: str,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
    expected_review_snapshot_hash: str,
) -> dict[str, Any]:
    """Repair an approval invalidated solely by the corrected reconciliation bug."""
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise ReviewWorkflowError("PROPOSAL_NOT_FOUND", "Advisory proposal not found.", 404)
    _validate_expected_identity(
        proposal,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        expected_proposed_policy_epoch=expected_proposed_policy_epoch,
    )
    approval = _normalize_approval(proposal)
    if (
        approval.get("status") != "INVALIDATED_STALE_CONTEXT"
        or approval.get("invalidated_by") != "ATLAS_SYSTEM"
        or not approval.get("approved_at")
        or not approval.get("approval_snapshot_hash")
    ):
        raise ReviewWorkflowError(
            "APPROVAL_NOT_REPAIRABLE",
            "Only a previously approved, system-invalidated stale-context approval can be repaired.",
            409,
            {"approval_status": approval.get("status")},
        )
    actual_snapshot = _review_snapshot_hash(proposal)
    if (
        expected_review_snapshot_hash != actual_snapshot
        or approval.get("approval_snapshot_hash") != actual_snapshot
    ):
        raise ReviewWorkflowError(
            "REPAIR_SNAPSHOT_MISMATCH",
            "The proposal review snapshot no longer matches the original approval.",
            409,
            {
                "expected": expected_review_snapshot_hash,
                "actual": actual_snapshot,
                "original_approval": approval.get("approval_snapshot_hash"),
            },
        )

    repaired_at = _now_iso()

    def updater(current: dict[str, Any]) -> dict[str, Any]:
        current_approval = _normalize_approval(current)
        current_approval.update({
            "status": "APPROVED",
            "approved": True,
            "approval_note": note,
            "restored_at": repaired_at,
            "restored_by": actor,
            "restored_from_status": "INVALIDATED_STALE_CONTEXT",
            "restoration_reason": "CORRECTED_CURRENT_PROPOSAL_RECONCILIATION_BUG",
        })
        current["approval"] = current_approval
        return current

    updated = update_advisory_policy_proposal(proposal_id, updater)
    if updated is None:
        raise ReviewWorkflowError("PROPOSAL_NOT_FOUND", "Advisory proposal not found.", 404)
    event = _append_event(
        action="APPROVAL_RESTORED_AFTER_RECONCILIATION_FIX",
        proposal=updated,
        actor=actor,
        note=note,
        metadata={
            "approval_snapshot_hash": actual_snapshot,
            "runtime_fingerprint": expected_runtime_fingerprint,
            "proposed_policy_epoch": int(expected_proposed_policy_epoch),
        },
    )
    return {
        "proposal": updated,
        "event": event,
        "workflow_state": "APPROVED",
        "execution_allowed": False,
        "repair": True,
    }


def reject_proposal(
    proposal_id: str,
    *,
    reviewer: str,
    note: str | None,
    expected_runtime_fingerprint: str,
    expected_proposed_policy_epoch: int,
) -> dict[str, Any]:
    refresh_review_expirations()
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_FOUND",
            "Advisory proposal not found.",
            404,
        )

    _validate_expected_identity(
        proposal,
        expected_runtime_fingerprint=expected_runtime_fingerprint,
        expected_proposed_policy_epoch=expected_proposed_policy_epoch,
    )

    approval = _normalize_approval(proposal)
    status = approval.get("status")
    if status not in {"PENDING_APPROVAL", "APPROVED"}:
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_REVIEWABLE",
            "Only PENDING_APPROVAL or APPROVED proposals can be rejected.",
            409,
            {"status": status},
        )

    updated = _set_approval_state(
        proposal_id,
        status="REJECTED",
        actor=reviewer,
        note=note,
        timestamp_field="rejected_at",
        actor_field="rejected_by",
        extra={
            "approved": False,
            "rejected_from_status": status,
        },
    )

    event = _append_event(
        action="REJECTED",
        proposal=updated,
        actor=reviewer,
        note=note,
        metadata={"previous_status": status},
    )

    return {
        "proposal": updated,
        "event": event,
        "workflow_state": "REJECTED",
        "execution_allowed": False,
    }


def get_proposal_review_status(
    proposal_id: str,
) -> dict[str, Any]:
    refresh = refresh_review_expirations()
    proposal = get_advisory_policy_proposal(proposal_id)
    if proposal is None:
        raise ReviewWorkflowError(
            "PROPOSAL_NOT_FOUND",
            "Advisory proposal not found.",
            404,
        )

    approval = _normalize_approval(proposal)
    events = get_review_events(
        limit=200,
        proposal_id=proposal_id,
    )

    return {
        "proposal_id": proposal_id,
        "review_state": proposal.get("review_state"),
        "recommendation_ready": proposal.get("recommendation_ready"),
        "approval": approval,
        "execution": proposal.get("execution"),
        "review_snapshot_hash": _review_snapshot_hash(proposal),
        "events": events,
        "expiration_refresh": refresh,
        "ttl_seconds": {
            "pending_approval": PENDING_REVIEW_TTL_SECONDS,
            "approved": APPROVED_TTL_SECONDS,
        },
        "execution_allowed": False,
    }
