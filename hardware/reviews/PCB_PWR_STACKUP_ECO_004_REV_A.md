# PCB-PWR ECO-004 — outer copper 1 oz and LMR60440 land rule, Rev.A

Status: `CANDIDATE / NOT FOR MANUFACTURE`

## Decision

Customer decision 2026-09-24: PCB-PWR outer layers **1 oz (35 um finished)**
instead of 2 oz. Inner layers stay 1 oz (35 um), 4 layers, 1.6 mm ±10 %, ENIG,
minimum average hole-wall plating 18 um. The fabricator stackup identifier is
selected at checkout to match these values.

This record supersedes the 2 oz outer value of `JLC04161H-3313A` for the EVT
order. The historical request/response packets (`PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.*`,
`EVT_ENGINEERING_MANUFACTURING_BASELINE_REV_A.*`) stay byte-identical because
accepted candidate and routing audits bind their SHA-256; order documents
(FAB_NOTES of the EVT build release) take the copper weights from this record.

## Reason

The TI LMR60440 RAK0009A board pattern (SNAS877) places pins 6/7 0.125 mm from
the GND centre pad 2 of U3/U4. JLCPCB publishes a minimum spacing of about 8 mil
(0.2 mm) for 2 oz copper on multilayer boards and 0.09 mm for 1 oz, so the TI land
pattern is manufacturable only with 1 oz outer copper. Narrowing the TI pads was
rejected.

## Electrical impact

None on the accepted routing: the numeric power geometry
(`PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv`, 4.0 mm at 5 A, 3.0 mm at 4 A,
2.1 mm switch nodes) was already sized conservatively for 35 um copper and a
10 °C rise. Thermal and current-density margin that 2 oz would have added is
covered by the physical +70 °C / 5 A evidence on the EVT lot.

## Design rule

`hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_dru`: clearance min 0.12 mm only
between two items of the same regulator footprint (U3 or U4); every route
approaching U3/U4 keeps the board default. The board file is unchanged
(SHA-256 `b12f445d…`).

## Evidence

CI job `pcb-pwr-eco-004-drc` (KiCad 9.0.9, pinned image) runs DRC on the
authoritative board without and with the rule; `tools/audit_pcb_pwr_eco_004_drc_rev_a.py`
requires exactly the four U3/U4 pad-2 to pad-6/7 clearance errors removed, no new
fingerprint and unchanged unconnected items.
