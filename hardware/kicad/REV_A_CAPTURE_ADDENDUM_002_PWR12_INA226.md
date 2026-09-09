# EVT-PRE-20 Rev.A capture addendum 002 — 12-pin PWR interface and INA226

Status: `AUTHORITATIVE ADDENDUM / ELECTRICAL FROZEN / BLOCKING / NOT FOR MANUFACTURE`
Date: 2026-09-09
Decision: `Variant A / 12-pin / INA226 retained on PCB-PWR with I2C`

This addendum **supersedes conflicting 10-contact MAIN/PWR text** in `REV_A_CAPTURE_SPEC.md` until the next consolidated capture-spec revision. Native schematic capture and Review A must apply this addendum together with the main specification and Addendum 001.

## A. MAIN/PWR physical interface

Rev.A uses a 12-contact Molex Micro-Fit 3.0 interface between PCB-PWR and PCB-MAIN.

Active selection:
- board header on PCB-PWR: Molex `43045-1202` / `0430451202`, 12 circuits, right-angle, through-hole, gold;
- board header on PCB-MAIN: Molex `43045-1202` / `0430451202`, same electrical pin contract;
- cable housing at each end: Molex `43025-1200` / `0430251200`;
- 18 AWG power/return contacts: Molex `43030-0038`;
- 20-24 AWG control/I2C contacts: Molex `43030-0001`.

Exact board-edge orientation and mechanical keepout may change only as a mechanical ECO and must not change the electrical pin order.

## B. Frozen 12-pin contract

| Pin | Net | Direction at MAIN | Electrical class |
|---:|---|---|---|
| 1 | `3V8_MODEM` | IN | power |
| 2 | `GND_MODEM` | RETURN | power return |
| 3 | `3V3_DIGITAL` | IN | power |
| 4 | `GND_DIGITAL` | RETURN | power return |
| 5 | `1V8_MIC` | IN | power |
| 6 | `GND_MIC` | RETURN | power return |
| 7 | `PWR_GOOD` | IN | 3.3 V logic |
| 8 | `FAULT` | IN | 3.3 V logic |
| 9 | `EN_MODEM` | OUT | 3.3 V logic |
| 10 | `EN_AUX` | OUT | 3.3 V logic |
| 11 | `I2C2_SCL` | BIDIR open-drain | 3.3 V I2C |
| 12 | `I2C2_SDA` | BIDIR open-drain | 3.3 V I2C |

Pins 1-10 preserve the previous logical order. The 10-contact connector and all BOM/PCB/harness artifacts based on it are superseded.

## C. INA226 placement and electrical baseline

`INA226AIDGSR` is physically located on PCB-PWR and measures total protected battery input before the regulated-rail split. Its purpose is real station-level battery telemetry, not a proxy derived from individual rail estimates.

Rev.A capture baseline:
- 7-bit I2C address: `0x40`;
- STM32 bus: `I2C2`, PB13=`I2C2_SCL`, PB14=`I2C2_SDA`;
- initial bus rate: `100 kHz` until final-harness rise/fall-time validation;
- shunt capture value: `10 mOhm`, 4-terminal/Kelvin, >=1 W, low TCR; exact MPN remains a release blocker;
- `Current_LSB = 200 uA/bit`;
- calibration register `CAL = 2560` for the 10 mOhm capture shunt;
- `Power_LSB = 5 mW/bit`;
- pull-ups are authoritative on PCB-MAIN to `3V3_DIGITAL`; optional PCB-PWR pull-up footprints shall be DNP by default;
- reserve source-side 22-47 Ohm series-damping footprints for SCL/SDA, populated only if SI measurement requires them.

INA226 ALERT may feed the aggregate `FAULT` path through an electrically correct open-drain/logic implementation. **ALERT/FAULT never substitutes for I2C telemetry.** Loss of I2C access to INA226 is a diagnosable telemetry fault.

## D. Required station telemetry

The station firmware/server/diagnostic contract shall expose at minimum:
- battery bus voltage from INA226;
- signed battery current;
- battery power;
- INA226 communication/calibration validity;
- an error/status indication when the monitor is unavailable or returns invalid data.

The existing battery percentage field may remain as a derived state-of-charge estimate, but it does not replace measured voltage/current/power.

## E. Layout rules

- RSHUNT uses true Kelvin sense routing to INA226 IN+/IN-; load current must not flow through sense traces.
- Locate INA226 and the shunt away from DC/DC switch nodes and modem RF/burst-current return loops.
- SCL/SDA shall use the `GND_DIGITAL` return reference, be kept short, and avoid parallel routing beside `3V8_MODEM` high-current conductors where practical.
- I2C pull-up strength is frozen after measuring total bus capacitance at the final harness length; initial design window is 2.2-4.7 kOhm.
- Test points are required for SCL, SDA, shunt Kelvin nodes and protected battery bus.

## F. Review A / EVT checks

Review A must reject any capture containing a 10-pin MAIN/PWR connector or an INA226 without I2C connectivity.

Minimum EVT verification:
1. pin-by-pin continuity and keying of all 12 contacts;
2. INA226 enumeration at address `0x40`;
3. voltage comparison against reference DMM;
4. current comparison at approximately 0.05 A, 0.2 A, 1 A and 3 A plus representative LTE burst current;
5. power scaling/sign verification;
6. I2C rise/fall time and NACK/error counter at 100 kHz on the final harness;
7. SCL open, SDA open and INA226 power/reset fault injection;
8. 72-hour energy comparison against a reference power/energy meter.

## G. Authoritative files

- `hardware/PWR_MAIN_12PIN_I2C_FREEZE_REV_A.md` — decision and interface freeze;
- `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv` — physical pin order;
- `hardware/CONNECTOR_FREEZE_REV_A.csv` — connector MPN authority;
- `hardware/POWER_COMPONENT_FREEZE_REV_A.csv` — INA226 component authority;
- `hardware/POWER_DESIGN_BASELINE_REV_A.json` — capture/calibration baseline.

Any generated schematic, PCB, BOM, PnP, assembly drawing or harness document that conflicts with this addendum must fail Review A.
