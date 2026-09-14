# EVT-PRE-20 Rev.A production BOM policy

Status: `ACTIVE / PRODUCTION BOM BLOCKED`

`hardware/EVT_PRE_20_BOM_REV_A.csv` is the generated controlled engineering BOM.
`hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv` is its MPN-level procurement roll-up.
Both contain explicit lot calculations for 4, 10 and 20 stations. They may be used for
sourcing work and design review, but they are not a factory release while QG-2 reports
`BLOCKED`.

`manufacturing/EVT_LOT_SELECTION_REV_A.csv` is the scenario-selection authority.
Exactly one scenario must be selected before purchase release; quantities and spare
columns from different scenarios must never be mixed.

## Required line data

Every fitted electrical, harness and system line must contain:

- one unambiguous assembly and reference designation;
- manufacturer and exact orderable MPN;
- value where applicable, exact package or mechanical form;
- population state, quantity per station, lot quantities, spares and procurement totals
  for 4, 10 and 20 stations;
- operating temperature capability compatible with the Rev.A environment rule;
- selection status, source evidence and incoming-control method.

PCBA service and bare-PCB lines use the released fabrication/assembly specification and
approved supplier instead of an electronic-component MPN. Conditional housing options
must have zero quantity unless that variant is formally selected.

## Quantity authority

- one station has one PCB-MAIN, one PCB-PWR and four identical PCB-MIC assemblies;
- four MIC cables require eight `5040510601` housings and 48 `5040520098` terminals;
- the four MIC leaves and PCB-MAIN require eight `5040500691` board headers total;
- one MAIN-PWR cable requires two `43025-1200` housings and 24 terminals: 12 power
  terminals `43030-0038` and 12 control/I2C terminals `43030-0001`;
- `Qty_N = Qty_per_station x N` and `Procure_qty_N = Qty_N + Spares_N` for
  `N = 4, 10, 20` on every engineering and procurement row.
- `SCALE_CEIL_FROM_20_BASELINE` scales the controlled 20-station spare allowance with
  upward rounding. `FIXED_LOT_MIN` keeps the same handling minimum for every supported
  lot. `NONE` requires zero spares.
- DNP lines and non-procured PCB features carry zero spares. PCB-PWR inductors carry a
  fixed minimum of 10 lot spares. Fitted small PCB-PWR passives and the two PCB-MIC
  0402 lines carry a fixed minimum of 40 lot spares. MIC crimp terminals carry one
  complete station spare set, 48 terminals, for every supported lot.

Exact identity, package, and rating evidence normalized during BOM work is recorded in
`hardware/EVT_PRE_20_BOM_EVIDENCE_REV_A.md`.

PCB-PWR passive, net-tie and DFT physical references are sourced only from
`hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv`. The generator groups its 17 procured
or fabricated BOM item IDs from that per-reference authority; DFT points have no BOM
item ID and must not leak into procurement quantities.

## Double control

QG-1 (`tools/validate_evt_pre_20_bom_qg1.py`) checks schema, 4/10/20 arithmetic,
spare-policy application, engineering-to-procurement reconciliation, native PCB-PWR
major RefDes mapping, connector MPNs and quantity invariants.

QG-2 (`tools/audit_evt_pre_20_bom_qg2.py`) independently compares freeze tables,
checks exact fitted-line fields, independently reconstructs the 17 PCB-PWR passive
groups from the 47-row authority, repeats the 4/10/20 lot and roll-up reconciliation,
verifies schematic RefDes coverage and refuses a production release while native
schematic or system SKU evidence is incomplete.

The actual factory gate is:

```bash
python tools/generate_evt_pre_20_bom_rev_a.py --check
python tools/validate_evt_pre_20_bom_qg1.py
python tools/audit_evt_pre_20_bom_qg2.py --strict
python tools/audit_evt_pre_20_hardware_release.py --strict
```

No spreadsheet cleanup, RFQ response or supplier substitution may bypass the strict
gate or the independent PCB Review A and Review B requirements.
