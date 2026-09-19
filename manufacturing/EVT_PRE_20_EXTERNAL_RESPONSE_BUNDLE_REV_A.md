# EVT-PRE-20 external-response request bundle — Rev.A

Status: `READY TO ISSUE FOR ATTRIBUTABLE RESPONSES / NOT A PURCHASE ORDER / NOT FOR MANUFACTURE`

This controlled bundle consolidates the external inputs that now block the
production hardware release. It is intentionally narrower than the full
engineering archive and contains no firmware, server, Android or provisioning
material.

## Procurement boundary

- The selected lot remains `EVT-20`.
- The primary quotation track is full PCBA for `PCB-MAIN`, `PCB-PWR` and
  `PCB-MIC`.
- Bare-board quotations are alternatives only. They are never added to the
  full-PCBA total.
- Quantities for `EVT-4`, `EVT-10` and `EVT-20`, including the controlled board
  reserve, come only from `EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv` and
  `CHINA_PROCUREMENT_RFQ.csv`.
- This archive is a request for technical response and quotation. It is not a
  fabrication release, assembly release, purchase order or authorization to
  edit source/CAM data.

## Included response packets

| Packet | Recipient | Current acceptance state |
|---|---|---:|
| PCB-MAIN stackup and impedance | Two independent PCB fabricators | 0/2 complete fabricator sets |
| PCB-MAIN DFM/stencil | Selected full-PCBA assembler candidate | 0/14 rows accepted |
| PCB-PWR DIM-003 | Project mechanical/enclosure authority | 0/18 rows accepted |
| PCB-PWR stackup and copper | Two independent PCB fabricators | 0/24 rows and 0/2 sets accepted |
| PCB-MIC DFM/acoustic process | PCB fabricator and assembler | 0/9 rows accepted |
| Complete harness set | Harness supplier candidate | 0/16 rows accepted |

Every returned item must retain its `Gate_ID`, identify the legal entity and
manufacturing site where requested, name the responder and date, and cite the
returned drawing, quotation, calculation or process record. A generic sales
page does not close a job-specific row.

## Native-board boundary

The archive includes native board candidates only to support capability,
mechanical and DFM review. `PCB-MAIN` and `PCB-PWR` are unrouted. Their files
must not be converted into CAM or fabricated. `PCB-MIC` has routed candidate
copper, but its manufacturing handoff and Review B remain open; the separate
commit-bound PCB Native Gate CAM artifact is still required for an actual DFM
handoff.

No supplier may silently modify a footprint, outline, drill, layer count,
stackup, copper rule, panel, paste aperture or source file. Every proposed
change returns as a uniquely identified DFM finding and is applied only through
a controlled project ECO.

## Public capability pre-screen

Two Chinese fabricators are suitable candidates for the identical `FAB-A` and
`FAB-B` requests, but neither is selected or accepted by this pre-screen:

- `FAB-A` candidate: JLCPCB. Its official controlled-impedance page publishes
  4- and 6-layer stackups, a 1.6 mm 6-layer option including
  `JLC06161H-3313`, and headline capability of 3.5 mil minimum track/space and
  0.20 mm minimum via. Source:
  <https://jlcpcb.com/impedance>.
- `FAB-B` candidate: PCBWay. Its official stackup pages publish standard
  multilayer constructions and state that job-specific/custom impedance
  constructions may be adjusted for manufacturing capability or material
  stock. Sources:
  <https://www.pcbway.com/multi-layer-laminated-structure.html> and
  <https://www.pcbway.com/pcb_prototype/_Stack_up_for_Prototypes.html>.

These public pages support candidate screening only. They do not provide the
site-specific signed stackup, impedance geometry, coupon plan, DFM closure,
plating tolerances, panel assumptions or quotation evidence required by the
response registers.

## Archive control

Build the deterministic request archive with:

```bash
python tools/build_evt_pre_20_packages.py
```

The expected file is
`artifacts/evt-pre-20-current/Dioneya_EVT_PRE_20_EXTERNAL_RESPONSE_REQUESTS_CURRENT.zip`.
It contains `BUNDLE_MANIFEST.sha256`, which binds every included source byte.
Validate both the archive and `SHA256SUMS.txt` with:

```bash
python tools/audit_evt_pre_20_external_response_bundle.py \
  --archive artifacts/evt-pre-20-current/Dioneya_EVT_PRE_20_EXTERNAL_RESPONSE_REQUESTS_CURRENT.zip \
  --sums artifacts/evt-pre-20-current/SHA256SUMS.txt
```

Archive integrity is not design release. Hardware design release, purchase
release and manufacturing release remain `BLOCKED` until the returned evidence
is accepted and all separate routing, DRC, CAM, DFM, mechanical, physical-test
and Review B gates pass.
