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
- Supplier stock, price, MOQ, payment, freight and destination delivery are
  customer-owned order-time fields and are not awaited by the engineering gate.
- This archive is primarily a request for technical manufacturing response; a
  recipient may also return a quotation for customer use. It is not a
  fabrication release, assembly release, purchase order or authorization to
  edit source/CAM data.

## Included response packets

| Packet | Recipient | Current acceptance state |
|---|---|---:|
| PCB-MAIN stackup and impedance | Two independent PCB fabricators | 0/2 complete fabricator sets |
| PCB-MAIN DFM/stencil | Selected full-PCBA assembler candidate | 0/14 rows accepted |
| PCB-PWR DIM-003 | Project mechanical/enclosure authority | 18/18 EVT engineering accepted; serial revalidation required |
| PCB-PWR stackup and copper | Two independent PCB fabricators | 0/24 rows and 0/2 sets accepted |
| PCB-MIC DFM/acoustic process | PCB fabricator and assembler | 0/9 rows accepted |
| Complete harness set | Harness supplier candidate | 0/16 rows accepted |

The PCB-PWR DIM-003 packet is retained as accepted EVT traceability; the other
five response packets remain pending. Every returned item must retain its `Gate_ID`, identify the legal entity and
manufacturing site where requested, name the responder and date, and cite the
returned drawing, quotation, calculation or process record. A generic sales
page does not close a job-specific row.

## Native-board boundary

The archive includes native board candidates only to support capability,
mechanical and DFM review. `PCB-MAIN` is partially routed and `PCB-PWR` remains
unrouted. Their files and numeric engineering bases must not be converted into
CAM or fabricated. `PCB-MIC` has routed candidate copper, but its manufacturing
handoff and Review B remain open; the separate
commit-bound PCB Native Gate CAM artifact is still required for an actual DFM
handoff.

No supplier may silently modify a footprint, accepted EVT outline or mounting
drill, layer count,
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
  <https://jlcpcb.com/impedance>. Its official calculator recommends that public
  stack and returns L1/L2 candidate geometry of `0.1509 mm` for 50 ohm and
  `0.1537/0.2032 mm` width/gap for 90 ohm under the controlled inputs recorded
  in `PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json`. Calculator:
  <https://jlcpcb.com/pcb-impedance-calculator>.
- `FAB-B` candidate: PCBWay. Its official stackup pages publish standard
  multilayer constructions and state that job-specific/custom impedance
  constructions may be adjusted for manufacturing capability or material
  stock. Sources:
  <https://www.pcbway.com/multi-layer-laminated-structure.html> and
  <https://www.pcbway.com/pcb_prototype/_Stack_up_for_Prototypes.html>.

These public pages support candidate screening and a bounded PCB-MAIN
engineering routing basis only. They do not provide the site-specific signed
job stackup, production impedance tolerance, coupon plan, DFM closure, plating
tolerances or panel assumptions required by the response registers. All 22
PCB-MAIN fabricator response rows remain pending.

The bundle also includes the bounded PCB-PWR `JLC04161H-3313` / 35 µm numeric
EVT routing basis and its 31-net rule manifest. Those files expose the candidate
4.0 mm / 5 A and 3.0 mm / 4 A assumptions for fabricator review; they neither
accept the 2 oz / 1 oz job target nor populate any of the 24 PCB-PWR response
rows. Final copper, plating, via-current, fault and thermal acceptance remain
job-specific.

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
