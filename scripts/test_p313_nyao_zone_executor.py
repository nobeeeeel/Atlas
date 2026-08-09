from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.bridge.schemas import Status  # noqa: E402
from backend.app.intelligence.zone_execution_plan import (  # noqa: E402
    CAMPAIGN_REATTACH_GRACE_SECONDS,
    flatten_zone_execution_directive,
    persist_zone_execution_directive,
)
from backend.app.main import DASHBOARD_TEMPLATE  # noqa: E402


NYAO_SOURCE = PROJECT_ROOT / "external" / "nyao" / "nyao_scalper.mq5"


def _plan() -> dict:
    return {
        "symbol": "#BTCUSD",
        "zone_map_id": "map-1",
        "state": "ZONE_ENTRY_CONFIRMED",
        "mode": "ZONE_MODE",
        "ordinary_scalping_allowed": False,
        "directive_preview": {"zone_entry_allowed": True},
        "zone_plan": {
            "plan_id": "plan-1",
            "side": "BUY",
            "stop_loss": 98.0,
            "risk": {"account_risk_pct": 0.5},
            "entries": [
                {"entry_price": 100.0, "risk_allocation_pct": 40.0},
                {"entry_price": 99.5, "risk_allocation_pct": 35.0},
                {"entry_price": 99.0, "risk_allocation_pct": 25.0},
            ],
            "take_profits": [
                {"price": 102.0, "close_allocation_pct": 40.0},
                {"price": 103.0, "close_allocation_pct": 35.0},
                {"price": 104.0, "close_allocation_pct": 25.0},
            ],
        },
    }


def test_flat_directive_contract_and_atomic_persistence() -> None:
    directive = flatten_zone_execution_directive(_plan())
    assert directive["symbol"] == "#BTCUSD"
    assert directive["execution_requested"] is True
    assert directive["suspend_ordinary_scalp_entries"] is True
    assert directive["zone_entry_allowed"] is True
    assert directive["entry_count"] == 3
    assert directive["entry_1_price"] == 100.0
    assert directive["entry_3_risk_pct"] == 25.0
    assert directive["tp_3_price"] == 104.0

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "zone_directive.json"
        persisted = persist_zone_execution_directive(_plan(), path)
        assert json.loads(path.read_text(encoding="utf-8")) == persisted
        assert not path.with_suffix(".tmp").exists()


def test_active_campaign_is_immutable_until_exposure_closes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "zone_directive.json"
        first = persist_zone_execution_directive(_plan(), path)
        replacement = _plan()
        replacement["zone_plan"]["plan_id"] = "plan-2"
        replacement["zone_plan"]["entries"][1]["entry_price"] = 200.0

        locked = persist_zone_execution_directive(
            replacement,
            path,
            status_data={
                "zone_plan_id": "plan-1",
                "strategy_open_positions": 1,
                "working_limit_orders": 2,
            },
        )
        assert locked["campaign_locked"] is True
        assert locked["plan_id"] == "plan-1"
        assert locked["entry_2_price"] == first["entry_2_price"]
        assert locked["state"] == "ZONE_CAMPAIGN_ACTIVE"
        assert locked["zone_entry_allowed"] is True
        assert locked["suspend_ordinary_scalp_entries"] is True

        reattach_held = persist_zone_execution_directive(
            replacement,
            path,
            status_data={
                "zone_plan_id": "plan-1",
                "strategy_open_positions": 0,
                "working_limit_orders": 0,
            },
        )
        assert reattach_held["campaign_locked"] is True
        assert reattach_held["campaign_lock_reason"] == "EA_REATTACH_GRACE"
        assert reattach_held["plan_id"] == "plan-1"
        assert reattach_held["account_risk_pct"] == 0.5

        reattach_held["campaign_last_exposure_epoch"] = (
            reattach_held["generated_at_epoch"]
            - CAMPAIGN_REATTACH_GRACE_SECONDS
            - 1
        )
        path.write_text(json.dumps(reattach_held), encoding="utf-8")
        released = persist_zone_execution_directive(
            replacement,
            path,
            status_data={
                "zone_plan_id": "plan-1",
                "strategy_open_positions": 0,
                "working_limit_orders": 0,
            },
        )
        assert released["campaign_locked"] is False
        assert released["plan_id"] == "plan-2"
        assert released["entry_2_price"] == 200.0


def test_status_acknowledgement_contract() -> None:
    payload = Status().model_dump(mode="json")
    for key in (
        "zone_execution_supported",
        "zone_execution_enabled",
        "zone_directive_fresh",
        "zone_mode_active",
        "zone_scalp_suspended",
        "zone_plan_id",
        "zone_last_execution_reason",
    ):
        assert key in payload


def test_nyao_executor_source_contract() -> None:
    source = NYAO_SOURCE.read_text(encoding="utf-8")
    for marker in (
        "input bool EnableAtlasZoneExecution = true",
        "void ReadAtlasZoneDirective()",
        "void ExecuteAtlasZonePlan()",
        "double AtlasZoneRiskLot(",
        "OrderCalcProfit(direction, _Symbol, 1.0, entryPrice, stopLoss",
        "CancelAtlasOrdinaryPendingOrders();",
        "bool AtlasZoneSpreadTooWide(",
        "VIRTUAL_ZONE_LAYER_WAITING_FOR_TOUCH",
        "IsAllowedToOpenPosition(false)",
        "adaptiveCap < cap",
        '"ATLAS_ZONE_VIRTUAL_LAYER"',
        "leg == 0 && !submittedSamePlan",
        "bool AtlasZoneLegEverFilled(int legIndex)",
        "bool AtlasIsZoneLegComment(string comment, int legIndex)",
        "bool AtlasHasForeignStrategyPosition()",
        'AtlasIsZoneComment(comment) && sideMatches',
        "if(atlasZoneScalpSuspended)",
        'managedPositions[posIndex].orderOrigin == "ATLAS_ZONE"',
        "SignalStrength zoneStrength = GetSignalStrength(direction);",
        "WAITING_FOR_ATLAS_ZONE_CONFIRMATION",
        'json += "\\\"zone_confirmation_score\\\":"',
        'json += "\\\"zone_spread_within_limit\\\":"',
        'json += "\\\"zone_execution_supported\\\":true,"',
    ):
        assert marker in source, marker


def test_dashboard_executor_ack_contract() -> None:
    for marker in (
        "zone_execution_supported",
        "zone_mode_active",
        "ZONE MODE LIVE",
        "LIVE IN NYAO",
        "INSTALL BUILD",
        "MARKET_ON_CONFIRMATION",
        "Live MT5 bid",
        "Closed M30 reference",
    ):
        assert marker in DASHBOARD_TEMPLATE, marker


if __name__ == "__main__":
    test_flat_directive_contract_and_atomic_persistence()
    test_active_campaign_is_immutable_until_exposure_closes()
    test_status_acknowledgement_contract()
    test_nyao_executor_source_contract()
    test_dashboard_executor_ack_contract()
    print("P3.13 Nyao zone executor checks passed.")
