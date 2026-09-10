# Дионея EVT-PRE-20 Rev.A - PCB-PWR Review A pin/net authority

Status: `REVIEW A PIN/NET PASS / NATIVE SCHEMATIC CAPTURE AUTHORIZED / NOT FOR MANUFACTURE`
Date: 2026-09-09
Board: `PCB-PWR`
Configuration: `EVT-PRE-20 Rev.A`

## 1. Scope

This Review A covers only component pin authority, named-net authority, inter-board pin contract, startup dependencies and controlled ground-return joins required before native KiCad schematic capture.

It does not approve final passive MPNs, TVS/fuse coordination, thermal design, PCB layout, DFM, EMC/EMI, environmental qualification or manufacturing release. Those remain Review B / EVT / release items.

## 2. Authoritative inputs reviewed

- `hardware/PCB_PWR_PIN_AUTHORITY_REV_A.csv`
- `hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv`
- `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv`
- `hardware/PWR_MAIN_12PIN_I2C_FREEZE_REV_A.md`
- `hardware/CONNECTOR_FREEZE_REV_A.csv`
- `hardware/POWER_COMPONENT_FREEZE_REV_A.csv`
- `hardware/POWER_DESIGN_BASELINE_REV_A.json`
- `hardware/kicad/sheets/01_POWER.csv`
- TI primary datasheets for LM74700-Q1, CSD18540Q5B, LMR60440, TPS7A20 and INA226.

## 3. Review findings and dispositions

### RA-PWR-001 - critical startup deadlock

Original authority connected `U4 LMR604403` pin 9 EN to `EN_AUX`. This is invalid because PCB-MAIN is powered by the `3V3_DIGITAL` rail produced by U4. MAIN cannot assert EN_AUX before its own 3.3 V supply exists.

Disposition: `CLOSED`.

Rev.A authority is now:

- U4 VIN -> `VBAT_SYS`;
- U4 EN -> `VBAT_SYS` directly;
- `3V3_DIGITAL` is the always-on MAIN/AON bootstrap rail;
- `EN_AUX` must never gate U4;
- `EN_AUX` now controls U5 TPS7A2018 pin 3 EN and therefore gates only `1V8_MIC`;
- firmware keeps EN_AUX asserted whenever T5838 AAD monitoring must remain armed.

This preserves the existing 12-pin connector contract without adding another control signal.

### RA-PWR-002 - ambiguous ground-return join

Original authority allowed `GND_MODEM`, `GND_DIGITAL` and `GND_MIC` to join `GND_PWR` as `NET_TIE_OR_PLANE`, which is ambiguous for schematic capture and DRC.

Disposition: `CLOSED`.

Rev.A authority now requires explicit two-pin net-tie components:

- `GND_MODEM -> NT_GND_MODEM -> GND_PWR`;
- `GND_DIGITAL -> NT_GND_DIGITAL -> GND_PWR`;
- `GND_MIC -> NT_GND_MIC -> GND_PWR`.

The three harness returns remain distinct until their controlled low-impedance join region on PCB-PWR.

## 4. Locked power path

The approved schematic capture sequence is:

`J_PWR_IN -> F1/TVS candidate stage -> LM74700-Q1 + CSD18540Q5B -> RSH1 10 mOhm Kelvin -> VBAT_SYS -> U3 3V8 + U4 3V3 -> U5 1V8`

INA226 is connected across the Kelvin sense pair and measures the load-side protected battery bus. Both switching-regulator inputs are downstream of RSH1, so the monitor measures total station battery current rather than a single rail.

## 5. Locked key pin/net mappings

### LM74700-Q1 U1

- pin 1 VCAP -> `LM74700_VCAP`;
- pin 2 GND -> `GND_PWR`;
- pin 3 EN -> `VBAT_FUSED`;
- pin 4 CATHODE -> `VBAT_PROTECTED`;
- pin 5 GATE -> `REV_GATE`;
- pin 6 ANODE -> `VBAT_FUSED`.

EN is tied to ANODE/input for always-on reverse protection.

### CSD18540Q5B Q1

- pins 1,2,3 SOURCE -> `VBAT_FUSED`;
- pin 4 GATE -> `REV_GATE`;
- pins 5,6,7,8 DRAIN -> `VBAT_PROTECTED`.

### LMR604403 U3 - 3V8_MODEM

- pin 1 VIN -> `VBAT_SYS`;
- pin 2 PGND -> `GND_PWR`;
- pin 3 SW -> `SW_3V8`;
- pin 4 BOOT -> `BOOT_3V8`;
- pin 5 PG -> `PG_3V8` diagnostic only;
- pin 6 FB -> `FB_3V8`, 100 kOhm / 35.7 kOhm divider;
- pin 7 MODE/SYNC -> `MODE_3V8`, PFM default;
- pin 8 RT -> `RT_3V8`, 86.6 kOhm, 400 kHz baseline;
- pin 9 EN -> `EN_MODEM`, 100 kOhm pull-down, default OFF.

### LMR604403 U4 - 3V3_DIGITAL

- pin 1 VIN -> `VBAT_SYS`;
- pin 2 PGND -> `GND_PWR`;
- pin 3 SW -> `SW_3V3`;
- pin 4 BOOT -> `BOOT_3V3`;
- pin 5 PG -> `PWR_GOOD`;
- pin 6 FB -> `3V3_DIGITAL`, fixed 3.3 V mode;
- pin 7 MODE/SYNC -> `MODE_3V3`, PFM default;
- pin 8 RT -> `RT_3V3`, 86.6 kOhm, 400 kHz baseline;
- pin 9 EN -> `VBAT_SYS`, always-on startup policy.

`PWR_GOOD` intentionally reflects the critical 3V3 MAIN/AON rail only. It is not ANDed with `PG_3V8` because the modem rail may be intentionally disabled.

### TPS7A2018 U5 - 1V8_MIC

- pin 1 IN -> `3V3_DIGITAL`;
- pin 2 GND -> `GND_PWR`;
- pin 3 EN -> `EN_AUX`;
- pin 4 NC -> no connection;
- pin 5 OUT -> `1V8_MIC`.

### INA226 U2

- pin 1 A1 -> `GND_PWR`;
- pin 2 A0 -> `GND_PWR`;
- pin 3 ALERT -> `FAULT`;
- pin 4 SDA -> `I2C2_SDA`;
- pin 5 SCL -> `I2C2_SCL`;
- pin 6 VS -> `3V3_DIGITAL`;
- pin 7 GND -> `GND_PWR`;
- pin 8 VBUS -> `VBAT_SYS`;
- pin 9 IN- -> `SHUNT_LOAD_SENSE`;
- pin 10 IN+ -> `SHUNT_SOURCE_SENSE`.

A1=A0=GND fixes the Rev.A 7-bit address at `0x40`. PCB-PWR I2C pull-up footprints are DNP by default; the authoritative pull-ups are on PCB-MAIN. ALERT may assert FAULT but does not replace I2C telemetry.

## 6. Frozen MAIN/PWR connector contract

The Review A authority accepts only the 12-pin contract:

1. `3V8_MODEM`
2. `GND_MODEM`
3. `3V3_DIGITAL`
4. `GND_DIGITAL`
5. `1V8_MIC`
6. `GND_MIC`
7. `PWR_GOOD`
8. `FAULT`
9. `EN_MODEM`
10. `EN_AUX`
11. `I2C2_SCL`
12. `I2C2_SDA`

Any 10-pin MAIN/PWR interface is stale and must fail the capture audit.

## 7. Review A verdict

`PASS - PIN/NET AUTHORITY`

PCB-PWR is authorized to proceed to native KiCad schematic capture using only the reviewed authorities above.

The native schematic must fail Review A regression if it:

- gates U4 3V3 with EN_AUX;
- hard-ties U5 EN to 3V3 instead of EN_AUX;
- omits INA226 I2C pins 11/12;
- removes true Kelvin shunt sense nets;
- joins dedicated harness ground nets without explicit net-ties;
- changes the 12-pin MAIN/PWR order;
- treats FAULT as a replacement for INA226 I2C telemetry.

## 8. Open items outside this Review A scope

- exact shunt MPN and Kelvin layout;
- final TVS and fuse values and coordination;
- exact inductor/capacitor/bulk MPNs and derating;
- selected battery/BMS voltage limits;
- MPPT/harness transient envelope;
- I2C final harness capacitance and pull-up validation;
- reverse MOSFET SOA and gate transient review;
- load-step, LTE-burst, cold-start, +70 C thermal and S0 standby tests;
- INA226 reference-meter calibration;
- EMC/EMI evidence;
- PCB layout, DRC, DFM and Review B.

Manufacturing status remains `NOT FOR MANUFACTURE`.
