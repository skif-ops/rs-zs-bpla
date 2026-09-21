# EVT-PRE-20 Rev.A production BOM policy

Status: `ACTIVE / TECHNICAL BOM QG-2 CONTROLLED / HARDWARE RELEASE BLOCKED`

`hardware/EVT_PRE_20_BOM_REV_A.csv` is the generated controlled engineering BOM.
`hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv` is its MPN-level procurement roll-up.
`hardware/EVT_PRE_20_BOM_PRICE_ESTIMATE_REV_A.csv` is the non-binding budgetary
price layer for the same procurement rows.
Both contain explicit lot calculations for 4, 10 and 20 stations. Technical BOM QG-2
reports `PASS` when exact component identities, project-owned build-to-print article
identities and quantity arithmetic are controlled. That result is not a factory release:
supplier selection, job-specific manufacturing evidence and the hardware release gate
remain separate.

Supplier identity is advisory in the price layer. The exact MPN and technical
requirements remain mandatory; a buyer may select another established supplier.
Published prices are dated snapshots and all other values are explicitly marked as
engineering estimates. Cost columns are planning values only: displayed stock is not
a delivery guarantee, and final VAT, customs, dangerous-goods handling, destination
delivery and payment terms are controlled by the customer in the cart or commercial
quotation. Empty quote, stock, MOQ, price, lead-time or delivery fields do not block
technical BOM QG-2 or the customer procurement handoff.

`manufacturing/EVT_LOT_SELECTION_REV_A.csv` is the scenario-selection authority.
`EVT-20` is selected for the current customer. The 4- and 10-station columns remain
controlled comparison scenarios only; quantities and spare columns from different
scenarios must never be mixed. The customer owns purchase execution. Selection does
not authorize PCB/PCBA, harness or housing manufacture while job-specific DFM or the
applicable technical hardware release remains open.

## Required line data

Every fitted electrical, harness and system line must contain:

- one unambiguous assembly and reference designation;
- manufacturer and exact orderable MPN, or a project-owned build-to-print article
  identity for a custom fabrication/assembly scope;
- value where applicable, exact package or mechanical form;
- population state, quantity per station, lot quantities, spares and procurement totals
  for 4, 10 and 20 stations;
- operating temperature capability compatible with the Rev.A environment rule;
- selection status, source evidence and the receipt/assembly/EOL/EVT validation route.

An exact hardware MPN may be `CONTROLLED_PENDING_VERIFICATION` when the remaining
evidence can only be collected on assembled stations. For `U8`, `BG95-M3` is the
controlled hardware identity; article, firmware and IMEI are verified during PCBA
programming/EOL, while operator/SIM attach and representative burst results remain
assembled-station EVT. Those later tests may not be marked PASS in the BOM and do not
revert the exact MPN to an unresolved engineering selection.

The selected system OTS set `BAT1`, `PV1`, `MPPT1`, `MPPT-TEMP`, `ANT-CELL`,
`ANT-GNSS`, `ANT-LORA` and `RF-PIGTAIL` uses a documentary purchase gate. Each line
has an exact manufacturer MPN, current manufacturer authority and a supplier
catalogue/quotation route with `NO SUBSTITUTION`. The selected EVT lot itself is the
qualification batch. A separate pre-order qualification unit, receiving quarantine,
mandatory photographs, fixed incoming body count, future lot/date code and CoC are
not required. Ordinary PO/packing-slip/quantity/damage reconciliation is not a
technical qualification gate; functional, fit, thermal, RF and environmental checks
remain at assembly, EOL and EVT. Battery transport documents remain required where
the chosen SKU and route make them applicable.

The six PCBA/bare-PCB scopes, the harness set and the selected vacuum-cast housing use
the project-owned identities `DIO-ASM-MAIN-REV-A`, `DIO-PCB-MAIN-REV-A`,
`DIO-ASM-PWR-REV-A`, `DIO-PCB-PWR-REV-A`, `DIO-ASM-MIC-REV-A`,
`DIO-PCB-MIC-REV-A`, `DIO-HARNESS-SET-REV-A` and `DIO-HSG-VC-REV-A`.
These identify controlled build-to-print scopes; they are not supplier part numbers,
selected legal entities, accepted process responses or permission to build. Conditional
housing options must have zero quantity unless that variant is formally selected.

The selected procurement route for Rev.A is the **full-PCBA track**: the contract
manufacturer supplies assembled PCB-MAIN, PCB-PWR and PCB-MIC boards with the
specified assembly inspection and EOL controls. Bare-PCB RFQs remain active only as
an alternative quotation and schedule fallback. They are not part of the selected
purchase set and may not be ordered in addition to the PCBA quantities without a new
documented procurement decision. This selection does not bypass Review B, CAM/DFM,
selected-process acceptance or the hardware release gate.

## Quantity authority

- one station has one PCB-MAIN, one PCB-PWR and four identical PCB-MIC assemblies;
- four MIC cables require eight `5040510601` housings and 48 `5040520098` terminals;
- the four MIC leaves and PCB-MAIN require eight `5040500691` board headers total;
- one MAIN-PWR cable requires two `43025-1200` housings and 24 terminals: 12 power
  terminals `43030-0038` and 12 control/I2C terminals `43030-0001`;
- `Qty_N = Qty_per_station x N` and `Procure_qty_N = Qty_N + Spares_N` for
  `N = 4, 10, 20` on every engineering and procurement row.
- The bare-PCB and assembled-PCBA tracks each carry exactly two spare boards of
  every design for every supported lot. Procurement quantities are therefore
  PCB-MAIN/PCB-PWR `N + 2` and PCB-MIC `4N + 2`; the two tracks are alternative
  cost views and must not be summed as independent finished-board purchases. The
  assembled-PCBA quantities are the selected primary procurement quantities; the
  bare-PCB quantities are retained for alternative quotations only.
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
major RefDes mapping, connector MPNs and quantity invariants. Every controlled RFQ
also names its source BOM item or items; QG-1 independently sums their
`Procure_qty_4/10/20` values and requires an exact match to the RFQ quantities.
Dedicated sourcing rows are mandatory for the ten system/mechanical items
`BAT1`, `PV1`, `MPPT1`, `MPPT-TEMP`, `ANT-CELL`, `ANT-GNSS`, `ANT-LORA`,
`RF-PIGTAIL`, `HARNESS` and `HSG-VC`.
The three PCBA service lines `ASM-MAIN`, `ASM-MIC` and `ASM-PWR` and the three bare-PCB
fabrication lines `PCB-MAIN`, `PCB-MIC` and `PCB-PWR` also require six separate RFQs.
The PCBA and bare-PCB quantities must not be merged because they represent separate
supplier quotations and alternative cost tracks, even though both now use the same
fixed reserve of two boards per design. The full-PCBA quotation is the selected route;
bare-PCB quotations remain non-selected alternatives. A PCB-PWR fabrication RFQ may
collect a clearly marked provisional budgetary response, but it is not build
authorization while `DIM-003`, the final stackup/copper weight, routing, CAM and
Review B remain open.

These rows preserve exact scope and 4/10/20 arithmetic for the customer. Their
commercial response fields are optional in the engineering repository. Technical
fabricator, assembler and harness responses are controlled separately by the
job-specific response registers and remain blocking where the design depends on
the selected process.

QG-2 (`tools/audit_evt_pre_20_bom_qg2.py`) independently compares freeze tables,
checks exact fitted-line fields, independently reconstructs the 17 PCB-PWR passive
groups from the 49-row authority, repeats the 4/10/20 lot and roll-up reconciliation,
verifies schematic RefDes coverage and binds all eight custom build-to-print identities
to the supplier-open RFQ boundary. A QG-2 `PASS` releases the technical BOM identity
and quantities only. It does not release routing, fabrication, assembly, harness or
housing manufacture.

`tools/audit_evt_system_ots_procurement_identity_rev_a.py` independently binds the
eight exact OTS identities to the BOM, their RFQs, manufacturer sources, supplier
catalogue records, the no-substitution rule and the non-blocking receipt boundary. It
also prevents the former sample-only/quarantine policy from reappearing in the RFQ
and receipt plan. Passing this documentary audit does not mark any physical test PASS.

`tools/audit_evt_pre_20_bom_workbook.py` reads the XLSX package independently with
the Python standard library. It compares every displayed value in the Engineering
BOM, Procurement, RFQ and Cost estimate worksheets with their CSV authorities and
verifies the native Excel-table ranges, summary lot quantities and gate statuses.
It also recomputes the bare-PCB and primary full-PCBA tracks for lots 4, 10 and 20,
requires exactly two spare boards per design, checks the full-PCBA per-station value
and enforces the approved 15% ceiling against the customer-presented direct BOM.

The release-gate sequence is:

```bash
python tools/generate_evt_pre_20_bom_rev_a.py --check
python tools/validate_evt_pre_20_bom_qg1.py
python tools/audit_evt_pre_20_bom_workbook.py
python tools/audit_evt_system_ots_procurement_identity_rev_a.py
python tools/audit_evt_pre_20_bom_qg2.py --strict
python tools/audit_evt_pre_20_hardware_release.py --strict
```

The BOM QG-2 command is expected to pass; the final hardware-release command remains
blocking until routing, DRC, CAM, job-specific DFM, Review B, mechanics, harness and
physical evidence are complete. No spreadsheet cleanup, RFQ response or supplier
substitution may bypass those controls.
