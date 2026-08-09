from backend.app.intelligence.risk_units import build_risk_units


def row(ticket, pl=None, active=False, layer=1, plan="44d65d08", policy=41):
    base = {
        "ticket": ticket,
        "order_origin": "ATLAS_ZONE",
        "origin_guess": "ATLAS_ZONE",
        "trading_mode": "ZONE",
        "entry_policy_epoch": policy,
        "initial_position": {
            "ticket": ticket,
            "order_origin": "ATLAS_ZONE",
            "entry_comment": f"AZ|{plan}|L{layer}",
            "zone_plan_id": plan,
            "zone_layer": layer,
        },
        "latest_position": {
            "ticket": ticket,
            "order_origin": "ATLAS_ZONE",
            "zone_plan_id": plan,
            "zone_layer": layer,
        },
    }
    if not active:
        base.update({
            "exact_realized_pl_available": True,
            "realized_net_pl": pl,
            "close_time_epoch": 1786274000 + layer,
        })
    return base

# Closed layer losses must remain provisional while another campaign layer is active.
payload = {"closed": [row(1001, -4.0, layer=1), row(1002, -2.0, layer=2)], "active": [row(1003, active=True, layer=3)]}
risk = build_risk_units(payload)
assert risk["unit_count"] == 1, risk
unit = risk["units"][0]
assert unit["unit_type"] == "ZONE_CAMPAIGN", unit
assert unit["state"] == "ACTIVE", unit
assert unit["eligible_for_loss_streak"] is False, unit
assert risk["consecutive_completed_loss_units"] == 0, risk
assert unit["zone_plan_id"] == "44d65d08", unit
assert unit["zone_layers"] == [1, 2, 3], unit

# Once flat, all layers score exactly once as the aggregate campaign result.
payload = {"closed": [row(1001, -4.0, layer=1), row(1002, -2.0, layer=2), row(1003, 10.0, layer=3)], "active": []}
risk = build_risk_units(payload)
unit = risk["units"][0]
assert unit["state"] == "COMPLETE", unit
assert unit["result_class"] == "WIN", unit
assert abs(unit["realized_net_pl"] - 4.0) < 1e-9, unit
assert risk["consecutive_completed_loss_units"] == 0, risk

# Historical exit-only reconstruction can group directly from the immutable AZ comment token.
legacy = {
    "ticket": 231249670,
    "order_origin": "ATLAS_ZONE",
    "origin_guess": "ATLAS_ZONE",
    "trading_mode": "ZONE",
    "entry_policy_epoch": 0,
    "entry_context_quality": "EXIT_ONLY_RECONSTRUCTED",
    "initial_position": {"entry_comment": "AZ|44d65d08|L1"},
    "exact_realized_pl_available": True,
    "realized_net_pl": -1.50,
    "close_time_epoch": 1786216223,
}
risk = build_risk_units({"closed": [legacy], "active": []})
unit = risk["units"][0]
assert unit["unit_type"] == "ZONE_CAMPAIGN", unit
assert unit["unit_id"] == "zone:44d65d08", unit
assert unit["zone_plan_id"] == "44d65d08", unit
assert unit["zone_layers"] == [1], unit

# Producer and bridge must carry zone lineage end-to-end.
from pathlib import Path
root = Path(__file__).resolve().parents[1]
mq5 = (root / "external/nyao/nyao_scalper.mq5").read_text()
schema = (root / "backend/app/bridge/schemas.py").read_text()
outcomes = (root / "backend/app/intelligence/outcomes.py").read_text()
main = (root / "backend/app/main.py").read_text()
assert '#property version "44.3"' in mq5
for token in ("entry_zone_plan_id", "entry_zone_layer", "zone_plan_id", "zone_layer"):
    assert token in schema
assert "AtlasParseZoneLineageComment" in mq5
assert 'parts[0] == "AZ"' in mq5 and 'StringSubstr(parts[3], 0, 1) == "P"' in mq5
assert '"|P" + IntegerToString(atlasZonePolicyEpoch)' in mq5
assert 'entryZonePlanId' in mq5 and 'entryZoneLayer' in mq5
assert '"trading_mode": "ZONE" if entry_order_origin.upper() == "ATLAS_ZONE" else "SCALP"' in outcomes
assert 'id="protect-composite-active"' in main
assert 'id="protect-composite-latest"' in main
print("P3.30.2 zone campaign composite risk-unit regression passed")
