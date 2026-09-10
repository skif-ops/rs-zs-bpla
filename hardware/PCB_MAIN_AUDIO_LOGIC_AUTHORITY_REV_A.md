# PCB-MAIN audio and AAD logic authority - EVT-PRE-20 Rev.A

Status: `AUDIO_LOGIC_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-003`. It freezes the exact U7, U17, and U18 physical-pin maps, voltage domains, directions, AAD OR topology, safe states, unused channels, and mandatory local networks. It does not release native PCB-MAIN capture, PCB Review A, PCB Review B, or the production BOM.

Machine authority: `hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `ff84acbcc8ecc104cbc6691d5a2eaed652adfab082c510518bd0ab487da68267`.

## Primary evidence

- TI `SN74AXC8T245` datasheet SCES875C, Revision C, January 2024: `https://www.ti.com/lit/ds/symlink/sn74axc8t245.pdf`. Retrieved document SHA-256: `6cf4003c438c0546fb86f0932613896197dd19a75bdb307f385eb6e75535126e`.
- TI `SN74LVC32A` datasheet SCAS286U, Revision U, July 2024: `https://www.ti.com/lit/ds/symlink/sn74lvc32a.pdf`. Retrieved document SHA-256: `807f6fff7977736035c2a3144d530be7ad737a163b2f0fd11002a45953b47230`.
- TI `SN74AXC1T45` datasheet SCES882E, Revision E, December 2023: `https://www.ti.com/lit/ds/symlink/sn74axc1t45.pdf`. Retrieved document SHA-256: `41e03bd8f0740ae8bbdf92309e7c82bac1359a768556cbe68de41b0273e49f12`.
- TDK `T5838` datasheet DS-000383, Revision 1.2, release date 4 September 2025, obtained from the official TDK documentation API and CDN. Retrieved document SHA-256: `5befb710bfe7a415cdc1aba41ebc18b484d7f9fc320ce15a7481507531cf58a4`.
- Project MCU functional sources: `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv`, `hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv`, and `hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv`.
- Project harness source: `hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv`.

## U7 SN74AXC8T245PWR contract

The exact PW package has 24 pins and two independent direction groups. This is not a single-direction eight-channel translator. With `VCCA=1V8_MIC`, `VCCB=3V3_DIGITAL`, `DIR1=HIGH`, and `DIR2=LOW`, channels 1 through 4 translate from A to B while channels 5 through 8 translate from B to A at the same time.

| U7 group | Direction | 1.8 V port A | 3.3 V port B |
|---|---|---|---|
| 1 | A to B | A1..A4 = `PDM_DATA1_1V8`..`PDM_DATA4_1V8` | B1..B4 = `PDM_DATA1`..`PDM_DATA4` |
| 2 used | B to A | A5 = `PDM_CLK_1V8`; A6 = `AAD_CFG_1V8` | B5 = `PDM_CLK`; B6 = `AAD_CFG` |
| 2 unused | B to A | A7 and A8 externally NC | B7 and B8 tied directly to GND |

- U7 pin 2 `DIR1` is tied directly to `1V8_MIC`.
- U7 pin 11 `DIR2` is tied directly to GND.
- U7 pin 22 active-low `OE` is tied directly to GND, so `OE=LOW`. Rev.A therefore keeps U7 enabled whenever both rails are valid.
- This fixed-control choice consumes no additional STM32 GPIO and keeps all control inputs at valid VCCA-referenced levels during reset.
- TI specifies VCC isolation when either rail is below 100 mV, Ioff partial-power protection, and no required supply order. These features prevent a powered domain from back-feeding a fully unpowered domain.
- TI specifies 288 kOhm typical internal weak pull-downs on every U7 data I/O. They hold source-side inputs low during MCU or microphone tri-state conditions. No external pull-up or pull-down is allowed on any `PDM_DATAn_1V8` net because TDK explicitly prohibits it for the tri-stated PDM data waveform.
- `PDM_CLK` and `AAD_CFG` are held low outside active clocking or one-wire writes. Therefore U7 produces no microphone clock and no THSEL transition in S0, even though the translator itself remains enabled.
- U7 maximum combined static supply current is 55 uA at 125 C with valid static inputs. This current is an explicit S0 budget item and must be measured on the assembled system.
- Place 100 nF at VCCA pin 1 and 100 nF at each VCCB pin 23 and pin 24. Exact capacitor RefDes and MPN are assigned by `MAIN-AUTH-010`.
- `PDM_CLK_1V8` source termination and final `AAD_CFG_1V8` fanout damping, if required by measurement, are assigned by `MAIN-AUTH-010`. The four final harnesses remain subject to rise-time, overshoot, skew, and THSEL-write verification.

The harness-facing 1.8 V nets carry `_1V8` in native KiCad so they cannot be accidentally shorted across U7 to the same logical names on the 3.3 V MCU side. The logical MIC harness contract remains `PDM_CLK`, `PDM_DATAn`, and `AAD_CFG`; the CSV records the physical-domain mapping at U7.

## U17 SN74LVC32APWR contract

U17 operates from `1V8_MIC`. Its three used gates implement this exact active-high function:

`MIC_WAKE_OR_1V8 = (MIC_WAKE1 OR MIC_WAKE2) OR (MIC_WAKE3 OR MIC_WAKE4)`

- Gate 1 uses pins 1, 2, and 3 for `MIC_WAKE1`, `MIC_WAKE2`, and `MIC_WAKE12_OR_1V8`.
- Gate 2 uses pins 4, 5, and 6 for `MIC_WAKE3`, `MIC_WAKE4`, and `MIC_WAKE34_OR_1V8`.
- Gate 3 uses pins 9, 10, and 8 for the two first-stage outputs and `MIC_WAKE_OR_1V8`.
- Unused gate inputs pin 12 and pin 13 are tied directly to GND. Unused output pin 11 is externally NC.
- Each `MIC_WAKEn` input has a required 100 kOhm pull-down to GND, so an absent or open MIC harness is inactive rather than floating. Each input also has a Review A test point before aggregation. Passive RefDes and exact resistor MPNs are assigned by `MAIN-AUTH-010`.
- T5838 WAKE is a push-pull active-high output. TDK guarantees `VOH >= 0.7 x VDD` at 0.5 mA, while U17 requires `VIH >= 0.65 x VCC` from 1.65 V to 1.95 V. Because both use the same `1V8_MIC` rail, the guaranteed ratio has 0.05 x rail margin. A 100 kOhm pull-down draws only 18 uA at 1.8 V, far below the 0.5 mA TDK test load.
- U17 drives only the U18 A input and its internal 288 kOhm pull-down. At the TI 100 uA output test point, U17 guarantees `VOH >= VCC - 0.3 V` and `VOL <= 0.3 V` through 125 C, both valid for the U18 VCCA-referenced input thresholds.
- Place one 100 nF bypass capacitor at U17 pin 14 to GND pin 7. Exact capacitor RefDes and MPN are assigned by `MAIN-AUTH-010`.

## U18 SN74AXC1T45DRLR contract

- U18 DRL package pin 1 `VCCA` uses `1V8_MIC`; pin 6 `VCCB` uses `3V3_DIGITAL`; pin 2 is GND.
- Pin 5 `DIR` is tied directly to `1V8_MIC`, fixing A-to-B translation.
- Pin 3 A receives `MIC_WAKE_OR_1V8` from U17 pin 8. Pin 4 B drives STM32 `MIC_WAKE` at PA8, LQFP100 pin 67.
- `MIC_WAKE` has a required 100 kOhm pull-down to GND on the MCU side. PA8 therefore remains inactive if U18 is high impedance during a partial-power condition.
- TI specifies Ioff, VCC isolation below 100 mV on either rail, glitch suppression, and unrestricted supply order. U18 maximum combined static supply current is 16 uA at 125 C.
- Place one 100 nF bypass capacitor at each U18 supply pin. Exact capacitor RefDes and MPN are assigned by `MAIN-AUTH-010`.

## Deterministic states

| Condition | Required state |
|---|---|
| Reset or MCU GPIO high impedance with both rails valid | U7 data-input weak pull-downs keep `PDM_CLK_1V8` and `AAD_CFG_1V8` low; U17 external pulls keep all open harness inputs low |
| AAD A or AAD D2 S0 monitoring | `1V8_MIC` remains on; `PDM_CLK=LOW`; `AAD_CFG=LOW`; U17 and U18 remain active; PA8 is low until any T5838 asserts WAKE |
| Any one MIC connector absent | Its 100 kOhm input pull-down represents inactive LOW; the remaining three WAKE channels still aggregate normally |
| `1V8_MIC` fully off or `3V3_DIGITAL` fully off | AXC VCC isolation and Ioff prevent active drive into the unpowered domain; PA8 external pull-down keeps `MIC_WAKE` low when applicable |
| Normal PDM capture | U7 channels 1 through 4 translate four independent data lines to the MCU while channel 5 translates the common clock to all leaves |
| AAD one-wire configuration | U7 channel 6 broadcasts PA15 `AAD_CFG` to all four T5838 THSEL pins; PDM clock follows the TDK sequence required by the selected AAD mode |

## Review A measurements still required

Closing `MAIN-AUTH-003` freezes capture inputs but does not replace hardware verification. Review A and EVT must still include:

- oscilloscope validation of all four PDM data channels at the U7 A and B ports, including T5838 tri-state intervals;
- final-harness PDM clock rise/fall time, overshoot, ringing, duty cycle, inter-channel skew, and source-termination decision;
- `AAD_CFG_1V8` one-wire amplitude, rise time, fanout, register-write success, cold boot, brownout, and microphone-rail-cycle recovery;
- individual `MIC_WAKE1..4`, both U17 first-stage nodes, U17 aggregate output, U18 output, and PA8 Stop-mode wake latency;
- open-harness and short-to-ground fault behavior for every microphone connector;
- false-wake and missed-wake tests over the project acoustic and temperature matrix;
- measured U7/U17/U18 current and complete system S0 current at the defined environmental points.

Exact passive identities remain controlled by `MAIN-AUTH-010`. Native capture, ERC, BOM-from-schematic comparison, and independent PCB Review A remain mandatory.
