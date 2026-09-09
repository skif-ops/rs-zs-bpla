# PCB-MAIN cellular modem authority - EVT-PRE-20 Rev.A

Status: `CELLULAR_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-004`. It freezes the exact U8 BG95-M3 and U16 translator pads, the two open-collector control stages, deterministic reset states, modem power sequencing, and the required local burst network. It does not close the dual-SIM network in `MAIN-AUTH-005`, the cellular RF endpoint and recovery fixture in `MAIN-AUTH-009`, the exact passive set in `MAIN-AUTH-010`, layout authority in `MAIN-AUTH-011`, native capture, PCB Review A, PCB Review B, or the production BOM.

Machine authority: `hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `f7aee6022ad4d74a8cc7cca9626a1f3d009ed5c461702edf44c30887b34e0c3a`.

## Primary evidence

- Quectel `BG95 Series Hardware Design`, version 1.6, 14 August 2023. The retrieved original Quectel document has SHA-256 `6ff03aa31577971d02dc15eac11adee4d52b80077ae3fa3503978c1b12496e81`. Public document copy: `https://raw.githubusercontent.com/jamesmarrs/farseer/fd4425f955fb3ebf50f330afe9228b8911a85a86/datasheets/quectel_bg95_series_hardware_design_v1-6.pdf`. Canonical product page: `https://www.quectel.com/product/lpwa-bg95-cat-m1-cat-nb2-egprs-series/`.
- TI `SN74AXC8T245` datasheet SCES875C, Revision C, January 2024: `https://www.ti.com/lit/ds/symlink/sn74axc8t245.pdf`. Retrieved document SHA-256: `6cf4003c438c0546fb86f0932613896197dd19a75bdb307f385eb6e75535126e`.
- Nexperia `MMBT3904` product data sheet, version 5, 8 April 2026: `https://assets.nexperia.com/documents/data-sheet/MMBT3904.pdf`.
- Project sources: `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv`, `hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv`, `hardware/POWER_DESIGN_BASELINE_REV_A.json`, `hardware/POWER_DESIGN_CALC_REV_A.md`, and `hardware/PWR_MAIN_12PIN_I2C_FREEZE_REV_A.md`.

## U8 BG95-M3 pad contract

The selected module is the 102-pad `BG95-M3` in the 23.6 x 19.9 mm LGA form. Every physical pad is accounted for in the machine authority. The accounting includes 28 ground pads, four VBAT pads, one VDD_EXT output, seven locally closed functional signals, six dual-SIM pads owned by `MAIN-AUTH-005`, seven RF/recovery pads owned by `MAIN-AUTH-009`, and all unused, unsupported, and reserved pads.

The following locally closed signals are exact:

| U8 pad | BG95 signal | Rev.A net | Destination |
|---:|---|---|---|
| 15 | `PWRKEY` | `U8_PWRKEY_N` | Q1 open collector |
| 17 | `RESET_N` | `U8_RESET_N` | Q2 open collector |
| 20 | `STATUS` | `U8_STATUS_1V8` | U16 A2 |
| 29 | `VDD_EXT` | `U8_VDD_EXT_1V8` | U16 VCCA and local 1.8 V pull-ups |
| 30 | `MAIN_DTR` | `U8_MAIN_DTR_1V8` | U16 A6 |
| 34 | `MAIN_RXD` | `U8_MAIN_RXD_1V8` | U16 A5 |
| 35 | `MAIN_TXD` | `U8_MAIN_TXD_1V8` | U16 A1 |
| 39 | `MAIN_RI` | `U8_MAIN_RI_1V8` | U16 A3 |

- Pads 32 and 33 are both `VBAT_BB` and connect to `3V8_MODEM_BB`.
- Pads 52 and 53 are both `VBAT_RF` and connect to `3V8_MODEM_RF`.
- The BG95-M3 input range is 3.3 to 4.3 V with 3.8 V nominal. The rail must never fall below 3.3 V at any U8 VBAT pad.
- All 28 module GND pads connect to the low-impedance `GND_MODEM` plane with ground vias placed according to the Quectel land pattern.
- Pad 60 `ANT_MAIN` is fixed as the `CELL_RF` source, but its 50 Ohm route, matching, protection, U.FL endpoint, and layout acceptance remain owned by `MAIN-AUTH-009` and `MAIN-AUTH-011`.
- Pads 42 through 47 are explicitly owned by `MAIN-AUTH-005`; their presence in this map fixes the U8 pad identities but does not release the dual-SIM circuit.
- Pads 8 through 10, 22, 23, and 75 remain owned by `MAIN-AUTH-009` for modem firmware-recovery and production-fixture decisions.
- All reserved pads remain NC. Unsupported `ANT_WIFI` pad 56 and `GNSS_LNA_EN` pad 51 remain NC for BG95-M3. Unused BOOT_CONFIG pads have no pull-up.

## Burst-current supply network

The external source is the single `3V8_MODEM` rail from PCB-PWR. It splits at a star point close to U8:

| Branch | Required local network | Copper rule |
|---|---|---|
| `3V8_MODEM_BB` | 100 uF low-ESR bulk plus 220 nF, 47 nF, 150 pF, 100 pF, 68 pF, 33 pF, and 10 pF; ferrite bead immediately before U8 | at least 0.6 mm equivalent width and wider for longer routes |
| `3V8_MODEM_RF` | 100 uF low-ESR bulk plus 100 nF, 33 pF, and 10 pF; 0 Ohm link immediately before U8 | at least 2.7 mm equivalent width and no neck-down |

- The ferrite bead must be rated at least 600 mA, have low DC resistance, and provide at least 800 Ohm impedance in the 700 to 960 MHz range. Its exact MPN remains `MAIN-AUTH-010`.
- The two low-leakage TVS positions recommended by Quectel and all exact capacitor, ferrite, and 0 Ohm MPNs remain `MAIN-AUTH-010` items.
- The 4 A PCB-PWR source remains mandatory because BG95-M3 supports EGPRS and Quectel requires a supply capability above 2.7 A when LTE Cat M1, Cat NB2, and EGPRS are enabled.
- Review A must probe the rail at all four U8 VBAT pads. Load-step and representative 2G burst tests must prove `VBAT_BB >= 3.3 V` and `VBAT_RF >= 3.3 V` at the module.

## U16 SN74AXC8T245PWR contract

U16 uses the BG95 `VDD_EXT` output for VCCA. It therefore powers down with the modem 1.8 V domain. VCCB uses `3V3_DIGITAL`, U16 GND uses `GND_MODEM`, and active-low OE is tied to `GND_MODEM`. TI VCC isolation and Ioff prevent a powered 3.3 V MCU domain from driving an unpowered modem domain.

| U16 group | Direction | 1.8 V port A | 3.3 V port B |
|---|---|---|---|
| 1 | A to B | A1 `MAIN_TXD`, A2 `STATUS`, A3 `MAIN_RI` | B1 `CELL_RX`, B2 `CELL_STATUS`, B3 `CELL_RI` |
| 1 unused | A to B | A4 tied to `GND_MODEM` | B4 NC |
| 2 | B to A | A5 `MAIN_RXD`, A6 `MAIN_DTR` | B5 `CELL_TX`, B6 `CELL_DTR` |
| 2 unused | B to A | A7 and A8 NC | B7 and B8 tied to `GND_MODEM` |

- DIR1 is tied directly to `U8_VDD_EXT_1V8`, so channels 1 through 4 translate A to B.
- DIR2 is tied directly to `GND_MODEM`, so channels 5 through 8 translate B to A.
- OE is tied directly to `GND_MODEM`; the translator is enabled only while both rails are valid and is isolated when `VDD_EXT` is absent.
- Place 100 nF at U16 VCCA and at each VCCB pin. Exact capacitor RefDes and MPNs remain `MAIN-AUTH-010`.
- `CELL_TX` has 10 kOhm to `3V3_DIGITAL` so the modem RX input defaults to UART idle HIGH.
- `CELL_DTR` has 100 kOhm to `GND_MODEM` so the modem remains awake until firmware deliberately requests sleep.
- `U8_MAIN_TXD_1V8` and `U8_MAIN_RI_1V8` each have 10 kOhm to `U8_VDD_EXT_1V8`. This overcomes U16's 288 kOhm typical weak pull-down and defines the required inactive HIGH state.
- `CELL_RX` and `CELL_RI` have 100 kOhm to `3V3_DIGITAL`; `CELL_STATUS` has 100 kOhm to `GND_MODEM`. Firmware masks RI and ignores UART data until `CELL_STATUS=HIGH`.

At the minimum U16 VCCA value of 1.65 V, the guaranteed U16 output HIGH toward BG95 is 1.35 V and the BG95 input requirement is 1.2 V. The guaranteed HIGH margin is therefore 150 mV. Review A must measure the peak `GND_MODEM` to `GND_DIGITAL` offset plus noise under 2G burst and prove it is below 75 mV at U16.

## Q1 and Q2 open-collector controls

Q1 and Q2 are Nexperia `MMBT3904,215` in SOT23. The exact pin order is 1 base, 2 emitter, 3 collector.

- Each base is driven through 4.7 kOhm from its STM32 command and has 47 kOhm from base to emitter.
- Both emitters connect to `GND_MODEM`.
- Q1 collector connects to U8 pad 15 `PWRKEY`; the node has 10 nF to `GND_MODEM` and a Review A test point.
- Q2 collector connects to U8 pad 17 `RESET_N`; the node has a Review A test point and no large capacitance.
- MCU command HIGH asserts the corresponding active-LOW U8 input. MCU reset or command LOW leaves the transistor off.
- The Q1 and Q2 commands must never overlap. Quectel states that RESET_N connects internally to PWRKEY.

Exact 4.7 kOhm, 47 kOhm, and 10 nF passive MPNs remain `MAIN-AUTH-010`, but their values and topology are fixed by this authority.

## Deterministic power sequence

| Operation | Required sequence |
|---|---|
| Cold OFF | `EN_MODEM=LOW`; Q1 and Q2 off; U16 VCCA absent; U16 I/O isolated; `CELL_STATUS=LOW` |
| Power on | Set both commands LOW and `CELL_DTR=LOW`; assert `EN_MODEM`; wait for stable `PWR_GOOD`; wait at least 30 ms; assert `CELL_PWRKEY_CMD=HIGH` for the selected 700 ms pulse inside the Quectel 500-1000 ms window; release LOW |
| Ready | Wait for `CELL_STATUS=HIGH`; do not trust UART or RI before this state; then synchronize AT commands |
| UART sleep | After `AT+QSCLK=1`, set `CELL_DTR=HIGH`; drive it LOW before sending AT data |
| Normal shutdown | Stop traffic; persist queues; issue `AT+QPOWD`; keep Q1 off; wait for `CELL_STATUS=LOW`; only then deassert `EN_MODEM` |
| Shutdown fallback | If AT shutdown fails, pulse Q1 for 650-1500 ms; wait for `CELL_STATUS=LOW`; only then remove the rail |
| Emergency reset | With the rail on, assert Q2 for 2-3.8 s and then release; do not assert Q1 simultaneously |

The rail must not be cut while `CELL_STATUS=HIGH`. Fast shutdown on U8 pad 25 is not enabled in Rev.A.

## Review A and EVT evidence still required

- Verify all 102 U8 pads against the final native symbol and land pattern.
- Record the exact ordered BG95-M3 firmware and regional procurement identity.
- Probe PWRKEY, RESET_N, STATUS, VDD_EXT, both UART directions, DTR, and RI across cold start, warm restart, shutdown, and brownout.
- Verify the 700 ms power-on pulse, the 650-1500 ms shutdown fallback window, and the 2-3.8 s emergency reset window.
- Verify U16 partial-power isolation with `3V3_DIGITAL` present and `3V8_MODEM` absent.
- Verify all four U8 VBAT pads remain at or above 3.3 V during representative LTE and EGPRS bursts.
- Measure `GND_MODEM` to `GND_DIGITAL` offset and noise at U16; the peak must remain below 75 mV.
- Complete dual-SIM, modem recovery, cellular RF, exact passive, layout, native ERC, BOM-from-schematic, and independent PCB reviews before any manufacturing release.
