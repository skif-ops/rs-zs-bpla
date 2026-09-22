# EVT engineering and manufacturing baseline — Rev.A

Status: `ACCEPTED FOR EVT ENGINEERING / EXTERNAL REPLIES NOT REQUIRED / NOT A MANUFACTURING RELEASE`

Decision date: `2026-09-21`

This is the controlling manual for the test lot. The customer places PCB and
PCBA orders, so named-site e-mail replies and signed quotation attachments are
not prerequisites. Public manufacturer limits, project calculations and the
standard process below replace those administrative gates. An order-site DFM or
file-parser error is still a stop condition, and no line in this manual marks an
unrouted board or incomplete Review B as released for manufacture.

## 1. PCB-MAIN

Use the published JLCPCB six-layer construction `JLC06161H-3313`, or an
equivalent customer-selected process that meets every controlled number:

- order thickness `1.6 mm`; public construction `1.54 mm`, tolerance `±10%`;
- outer copper `1 oz`, inner copper `0.5 oz`, green LPI mask, ENIG;
- controlled impedance `±10%`;
- L1-to-L2 50-ohm single-ended width `0.1509 mm`;
- L1-to-L2 90-ohm differential width/gap `0.1537/0.2032 mm`;
- continuous reference below RF and USB; no plane split under either geometry;
- select the standard impedance option and obtain the standard coupon/TDR
  report when the checkout offers it.

These values authorize layout. Native DRC, CAM review and independent Review B
remain required before upload.

## 2. PCB-PWR

Use public four-layer construction `JLC04161H-3313A`, or an equivalent process:

- `1.6 mm ±10%`, outer finished copper `70 um`, inner copper `35 um`;
- average hole-wall plating at least `18 um`, ENIG, green LPI mask;
- fabrication floor `0.15/0.15 mm`; project preferred signal rule
  `0.20/0.20 mm`;
- current path values and via counts are controlled by
  `hardware/PCB_PWR_CURRENT_GEOMETRY_BASIS_REV_A.csv`.

The calculation uses copper resistivity `1.724e-8 ohm*m` at 20 C and temperature
factor `1.1965` at 70 C. The table is a conservative routing minimum, not proof
of thermal performance. Verify rail drop and temperature at `+70 C` on EVT.

DIM-003 remains four circular `3.20 mm` M3 NPTH holes. There are no mounting
slots. The asymmetric fourth hole is intentional; use the accepted printed
boss/insert scheme.

## 3. PCB-MIC

Use standard two-layer FR-4, `1.0 mm ±10%`, `1 oz`, ENIG, green LPI mask.
All ordinary NPTH-to-copper clearance is at least `0.20 mm`. The sole exception
is the manufacturer-derived MK1 ground land around the `0.8 mm` acoustic NPTH:
`0.10 mm` minimum to that ground land only. It does not authorize a signal trace
or copper zone at that distance.

The first panel must show a clean, unplated, unobstructed acoustic bore without
copper breakout or burr. Use vendor-standard tooling rails and routed tabs away
from MK1, its acoustic path and H1/H2. Support the leaf during depaneling and
inspect every acoustic port afterward. Do not apply paste, adhesive, conformal
coating or membrane glue in the acoustic path.

## 4. Assembly process

Select a standard PCBA service. Process baseline:

- SAC305, no-clean, Type-4 paste;
- `100 um` laser-cut electropolished stainless stencil;
- reflow peak `240 ±5 C`, `45–75 s` above `217 C`, ramp `0.5–1.5 C/s`,
  cooling no faster than `4 C/s`;
- U2 aperture `1.85 x 0.55 mm` per pad;
- U25/U26 aperture `0.27 x 0.27 mm` per pad;
- U9 uses the exact controlled component land-pattern apertures; automatic 1:1
  paste generation is prohibited;
- 100% SPI and AOI; X-ray hidden LGA/QFN joints; visual check of polarity,
  connector seating and every PCB-MIC acoustic path.

Build two first articles. Hold the remaining 20 assembled boards until SPI,
AOI/X-ray findings and current-limited smoke/interface tests are accepted.

## 5. Harness construction and lengths

The route estimate is frozen with a 10% service allowance:

| Assembly | Base | Released cut length | Tolerance |
|---|---:|---:|---:|
| H-MIC1..4 | 250 mm | 275 mm | ±5 mm |
| H-MAIN-PWR | 400 mm | 440 mm | ±5 mm |
| H-BAT-PWR | 300 mm | 330 mm | ±5 mm |

Use equal microphone lengths; stow lower-pod excess as a service loop without a
tight bend. Exact conductor-by-conductor values are in
`hardware/HARNESS_EVT_LENGTH_BASIS_REV_A.csv`.

- MIC: TE Raychem `55A0111-24`, 24 AWG, nominal OD `0.94 mm`, with Molex
  `5040520098`.
- MAIN/PWR pins 1–6 and battery pair: TE Raychem `55A0111-18`, 18 AWG,
  nominal OD `1.52 mm`, with Molex `430300038`.
- MAIN/PWR pins 7–12: Alpha Wire `3051`, 22 AWG, nominal OD `1.575 mm`,
  with Molex `430300001`.
- Battery M8 end: TE SOLISTRAND `8-34114-1`; cold qualification of the finished
  crimp is mandatory for EVT.

For 20–24 AWG Micro-Fit contacts, follow Molex ATS-638190000 strip/crimp values.
For 18 AWG Micro-Fit and Pico-Lock, use the correct terminal-specific production
applicator and approve the first-off measured crimp height and destructive pull;
do not infer a tool from the 20–24 AWG hand-tool sheet.

Test every harness for continuity, polarity and cross-shorts. Maximum measured
end-to-end conductor resistance is `0.15 ohm` for MIC and MAIN/PWR, and
`0.10 ohm` for each battery conductor.

## 6. EVT acceptance and escalation

Before the remaining lot is released, run:

1. rail-drop, startup and modem-burst tests;
2. I2C at `100 kHz` through the 440 mm harness;
3. four-channel PDM/AAD gain, phase, noise and wake tests;
4. powered `+70 C` thermal run;
5. `-40 C` continuity and functional start, including the M8 joint;
6. harness flex/strain and connector-retention checks;
7. 100% PCB-MIC acoustic-path inspection.

Any checkout DFM error, first-article defect or functional failure opens a
controlled ECO. At transfer to a serial lot, repeat fabricator/assembler DFM,
process-capability, tooling, environmental and supplier qualification. This EVT
decision must not be copied forward as a series waiver.

## Official public sources

- JLCPCB PCB capability: <https://jlcpcb.com/capabilities/pcb-capabilities>
- JLCPCB impedance stackups: <https://jlcpcb.com/impedance>
- JLCPCB assembly capability: <https://jlcpcb.com/capabilities/pcb-assembly-capabilities>
- Molex Pico-Lock terminal 5040520098: <https://www.molex.com/en-us/products/part-detail/5040520098>
- Molex Micro-Fit 430300038: <https://www.molex.com/en-us/products/part-detail/430300038>
- Molex Micro-Fit 430300001: <https://www.molex.com/en-us/products/part-detail/430300001>
- Molex ATS-638190000: <https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/applicationtoolingspecificationpdf/638/63819/ATS-638190000-001.pdf?inline=>
- TE 55A0111-18: <https://www.te.com/en/product-2162473001.html>
- TE 55A0111-24: <https://www.te.com/en/product-2160463004.html>
- Alpha Wire 3051: <https://www.alphawire.com/products/wire/hook-up-wire/premium/3051>
- TE SOLISTRAND 8-34114-1: <https://www.te.com/en/product-8-34114-1.html>
