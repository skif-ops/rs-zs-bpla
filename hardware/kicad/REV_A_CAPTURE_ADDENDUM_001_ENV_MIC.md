# EVT-PRE-20 Rev.A capture addendum 001 — environment and MIC connector

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

## B. MIC connector — supersedes JST GH references

The JST GH `BM05B-GHS-TBT` / `GHR-05V-S` family is **rejected for Rev.A** because the selected board header does not meet the −40 °C project lower limit.

The active Rev.A MIC connector is Molex Pico-Lock 1.50 mm positive-lock:

- board header: `5040500591`, 5 circuits, right-angle SMT, gold plating;
- cable housing: `5040510501`, 5 circuits;
- crimp terminal: `5040520098`, 24–28 AWG;
- published operating range: −40…+105 °C.

Physical pin order remains unchanged:

1. `1V8_MIC`
2. `GND`
3. `PDM_CLK`
4. `PDM_DATAn`
5. `MIC_WAKEn`

`WAKE` remains mandatory. A 4-position connector or any connector family rated above −40 °C minimum is prohibited.

## C. Capture/release rule

- Symbol/footprint/BOM fields for `J_MIC1..J_MIC4` and `PCB-MIC:J1` must use the Molex parts above.
- `hardware/CONNECTOR_FREEZE_REV_A.csv` is the machine-checkable connector authority.
- `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv` remains the pin-order authority.
- ERC/DRC PASS does not override this addendum.
- Any generated Gerber/BOM/PnP containing JST GH for Rev.A must fail release review.
