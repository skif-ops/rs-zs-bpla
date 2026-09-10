# PCB-MAIN GNSS authority - EVT-PRE-20 Rev.A

Status: `GNSS_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-006`. It freezes the 18 U9 module pads, J9 electrical contacts, 3.3 V supply option, no-backup decision, UART/PPS endpoints, active-antenna supervisor signals, and the required RF/bias topology. It does not release the exact support-component MPN set, external antenna/cable, native capture, RF layout, connector placement, PCB Review A, PCB Review B, or the production BOM.

Machine authority: `hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `72b0604e6010d98761857a9aaacd86d21a0935bd01a9365050a3392db3d4cd6e`.

## Primary evidence

- u-blox `MAX-M10S Data sheet`, UBX-20035208 R08, 30 January 2026: `https://content.u-blox.com/sites/default/files/MAX-M10S_DataSheet_UBX-20035208.pdf`. Retrieved SHA-256: `e36d9c8585809c0dc486804d2634c66cd1888ad71af0f28ce0b830ffa8df6bec`.
- u-blox `MAX-M10S Integration manual`, UBX-20053088 R05, 28 April 2026: `https://content.u-blox.com/sites/default/files/MAX-M10S_IntegrationManual_UBX-20053088.pdf`. Retrieved SHA-256: `5a7510ef84f7e2757c57e362a25e3c16bcf8c80af5a4f70790c2e51032dbcd13`.
- u-blox `MAX-M10 series` product page: `https://www.u-blox.com/en/product/max-m10-series`.
- Hirose exact U.FL receptacle product page: `https://www.hirose.com/en/product/p/CL0331-0472-2-60`.

The selected BOM MPN is the professional-grade global ordering code `MAX-M10S-00B`. The current R08 data sheet identifies type number `MAX-M10S-00B-01`, ROM SPG 5.10, as mass production. The orderable code and type number must not be confused.

## U9 supply and backup decision

U9 `VCC` and `V_IO` both use `3V3_DIGITAL`. `VIO_SEL` is intentionally open, selecting the 2.7 to 3.6 V I/O range. `V_IO` must never exceed `VCC + 0.3 V`.

U9 VCC has local 100 nF plus 10 uF and a total feed resistance no greater than 0.2 Ohm. The 3.3 V rail and local network must support the specified startup inrush of up to 100 mA. Exact capacitor MPNs and RefDes are frozen by `MAIN-AUTH-010`.

`V_BCKP` is NC in Rev.A. No coin cell, supercapacitor, diode feed, or capacitor-only substitute is fitted. The station normally maintains `3V3_DIGITAL`; after a total power loss, U9 performs a cold restart and may receive trusted host time/orbit assistance. This avoids an unqualified energy store and makes the backup state deterministic.

`RESET_N` is NC with no capacitor. Hardware reset would clear RTC and BBR contents and cause a cold start; normal recovery uses a controlled UBX reset command. `EXTINT` is NC because the three-pin antenna supervisor uses PIO2/PIO3. I2C is disabled before those PIOs are reassigned.

## UART and TIMEPULSE

| U9 pad | Module signal | Rev.A endpoint |
|---:|---|---|
| 2 | TXD | `GNSS_RX` to STM32 PA3 / USART2_RX |
| 3 | RXD | `GNSS_TX` from STM32 PA2 / USART2_TX |
| 4 | TIMEPULSE | `GNSS_PPS` to STM32 PA0 / TIM2_CH1 |

Each line has a populated 22 Ohm source-series tuning position. TIMEPULSE also has a high-impedance test point. No external pull-up, pull-down, large capacitor, level translator, or powered-off drive is allowed on these 3.3 V lines.

U9 TIMEPULSE is internally coupled to `SAFEBOOT_N` through 1 kOhm. `SAFEBOOT_N` remains completely NC. A load that pulls TIMEPULSE LOW during receiver startup is prohibited because it can enter safeboot instead of normal GNSS operation.

The data sheet specifies 30 ns RMS and 60 ns at 99% time-pulse accuracy. These are module specifications, not end-to-end station guarantees. Review A and EVT must measure routing, timer capture, firmware latency, holdover, and coexistence error before any TDOA claim.

## Active antenna supervisor and RF path

Rev.A uses the u-blox Figure 38 three-pin active-antenna supervisor topology so firmware can distinguish open and short conditions and remove antenna power after a short.

| Function | U9 pad | Rev.A net | Configuration |
|---|---:|---|---|
| antenna supply switch | 13 `LNA_EN` / PIO7 | `GNSS_ANT_OFF_N` | `CFG-HW-ANT_SUP_SWITCH_PIN=7` |
| open detect | 16 `SDA` / PIO2 | `GNSS_ANT_DETECT` | `CFG-I2C-ENABLED=0`; `CFG-HW-ANT_SUP_OPEN_PIN=2` |
| short detect | 17 `SCL` / PIO3 | `GNSS_ANT_SHORT_N` | `CFG-I2C-ENABLED=0`; `CFG-HW-ANT_SUP_SHORT_PIN=3` |

Voltage control, short detect, open detect, power-down on fault, and automatic recovery are enabled. Open and short polarity are active HIGH and active LOW respectively as defined by R05 Figure 38 and Table 50. `LNA_EN` HIGH enables the active-antenna supply.

The antenna supply uses U9 `VCC_RF`, nominally `VCC - 0.1 V` and limited by specification to 50 mA output. The Figure 38 switch/sense network feeds 10 Ohm, 5%, 0.25 W current sensing, then a 27 nH, 5% bias-T inductor with impedance greater than 500 Ohm at GNSS L1 and current rating above 300 mA. The sense node has 10 nF, 10%, 16 V X7R to ground. Because `V_ANT` and `V_IO` are the same 3.3 V level, the optional level-shifting open-drain buffers shown by u-blox are omitted.

The controlled RF chain is:

`J9 center -> ultra-low-capacitance ESD -> biased antenna node -> 47 pF 5% 25 V C0G DC block -> populated external wideband GNSS SAW -> U9 pin 11 RF_IN`.

The external SAW is mandatory in Rev.A because the unit contains nearby cellular and RU868 transmitters. Its passband must cover every enabled L1 constellation, including GLONASS L1OF. The exact SAW, ESD, comparator, P/N switch, resistors, capacitors, inductor, their RefDes, and their physical pin maps are frozen by `MAIN-AUTH-010`; changing the topology or active levels requires reopening `MAIN-AUTH-006` and `MAIN-AUTH-010`.

J9 is exact Hirose `U.FL-R-SMT-1(60)`. Center contact 1 carries `GNSS_RF_ANT_BIASED`; both ground terminals and shell connect to uninterrupted RF ground. The external cable and active antenna remain separate unreleased system BOM lines.

## Layout and firmware constraints

- Keep the U9 RF section and J9 path away from digital clocks, DC/DC switch nodes, cellular, and RU868 zones.
- Place the populated SAW close to U9 RF_IN and the ESD/bias injection close to J9. Use a continuous reference plane, 50 Ohm controlled impedance, and a ground-via fence.
- Keep at least 5 mm from other RF components where the final board geometry allows; maximize cellular-to-GNSS antenna separation.
- Do not route signals under U9 on the top or second copper layer. Ground those layers below the module and use dense stitching vias.
- Read `UBX-MON-RF`, `UBX-SEC-SIG`, `UBX-NAV-STATUS`, `UBX-NAV-CLOCK`, and `UBX-TIM-TP` evidence. Position trust and time trust remain independent.
- A GNSS position change never silently modifies commissioned station coordinates. Suspect time or PPS invalidates TDOA use until the configured recovery criteria pass.

## Review A and EVT evidence still required

- Verify all 20 authority rows against final symbols, the u-blox land pattern, and the Hirose footprint.
- Measure VCC/V_IO ramp, startup inrush, continuous and standby current, PPS level, PPS jitter, UART loading, and powered-off drive behavior at temperature.
- Prove open/short antenna detection, power removal, automatic recovery, and no damage under cable faults.
- Measure the complete active-antenna bias voltage/current and qualify one exact antenna/cable assembly over temperature and cable length.
- Measure SAW insertion loss, receiver sensitivity, LTE/EGPRS/RU868 coexistence, antenna isolation, conducted spurious response, and enclosure impact.
- Complete exact support-component MPNs, native ERC, layout Review B, BOM-from-schematic provenance, and both independent PCB reviews before manufacturing release.
