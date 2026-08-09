from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import DASHBOARD_TEMPLATE, _advisory_lifecycle  # noqa: E402


def test_applied_lifecycle() -> None:
    proposal = {"review_state": "READY_FOR_HUMAN_REVIEW", "proposed_policy_epoch": 15}
    context = {
        "llm_context_status": {
            "phase": "APPLYING_OR_APPLIED",
            "status_policy_epoch": 15,
        }
    }
    lifecycle = _advisory_lifecycle(proposal, context)
    assert lifecycle["state"] == "APPLIED"
    assert lifecycle["manual_action_complete"] is True


def test_dashboard_uses_execution_lifecycle() -> None:
    assert "reconcileAuthoritativeState" in DASHBOARD_TEMPLATE
    assert 'packageLifecycle=ackEvent?.action==="NYAO_ACK_CONFIRMED"?"APPLIED"' in DASHBOARD_TEMPLATE
    assert 'completedEvent?"Policy applied":"Execute policy"' in DASHBOARD_TEMPLATE
    assert 'ackState==="CONFIRMED"?"Nyao confirmed"' in DASHBOARD_TEMPLATE
    assert "const ackMatchesExecution=Boolean(" in DASHBOARD_TEMPLATE
    assert "ack && completedEvent && ack.execution_id===completedEvent.execution_id" in DASHBOARD_TEMPLATE
    assert "ack?.execution_id===completedEvent?.execution_id?ack.state" not in DASHBOARD_TEMPLATE
    assert "await reconcileAuthoritativeState()" in DASHBOARD_TEMPLATE


if __name__ == "__main__":
    test_applied_lifecycle()
    test_dashboard_uses_execution_lifecycle()
    print("P3.8 dashboard reconciliation checks passed.")
