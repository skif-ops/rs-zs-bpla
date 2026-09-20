# EVT-PRE-20 hardware production release gate — Rev.A

Status: `ACTIVE / BLOCKING`

This gate is the release authority for the physical station hardware and its
procurement BOM. It intentionally excludes application firmware, server and
Android deliverables. Software becomes part of this gate only when an explicit
pinout, power sequence, hardware interface or production-test dependency requires
it.

## Engineering release and customer procurement boundary

`hardware design release` proves that the three PCBAs, system components,
mechanics and harness are technically complete and independently reviewed.
It requires production BOM QG-2, completed routing, DRC, CAM, DFM, Review B and
closed mechanical dimensions.

`customer procurement handoff` additionally requires exactly one selected lot
quantity from 4, 10 or 20 stations and a technically controlled procurement
package. Mixing quantity columns is prohibited. Supplier stock, price, MOQ,
payment, freight and destination delivery are customer order-time fields; they
may remain blank and do not block this engineering gate.

The selected lot is `EVT-20` for 20 stations. This closes the lot-selection
condition. Actual purchase execution is owned by the customer. PCB/PCBA,
harness and housing manufacture remains prohibited while technical design,
job-specific DFM or manufacturing-release evidence is blocked.

The eight selected OTS system identities `RB40`, `SLP080S-12M`,
`SCC075010060R`, `SBS050150200`, `G30.B.108111`, `AA.166.A.301111`,
`TI.89.B.2111W` and `CAB.0243` pass their documentary purchase-identity gate.
They are ordered as exact manufacturer MPNs with `NO SUBSTITUTION`; the selected
EVT lot is the qualification batch. This gate requires no stand-alone pre-order
qualification unit, receiving quarantine, mandatory photographs, fixed body count,
future lot/date code or CoC. Commercial availability, price and destination delivery
date are non-blocking customer order-time fields. Physical fit, electrical, thermal, RF and
environmental evidence remains open at assembly, EOL and EVT and still blocks the
hardware design release where applicable.

The production interlock is implemented by:

```bash
python tools/audit_evt_pre_20_hardware_release.py --strict
```

Default mode records the same blockers without failing engineering CI. A PASS
must not be inferred from source completeness, BOM QG-1, placement or partial
routing subgates, or successful software tests.

PCB-MAIN has passed its bounded 2D placement-clearance subgate: the controlled
225-reference repack gives all 227 fitted assembly footprints an explicit
courtyard and the strict audit reports zero component, mounting-exclusion and
U.FL tool-zone conflicts. The authoritative board is now partially routed: 691
segments plus 285 vias, with three copper zones and four rule areas, reflect
accepted bounded ground-domain, hard-signal, OctoSPI and seven-net RF P0
subgates. This is engineering progress only; remaining routing, final DRC,
3D/service evidence, CAM, DFM and independent Review B remain required.

PCB-MAIN also has an accepted human-readable hierarchy-only subgate. Source
commit `9aceca9531f0b9c18679bee1a8050ae7cd94308a` has commit-bound KiCad 9.0.9
ERC with zero violations, an ordered ten-page A2 PDF and exact electrical
equivalence to all 247 physical symbols and 1,077 physical pad occurrences.
Reviewer `Скиф` recorded `ACCEPT_HIERARCHY_ONLY` on `2026-09-16`. This does not
authorize routing, fabrication, assembly, Review B or manufacturing release.

PCB-MAIN also has explicit pre-route constraint coverage for all 186 native
nets. The independent audit enforces disjoint route classes, ground-domain
references, four USB differential-pair segments, seven 50-ohm RF nets and the
controlled modem-feed minimum widths. The official JLCPCB public
`JLC06161H-3313` calculator result is now a bounded numeric engineering routing
basis: `0.1509 mm` for 50-ohm single-ended traces and `0.1537/0.2032 mm` for
90-ohm differential width/gap on L1 over L2. This permits an engineering
candidate only. Pair-aware routing and audit, the returned job stackup,
production tolerance, coupon plan, routed copper, DRC, CAM, DFM and Review B
remain open.

The independent RF/SI return-path review of authoritative PCB SHA-256
`9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`
is `ECO_REQUIRED`. `CELL_RF` and `CELL_RF_ANT` lack the `GND_MODEM` L2
reference assumed by the L1-over-L2 geometry; `PCB-MAIN-RF-RETURN-001`
proposes one bounded local L2 zone. Commit-bound PCB Native Gate `#267` passed
comparative KiCad 9 refill/DRC with 226 -> 226 violations, 429 -> 429
unconnected items and 623/623 covered cellular RF centreline samples. The
candidate is not applied and still requires independent acceptance.
`GNSS_RF_FILTERED` separately
requires a U9/FL1/C64 placement/routing ECO. Neither the accepted RF P0 subgate
nor the cellular proposal closes RF/SI review or authorizes manufacture.

PCB-PWR has explicit pre-route constraint coverage for all 31 native nets. The
independent audit binds the 5 A system basis, both 4 A buck channels, the 3.3 A
BG95 BB+RF peak basis, three separate harness returns/net ties, two switch nodes,
two bootstrap loops, two Kelvin lines, feedback and 100 kHz I2C. Numeric widths,
via arrays and plane geometry remain blocked on `DIM-003`, final current/fault
envelopes, selected stackup/copper weights and thermal/current-density review.
The board remains unrouted with zero copper zones; DRC, CAM, DFM and Review B are
open.

PCB-PWR is no longer a one-page label-only capture. Its native project now has a
system overview and four bounded functional child sheets for input protection and
current monitoring, 3V8 modem power, 3V3 digital power, and 1V8/harness interfaces.
The independent hierarchy audit finds 65 symbols, 189 explicit wire segments,
9 cross-sheet nets, 26 hierarchical labels, no cross-net wire collision and exact
pad/net equivalence to all 62 PCB footprints. This retains the signed pin/net
authority only. The KiCad 9 ERC/PDF evidence and independent hierarchy decision
accepted on `2026-09-16` for source commit
`2a973f6856aa115aa59323d619be985578780682` are historical evidence for the
superseded F1 value. For the post-ECO source at commit
`091a2eb223161cb4396fc6838921eeb79150c38d`, KiCad 9.0.9 ERC reported zero
violations on all five sheets, but independent review found text overlapping
symbols and connection marks in its five-page A3 PDF. That PDF remains
superseded. The presentation-only remediation retains exact pin/net equivalence.
For the remediated source commit
`6ba3ba5d219b95cb7de12f37c4eb646f7f18cfa8`, Schematic Gate
[#35209892756](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35209892756)
passes KiCad 9.0.9 ERC with zero violations on all five sheets; the new A3 PDF
SHA-256 is
`16afef6ecb337109f2a61318c9459167c6d06f4b74534b656c97884c1fed57dd`
and all five pages pass visual preflight without text/symbol/connection overlap
or clipping. The later C20/C21 local-CIN_HF electrical ECO supersedes that
artifact. For active source commit
`e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`, Schematic Gate
[#35217048575](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575)
passes KiCad 9.0.9 ERC with zero violations on all five sheets. Its five-page A3
PDF SHA-256 is
`7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`;
all pages pass visual preflight without text/symbol/connection overlap or
clipping. Reviewer `Скиф` accepted this exact source/PDF pair on `2026-09-17`
with decision `ACCEPT_HIERARCHY_ONLY`. Routing and manufacturing release remain
blocked by the separate gates below.

The independent review's LMR60440 part-mode and LM74700 VCAP document questions
are now closed by the machine-audited
`PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}` record. TI SNAS877 page 3
identifies exact `LMR604403SRAKR` as `3.3V fixed / adjustable`; page 13 defines
the below-1-ohm fixed and above-3-kohm adjustable mode thresholds; TI's
2025-11-08 package-option addendum lists the exact orderable as Active
Production. U3's independently recomputed parallel divider is 26.308 kohm and
its nominal output is 3.801120 V; U4's FB is directly on `3V3_DIGITAL` and
selects fixed 3.3 V. TI SNOSD17G page 5 specifies 0.1 uF VCAP-to-ANODE, matching
C1. This evidence-only change does not alter the native schematic. C11/C12
effective capacitance, routed C11/C20/U3 and C12/C21/U4 hot loops, EMI/filter
decision, F1 qualification, modem-feed physical evidence and all downstream
release gates remain open.

The PCB-PWR input-protection desk review rejects the signed native F1 value
`0451005.MRL` for the 5 A continuous-current basis: Littelfuse's standard 25%
continuous derating reduces it to 3.75 A before temperature rerating. The
controlled BOM and qualification packet select exact candidate
`0451008.MRL` 8 A in the same Nano2 451 land pattern and retain
`SMBJ18A`. The bounded value-only ECO is applied to the active native schematic,
PCB and generators with footprint, placement, topology, nets and pad mapping
retained. This does not extend the prior hierarchy acceptance. The earlier
post-ECO PDF is superseded by the legibility remediation, and the later C20/C21
electrical ECO supersedes the first remediated artifact. Fresh active-source
KiCad 9 ERC/PDF evidence and independent human hierarchy review now pass.
Official Littelfuse/Molex payloads for exact `0451008.MRL`, `SMBJ18A`,
`43045-0213` and `43030-0038` are retrieval-date and SHA-256 bound in
`PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}`. The
input-protection matrix has `4/20` accepted rows
(`PWR-IPQ-001/002/003/004`). `PWR-IPQ-002` is closed from manufacturer
documents and exact-MPN supplier catalogue records, without a receiving
quarantine/photo/body-sample gate. PCBA procurement and manufacturing release
remain prohibited by the remaining physical and release gates.

PCB-PWR has also passed its bounded fitted-body 2D placement-clearance subgate.
All 44 simultaneously fitted footprints have controlled courtyards, the required
minimum is 0.20 mm, the observed minimum is 0.22 mm and conflicts are zero. This
does not close `DIM-003`, mounting or connector/tool service volumes, DNP and DFT
fixture access, assembled STEP, routing, DRC, CAM, DFM or Review B.

The PCB-PWR `DIM-003` mechanical-freeze request is now internally complete and
machine-audited, but its response register has `0/18` accepted rows. The packet
requires final outline and mounting authority, J1/J2 mating and cable volumes,
DFT fixture/probe access, assembled height, enclosure/thermal keep-outs, harness
length datums and a hash-bound frozen STEP. It is an input request only; no
provisional dimension, routing or harness cut length is released.

The PCB-PWR stackup/copper request is internally complete and machine-audited,
but it has `0/24` accepted rows across `0/2` independent fabricator slots and no
selected construction. It requests the actual four-layer cross-section,
material, finished thickness, base/finished copper, hole-wall plating, via and
heavy-copper process limits, mask/finish, panel controls, net test and DFM
traceability. This establishes a controlled external input path only; it does
not authorize numeric current geometry, routing or fabrication.

The PCB-MAIN stackup/impedance request packet is internally ready, but it has
0/2 fabricator responses accepted and no selected construction. Its 22-row
register remains the final job-specific manufacturing-acceptance path. The
separate public numeric routing basis does not populate any response row and is
not Gerber, a purchase order or a fabrication release.

The bounded PCB-MAIN assembler request for `U2`, `U25`, `U26` and `U9` is also
internally ready, but it has 0/14 assembler DFM/stencil responses accepted and
no selected assembler legal entity, manufacturing site or controlled process.
The blank response register does not approve U9 paste, any land/mask/stencil
rule, PnP polarity, first-article assembly, Review B or manufacturing release.

The harness supplier capability packet is internally complete, but it has
`0/16` accepted responses and no selected legal entity, manufacturing site,
supplier assembly MPN, assembly-level temperature rating or accepted wire/crimp
process. It is a capability and quotation input only. Final cut lengths remain
blocked by `DIM-001`, `DIM-003` and `DIM-012`; the packet is not a build release.

All six internally ready external-response packets are now assembled into one
deterministic, source-only request archive controlled by
`manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.{md,json}`. The archive
contains the two-fabricator PCB-MAIN request, PCB-MAIN assembler request,
PCB-PWR DIM-003 request, two-fabricator PCB-PWR request, PCB-MIC DFM request and
harness-supplier request, plus the selected-lot procurement tables. Its
embedded SHA-256 manifest is machine-audited, while every response register
remains pending. This closes only the packaging/issuance preparation subgate;
it is not a quotation, purchase order, routing authority or manufacturing
release.

## Current blocker classes

- physical assembly/EOL/EVT qualification of the documentarily controlled exact
  `BAT1`, `PV1`, `MPPT1`, `MPPT-TEMP`, `ANT-CELL`, `ANT-GNSS`, `ANT-LORA` and
  `RF-PIGTAIL` items; exact supplier/manufacturing identities and release evidence
  for `HARNESS` and `HSG-VC` remain open;
- PCB-MAIN and PCB-PWR routing, DRC and CAM; PCB-PWR `DIM-003`, final stackup,
  numeric current-density/thermal geometry and physical power evidence; PCB-MIC independent Review B,
  CAM comparison, panelization and acoustic-stack review; all three boards'
  DFM and manufacturing release;
- the remaining 17 PCB-PWR input-protection qualification rows after accepted
  manufacturer source control, native-value and repeat-hierarchy gates,
  including +70 C 5 A thermal,
  prospective-current, battery-side primary-fuse and SMBJ18A coordination;
- selected-assembler acceptance of the PCB-MAIN U2/U25/U26 project IPC
  candidates, U9 process-dependent stencil adaptation, PnP polarity,
  first-article controls and closure of blocker/critical DFM findings;
- acceptance of all 18 PCB-PWR `DIM-003` rows in
  `PCB_PWR_DIM_003_RESPONSE_REV_A.csv`, plus the remaining enclosure, antenna,
  harness, installation and environmental mechanical inputs;
- acceptance of both PCB-PWR stackup/copper fabricator sets in the 24-row
  `PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv`, selection of one construction,
  and separate current-density/DC-drop/fault/+70 °C thermal approval;
- acceptance of all 16 attributable harness supplier responses in
  `HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv`, followed by final lengths,
  external endpoints, FAI and physical electrical/SI/thermal validation;
- attributable fabricator, assembler and harness technical responses required
  for the selected construction and build process; commercial quotation,
  availability and delivery fields are customer-owned and non-blocking here.

Physical EVT and operator/SIM evidence remain later acceptance evidence after
stations are assembled; they are not replaced by this pre-production audit.
