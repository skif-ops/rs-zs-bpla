# PCB-PWR Rev.A input-protection qualification

Status: `CONTROLLED PLAN / F1 NATIVE VALUE ECO APPLIED / C20/C21 CIN_HF ECO APPLIED / COMMIT-BOUND ERC, PDF AND HUMAN HIERARCHY EVIDENCE PASS / PHYSICAL EVIDENCE PENDING / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`

This packet controls the PCB-PWR input fuse and TVS decision. The bounded F1
value-only ECO is applied without changing footprint, placement, topology, nets
or pad mapping. The previously accepted five-page source remains historical
evidence only. The post-ECO PDF was superseded after independent review found
text/symbol overlap. The later C20/C21 electrical ECO superseded the first
remediated artifact. Fresh commit-bound ERC/PDF evidence for the active source
passes, and reviewer `Скиф` accepted the exact active source/PDF hierarchy on
`2026-09-17`. Physical qualification remains required before production PCBA
or manufacturing release. A separate sample-only purchase is not required:
the exact parts may be included in the controlled EVT test-batch order when
other procurement gates permit, then held in quarantine until the first-lot
receiving identity gate passes.

Manufacturer source control is now complete. The machine-audited
`PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}` record binds
the exact four orderables to six official Littelfuse/Molex payloads, retrieval
date, byte sizes and SHA-256 values. This closes `PWR-IPQ-001` only.

The machine-audited
`PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.{md,json}` record now
closes the pre-purchase documentary subgate for `PWR-IPQ-002`. It binds online
photos, exact body-marking rules, packaging formats and authorized-channel
traceability requirements. The row itself remains `PENDING_PHYSICAL_TEST`
because the actual date/lot code of the future shipment can only be recorded
from the delivered EVT batch.

## 1. Controlled decision

The prior signed native source and PDF contain F1 value `0451005.MRL`. That part
is rejected for the project 5 A continuous-current basis. The active native
schematic, PCB and their generators now contain `0451008.MRL`. Littelfuse specifies
a standard 25% derating for continuous operation in addition to the temperature
rerating curve:

- `5 A x 0.75 = 3.75 A`, below the project load;
- `7 A x 0.75 = 5.25 A`, leaving only 5% before the additional +70 C
  temperature rerating;
- `8 A x 0.75 = 6.0 A`, so `0451008.MRL` is the minimum selected candidate
  that provides a usable desk margin before the mandatory hot test.

The exact EVT qualification pair is:

| Function | Candidate | Controlled rating | State |
|---|---|---|---|
| F1 PCB input fuse | Littelfuse `0451008.MRL` | 8 A; 7.7 mOhm nominal cold resistance; 20.23 A²s nominal melting I²t; 400 A at 32 VDC interrupting rating | Native value ECO retained through C20/C21 ECO; active-source ERC/PDF/human hierarchy evidence passes; physical qualification pending |
| D1 transient clamp | Littelfuse `SMBJ18A` | 18 V standoff; 20.0–22.1 V breakdown; 29.2 V maximum clamp at 20.6 A; 600 W at 10/1000 us | Selected for qualification; measured transient envelope pending |

At 5 A the fuse's nominal cold loss is:

`P = I²R = 5² x 0.0077 = 0.1925 W`.

The J1 `43045-0213` header and `43030-0038` 18 AWG / 0.75 mm² terminal each
publish a maximum of 8.5 A per contact. This does not release an 8 A continuous
system current. The operating envelope stays 5 A, and the complete
connector/crimp/wire path must pass the +70 C test.

The exact source payload hashes and ordering-code derivations are controlled in
`PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}`. No adjacent
family member is accepted as evidence for any of the four orderables.

## 2. Native-source interlock

This is a two-stage ECO gate:

1. The controlled BOM and qualification contract select `0451008.MRL` and
   prohibit procurement of `0451005.MRL`.
2. The bounded value-only native ECO changes F1 in the generator,
   `.kicad_sch` and `.kicad_pcb`. Independent semantic checks retain the exact
   F1 footprint, placement, topology, nets and pad mapping.

The earlier commit-bound ERC, PDF and human acceptance remain the historical
record for the superseded 5 A value. They do not approve the active 8 A value.
For the active value, KiCad 9.0.9 ERC passed with zero violations on five sheets
at commit `091a2eb223161cb4396fc6838921eeb79150c38d`, but independent review found
text overlapping symbols and connection marks in that commit's five-page A3
PDF. That PDF is superseded as active review evidence. A presentation-only
legibility remediation retains the exact pin/net semantic hash. For source
commit `6ba3ba5d219b95cb7de12f37c4eb646f7f18cfa8`, KiCad 9.0.9 ERC passes
with zero violations on five sheets and PDF SHA-256
`16afef6ecb337109f2a61318c9459167c6d06f4b74534b656c97884c1fed57dd`
covers five visually preflighted A3 landscape pages without text/symbol/
connection overlap or clipping. That evidence was superseded before review by
the subsequent C20/C21 CIN_HF electrical ECO, which retains F1 and changes
the active pin/net digest. For exact source commit
`e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a`, Schematic Gate
[#35217048575](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35217048575)
passes KiCad 9.0.9 ERC with zero violations on five sheets. Its five-page A3
PDF SHA-256 is
`7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130`
and passes visual preflight without text/symbol/connection overlap or clipping.
Reviewer `Скиф` accepted that exact source/PDF pair on `2026-09-17` with
decision `ACCEPT_HIERARCHY_ONLY`; `PWR-IPQ-004` is therefore `PASS`.

The retained interlocks are:

- no PCB-PWR PCBA procurement is authorized;
- no BOM line may claim `CONTROLLED` release for F1;
- `0451005.MRL` may appear only in historical/provenance text, never in an
  active native or generator value field;
- manufacturing release remains false.

## 3. TVS acceptance boundary

`SMBJ18A` is a pulse clamp, not a sustained-overvoltage regulator. Its
tabulated 29.2 V maximum clamp leaves 6.8 V to the 36 V absolute maximum input
of the selected buck regulators before layout overshoot and tolerance.

The qualification candidate limit is therefore:

- `<=32.0 V` measured at the protected node for every accepted battery and
  MPPT event;
- any measured value `>=36.0 V` is an immediate reject;
- sustained overvoltage must be prevented by the battery/BMS/MPPT architecture,
  not absorbed continuously by D1.

The final criterion may be tightened after the measured source impedance and
transient envelope are available. It may not be relaxed above the 36 V hard
ceiling.

## 4. Measurement boundary

The INA226 normal-operation calibration remains `200 uA/bit` for the released
5 A operating envelope. Its positive signed current range is approximately
`6.5534 A`. It is not the instrument for fuse-opening or fault-energy tests.

Every overload, short-circuit and TVS-coordination test above that range uses an
external calibrated current probe and oscilloscope. Firmware must not report a
register wrap or overflow as a plausible valid current.

## 5. Safe test sequence

Tests run in the order controlled by
`PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv`:

1. source control (`PWR-IPQ-001 PASS`), pre-purchase identity evidence, then
   first-lot receiving inspection using the quarantined EVT batch and the
   bounded native ECO;
2. repeat ERC/PDF/human hierarchy gate after the legibility remediation and C20/C21 ECO (`PASS`);
3. 25 C, +70 C and -40 C operating tests;
4. inrush and modem-burst tests;
5. overload, prospective-short and primary-fuse coordination using a
   current/energy-limited fixture;
6. connector/harness thermal and voltage-drop tests;
7. battery and MPPT transient capture;
8. bounded TVS pulse, reverse-polarity and TVS fail-short tests;
9. INA226 range/error-state verification;
10. independent evidence audit.

An unprotected direct short of an RB40 is prohibited. The test fixture must limit
available current and energy, provide remote shutdown, use a guarded enclosure
and capture source impedance before the fault is applied.

## 6. Release rule

The plan audit may pass while every physical test remains pending. Qualification
is complete only when all 20 rows are `PASS`, each row names an operator and
date, every required artifact has a SHA-256, the native F1 value equals
`0451008.MRL`, and repeat hierarchy evidence is accepted.

This packet never closes PCB-PWR routing, DIM-003, stackup/copper, DRC, CAM, DFM,
Review B or manufacturing release.

The current matrix state is `3/20 PASS`; 17 rows remain open.

## 7. Procurement identity

No stand-alone identity samples are purchased. The first controlled EVT batch
is the inspected lot. Before kitting, photograph every received package/reel/
tray, inspect at least five bodies per MPN per date/lot (or all when fewer than
five), and bind the photos to the PO, exact MPN, quantity, supplier, date/lot,
packing record and inspector.

The key online identifiers are:

- `0451008.MRL`: official family rule is brand plus ampere rating; expected
  body marking is Littelfuse `F` plus `8A`, while the exact suffix and lot must
  remain traceable through the label/paperwork;
- `SMBJ18A`: exact code `LT`, trace format `YMXXX` (year, month, lot) and a
  cathode band; `BT` is the rejected bidirectional `SMBJ18CA`;
- `43045-0213`: exact official Molex product image and tray packaging; body
  geometry cannot replace the labelled MPN/date-lot trace;
- `43030-0038`: exact official Molex product image and packaging drawing
  `PK-43030-001-001` Rev.B1, with 12,000 pieces per 24-inch reel and a defined
  product-label location.

Controlled JSON SHA-256:
`f6baf0cc053396ef98d91d28b3f52c4839f7fb4d345a49f30cc3ef073dd532ae`.

## 8. Primary evidence

- Controlled hash record:
  `PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.{md,json}`

- Controlled procurement-identity record:
  `PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.{md,json}`

- [Littelfuse 0451008 product page](https://www.littelfuse.com/products/fuses-overcurrent-protection/fuses/surface-mount-fuses/nano-2-fuses/451/0451008)
- [Littelfuse 451/453 series data sheet](https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1)
- [Littelfuse SMBJ18A product page](https://www.littelfuse.com/products/overvoltage-protection/tvs-diodes/surface-mount/smbj/smbj18a)
- [Littelfuse SMBJ series data sheet](https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e)
- [Molex 43045-0213 product page](https://www.molex.com/en-us/products/part-detail/430450213)
- [Molex 43030-0038 product page](https://www.molex.com/en-us/products/part-detail/430300038)
