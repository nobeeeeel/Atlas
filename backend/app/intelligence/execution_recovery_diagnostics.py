from __future__ import annotations

from typing import Any

from backend.app.intelligence.supervised_execution_gate import (
    get_execution_events,
    verify_execution_event_chain,
)


def build_execution_recovery_diagnostics(
    *,
    supervised_command_id: str | None = None,
) -> dict[str, Any]:
    data = get_execution_events(
        limit=5000,
        supervised_command_id=supervised_command_id,
    )
    events = list(data.get("events") or [])

    executions: dict[str, dict[str, Any]] = {}
    for event in reversed(events):
        execution_id = str(event.get("execution_id") or "")
        if not execution_id:
            continue
        row = executions.setdefault(
            execution_id,
            {
                "execution_id": execution_id,
                "supervised_command_id": event.get("supervised_command_id"),
                "actions": [],
                "authorized": False,
                "executed": False,
                "executed_recovered": False,
                "write_failed": False,
                "readback_mismatch": False,
                "ack_terminal": None,
            },
        )
        action = str(event.get("action") or "")
        row["actions"].append(action)
        if action == "EXECUTION_AUTHORIZED":
            row["authorized"] = True
        elif action == "EXECUTED":
            row["executed"] = True
        elif action == "EXECUTED_RECOVERED":
            row["executed_recovered"] = True
        elif action == "EXECUTION_WRITE_FAILED":
            row["write_failed"] = True
        elif action == "EXECUTION_READBACK_MISMATCH":
            row["readback_mismatch"] = True
        elif action in {
            "NYAO_ACK_CONFIRMED",
            "NYAO_ACK_TIMEOUT",
            "NYAO_ACK_MISMATCH",
            "NYAO_ACK_SUPERSEDED_UNCONFIRMED",
        }:
            row["ack_terminal"] = action

    rows = list(executions.values())
    for row in rows:
        row["replay_should_be_blocked"] = bool(
            row["executed"] or row["executed_recovered"]
        )
        row["authorized_without_terminal_write_result"] = bool(
            row["authorized"]
            and not row["executed"]
            and not row["executed_recovered"]
            and not row["write_failed"]
            and not row["readback_mismatch"]
        )

    return {
        "diagnostic_version": "0.8",
        "mode": "EXECUTION_FAILURE_RECOVERY_DIAGNOSTICS",
        "execution_count": len(rows),
        "executions": rows,
        "summary": {
            "replay_block_candidates": sum(
                1 for row in rows if row["replay_should_be_blocked"]
            ),
            "authorized_without_terminal_write_result": sum(
                1
                for row in rows
                if row["authorized_without_terminal_write_result"]
            ),
            "executed_recovered_count": sum(
                1 for row in rows if row["executed_recovered"]
            ),
            "ack_confirmed_count": sum(
                1 for row in rows
                if row["ack_terminal"] == "NYAO_ACK_CONFIRMED"
            ),
            "ack_timeout_count": sum(
                1 for row in rows
                if row["ack_terminal"] == "NYAO_ACK_TIMEOUT"
            ),
            "ack_mismatch_count": sum(
                1 for row in rows
                if row["ack_terminal"] == "NYAO_ACK_MISMATCH"
            ),
            "ack_superseded_unconfirmed_count": sum(
                1
                for row in rows
                if row["ack_terminal"] == "NYAO_ACK_SUPERSEDED_UNCONFIRMED"
            ),
        },
        "hash_chain": verify_execution_event_chain(),
        "interpretation": (
            "Diagnostics classify persisted execution/audit state only. "
            "They do not write commands or change Nyao."
        ),
    }
