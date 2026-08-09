from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.intelligence import autonomous_policy  # noqa: E402


def _advisory(pid: str, epoch: int, proposed: float) -> dict:
    return {
        "proposal_id": pid,
        "current_policy_epoch": epoch,
        "changed_controls": {
            "min_buy_signal_score": {
                "current": 7.5,
                "shadow": proposed,
                "confidence": 80,
            }
        },
    }


def _llm(pid: str) -> dict:
    return {
        "proposal_id": pid,
        "eligible_for_rapid_supervised_review": True,
        "bundle": {"overall_confidence": 80.0},
    }


def main() -> None:
    originals = {
        "consensus": autonomous_policy.AUTONOMOUS_CONSENSUS_FILE,
        "events": autonomous_policy.AUTONOMOUS_EVENT_FILE,
    }
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            autonomous_policy.AUTONOMOUS_CONSENSUS_FILE = root / "consensus.json"
            autonomous_policy.AUTONOMOUS_EVENT_FILE = root / "events.json"

            schedule = {"last_auto_applied_at": None}
            command_20 = {"policy_epoch": 20, "min_buy_signal_score": 7.5}
            first = autonomous_policy._record_consensus_observation(
                llm_result=_llm("llm-20"),
                advisory=_advisory("proposal-20", 20, 8.0),
                schedule=schedule,
                current_command=command_20,
            )
            assert first["observation_count"] == 1
            assert first["lifetime_observation_count"] == 1

            command_21 = {"policy_epoch": 21, "min_buy_signal_score": 7.5}
            second = autonomous_policy._record_consensus_observation(
                llm_result=_llm("llm-21"),
                advisory=_advisory("proposal-21", 21, 8.2),
                schedule=schedule,
                current_command=command_21,
            )
            # A new active policy epoch starts a fresh consensus window, but the
            # previous observation remains archived instead of being erased.
            assert second["observation_count"] == 1
            assert second["lifetime_observation_count"] == 2
            assert second["archived_window_count"] == 1
            store = json.loads((root / "consensus.json").read_text())
            assert len(store["observations"]) == 2
            assert {row["baseline_policy_epoch"] for row in store["observations"]} == {20, 21}
    finally:
        autonomous_policy.AUTONOMOUS_CONSENSUS_FILE = originals["consensus"]
        autonomous_policy.AUTONOMOUS_EVENT_FILE = originals["events"]

    main_py = (PROJECT_ROOT / "backend/app/main.py").read_text(encoding="utf-8")
    assert "with scoped_account_performance(status_data):" in main_py
    assert "Current-window observations" in main_py
    assert "Lifetime observations" in main_py
    assert "EARLY SUPPORT" in main_py
    assert "Recent closed trades" in main_py
    assert "HTF structure" in main_py
    assert "Relation to live thesis" in main_py
    assert 'capitalBadge.textContent=capitalSyncing?"SYNCING"' in main_py

    start = main_py.index("<script>") + len("<script>")
    end = main_py.index("</script>", start)
    js = main_py[start:end].replace("__CONTROL_CONFIG__", "[]")
    with TemporaryDirectory() as directory:
        js_file = Path(directory) / "dashboard.js"
        js_file.write_text(js, encoding="utf-8")
        subprocess.run(["node", "--check", str(js_file)], check=True)

    print("P3.26A truthful state, consensus history, and portfolio records tests passed")


if __name__ == "__main__":
    main()
