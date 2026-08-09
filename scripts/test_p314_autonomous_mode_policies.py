from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.bridge.reader import read_json  # noqa: E402
from backend.app.bridge.schemas import Command  # noqa: E402
from backend.app.intelligence import autonomous_policy, llm_cycle_scheduler, zone_policy  # noqa: E402
from backend.app.intelligence.autonomous_policy import (  # noqa: E402
    apply_autonomous_llm_policy,
    apply_pending_autonomous_policy,
)
from backend.app.intelligence.zone_execution_plan import build_zone_execution_plan  # noqa: E402


def _zone_map() -> dict:
    return {
        "state": "DETECTED_NOT_ACTIVATED",
        "symbol": "TESTUSD",
        "map_id": "map-zone-policy",
        "current_price": 100.0,
        "composite_bias": "BULLISH",
        "market_structure": {"M30": {"atr": 1.0}},
        "zones": [{
            "zone_id": "demand-1",
            "side": "DEMAND",
            "low": 99.0,
            "high": 101.0,
            "score": 85.0,
            "timeframe": "H4",
            "kind": "ORDER_BLOCK",
            "status": "FRESH",
            "confluence": ["H1 FVG", "M30 SUPPORT_RESISTANCE"],
        }],
    }


def _status() -> dict:
    return {
        "connected": True,
        "symbol": "TESTUSD",
        "bid": 99.95,
        "ask": 100.05,
        "balance": 5_000.0,
        "equity": 5_000.0,
        "free_margin": 5_000.0,
        "spread_within_limit": True,
        "strategy_open_positions": 0,
        "buy_adjusted_score": 5.0,
        "sell_adjusted_score": 0.0,
        "zone_mode_active": False,
    }


def main() -> None:
    originals = {
        "schedule": llm_cycle_scheduler.SCHEDULE_FILE,
        "zone": zone_policy.ZONE_POLICY_FILE,
        "event": autonomous_policy.AUTONOMOUS_EVENT_FILE,
        "backup": autonomous_policy.AUTONOMOUS_BACKUP_DIR,
        "pending": autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE,
    }
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            llm_cycle_scheduler.SCHEDULE_FILE = root / "schedule.json"
            zone_policy.ZONE_POLICY_FILE = root / "zone_policy.json"
            autonomous_policy.AUTONOMOUS_EVENT_FILE = root / "events.json"
            autonomous_policy.AUTONOMOUS_BACKUP_DIR = root / "backups"
            autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE = root / "pending.json"
            command_file = root / "commands.json"

            plan = build_zone_execution_plan(_zone_map(), _status())
            confirmation = plan["zone_plan"]["confirmation"]["zone_confirmation"]
            assert plan["state"] == "ZONE_ENTRY_CONFIRMED"
            assert confirmation["eligible"] is True
            assert confirmation["directional_score"] == 5.0
            assert confirmation["minimum_directional_score"] == 3.5

            schedule = llm_cycle_scheduler.update_llm_cycle_schedule(
                enabled=True,
                interval_minutes=60,
                execution_mode="AUTONOMOUS",
                minimum_dwell_minutes=60,
                minimum_confidence=70,
            )
            assert schedule["execution_authority"] == "VALIDATED_AUTONOMOUS"
            assert schedule["manual_application_required"] is False

            current = Command().model_dump(mode="json", exclude_none=True)
            result = apply_autonomous_llm_policy(
                llm_result={
                    "eligible_for_rapid_supervised_review": True,
                    "bundle": {"overall_confidence": 80.0},
                    "zone_policy_decision": {
                        "action": "KEEP",
                        "proposed_policy": zone_policy.ZonePolicy().model_dump(mode="json"),
                    },
                },
                advisory={
                    "proposal_id": "auto-1",
                    "changed_controls": {"min_buy_signal_score": {}},
                    "proposed_runtime": {"min_buy_signal_score": 5.0},
                },
                current_status=_status(),
                current_command=current,
                command_file=command_file,
            )
            assert result["applied"] is True
            written = read_json(command_file) or {}
            assert written["command_version"] == int(current["command_version"]) + 1
            assert written["policy_epoch"] == int(current["policy_epoch"]) + 1
            assert written["min_buy_signal_score"] == 5.0

            # A later accepted proposal is queued while a zone plan owns the
            # executor. It remains pending until the mode boundary and dwell
            # requirements both permit activation.
            deferred = apply_autonomous_llm_policy(
                llm_result={
                    "eligible_for_rapid_supervised_review": True,
                    "bundle": {"overall_confidence": 82.0},
                    "zone_policy_decision": {
                        "action": "KEEP",
                        "proposed_policy": zone_policy.ZonePolicy().model_dump(mode="json"),
                    },
                },
                advisory={
                    "proposal_id": "auto-deferred",
                    "current_policy_epoch": written["policy_epoch"],
                    "changed_controls": {"min_sell_signal_score": {}},
                    "proposed_runtime": {"min_sell_signal_score": 5.5},
                },
                current_status={**_status(), "zone_mode_active": True, "zone_plan_id": "plan-1", "zone_entry_count": 3},
                current_command=written,
                command_file=command_file,
            )
            assert deferred["status"] == "DEFERRED_ACTIVE_ZONE_PLAN"
            assert deferred["queue_action"] == "QUEUED"
            pending = read_json(autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE) or {}
            assert pending["status"] == "PENDING_MODE_BOUNDARY"

            confirmed = apply_autonomous_llm_policy(
                llm_result={
                    "eligible_for_rapid_supervised_review": True,
                    "bundle": {"overall_confidence": 84.0},
                    "zone_policy_decision": {
                        "action": "KEEP",
                        "proposed_policy": zone_policy.ZonePolicy().model_dump(mode="json"),
                    },
                },
                advisory={
                    "proposal_id": "same-policy-new-review",
                    "current_policy_epoch": written["policy_epoch"],
                    "changed_controls": {"min_sell_signal_score": {}},
                    "proposed_runtime": {"min_sell_signal_score": 5.5},
                },
                current_status={**_status(), "zone_mode_active": True, "zone_plan_id": "plan-1", "zone_entry_count": 3},
                current_command=written,
                command_file=command_file,
            )
            assert confirmed["queue_action"] == "CONFIRMED"
            assert confirmed["active_proposal_id"] == "auto-deferred"

            retained = apply_autonomous_llm_policy(
                llm_result={
                    "eligible_for_rapid_supervised_review": True,
                    "bundle": {"overall_confidence": 85.0},
                    "zone_policy_decision": {"action": "KEEP"},
                },
                advisory={
                    "proposal_id": "weak-challenger",
                    "current_policy_epoch": written["policy_epoch"],
                    "changed_controls": {"min_sell_signal_score": {}},
                    "proposed_runtime": {"min_sell_signal_score": 6.0},
                },
                current_status={**_status(), "zone_mode_active": True, "zone_plan_id": "plan-1", "zone_entry_count": 3},
                current_command=written,
                command_file=command_file,
            )
            assert retained["queue_action"] == "RETAINED"
            assert retained["active_proposal_id"] == "auto-deferred"

            boundary = apply_pending_autonomous_policy(
                current_status=_status(),
                current_command=written,
                command_file=command_file,
            )
            assert boundary["status"] == "MINIMUM_DWELL_ACTIVE"
            pending = read_json(autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE) or {}
            assert pending["status"] == "PENDING_MODE_BOUNDARY"
    finally:
        llm_cycle_scheduler.SCHEDULE_FILE = originals["schedule"]
        zone_policy.ZONE_POLICY_FILE = originals["zone"]
        autonomous_policy.AUTONOMOUS_EVENT_FILE = originals["event"]
        autonomous_policy.AUTONOMOUS_BACKUP_DIR = originals["backup"]
        autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE = originals["pending"]

    print("P3.14 autonomous mode-policy checks passed.")


if __name__ == "__main__":
    main()
