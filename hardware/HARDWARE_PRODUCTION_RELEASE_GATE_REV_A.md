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
It requires technical BOM QG-2 `PASS`, completed routing, DRC, CAM, DFM, Review B
and closed mechanical dimensions.

`customer procurement handoff` uses one controlled `EVT-20` quantity column per
build lot and a separate aggregate program plan. Mixing per-lot quantity columns
is prohibited. Supplier stock, price, MOQ,
payment, freight and destination delivery are customer order-time fields; they
may remain blank and do not block this engineering gate.

The controlled lot is `EVT-20` for 20 stations. The current program contains two
such lots plus one bench station, 41 stations total, with two independent EVT-20
reserve pools and no third reserve pool for the bench unit. Actual purchase
execution is owned by the customer. PCB/PCBA,
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

Technical BOM QG-2 also controls eight project-owned build-to-print identities for
the six PCB/PCBA scopes, harness set and selected vacuum-cast housing. These internal
article numbers close BOM identity only. The customer-selected supplier legal entity,
quotation and commercial order remain open by design. Standard-process technical
baselines are accepted; routing, checkout DFM, CAM, Review B, mechanics and
physical evidence remain blocking here.

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
U.FL tool-zone conflicts. The authoritative board is now partially routed: 738
segments plus 285 vias (1023 trace items), with eight copper zones and four rule areas, reflect
accepted bounded ground-domain, hard-signal, OctoSPI, seven-net RF P0, USB
MCU-source, cellular-modem and cellular-fixture subgates. This is engineering progress only; remaining routing, final DRC,
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
candidate only. The EVT stackup and ±10% impedance target are accepted;
pair-aware remaining routing, routed-copper review, DRC, CAM, checkout DFM and
Review B remain open.

The two remediations raised by RF/SI return-path review 001 are independently
accepted and applied. `PCB-MAIN-RF-RETURN-001` contributes the exact bounded
local `GND_MODEM` L2 zone accepted after PCB Native Gate `#267`.
`PCB-MAIN-GNSS-RF-ECO-001` keeps U9/J9 fixed, moves only FL1/C64 and reduces
the post-SAW route to 1.326997 mm; its reviewed candidate passed PCB Native
Gate `#273`. The deterministic RF composition is predecessor PCB SHA-256
`f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9`.
The exact accepted R91/R92 USB placement successor SHA-256
`d060e09062fd60b750b09cda029b6529711aab4c14f31c8b3036c21f55cd8d9e`
changes no copper and application commit `1f8c0bad` passed CI `#557` and PCB
Native `#284`. Its accepted USB MCU-source routing successor is authoritative
SHA-256 `76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5`;
application commit `6c27d3ae` passed CI `#562` and PCB Native `#289` with
violations `232→232`, zero new errors and unconnected `429→427`.
Its exact cellular-modem USB successor is authoritative SHA-256
`4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5`;
application commit `4c9a2a85` passed CI `#566` and PCB Native `#293` with
violations `232→232`, zero new errors and unconnected `427→425`.
Its exact cellular-fixture USB successor is authoritative SHA-256
`2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273`.
Proposal commit `11af5c9d` passed CI `#568` and PCB Native `#295` with
violations `232→232`, zero new errors and unconnected `425→421`; the exact
candidate is applied in commit `8acd6579`. Gate-source commit `c48217af`
passed CI `#570` and PCB Native `#297` with the same `232→232`, zero-new-error
and `425→421` result. Artifact `10615386189` has digest
`sha256:39b47e938a23aece20d62a269352334af1ca3d5b0e3f37d156726eac840eaabd`;
the fixture application gate is closed.
Commit-bound source commit `7ee9cfc9` passed CI `#550` and PCB Native Gate
`#277`: comparative DRC added no errors or unconnected regression, and both
filled-reference audits cover every cellular and GNSS sample. The bounded
repeat return-path review is therefore complete. Neither application authorizes
manufacture; remaining routing, final SI/PI, checkout DFM, Review B and CAM
remain open.

PCB-PWR has explicit pre-route constraint coverage for all 31 native nets. The
independent audit binds the 5 A system basis, both 4 A buck channels, the 3.3 A
BG95 BB+RF peak basis, three separate harness returns/net ties, two switch nodes,
two bootstrap loops, two Kelvin lines, feedback and 100 kHz I2C. `DIM-003` is
accepted `18/18` for EVT. A separate public `JLC04161H-3313A` reference and
conservative 35 µm / 10 °C-rise screen now pass as a bounded numeric EVT routing
input: 4.0 mm at 5 A, 3.0 mm at 4 A, 2.1 mm for local switch nodes and 0.5 mm
at 0.3 A across a 31-net manifest. JLC04161H-3313A, 70/35 µm copper and minimum
18 µm average hole-wall plating are accepted for EVT; via sharing, current/fault
envelopes and physical thermal/current-density evidence remain open. The active
board contains exactly 14 accepted trace items after exact power-stage ECO-002
application, with zero vias and zero copper zones. The predecessor `REV_GATE`
routing 004 application gate is closed; the ECO-002 commit-bound application
gate, physical +70 °C first-article validation, all remaining routing, DRC, CAM,
checkout DFM and Review B are open.

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
minimum is 0.20 mm, the observed minimum is 0.22 mm and conflicts are zero. The
four accepted H1-H4 mounting exclusions also have zero fitted-body/pad conflicts
and 0.53 mm minimum fitted-body margin. DNP service review, exact serial enclosure
fit, routing, DRC, CAM, DFM and Review B remain open.

The exact accepted PCB-PWR dual-buck placement ECO-001 was applied byte-for-byte:
only C4, C6, L1 and L2 moved, that historical placement candidate was unrouted, and all 44 fitted
courtyards still pass and the minimum clearance remains 0.22 mm. CI #583 and
PCB Native #310 pass for source commit `878425d2`, with zero new error classes
and `126 -> 126` unconnected items. This placement subgate is not a routing or
manufacturing release.

The separate hash-bound warning-remediation successor preserves all component
poses and pad copper geometry, canonically normalizes only C4/C6 rotated child
data, retains both C4/C6 reference centres and moves only the visible R10
reference. Native run 312 rejected the first serialization after detecting two
replacement reference-to-mask warnings; the corrected candidate passes CI #586,
PCB-PWR Schematic #65 and PCB Native #313. The comparative result is exact:
`90 -> 86` violations, `126 -> 126` unconnected items, four intended warning
removals and no other DRC fingerprint change. Reviewer `Скиф` accepted the exact
candidate, and SHA-256 `b1d221d5...` is now applied byte-for-byte. Its fresh
application gate passes at CI #592, PCB-PWR Schematic #70 and PCB Native #319
with the exact `90 -> 86`, `126 -> 126` comparison and no other DRC fingerprint
delta, so the four intended warning-only items are closed. Review B, routing,
CAM and manufacturing release remain prohibited by their independent gates.

The PCB-PWR `DIM-003` mechanical authority is machine-audited and accepted
`18/18` for the EVT test batch. It binds the 90 x 60 x 1.6 mm basis, four round
NPTH M3 holes, J1/J2 mating and cable volumes, DFT fixture/probe access,
assembled-height and enclosure/thermal keep-outs, harness board datums and a
hash-bound frozen STEP. It authorizes those inputs for EVT routing only. Harness
cut lengths are accepted at 275/440/330 mm with a 10% service allowance;
installed-route validation, serial enclosure revalidation and all manufacturing
gates remain required.

The PCB-PWR stackup/copper request is internally complete and machine-audited.
For EVT engineering and ordering, the selected standard profile is JLCPCB
`JLC04161H-3313A`, 1.6 mm, outer 2 oz / inner 1 oz; routing remains
conservatively sized against only 35 µm copper. All `24/24` historical response
rows are closed by the engineering baseline and no factory reply is required.
Any actual checkout parser/DFM deviation must be closed by ECO. The profile does
not authorize fabrication.

The PCB-MAIN stackup/impedance request is a retained historical packet. All
`22/22` rows are engineering-baseline closures and JLC06161H-3313 controls EVT
geometry. It is not Gerber, a purchase order or a fabrication release.

The bounded PCB-MAIN assembler request for `U2`, `U25`, `U26` and `U9` is also
retained historically. All `14/14` rows are engineering-baseline closures for
the standard process. Selected assembler identity remains a customer checkout
field; controlled paste export still requires DRC/CAM, and first-article,
Review B and manufacturing release remain open.

The harness supplier capability packet is retained historically. All `16/16`
rows are engineering-baseline closures; exact wire MPNs and 275/440/330 mm
lengths are accepted for EVT. Supplier identity is a customer order field.
First-off crimp/pull qualification, 100% electrical tests and installed-route
EVT validation still block manufacturing release.

All six controlled response-packet records are retained in one deterministic,
source-only historical archive controlled by
`manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.{md,json}`. The archive
contains the two-fabricator PCB-MAIN request, PCB-MAIN assembler request,
PCB-PWR DIM-003 request, two-fabricator PCB-PWR request, PCB-MIC DFM request and
harness-supplier request, both bounded public numeric routing bases and the
selected-lot procurement tables. Its
embedded SHA-256 manifest is machine-audited. The five former external registers
contain 85 engineering-baseline closures and DIM-003 remains accepted 18/18.
This closes the external-wait subgate only;
it is not a quotation, purchase order, routing authority or manufacturing
release.

## Current blocker classes

- physical assembly/EOL/EVT qualification of the documentarily controlled exact
  `BAT1`, `PV1`, `MPPT1`, `MPPT-TEMP`, `ANT-CELL`, `ANT-GNSS`, `ANT-LORA` and
  `RF-PIGTAIL` items; `HARNESS` and `HSG-VC` internal article identities are
  controlled, while final design inputs and physical release evidence remain open;
- PCB-MAIN and PCB-PWR remaining routing, DRC and CAM; PCB-PWR physical
  current-density/thermal/fault and rail-drop evidence beyond the accepted
  numeric EVT routing input; PCB-MIC independent Review B,
  CAM comparison, panelization and acoustic-stack review; all three boards'
  DFM and manufacturing release;
- PCB-MAIN USB source-termination routeability: the bounded R91/R92 placement
  ECO was accepted and applied exactly after proposal PCB Native #281; U1/J11/
  U25 and accepted RF copper remain fixed; its application commit-bound gate
  passed; the bounded MCU-source pair application gate passed on PCB Native
  #289, cellular-modem on #293 and cellular-fixture on #297; only the
  main-connector controlled 90-ohm segment remains open and DFM-blocked;
- the remaining 16 PCB-PWR input-protection qualification rows after accepted
  manufacturer source control, native-value and repeat-hierarchy gates,
  including +70 C 5 A thermal,
  prospective-current, battery-side primary-fuse and SMBJ18A coordination;
- controlled PCB-MAIN paste/CAM implementation, checkout DFM, two-board
  first-article evidence and closure of blocker/critical findings;
- serial revalidation of the EVT-accepted PCB-PWR `DIM-003` geometry against the
  final enclosure, exact component models, harness routing, installation and
  environmental inputs;
- PCB-PWR checkout DFM plus physical current-density/DC-drop/fault/+70 °C
  thermal approval;
- harness first-off crimp/pull qualification, 100% electrical records and
  installed-route electrical/SI/thermal validation;
- commercial quotation, availability, selected factory identity and delivery
  fields are customer-owned and non-blocking here.

Physical EVT and operator/SIM evidence remain later acceptance evidence after
stations are assembled; they are not replaced by this pre-production audit.
