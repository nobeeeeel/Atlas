from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence import llm_cycle_scheduler as scheduler


def main() -> None:
    original = scheduler.SCHEDULE_FILE
    try:
        with TemporaryDirectory() as directory:
            scheduler.SCHEDULE_FILE = Path(directory) / "llm_cycle_schedule.json"

            initial = scheduler.get_llm_cycle_schedule()
            assert initial["enabled"] is False
            assert initial["last_status"] == "NEVER_RUN"
            assert initial["manual_application_required"] is True

            configured = scheduler.update_llm_cycle_schedule(
                enabled=True,
                interval_minutes=60,
            )
            assert configured["enabled"] is True
            assert configured["interval_minutes"] == 60
            assert configured["next_run_at"]

            faster = scheduler.update_llm_cycle_schedule(
                enabled=True,
                interval_minutes=15,
                minimum_dwell_minutes=30,
            )
            assert faster["interval_minutes"] == 15
            assert faster["minimum_dwell_minutes"] == 30


            claimed = scheduler.claim_llm_cycle(trigger="TEST", force=True)
            assert claimed["claimed"] is True
            assert claimed["running"] is True

            duplicate = scheduler.claim_llm_cycle(trigger="TEST", force=True)
            assert duplicate["claimed"] is False
            assert duplicate["reason"] == "ALREADY_RUNNING"

            completed = scheduler.complete_llm_cycle(
                status="READY_FOR_HUMAN_REVIEW",
                llm_proposal_id="llm-test",
                advisory_proposal_id="advisory-test",
                critic_verdict="ACCEPT",
            )
            assert completed["running"] is False
            assert completed["run_count"] == 1
            assert completed["last_advisory_proposal_id"] == "advisory-test"

            scheduler.claim_llm_cycle(trigger="TEST_RESTART", force=True)
            recovered = scheduler.recover_interrupted_llm_cycle()
            assert recovered["running"] is False
            assert recovered["last_status"] == "INTERRUPTED_BY_RESTART"
    finally:
        scheduler.SCHEDULE_FILE = original

    print("P3.6 LLM cycle scheduler tests passed.")


if __name__ == "__main__":
    main()
