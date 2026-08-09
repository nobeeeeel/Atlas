from __future__ import annotations

import json
import os
import tempfile
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from statistics import median

from backend.app.bridge.reader import read_json
from backend.app.bridge.schemas import Command
from backend.app.bridge.writer import write_json
from backend.app.intelligence.llm_cycle_scheduler import (
    get_llm_cycle_schedule,
    record_autonomous_application,
)
from backend.app.intelligence.risk_governor import assess_risk


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
AUTONOMOUS_EVENT_FILE = DATA_DIR / "autonomous_policy_events.json"
AUTONOMOUS_BACKUP_DIR = DATA_DIR / "autonomous_policy_backups"
PENDING_AUTONOMOUS_POLICY_FILE = DATA_DIR / "pending_autonomous_policy.json"
AUTONOMOUS_CONSENSUS_FILE = DATA_DIR / "autonomous_policy_consensus.json"
CONSENSUS_MIN_OBSERVATIONS = 3
CONSENSUS_SUPPORT_RATIO = 0.60
CONSENSUS_MAX_OBSERVATIONS = 96
CONSENSUS_MAX_HISTORY_OBSERVATIONS = 2_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_pending_autonomous_policy() -> dict[str, Any]:
    """Return the symbol-scoped autonomous candidate waiting for a mode boundary."""
    try:
        value = json.loads(PENDING_AUTONOMOUS_POLICY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)



def _read_consensus_store() -> dict[str, Any]:
    """Read the persistent consensus ledger without discarding prior policy windows."""
    try:
        value = json.loads(AUTONOMOUS_CONSENSUS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = {"version": 2, "observations": []}
    if not isinstance(value, dict):
        value = {"version": 2, "observations": []}
    value["version"] = max(2, int(value.get("version") or 1))
    if not isinstance(value.get("observations"), list):
        value["observations"] = []
    return value


def _consensus_history_summary(
    observations: list[dict[str, Any]],
    *,
    current_baseline_epoch: int,
) -> dict[str, Any]:
    """Summarize consensus windows and show the applied epoch each archived window produced."""
    by_epoch: dict[int, list[dict[str, Any]]] = {}
    for row in observations:
        if not isinstance(row, dict):
            continue
        try:
            epoch = int(row.get("baseline_policy_epoch") or 0)
        except (TypeError, ValueError):
            epoch = 0
        by_epoch.setdefault(epoch, []).append(row)

    produced_by_baseline: dict[int, dict[str, Any]] = {}
    try:
        event_store = json.loads(AUTONOMOUS_EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        event_store = {"events": []}
    for event in list(event_store.get("events") or []):
        if not isinstance(event, dict) or event.get("action") != "AUTO_POLICY_APPLIED":
            continue
        try:
            baseline = int(event.get("baseline_policy_epoch") or 0)
            produced = int(event.get("policy_epoch") or 0)
        except (TypeError, ValueError):
            continue
        if produced <= 0:
            continue
        previous = produced_by_baseline.get(baseline)
        if previous is None or int(previous.get("policy_epoch") or 0) <= produced:
            produced_by_baseline[baseline] = {
                "policy_epoch": produced,
                "command_version": int(event.get("command_version") or 0),
                "applied_at": event.get("timestamp"),
                "minimum_dwell_overridden": bool(event.get("minimum_dwell_overridden")),
                "dwell_override_reason": event.get("dwell_override_reason"),
            }

    windows = []
    for epoch, rows in sorted(by_epoch.items(), key=lambda item: item[0], reverse=True):
        times = [_parse(row.get("observed_at")) for row in rows]
        times = [item for item in times if item is not None]
        application = produced_by_baseline.get(epoch) or {}
        windows.append({
            "baseline_policy_epoch": epoch,
            "produced_policy_epoch": application.get("policy_epoch"),
            "produced_command_version": application.get("command_version"),
            "applied_at": application.get("applied_at"),
            "minimum_dwell_overridden": application.get("minimum_dwell_overridden", False),
            "dwell_override_reason": application.get("dwell_override_reason"),
            "observation_count": len(rows),
            "first_observed_at": min(times).isoformat() if times else None,
            "last_observed_at": max(times).isoformat() if times else None,
            "current_window": epoch == int(current_baseline_epoch),
        })

    return {
        "lifetime_observation_count": sum(len(rows) for rows in by_epoch.values()),
        "window_count": len(by_epoch),
        "archived_window_count": sum(1 for epoch in by_epoch if epoch != int(current_baseline_epoch)),
        "recent_windows": windows[:12],
    }


def _baseline_anchor(schedule: dict[str, Any], current_command: dict[str, Any]) -> datetime | None:
    last_applied = _parse(schedule.get("last_auto_applied_at"))
    return last_applied


def _normalize_observations(
    store: dict[str, Any],
    *,
    baseline_epoch: int,
    baseline_anchor: datetime | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in list(store.get("observations") or []):
        if not isinstance(item, dict):
            continue
        if int(item.get("baseline_policy_epoch") or -1) != int(baseline_epoch):
            continue
        observed_at = _parse(item.get("observed_at"))
        if baseline_anchor and observed_at and observed_at < baseline_anchor:
            continue
        rows.append(item)
    return rows[-CONSENSUS_MAX_OBSERVATIONS:]


def _record_consensus_observation(
    *,
    llm_result: dict[str, Any],
    advisory: dict[str, Any],
    schedule: dict[str, Any],
    current_command: dict[str, Any],
) -> dict[str, Any]:
    baseline_epoch = int(advisory.get("current_policy_epoch") or current_command.get("policy_epoch") or 0)
    anchor = _baseline_anchor(schedule, current_command)
    store = _read_consensus_store()
    all_observations = [
        dict(item) for item in list(store.get("observations") or []) if isinstance(item, dict)
    ]
    observations = _normalize_observations(
        {"observations": all_observations}, baseline_epoch=baseline_epoch, baseline_anchor=anchor
    )
    proposal_id = str(advisory.get("proposal_id") or llm_result.get("proposal_id") or "")
    if proposal_id and any(
        str(row.get("proposal_id") or "") == proposal_id
        and int(row.get("baseline_policy_epoch") or -1) == baseline_epoch
        for row in all_observations
    ):
        snapshot = _consensus_snapshot(
            observations=observations,
            current_command=current_command,
            baseline_epoch=baseline_epoch,
            baseline_anchor=anchor,
        )
        return {**snapshot, **_consensus_history_summary(
            all_observations, current_baseline_epoch=baseline_epoch
        )}

    changes: dict[str, Any] = {}
    for name, row in dict(advisory.get("changed_controls") or {}).items():
        if not isinstance(row, dict):
            continue
        changes[str(name)] = {
            "current": row.get("current"),
            "proposed": row.get("shadow"),
            "confidence": row.get("confidence"),
            "rationale": row.get("rationale"),
        }
    observation = {
        "observed_at": _now().isoformat(),
        "proposal_id": proposal_id or None,
        "source_llm_proposal_id": advisory.get("source_llm_proposal_id") or llm_result.get("proposal_id"),
        "baseline_policy_epoch": baseline_epoch,
        "overall_confidence": float(((llm_result.get("bundle") or {}).get("overall_confidence") or 0.0)),
        "changes": changes,
    }
    all_observations.append(observation)
    all_observations = all_observations[-CONSENSUS_MAX_HISTORY_OBSERVATIONS:]
    observations = _normalize_observations(
        {"observations": all_observations}, baseline_epoch=baseline_epoch, baseline_anchor=anchor
    )
    snapshot = _consensus_snapshot(
        observations=observations,
        current_command=current_command,
        baseline_epoch=baseline_epoch,
        baseline_anchor=anchor,
    )
    history = _consensus_history_summary(
        all_observations, current_baseline_epoch=baseline_epoch
    )
    snapshot = {**snapshot, **history}
    _atomic_json(AUTONOMOUS_CONSENSUS_FILE, {
        "version": 2,
        "baseline_policy_epoch": baseline_epoch,
        "baseline_anchor": anchor.isoformat() if anchor else None,
        "updated_at": _now().isoformat(),
        "observations": all_observations,
        "snapshot": snapshot,
        "history": history,
    })
    _event("AUTO_CONSENSUS_OBSERVED", {
        "proposal_id": proposal_id or None,
        "baseline_policy_epoch": baseline_epoch,
        "observation_count": snapshot.get("observation_count"),
        "lifetime_observation_count": snapshot.get("lifetime_observation_count"),
        "consensus_control_count": snapshot.get("consensus_control_count"),
    })
    return snapshot

def _same_direction(value: Any, baseline: Any) -> str | None:
    if isinstance(value, bool) or isinstance(baseline, bool):
        return None
    if isinstance(value, (int, float)) and isinstance(baseline, (int, float)):
        if float(value) > float(baseline):
            return "UP"
        if float(value) < float(baseline):
            return "DOWN"
    return None


def _consensus_snapshot(
    *,
    observations: list[dict[str, Any]],
    current_command: dict[str, Any],
    baseline_epoch: int,
    baseline_anchor: datetime | None,
) -> dict[str, Any]:
    total = len(observations)
    controls: dict[str, dict[str, Any]] = {}
    names = sorted({
        name
        for obs in observations
        for name in dict(obs.get("changes") or {}).keys()
    })
    for name in names:
        baseline = current_command.get(name)
        proposals = []
        for obs in observations:
            row = dict(obs.get("changes") or {}).get(name)
            if isinstance(row, dict) and row.get("proposed") is not None:
                proposals.append(row.get("proposed"))
        if not proposals or total <= 0:
            continue

        selected = None
        support_count = 0
        method = "EXACT_TARGET"
        if isinstance(baseline, bool):
            counts: dict[bool, int] = {}
            for value in proposals:
                if isinstance(value, bool):
                    counts[value] = counts.get(value, 0) + 1
            if counts:
                selected, support_count = max(counts.items(), key=lambda x: x[1])
        elif isinstance(baseline, (int, float)) and not isinstance(baseline, bool):
            directional: dict[str, list[float]] = {"UP": [], "DOWN": []}
            for value in proposals:
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    direction = _same_direction(value, baseline)
                    if direction:
                        directional[direction].append(float(value))
            direction, values = max(directional.items(), key=lambda x: len(x[1]))
            if values:
                support_count = len(values)
                raw = median(values)
                selected = int(round(raw)) if isinstance(baseline, int) else float(raw)
                method = f"DIRECTIONAL_MEDIAN_{direction}"
        else:
            counts: dict[str, tuple[Any, int]] = {}
            for value in proposals:
                key = json.dumps(value, sort_keys=True, default=str)
                existing = counts.get(key)
                counts[key] = (value, (existing[1] if existing else 0) + 1)
            if counts:
                selected, support_count = max(counts.values(), key=lambda x: x[1])

        support_ratio = (support_count / total) if total else 0.0
        ready = bool(
            total >= CONSENSUS_MIN_OBSERVATIONS
            and support_count >= CONSENSUS_MIN_OBSERVATIONS
            and support_ratio >= CONSENSUS_SUPPORT_RATIO
            and selected is not None
            and selected != baseline
        )
        controls[name] = {
            "baseline": baseline,
            "selected": selected,
            "support_count": support_count,
            "observation_count": total,
            "support_ratio": round(support_ratio, 4),
            "ready": ready,
            "method": method,
        }

    patch = {name: row["selected"] for name, row in controls.items() if row.get("ready")}
    return {
        "version": "atlas-autonomous-consensus-v1",
        "baseline_policy_epoch": int(baseline_epoch),
        "baseline_anchor": baseline_anchor.isoformat() if baseline_anchor else None,
        "observation_count": total,
        "minimum_observations": CONSENSUS_MIN_OBSERVATIONS,
        "minimum_support_ratio": CONSENSUS_SUPPORT_RATIO,
        "consensus_control_count": len(patch),
        "ready": bool(patch) and total >= CONSENSUS_MIN_OBSERVATIONS,
        "consensus_patch": patch,
        "controls": controls,
        "recent_proposal_ids": [row.get("proposal_id") for row in observations[-12:]],
    }


def get_autonomous_policy_consensus(
    current_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = _read_consensus_store()
    all_observations = [
        dict(item) for item in list(store.get("observations") or []) if isinstance(item, dict)
    ]
    if current_command is None:
        snapshot = dict(store.get("snapshot") or {
            "version": "atlas-autonomous-consensus-v2",
            "observation_count": 0,
            "consensus_control_count": 0,
            "ready": False,
            "consensus_patch": {},
            "controls": {},
        })
        return {**snapshot, **_consensus_history_summary(
            all_observations,
            current_baseline_epoch=int(snapshot.get("baseline_policy_epoch") or 0),
        )}
    schedule = get_llm_cycle_schedule()
    baseline_epoch = int(current_command.get("policy_epoch") or 0)
    anchor = _baseline_anchor(schedule, current_command)
    observations = _normalize_observations(
        {"observations": all_observations}, baseline_epoch=baseline_epoch, baseline_anchor=anchor
    )
    snapshot = _consensus_snapshot(
        observations=observations,
        current_command=current_command,
        baseline_epoch=baseline_epoch,
        baseline_anchor=anchor,
    )
    snapshot["version"] = "atlas-autonomous-consensus-v2"
    return {**snapshot, **_consensus_history_summary(
        all_observations, current_baseline_epoch=baseline_epoch
    )}

def _consensus_advisory(
    *,
    advisory: dict[str, Any],
    current_command: dict[str, Any],
    consensus: dict[str, Any],
) -> dict[str, Any]:
    patch = dict(consensus.get("consensus_patch") or {})
    proposed_runtime = {**current_command, **patch}
    # Metadata is not part of the 157 runtime policy. Preserve proposal metadata
    # from the live advisory while changing only the selected runtime values.
    proposed_runtime.pop("command_version", None)
    proposed_runtime.pop("policy_epoch", None)
    proposed_runtime.pop("updated_at", None)
    changed = {
        name: {
            "current": current_command.get(name),
            "shadow": value,
            "rationale": "Autonomous dwell-window consensus across accepted Gemini observations.",
            "expected_effect": "Consensus-selected Nyao scalp-policy change.",
            "confidence": round(float((consensus.get("controls") or {}).get(name, {}).get("support_ratio") or 0.0) * 100.0, 1),
        }
        for name, value in patch.items()
    }
    return {
        **advisory,
        "proposed_runtime": proposed_runtime,
        "changed_controls": changed,
        "consensus": consensus,
        "consensus_selected": True,
    }

def _event(action: str, details: dict[str, Any]) -> dict[str, Any]:
    try:
        store = json.loads(AUTONOMOUS_EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        store = {"version": 1, "events": []}
    events = list(store.get("events") or [])
    row = {
        "sequence": len(events) + 1,
        "timestamp": _now().isoformat(),
        "action": action,
        **details,
    }
    events.append(row)
    _atomic_json(AUTONOMOUS_EVENT_FILE, {"version": 1, "events": events[-10000:]})
    return row


def get_autonomous_policy_events(limit: int = 100) -> dict[str, Any]:
    try:
        store = json.loads(AUTONOMOUS_EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        store = {"version": 1, "events": []}
    events = list(store.get("events") or [])
    return {
        "event_count": len(events),
        "events": events[-max(1, min(int(limit), 1000)):][::-1],
        "path": str(AUTONOMOUS_EVENT_FILE),
    }


def _candidate_fingerprint(
    llm_result: dict[str, Any], advisory: dict[str, Any]
) -> str:
    # P3.23B: autonomous identity is the NYAO runtime policy only. Zone policy is
    # deterministic read-only context and is deliberately excluded from the hash.
    material = {
        "baseline_policy_epoch": int(advisory.get("current_policy_epoch") or 0),
        "proposed_runtime": advisory.get("proposed_runtime") or {},
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _zone_campaign_owns_execution(status: dict[str, Any]) -> bool:
    """Return True only when an executable zone campaign owns fresh entries.

    A capital-infeasible zero-leg zone may remain useful context for P3.23A
    zone-aware scalping and must not block autonomous NYAO scalp-policy updates.
    """
    try:
        entry_count = int(status.get("zone_entry_count") or 0)
    except (TypeError, ValueError):
        entry_count = 0
    return bool(
        status.get("zone_mode_active")
        and entry_count > 0
        and status.get("zone_plan_id")
    )


def _pending_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    advisory = dict(candidate.get("advisory") or {})
    llm_result = dict(candidate.get("llm_result") or {})
    return {
        "proposal_id": advisory.get("proposal_id"),
        "candidate_fingerprint": candidate.get("candidate_fingerprint"),
        "baseline_policy_epoch": int(advisory.get("current_policy_epoch") or 0),
        "confidence": float((llm_result.get("bundle") or {}).get("overall_confidence") or 0.0),
        "queued_at": candidate.get("queued_at"),
        "last_seen_at": candidate.get("last_seen_at"),
        "confirmation_count": int(candidate.get("confirmation_count") or 1),
    }


def _queue_zone_boundary_candidate(
    *, llm_result: dict[str, Any], advisory: dict[str, Any]
) -> dict[str, Any]:
    """Keep one stable, auditable candidate while a zone campaign is live."""
    now = _now().isoformat()
    fingerprint = _candidate_fingerprint(llm_result, advisory)
    confidence = float((llm_result.get("bundle") or {}).get("overall_confidence") or 0.0)
    baseline = int(advisory.get("current_policy_epoch") or 0)
    existing = get_pending_autonomous_policy()
    existing_is_pending = existing.get("status") == "PENDING_MODE_BOUNDARY"
    existing_advisory = dict(existing.get("advisory") or {})
    existing_fingerprint = str(existing.get("candidate_fingerprint") or "")
    if existing_is_pending and not existing_fingerprint:
        existing_fingerprint = _candidate_fingerprint(
            dict(existing.get("llm_result") or {}), existing_advisory
        )
    history = list(existing.get("candidate_history") or [])

    if existing_is_pending and existing_fingerprint == fingerprint:
        queued = {
            **existing,
            "candidate_fingerprint": fingerprint,
            "last_seen_at": now,
            "confirmation_count": int(existing.get("confirmation_count") or 1) + 1,
        }
        action = "CONFIRMED"
    else:
        existing_confidence = float(
            ((existing.get("llm_result") or {}).get("bundle") or {}).get("overall_confidence")
            or 0.0
        )
        existing_baseline = int(existing_advisory.get("current_policy_epoch") or 0)
        replace = bool(
            not existing_is_pending
            or baseline != existing_baseline
            or confidence >= existing_confidence + 5.0
        )
        if replace:
            if existing_is_pending:
                history.append(_pending_candidate_summary(existing))
            queued = {
                "status": "PENDING_MODE_BOUNDARY",
                "queued_at": now,
                "last_seen_at": now,
                "confirmation_count": 1,
                "candidate_fingerprint": fingerprint,
                "candidate_history": history[-20:],
                "llm_result": llm_result,
                "advisory": advisory,
            }
            action = "REPLACED" if existing_is_pending else "QUEUED"
        else:
            queued = {
                **existing,
                "candidate_fingerprint": existing_fingerprint,
                "last_challenger_at": now,
                "last_challenger": {
                    "proposal_id": advisory.get("proposal_id"),
                    "candidate_fingerprint": fingerprint,
                    "confidence": confidence,
                    "baseline_policy_epoch": baseline,
                },
            }
            action = "RETAINED"

    _atomic_json(PENDING_AUTONOMOUS_POLICY_FILE, queued)
    active_proposal_id = (queued.get("advisory") or {}).get("proposal_id")
    _event(f"AUTO_PENDING_CANDIDATE_{action}", {
        "active_proposal_id": active_proposal_id,
        "candidate_fingerprint": queued.get("candidate_fingerprint"),
        "confirmation_count": queued.get("confirmation_count"),
        "challenger_proposal_id": advisory.get("proposal_id"),
    })
    return {
        "queue_action": action,
        "active_proposal_id": active_proposal_id,
        "candidate_fingerprint": queued.get("candidate_fingerprint"),
        "confirmation_count": queued.get("confirmation_count"),
    }


def apply_autonomous_llm_policy(
    *,
    llm_result: dict[str, Any],
    advisory: dict[str, Any],
    current_status: dict[str, Any],
    current_command: dict[str, Any],
    command_file: Path,
) -> dict[str, Any]:
    schedule = get_llm_cycle_schedule()
    if schedule.get("execution_mode") != "AUTONOMOUS":
        return {"status": "SUPERVISED_MODE", "applied": False}
    if not llm_result.get("eligible_for_rapid_supervised_review"):
        return {"status": "CRITIC_NOT_ACCEPTED", "applied": False}

    confidence = float(((llm_result.get("bundle") or {}).get("overall_confidence") or 0.0))
    required_confidence = float(schedule.get("minimum_confidence") or 0.0)
    if confidence < required_confidence:
        status = f"CONFIDENCE_BELOW_{required_confidence:.0f}"
        record_autonomous_application(status=status)
        _event("AUTO_APPLY_SKIPPED", {"reason": status, "confidence": confidence})
        return {"status": status, "applied": False}

    advisory_baseline_epoch = int(advisory.get("current_policy_epoch") or 0)
    live_epoch = int(current_command.get("policy_epoch") or 0)
    if advisory_baseline_epoch and advisory_baseline_epoch != live_epoch:
        record_autonomous_application(status="STALE_COMMAND_BASELINE")
        _event("AUTO_APPLY_SKIPPED", {
            "reason": "STALE_COMMAND_BASELINE",
            "advisory_baseline_epoch": advisory_baseline_epoch,
            "live_policy_epoch": live_epoch,
        })
        return {"status": "STALE_COMMAND_BASELINE", "applied": False}

    consensus = _record_consensus_observation(
        llm_result=llm_result,
        advisory=advisory,
        schedule=schedule,
        current_command=current_command,
    )

    # Do not activate a new NYAO scalp runtime while an executable zone campaign
    # owns fresh-entry authority. P3.23A zero-leg zone-aware scalp fallback is not
    # a zone campaign and therefore does not block autonomous scalp-policy updates.
    if _zone_campaign_owns_execution(current_status):
        queue_result = _queue_zone_boundary_candidate(
            llm_result=llm_result,
            advisory=advisory,
        )
        record_autonomous_application(status="DEFERRED_ACTIVE_ZONE_PLAN")
        _event("AUTO_APPLY_DEFERRED", {
            "reason": "ACTIVE_ZONE_PLAN_POLICY_LOCK",
            "zone_plan_id": current_status.get("zone_plan_id"),
        })
        return {
            "status": "DEFERRED_ACTIVE_ZONE_PLAN",
            "applied": False,
            "deferred": True,
            "consensus": consensus,
            **queue_result,
        }

    last_applied = _baseline_anchor(schedule, current_command)
    consensus_required = last_applied is not None
    dwell_minutes = int(schedule.get("minimum_dwell_minutes") or 0)
    capital_protection = dict(current_status.get("_atlas_capital_protection") or {})
    dwell_override = bool(
        capital_protection.get("active")
        and capital_protection.get("dwell_override_eligible")
        and consensus.get("ready")
    )
    if last_applied and (_now() - last_applied).total_seconds() < dwell_minutes * 60 and not dwell_override:
        remaining_seconds = max(
            0.0,
            dwell_minutes * 60 - (_now() - last_applied).total_seconds(),
        )
        eligible_at = last_applied + timedelta(minutes=dwell_minutes)
        record_autonomous_application(
            status="MINIMUM_DWELL_ACTIVE",
            eligible_at=eligible_at,
        )
        _event("AUTO_APPLY_DEFERRED", {
            "reason": "MINIMUM_DWELL_ACTIVE",
            "proposal_id": advisory.get("proposal_id"),
            "minimum_dwell_minutes": dwell_minutes,
            "remaining_seconds": round(remaining_seconds, 3),
        })
        return {
            "status": "MINIMUM_DWELL_ACTIVE",
            "applied": False,
            "deferred": True,
            "remaining_seconds": round(remaining_seconds, 3),
            "consensus": consensus,
        }

    if dwell_override:
        _event("AUTO_DWELL_OVERRIDE_LOSS_PROTECTION", {
            "reason": "LOSS_PROTECTION_CONSENSUS_READY",
            "proposal_id": advisory.get("proposal_id"),
            "loss_protection_state": capital_protection.get("state"),
            "consecutive_losses": capital_protection.get("consecutive_losses"),
            "normal_minimum_dwell_minutes": dwell_minutes,
            "consensus_observation_count": consensus.get("observation_count"),
            "consensus_control_count": consensus.get("consensus_control_count"),
        })

    if consensus_required and not consensus.get("ready"):
        record_autonomous_application(status="CONSENSUS_NOT_READY")
        _event("AUTO_APPLY_DEFERRED", {
            "reason": "CONSENSUS_NOT_READY",
            "proposal_id": advisory.get("proposal_id"),
            "observation_count": consensus.get("observation_count"),
            "minimum_observations": consensus.get("minimum_observations"),
            "consensus_control_count": consensus.get("consensus_control_count"),
        })
        return {
            "status": "CONSENSUS_NOT_READY",
            "applied": False,
            "deferred": True,
            "consensus": consensus,
        }

    if consensus_required:
        advisory = _consensus_advisory(
            advisory=advisory,
            current_command=current_command,
            consensus=consensus,
        )

    risk = assess_risk(current_status)
    if risk.get("veto_new_risk"):
        record_autonomous_application(status="RISK_GOVERNOR_VETO")
        _event("AUTO_APPLY_SKIPPED", {"reason": "RISK_GOVERNOR_VETO", "risk": risk})
        return {"status": "RISK_GOVERNOR_VETO", "applied": False}

    proposed_runtime = dict(advisory.get("proposed_runtime") or {})
    runtime_changed = bool(advisory.get("changed_controls"))
    if not runtime_changed:
        record_autonomous_application(status="KEPT_CURRENT_NYAO_SCALP_POLICY")
        _event("AUTO_POLICY_RETAINED", {
            "proposal_id": advisory.get("proposal_id"),
            "policy_scope": "FULL_157_CONTROL_NYAO_SCALP_POLICY",
        })
        return {"status": "KEPT_CURRENT_NYAO_SCALP_POLICY", "applied": False}

    baseline_version = int(current_command.get("command_version") or 0)
    baseline_epoch = int(current_command.get("policy_epoch") or 0)
    candidate = {
        **current_command,
        **proposed_runtime,
        "command_version": baseline_version + (1 if runtime_changed else 0),
        "policy_epoch": baseline_epoch + (1 if runtime_changed else 0),
        "updated_at": _now(),
    }
    validated = Command.model_validate(candidate)

    identity = f"{_now().strftime('%Y%m%dT%H%M%S')}_{advisory.get('proposal_id') or 'policy'}"
    backup = AUTONOMOUS_BACKUP_DIR / f"{identity}_before.json"
    _atomic_json(backup, {
        "command_before": current_command,
        "source_proposal_id": advisory.get("proposal_id"),
        "policy_scope": "FULL_157_CONTROL_NYAO_SCALP_POLICY",
        "deterministic_authority_excluded": [
            "zone_policy",
            "zone_geometry",
            "zone_campaign_construction",
            "capital_regime",
            "broker_feasibility",
            "risk_governor",
        ],
    })

    write_json(validated, command_file)
    readback = read_json(command_file) or {}
    if (
        int(readback.get("command_version") or 0) != baseline_version + 1
        or int(readback.get("policy_epoch") or 0) != baseline_epoch + 1
    ):
        raise RuntimeError("Autonomous command readback did not match the target epoch.")

    command_version = baseline_version + 1
    policy_epoch = baseline_epoch + 1
    event = _event("AUTO_POLICY_APPLIED", {
        "proposal_id": advisory.get("proposal_id"),
        "confidence": confidence,
        "runtime_changed": True,
        "policy_scope": "FULL_157_CONTROL_NYAO_SCALP_POLICY",
        "zone_policy_mutable": False,
        "baseline_command_version": baseline_version,
        "baseline_policy_epoch": baseline_epoch,
        "command_version": command_version,
        "policy_epoch": policy_epoch,
        "backup": str(backup),
        "consensus_observation_count": consensus.get("observation_count"),
        "consensus_control_count": consensus.get("consensus_control_count"),
        "consensus_patch": consensus.get("consensus_patch"),
        "command_readback_patch": {
            name: readback.get(name)
            for name in dict(consensus.get("consensus_patch") or {})
        },
        "minimum_dwell_overridden": dwell_override,
        "dwell_override_reason": (
            "LOSS_PROTECTION_CONSENSUS_READY" if dwell_override else None
        ),
        "symbol": current_status.get("symbol"),
        "account_fingerprint": current_status.get("account_fingerprint"),
        "loss_protection_active_at_apply": bool(capital_protection.get("active")),
        "fresh_entry_material_change": bool(consensus.get("consensus_patch")),
    })
    record_autonomous_application(
        status="APPLIED",
        command_version=command_version,
        policy_epoch=policy_epoch,
    )
    return {"status": "APPLIED", "applied": True, "event": event}


def apply_ready_loss_protection_consensus(
    *,
    current_status: dict[str, Any],
    current_command: dict[str, Any],
    command_file: Path,
) -> dict[str, Any]:
    """
    During an Atlas loss-protection window, apply an already-qualified consensus
    without waiting for the next Gemini cycle or the normal policy dwell.

    Consensus support, autonomous mode, zone boundaries, schema validation and
    the deterministic risk governor remain mandatory.
    """
    schedule = get_llm_cycle_schedule()
    if schedule.get("execution_mode") != "AUTONOMOUS":
        return {"status": "SUPERVISED_MODE", "applied": False}

    protection = dict(current_status.get("_atlas_capital_protection") or {})
    if not (
        protection.get("active")
        and protection.get("dwell_override_eligible")
        and str(protection.get("state") or "") == "HARD_VETO"
    ):
        return {"status": "LOSS_PROTECTION_NOT_ACTIVE", "applied": False}

    if _zone_campaign_owns_execution(current_status):
        return {"status": "DEFERRED_ACTIVE_ZONE_PLAN", "applied": False}

    consensus = get_autonomous_policy_consensus(current_command)
    if not consensus.get("ready"):
        return {
            "status": "CONSENSUS_NOT_READY",
            "applied": False,
            "consensus": consensus,
        }

    risk = assess_risk(current_status)
    if risk.get("veto_new_risk"):
        return {"status": "RISK_GOVERNOR_VETO", "applied": False}

    patch = dict(consensus.get("consensus_patch") or {})
    if not patch:
        return {"status": "CONSENSUS_NOT_READY", "applied": False, "consensus": consensus}

    baseline_version = int(current_command.get("command_version") or 0)
    baseline_epoch = int(current_command.get("policy_epoch") or 0)
    candidate = {
        **current_command,
        **patch,
        "command_version": baseline_version + 1,
        "policy_epoch": baseline_epoch + 1,
        "updated_at": _now(),
    }
    validated = Command.model_validate(candidate)

    identity = f"{_now().strftime('%Y%m%dT%H%M%S')}_loss_protection_consensus"
    backup = AUTONOMOUS_BACKUP_DIR / f"{identity}_before.json"
    _atomic_json(backup, {
        "command_before": current_command,
        "source": "LOSS_PROTECTION_EXISTING_CONSENSUS",
        "policy_scope": "FULL_157_CONTROL_NYAO_SCALP_POLICY",
        "consensus": consensus,
    })

    write_json(validated, command_file)
    readback = read_json(command_file) or {}
    command_version = baseline_version + 1
    policy_epoch = baseline_epoch + 1
    if (
        int(readback.get("command_version") or 0) != command_version
        or int(readback.get("policy_epoch") or 0) != policy_epoch
    ):
        raise RuntimeError("Loss-protection consensus command readback did not match target epoch.")

    event = _event("AUTO_POLICY_APPLIED", {
        "proposal_id": "LOSS_PROTECTION_EXISTING_CONSENSUS",
        "runtime_changed": True,
        "policy_scope": "FULL_157_CONTROL_NYAO_SCALP_POLICY",
        "baseline_command_version": baseline_version,
        "baseline_policy_epoch": baseline_epoch,
        "command_version": command_version,
        "policy_epoch": policy_epoch,
        "backup": str(backup),
        "consensus_observation_count": consensus.get("observation_count"),
        "consensus_control_count": consensus.get("consensus_control_count"),
        "consensus_patch": patch,
        "command_readback_patch": {name: readback.get(name) for name in patch},
        "minimum_dwell_overridden": True,
        "dwell_override_reason": "LOSS_PROTECTION_EXISTING_CONSENSUS",
        "loss_protection": protection,
        "symbol": current_status.get("symbol"),
        "account_fingerprint": current_status.get("account_fingerprint"),
        "loss_protection_active_at_apply": True,
        "fresh_entry_material_change": bool(patch),
    })
    record_autonomous_application(
        status="APPLIED",
        command_version=command_version,
        policy_epoch=policy_epoch,
    )
    return {
        "status": "APPLIED",
        "applied": True,
        "event": event,
        "consensus": consensus,
    }


def apply_pending_autonomous_policy(
    *,
    current_status: dict[str, Any],
    current_command: dict[str, Any],
    command_file: Path,
) -> dict[str, Any]:
    pending = get_pending_autonomous_policy()
    if not pending:
        return {"status": "NO_PENDING_POLICY", "applied": False}
    if pending.get("status") != "PENDING_MODE_BOUNDARY":
        return {"status": str(pending.get("status") or "NO_PENDING_POLICY"), "applied": False}
    if _zone_campaign_owns_execution(current_status):
        return {"status": "WAITING_FOR_MODE_BOUNDARY", "applied": False}
    result = apply_autonomous_llm_policy(
        llm_result=dict(pending.get("llm_result") or {}),
        advisory=dict(pending.get("advisory") or {}),
        current_status=current_status,
        current_command=current_command,
        command_file=command_file,
    )
    retryable = {
        "MINIMUM_DWELL_ACTIVE",
        "RISK_GOVERNOR_VETO",
        "WAITING_FOR_MODE_BOUNDARY",
        "CONSENSUS_NOT_READY",
    }
    if result.get("status") in retryable:
        _atomic_json(PENDING_AUTONOMOUS_POLICY_FILE, {
            **pending,
            "status": "PENDING_MODE_BOUNDARY",
            "last_attempt_at": _now().isoformat(),
            "last_attempt_result": result,
        })
    else:
        _atomic_json(PENDING_AUTONOMOUS_POLICY_FILE, {
            **pending,
            "status": result.get("status"),
            "resolved_at": _now().isoformat(),
            "result": result,
        })
    return result
