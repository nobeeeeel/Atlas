from __future__ import annotations

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.bridge.schemas import Status

payload = {
    "connected": True,
    "symbol": "#BTCUSD",
    "spread_points": 60950.0,
    "effective_spread_cap_points": 67045.0,
    "spread_within_limit": True,
    "scalp_cost_gate_version": "nyao-scalp-cost-v3",
    "scalp_cost_gate_basis": "STRUCTURE_ADAPTIVE",
    "scalp_cost_limiting_factor": "STOP_AND_TARGET",
    "scalp_cost_adjusted": True,
    "scalp_cost_feasible": True,
    "scalp_cost_headroom_multiplier": 1.10,
    "scalp_base_stop_points": 5509.15,
    "scalp_base_target_points": 8263.725,
    "scalp_planned_stop_points": 335225.0,
    "scalp_planned_target_points": 502837.5,
    "scalp_spread_to_stop_ratio": 0.181818,
    "scalp_spread_to_target_ratio": 0.121212,
    "scalp_max_spread_stop_ratio": 0.20,
    "scalp_max_spread_target_ratio": 0.15,
    "future_nyao_telemetry_probe": "must-survive",
    "recent_exit_deals": [
        {
            "sequence": 7,
            "deal_ticket": 224176876,
            "position_id": 231292871,
            "order_ticket": 231292880,
            "time_epoch": 1786234112,
            "deal_type": "DEAL_TYPE_SELL",
            "deal_entry": "DEAL_ENTRY_OUT",
            "reason": "DEAL_REASON_SL",
            "volume": 0.05,
            "price": 64992.305,
            "net_pl": -5.01,
            "full_close": True,
            "entry_order_ticket": 231292871,
            "entry_time_epoch": 1786234000,
            "entry_time_msc": 1786234000123,
            "entry_price": 65052.0,
            "entry_volume": 0.05,
            "original_position_type": "BUY",
            "entry_comment": "ATLAS|pe=35",
            "entry_policy_epoch": 35,
            "future_exit_probe": 12345,
        }
    ],
}

status = Status.model_validate(payload)
roundtrip = status.model_dump(mode="json")

for key in (
    "scalp_cost_gate_version",
    "scalp_cost_gate_basis",
    "scalp_cost_limiting_factor",
    "scalp_cost_adjusted",
    "scalp_cost_feasible",
    "scalp_cost_headroom_multiplier",
    "scalp_base_stop_points",
    "scalp_base_target_points",
    "scalp_planned_stop_points",
    "scalp_planned_target_points",
    "scalp_spread_to_stop_ratio",
    "scalp_spread_to_target_ratio",
    "scalp_max_spread_stop_ratio",
    "scalp_max_spread_target_ratio",
):
    assert roundtrip[key] == payload[key], key

exit_deal = roundtrip["recent_exit_deals"][0]
for key in (
    "entry_order_ticket",
    "entry_time_epoch",
    "entry_time_msc",
    "entry_price",
    "entry_volume",
    "original_position_type",
    "entry_comment",
    "entry_policy_epoch",
):
    assert exit_deal[key] == payload["recent_exit_deals"][0][key], key

assert roundtrip["future_nyao_telemetry_probe"] == "must-survive"
assert exit_deal["future_exit_probe"] == 12345

print("P3.28/P3.29 bridge round-trip tests passed")


# Exercise the actual FastAPI route functions through the bridge writer/reader.
import tempfile
from pathlib import Path as _Path
import backend.app.main as main_module

with tempfile.TemporaryDirectory() as td:
    temp_status = _Path(td) / "status.json"
    old_status_file = main_module.STATUS_FILE
    main_module.STATUS_FILE = temp_status
    try:
        accepted = main_module.receive_nyao_status(status)
        assert accepted["accepted"] is True
        endpoint_payload = main_module.get_nyao_status()
        assert endpoint_payload["scalp_cost_gate_version"] == "nyao-scalp-cost-v3"
        assert endpoint_payload["scalp_cost_adjusted"] is True
        assert endpoint_payload["recent_exit_deals"][0]["entry_policy_epoch"] == 35
        assert endpoint_payload["recent_exit_deals"][0]["entry_price"] == 65052.0
    finally:
        main_module.STATUS_FILE = old_status_file

print("P3.28/P3.29 API status round-trip tests passed")
