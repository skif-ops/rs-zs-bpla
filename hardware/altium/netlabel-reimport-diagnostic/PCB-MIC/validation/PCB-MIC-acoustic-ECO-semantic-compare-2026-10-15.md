# PCB-MIC acoustic ECO semantic comparison

Result: **PASS**

| Check | Result |
|---|---|
| board_geometry_and_stack_unchanged | PASS |
| components_unchanged | PASS |
| classes_unchanged | PASS |
| exactly_32_mk1_pad3_fragments_changed | PASS |
| mk1_pad3_fragments_moved_radially_outward_0p010mm | PASS |
| exactly_two_gnd_track_endpoints_changed | PASS |
| only_expected_rule_records_changed | PASS |
| clearance_rule_scopes_values_and_priorities_match_baseline | PASS |

## Verified delta

- Changed MK1 pad-3 fragments: 32 of 53 pads.
- Changed GND track objects: 2 of 106 copper objects.
- Added one local 0.125 mm manufacturer-copper rule.
- Narrowed the 0.10 mm acoustic exception to MK1-3 versus MK1-Un1.
- Moved the general 0.20 mm clearance rule to priority 3.
- Board outline, stack, components, net classes and all other semantic objects are unchanged.

## Limits

This report does not by itself prove schematic-to-PCB parity or manufacturing-release readiness.