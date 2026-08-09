from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.bridge.reader import read_json  # noqa: E402
from backend.app.bridge.schemas import Command  # noqa: E402
from backend.app.intelligence import autonomous_policy  # noqa: E402


def iso(hours_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def advisory(pid: str, epoch: int, current: float | int, proposed: float | int) -> dict:
    return {
        "proposal_id": pid,
        "current_policy_epoch": epoch,
        "changed_controls": {
            "min_buy_signal_score": {
                "current": current,
                "shadow": proposed,
                "confidence": 80,
            }
        },
        "proposed_runtime": {"min_buy_signal_score": proposed},
    }


def llm(pid: str, confidence: float = 80.0) -> dict:
    return {
        "proposal_id": pid,
        "eligible_for_rapid_supervised_review": True,
        "bundle": {"overall_confidence": confidence},
    }


def main() -> None:
    originals = {
        "consensus": autonomous_policy.AUTONOMOUS_CONSENSUS_FILE,
        "events": autonomous_policy.AUTONOMOUS_EVENT_FILE,
        "backups": autonomous_policy.AUTONOMOUS_BACKUP_DIR,
        "pending": autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE,
        "get_schedule": autonomous_policy.get_llm_cycle_schedule,
        "record_apply": autonomous_policy.record_autonomous_application,
        "risk": autonomous_policy.assess_risk,
    }
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            autonomous_policy.AUTONOMOUS_CONSENSUS_FILE = root / "consensus.json"
            autonomous_policy.AUTONOMOUS_EVENT_FILE = root / "events.json"
            autonomous_policy.AUTONOMOUS_BACKUP_DIR = root / "backups"
            autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE = root / "pending.json"

            current = Command().model_dump(mode="json", exclude_none=True)
            current.update({
                "command_version": 20,
                "policy_epoch": 20,
                "min_buy_signal_score": 7.5,
                "updated_at": iso(5.0),
            })
            schedule = {
                "execution_mode": "AUTONOMOUS",
                "minimum_confidence": 70.0,
                "minimum_dwell_minutes": 240,
                "last_auto_applied_at": iso(5.0),
            }

            # Six of eight accepted Gemini observations support raising the BUY
            # threshold. Two disagree. Consensus should use the median target of
            # the supported direction rather than whichever proposal came last.
            targets = [8.0, 8.0, 8.2, 7.9, 8.1, 8.0, 7.0, 7.2]
            snapshot = None
            for i, target in enumerate(targets, start=1):
                snapshot = autonomous_policy._record_consensus_observation(
                    llm_result=llm(f"llm-{i}"),
                    advisory=advisory(f"proposal-{i}", 20, 7.5, target),
                    schedule=schedule,
                    current_command=current,
                )
            assert snapshot is not None
            row = snapshot["controls"]["min_buy_signal_score"]
            assert snapshot["observation_count"] == 8
            assert row["support_count"] == 6
            assert row["support_ratio"] == 0.75
            assert row["ready"] is True
            assert 7.99 <= float(row["selected"]) <= 8.11

            # Now verify the actual autonomous apply path uses accumulated
            # consensus instead of the final challenger proposal.
            autonomous_policy.AUTONOMOUS_CONSENSUS_FILE.unlink(missing_ok=True)
            for i, target in enumerate([5.0, 5.0, 5.0], start=1):
                autonomous_policy._record_consensus_observation(
                    llm_result=llm(f"seed-llm-{i}"),
                    advisory=advisory(f"seed-{i}", 20, 7.5, target),
                    schedule=schedule,
                    current_command=current,
                )

            autonomous_policy.get_llm_cycle_schedule = lambda: dict(schedule)
            autonomous_policy.record_autonomous_application = lambda **kwargs: kwargs
            autonomous_policy.assess_risk = lambda status: {"veto_new_risk": False}
            command_file = root / "commands.json"

            result = autonomous_policy.apply_autonomous_llm_policy(
                llm_result=llm("final-challenger", 85.0),
                advisory=advisory("final-challenger", 20, 7.5, 6.5),
                current_status={"zone_mode_active": False},
                current_command=current,
                command_file=command_file,
            )
            assert result["applied"] is True
            written = read_json(command_file) or {}
            # 3 of 4 observations support DOWN, and their median is 5.0. The
            # final proposal's 6.5 must not win merely because it was latest.
            assert written["min_buy_signal_score"] == 5.0
            event = result["event"]
            assert event["consensus_observation_count"] == 4
            assert event["consensus_control_count"] >= 1
    finally:
        autonomous_policy.AUTONOMOUS_CONSENSUS_FILE = originals["consensus"]
        autonomous_policy.AUTONOMOUS_EVENT_FILE = originals["events"]
        autonomous_policy.AUTONOMOUS_BACKUP_DIR = originals["backups"]
        autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE = originals["pending"]
        autonomous_policy.get_llm_cycle_schedule = originals["get_schedule"]
        autonomous_policy.record_autonomous_application = originals["record_apply"]
        autonomous_policy.assess_risk = originals["risk"]

    print("P3.25 autonomous policy consensus tests passed")


if __name__ == "__main__":
    main()
