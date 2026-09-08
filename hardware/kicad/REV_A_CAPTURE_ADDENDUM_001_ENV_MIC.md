# EVT-PRE-20 Rev.A capture addendum 001 — environment and MIC interface

Status: `AUTHORITATIVE ADDENDUM / BLOCKING / NOT FOR MANUFACTURE`
Date: 2026-09-08

This addendum **supersedes conflicting text** in `REV_A_CAPTURE_SPEC.md` until the next consolidated capture-spec revision. Native schematic capture and Review A must apply this addendum together with the main specification.

## A. Environment — supersedes the old IN-006/open wording

- `DEC-019` is LOCKED.
- Operating ambient: **−40…+70 °C**.
- Electronic components/connectors/cable assemblies exposed to enclosure ambient must be rated at least **−40…+85 °C** unless a formal waiver is approved.
- `STM32U585VIT6Q` exact selected part is −40…+85 °C and therefore is temperature-compatible with Rev.A; its remaining blockers are CubeMX/target/sample validation, not IN-006.
- `MDBT50Q-P1MV2` and `TS3A27518EPWR` −40…+85 °C limits are compatible with the operating range; their RF/SI/firmware blockers remain.
- Hot operation at +70 °C must include self-heating/junction-temperature evidence.
- Cold operation at −40 °C must include cold boot, AAD/PDM, RF/service, storage and connector evidence.
- LiFePO4 charging below 0 °C is prohibited unless an approved heater/low-temperature charging system is part of the selected battery design.
- Authoritative environmental details: `hardware/ENVIRONMENT_REV_A.md`.

## B. T5838 AAD interface — supersedes old 4/5-contact MIC clauses

The active T5838 interface requires both:

- pin 4 `WAKE` as an AAD event output;
- pin 5 `THSEL` as the one-wire AAD configuration/activation input.

Therefore Rev.A MIC harness has **6 physical contacts**. A 4-contact or 5-contact MIC harness is prohibited.

Physical pin order:

1. `1V8_MIC`
2. `GND`
3. `PDM_CLK`
4. `PDM_DATAn`
5. `MIC_WAKEn`
6. `AAD_CFG` -> T5838 `THSEL`

The four `MIC_WAKEn` lines remain independent through their harnesses and are OR-combined on PCB-MAIN before translation to STM32 `PA8/pin67`.

`AAD_CFG` is a shared 1.8 V one-wire fanout to all four T5838 THSEL pins. STM32 source is `PA15/pin77`, translated through a free MCU-to-1.8 V channel of U7 `SN74AXC8T245PWR`.

Authoritative AAD design: `hardware/T5838_AAD_INTERFACE_REV_A.md` and `hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv`.

## C. MIC connector — active Rev.A selection

JST GH is rejected because the applicable selected family does not satisfy the −40 °C project lower limit.

The previously selected 5-contact Pico-Lock `5040500591` / `5040510501` is also **superseded**, because it cannot carry both T5838 WAKE and THSEL/AAD_CFG.

The active Rev.A MIC connector is Molex Pico-Lock 1.50 mm positive-lock:

- board header: `5040500691`, 6 circuits, right-angle SMT;
- cable housing: `5040510601`, 6 circuits;
- crimp terminal: `5040520098`, 24–28 AWG;
- operating range: −40…+105 °C.

## D. Capture/release rule

- Symbol/footprint/BOM fields for `J_MIC1..J_MIC4` and `PCB-MIC:J1` must use the 6-contact Molex parts above.
- `hardware/CONNECTOR_FREEZE_REV_A.csv` is the machine-checkable connector authority.
- `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv` is the physical pin-order authority.
- `hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv` is the authoritative PA15/pin77 assignment until merged into the consolidated MCU pin map.
- ERC/DRC PASS does not override this addendum.
- Any generated Gerber/BOM/PnP containing JST GH, `5040500591`, `5040510501`, or a MIC connector with fewer than 6 circuits must fail release review.
