from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.agents.policy_proposal import (  # noqa: E402
    GemmaPolicyProposal,
    build_policy_input,
)
from backend.app.bridge.reader import read_json  # noqa: E402
from backend.app.bridge.schemas import Command  # noqa: E402
from backend.app.intelligence import autonomous_policy, llm_cycle_scheduler, zone_policy  # noqa: E402
from backend.app.intelligence.autonomous_policy import apply_autonomous_llm_policy  # noqa: E402
from backend.app.intelligence.parameter_registry import all_parameters  # noqa: E402
from backend.app.main import _build_gemini_scalp_zone_context  # noqa: E402


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
        "zone_spread_within_limit": True,
        "strategy_open_positions": 0,
        "working_limit_orders": 0,
        "buy_adjusted_score": 5.0,
        "sell_adjusted_score": 0.0,
        "zone_mode_active": False,
        "zone_entry_count": 0,
        "volatility_ratio": 1.0,
        "equity_drawdown_pct": 0.0,
        "basket_loss_pct": 0.0,
        "runtime_max_basket_loss_pct": 8.0,
        "basket_risk_remaining_pct": 8.0,
        "buy_lots": 0.0,
        "sell_lots": 0.0,
        "total_lots": 0.0,
        "active_hedge_chains": 0,
        "hedge_chain_loss_pct": 0.0,
        "max_active_hedge_level": 0,
        "max_active_hedge_cycle": 0,
        "trading_paused": False,
        "outside_trading_hours": False,
        "near_market_close": False,
        "leverage_changed": False,
        "runtime_max_open_orders": 8,
        "runtime_enable_duplicate_distance_filter": True,
        "runtime_enable_basket_stop": True,
        "runtime_enable_stop_loss": True,
        "runtime_enable_signal_dampening": True,
        "runtime_enable_loss_management": True,
        "runtime_enable_max_spread_filter": True,
    }


def _parameter_intelligence(command: dict) -> dict:
    return {
        "parameter_evidence": {
            row["name"]: {"current": command.get(row["name"])}
            for row in all_parameters()
        },
        "supervised_candidates": [],
        "top_investigation_candidates": [],
        "llm_evidence_packet": {
            "market_context": {"risk_state": "LOW"},
            "data_quality_warnings": [],
        },
    }


def test_full_nyao_runtime_catalog_is_gemini_scope() -> None:
    command = Command().model_dump(mode="json", exclude_none=True)
    packet = build_policy_input(_status(), _parameter_intelligence(command))
    catalog = {row["parameter"] for row in packet["control_catalog"]}

    assert len(catalog) == len(all_parameters()) == 157

    # Entry, sizing, management, recovery, exits and operational filters all
    # remain part of the NYAO scalp runtime policy presented to Gemini.
    for name in (
        "min_sell_signal_score",
        "base_lot_size",
        "max_lot_size",
        "enable_trailing",
        "trailing_distance_value",
        "enable_partial_close",
        "enable_hedge_chain",
        "hedge_trigger_atr",
        "enable_basket_stop",
        "enable_max_spread_filter",
    ):
        assert name in catalog, name


def test_gemini_schema_has_zone_context_not_zone_mutation() -> None:
    fields = set(GemmaPolicyProposal.model_fields)
    assert "zone_context_assessment" in fields
    assert "zone_policy_decision" not in fields


def test_zone_context_informs_scalping_lane() -> None:
    zone_map = {
        "composite_bias": "BEARISH",
        "nearest_demand": None,
        "nearest_supply": {"zone_id": "supply-1"},
    }
    zone_plan = {
        "state": "ZONE_CAPITAL_INFEASIBLE",
        "mode": "ZONE_MODE",
        "ordinary_scalping_allowed": True,
        "zone_aware_scalping_active": True,
        "zone_aware_scalping_side": "SELL",
        "zone_plan": {
            "side": "SELL",
            "selected_structure": "NO_TRADE",
            "source_zone": {
                "zone_id": "supply-1",
                "side": "SUPPLY",
                "timeframe": "H4",
                "kind": "ORDER_BLOCK",
                "low": 65000.0,
                "high": 65300.0,
                "score": 84.0,
                "status": "FRESH",
                "confluence": ["H1 FVG"],
            },
            "broker_feasibility": {"campaign_feasible": False},
        },
    }
    context = _build_gemini_scalp_zone_context(zone_map, zone_plan, _status())
    assert context["execution_lane"] == "ZONE_AWARE_SCALP"
    assert context["aligned_scalp_direction"] == "SELL"
    assert context["counter_direction_rule"] == "BLOCKED_DETERMINISTICALLY_BY_NYAO"
    assert context["active_zone"]["score"] == 84.0


def test_autonomous_can_apply_full_nyao_control_but_cannot_mutate_zone_policy() -> None:
    originals = {
        "schedule": llm_cycle_scheduler.SCHEDULE_FILE,
        "event": autonomous_policy.AUTONOMOUS_EVENT_FILE,
        "backup": autonomous_policy.AUTONOMOUS_BACKUP_DIR,
        "pending": autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE,
        "zone": zone_policy.ZONE_POLICY_FILE,
    }
    try:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            llm_cycle_scheduler.SCHEDULE_FILE = root / "schedule.json"
            autonomous_policy.AUTONOMOUS_EVENT_FILE = root / "events.json"
            autonomous_policy.AUTONOMOUS_BACKUP_DIR = root / "backups"
            autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE = root / "pending.json"
            zone_policy.ZONE_POLICY_FILE = root / "zone_policy.json"
            command_file = root / "commands.json"

            llm_cycle_scheduler.update_llm_cycle_schedule(
                enabled=True,
                interval_minutes=60,
                execution_mode="AUTONOMOUS",
                minimum_dwell_minutes=60,
                minimum_confidence=70,
            )

            current = Command().model_dump(mode="json", exclude_none=True)
            proposed = dict(current)
            proposed["base_lot_size"] = 0.02
            proposed["enable_hedge_chain"] = False

            before_zone = zone_policy.get_zone_policy()

            result = apply_autonomous_llm_policy(
                llm_result={
                    "eligible_for_rapid_supervised_review": True,
                    "bundle": {"overall_confidence": 90.0},
                    # A stale/malicious legacy key must have zero authority.
                    "zone_policy_decision": {
                        "action": "CHANGE",
                        "proposed_policy": {
                            **before_zone["policy"],
                            "total_risk_pct": 99.0,
                        },
                    },
                },
                advisory={
                    "proposal_id": "p323b-full-runtime",
                    "current_policy_epoch": current["policy_epoch"],
                    "changed_controls": {
                        "base_lot_size": {},
                        "enable_hedge_chain": {},
                    },
                    "proposed_runtime": proposed,
                },
                current_status=_status(),
                current_command=current,
                command_file=command_file,
            )

            assert result["applied"] is True
            written = read_json(command_file) or {}
            assert written["base_lot_size"] == 0.02
            assert written["enable_hedge_chain"] is False

            after_zone = zone_policy.get_zone_policy()
            assert after_zone == before_zone
    finally:
        llm_cycle_scheduler.SCHEDULE_FILE = originals["schedule"]
        autonomous_policy.AUTONOMOUS_EVENT_FILE = originals["event"]
        autonomous_policy.AUTONOMOUS_BACKUP_DIR = originals["backup"]
        autonomous_policy.PENDING_AUTONOMOUS_POLICY_FILE = originals["pending"]
        zone_policy.ZONE_POLICY_FILE = originals["zone"]


def test_zero_leg_zone_aware_scalp_does_not_defer_autonomous_policy() -> None:
    assert autonomous_policy._zone_campaign_owns_execution({
        "zone_mode_active": True,
        "zone_plan_id": "context-only",
        "zone_entry_count": 0,
    }) is False
    assert autonomous_policy._zone_campaign_owns_execution({
        "zone_mode_active": True,
        "zone_plan_id": "campaign",
        "zone_entry_count": 3,
    }) is True


if __name__ == "__main__":
    test_full_nyao_runtime_catalog_is_gemini_scope()
    test_gemini_schema_has_zone_context_not_zone_mutation()
    test_zone_context_informs_scalping_lane()
    test_autonomous_can_apply_full_nyao_control_but_cannot_mutate_zone_policy()
    test_zero_leg_zone_aware_scalp_does_not_defer_autonomous_policy()
    print("P3.23B corrected full-Nyao zone-informed policy tests passed")
