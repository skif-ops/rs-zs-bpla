# PCB-MAIN Rev.A power-integrity calculation and RA-003 disposition

Status: `CALCULATION PASS / PHYSICAL EVIDENCE OPEN / NOT FOR MANUFACTURE`

Configuration: `EVT-PRE-20 Rev.A`
Scope: U1 internal SMPS, MLCC effective-capacitance control and BG95-M3 burst supply.

## 1. Purpose and boundary

This note supplies the calculation record requested by Review-A finding `RA-003`.
It closes the missing-document/calculation part of that finding. It cannot close the
measurement part: voltage at all four U8 VBAT pads, return-domain offset, ripple,
temperature and U1 SMPS stability must be measured on an assembled PCB-MAIN.

## 2. Controlled inputs

- PCB-PWR `3V8_MODEM` capability: 4 A design rail.
- BG95-M3 worst controlled branch peaks: 0.6 A `VBAT_BB`, 2.7 A `VBAT_RF`.
- Nominal rail: 3.8 V; minimum permitted at U8 pads: 3.3 V.
- Local bulk: C36 and C44, KEMET `T520D107M006ATE015`, 100 uF, 6.3 V,
  15 milliohm nominal ESR, one on each branch.
- U1 VDDSMPS input: C13 `GRM188R61A106KE69D`, 10 uF, 10 V X5R.
- U1 output: L1 `LQH32PN2R2NN0L`, 2.2 uH, and two 2.2 uF VCORE capacitors.
- Layout limits already frozen: at least 0.6 mm equivalent copper for `VBAT_BB`,
  at least 2.7 mm for `VBAT_RF`, no neck-down, local star split and local return.

## 3. BG95 voltage budget

The available static plus dynamic drop budget is:

`3.8 V - 3.3 V = 0.5 V`.

At the 2.7 A RF peak, the entire path from the PCB-PWR source through connector,
harness, star split, R42 and copper must therefore remain below:

`R_path,max = 0.5 V / 2.7 A = 185 milliohm`.

This is a release ceiling, not a routing target. The Review-B routing target is
`<= 100 milliohm` end-to-end at 25 C, leaving at least 230 mV for source transient,
temperature rise and tolerance. C44 ESR contributes approximately
`2.7 A * 0.015 ohm = 40.5 mV` to a step initially supplied by the capacitor.

For the 0.6 A baseband peak, the absolute ceiling is 833 milliohm. The controlled
layout target is nevertheless `<= 150 milliohm`, because FB1 impedance, tolerance
and RF loss are frequency-dependent and must not consume the 0.5 V margin.

The 100 uF capacitors are edge/broadband support; they are not permitted to be used
as proof that the supply sustains a complete EGPRS burst. For example, capacitor-only
support at 2.7 A would consume the full 0.5 V budget after approximately:

`t = C * delta_V / I = 100 uF * 0.5 V / 2.7 A = 18.5 us`

before tolerance and ESR. Therefore a low-impedance live 4 A source and physical
burst measurement remain mandatory.

## 4. MLCC effective-capacitance rule

Nominal capacitance is not used directly for stability sign-off. Until a vendor
DC-bias curve is archived for the exact MPN, Review B shall use these conservative
minimum effective-capacitance factors:

| Network | Exact MPN / nominal | Bias | Provisional minimum effective value |
|---|---|---:|---:|
| U1 VDDSMPS C13 | GRM188R61A106KE69D / 10 uF | 3.3 V | 5.0 uF (50%) |
| U1 VCORE C14/C15 | exact 2.2 uF rows in MAIN-AUTH-010 | 1.1 V | 1.54 uF each (70%) |
| 3V8 broadband 220 nF | GRM155R71E224KE14D | 3.8 V | 110 nF (50%) |
| 3V8 broadband 100 nF | GRM155R71E104KE14D | 3.8 V | 50 nF (50%) |
| 1V8 local MLCC | exact MAIN-AUTH-010 MPN | 1.8 V | 60% of nominal |

The actual manufacturer curve or impedance measurement must meet or exceed these
values. A lower result is a component/layout change and invalidates affected review.
C0G RF capacitors are checked by tolerance and self-resonance, not by the X5R/X7R
derating factors above.

## 5. U1 SMPS acceptance window

The layout must place C13, L1 and C14/C15 at the corresponding VDDSMPS, VLXSMPS,
VDD11 and VSSSMPS pins without vias in the high-di/dt loop. The controlled bounds are:

- L1 = 2.2 uH +/-20%, saturation current >0.5 A, DCR <200 milliohm;
- C13 effective capacitance >=5.0 uF at 3.3 V;
- combined effective VCORE capacitance >=3.08 uF at 1.1 V;
- C13 ESR <10 milliohm at 3 MHz, as required by MAIN-AUTH-001;
- no external load on VCORE_1V1.

These bounds make the selected values eligible for layout. Oscilloscope evidence of
startup, steady-state ripple and load transition is still required because stability
cannot be proven from nominal part values alone.

## 6. Mandatory physical closure measurements

`RA-003-MEAS` remains open until one assembled board records all of the following:

1. `VBAT_BB` and `VBAT_RF` >=3.3 V at U8 pads 32, 33, 52 and 53 during LTE and EGPRS bursts.
2. Peak `GND_MODEM - GND_DIGITAL` offset plus noise <75 mV at U16.
3. End-to-end `3V8_MODEM_RF` path resistance <=100 milliohm at 25 C and thermal rise accepted.
4. U1 VCORE startup is monotonic; ripple and transient response remain inside STM32 limits.
5. Exact MLCC effective-capacitance evidence is archived for 3.8 V, 3.3 V, 1.8 V and 1.1 V rails.

## 7. Disposition

- `RA-003-CALC`: **CLOSED** by this controlled calculation.
- `RA-003-LAYOUT`: **OPEN** until final routed geometry is audited.
- `RA-003-MEAS`: **OPEN** until assembled-board evidence passes section 6.
- Overall `RA-003`: **OPEN**; it may be closed only when all three sub-items pass.
