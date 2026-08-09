# P3.30.2 — Zone Campaign Composite Risk Units

This phase completes the composite-risk-unit model for Atlas zone campaigns.

## Behaviour

- Atlas zone positions are no longer scored as standalone strategic outcomes when a durable zone lineage is available.
- Zone layers sharing the same immutable `AZ|<plan-token>|L<n>` lineage are grouped as one `ZONE_CAMPAIGN` risk unit.
- Individual layer exits remain ticket-level execution evidence, but they do not independently increment the completed-loss streak while another campaign layer remains active.
- Once every campaign member is flat, exact realised P/L is summed across the campaign and the campaign receives one `WIN`, `LOSS`, or `FLAT` result.
- Policy-performance and loss-protection consumers continue to use the composite risk-unit stream.

## Durable lineage

Nyao 44.0 now emits zone lineage on both live positions and historical exit telemetry:

- `zone_plan_id`
- `zone_layer`
- `entry_zone_plan_id`
- `entry_zone_layer`

Future zone order comments are written as:

`AZ|<8-char-plan-token>|L<layer>|P<policy_epoch>`

The parser remains backward-compatible with historical comments such as `AZ|44d65d08|L1`.

This also preserves the zone policy epoch across restart / exit-only reconstruction instead of defaulting historical zone trades to epoch 0 when the entry was not observed live.

## Dashboard

Protection Status now shows:

- active composite unit type(s)
- latest completed composite result and aggregate realised P/L

The explanatory copy explicitly states that recovery-chain and zone-campaign legs are scored only through their completed composite unit.

## Regression coverage

`test_p3302_zone_campaign_risk_units.py` verifies:

1. losing zone-layer exits do not increment the strategic loss streak while another campaign layer is active;
2. a completed three-layer campaign is scored once using aggregate realised P/L;
3. historical `AZ|...|L...` entry comments reconstruct into `ZONE_CAMPAIGN` units;
4. zone lineage survives Nyao -> bridge -> outcomes;
5. the UI exposes composite state.

Release versions:

- Atlas backend/dashboard: `1.30.15`
- Nyao source: `44.0`
