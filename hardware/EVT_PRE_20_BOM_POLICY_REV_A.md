# EVT-PRE-20 Rev.A production BOM policy

Status: \`ACTIVE / PRODUCTION BOM BLOCKED\`

\`hardware/EVT_PRE_20_BOM_REV_A.csv\` is the generated controlled engineering BOM. It
may be used for sourcing work and design review, but it is not a factory release while
QG-2 reports \`BLOCKED\`.

## Required line data

Every fitted electrical, harness and system line must contain:

- one unambiguous assembly and reference designation;
- manufacturer and exact orderable MPN;
- value where applicable, exact package or mechanical form;
- population state, quantity per station, lot quantity, spares and procurement total;
- operating temperature capability compatible with the Rev.A environment rule;
- selection status, source evidence and incoming-control method.

PCBA service and bare-PCB lines use the released fabrication/assembly specification and
approved supplier instead of an electronic-component MPN. Conditional housing options
must have zero quantity unless that variant is formally selected.

## Quantity authority

- one station has one PCB-MAIN, one PCB-PWR and four identical PCB-MIC assemblies;
- four MIC cables require eight \`5040510601\` housings and 48 \`5040520098\` terminals;
- the four MIC leaves and PCB-MAIN require eight \`5040500691\` board headers total;
- one MAIN-PWR cable requires two \`43025-1200\` housings and 24 terminals: 12 power
  terminals \`43030-0038\` and 12 control/I2C terminals \`43030-0001\`;
- \`Qty_20 = Qty_per_station x 20\` and \`Procure_qty = Qty_20 + Spares\` for every row.

## Double control

QG-1 (\`tools/validate_evt_pre_20_bom_qg1.py\`) checks schema, arithmetic, native PCB-PWR
major RefDes mapping, connector MPNs and quantity invariants.

QG-2 (\`tools/audit_evt_pre_20_bom_qg2.py\`) independently compares freeze tables,
checks exact fitted-line fields, verifies schematic RefDes coverage and refuses a
production release while native schematic or system SKU evidence is incomplete.

The actual factory gate is:

\`\`\`bash
python tools/generate_evt_pre_20_bom_rev_a.py
python tools/validate_evt_pre_20_bom_qg1.py
python tools/audit_evt_pre_20_bom_qg2.py --strict
\`\`\`

No spreadsheet cleanup, RFQ response or supplier substitution may bypass the strict
gate or the independent PCB Review A and Review B requirements.
