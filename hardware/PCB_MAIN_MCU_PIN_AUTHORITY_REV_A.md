# PCB-MAIN U1 pin authority - EVT-PRE-20 Rev.A

Status: `PIN_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-001`. It establishes the complete package-pin disposition for U1 `STM32U585VIT6Q` in the `LQFP100_SMPS` package. It does not release the native PCB-MAIN schematic, PCB Review A, PCB Review B, or the production BOM.

## Primary evidence

- ST CubeMX device data: `mcu/STM32U585VITxQ.xml` at pinned upstream commit `f4ec11f00e762e37ffc4020f6d4f20d225bc061d`.
- Pinned XML SHA-256: `4349055dfd06e6eb2dce1a440c44a995ad7c924e28435ede119a7d4bb10f556d`.
- ST datasheet: DS13086 Rev 10, July 2024, `https://www.st.com/resource/en/datasheet/stm32u585ai.pdf`.
- ST hardware-development application note: AN5373 Rev 7, `https://www.st.com/resource/en/application_note/an5373-getting-started-with-stm32u5-mcu-hardware-development-stmicroelectronics.pdf`.
- Project functional map: `hardware/EVT_PRE_20_PIN_MAP_REV_A.csv` plus `hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv`.

The 100 package positions are accounted for as 65 locked functional assignments, 14 explicit unused I/O positions, one NRST position, and 20 power, reference, SMPS, or ground positions.

## Power and reference implementation contract

| Package pin group | Rev.A net | Required local implementation |
|---|---|---|
| VDD pins 11, 27, 51, 75, 100 | `3V3_DIGITAL` | 100 nF at every VDD pin plus one package-level 10 uF bulk capacitor |
| VSS pins 10, 26, 50, 74, 99 | `GND` | Direct ground connection |
| VBAT pin 6 | `3V3_DIGITAL` | No backup cell in Rev.A; tie to VDD with 100 nF |
| VDDA pin 21 | `3V3_DIGITAL` | Direct single-supply connection with 100 nF plus 1 uF |
| VSSA pin 19 | `GND` | Direct analog-ground connection |
| VREF+ pin 20 | `3V3_DIGITAL` | Tie to VDDA with 100 nF plus 1 uF; VREFBUF disabled |
| VDDUSB pin 73 | `3V3_DIGITAL` | 100 nF local decoupling |
| VDDSMPS pin 47 | `3V3_DIGITAL` | 10 uF; ESR below 10 milliohm at 3 MHz; voltage rating at least 10 V |
| VLXSMPS pin 46 | `SMPS_SW` | 2.2 uH inductor to the joined VDD11 rail; tolerance +/-20 percent; Isat above 0.5 A; DCR below 200 milliohm |
| VDD11 pins 49 and 98 | `VCORE_1V1` | Joined only to the SMPS/LDO core node; 2 x 2.2 uF to VSSSMPS plus one optional 100 nF at each pin |
| VSSSMPS pin 48 | `GND` | Direct SMPS power-ground connection |

`VCORE_1V1` must never power external circuitry. The final capacitor and inductor MPNs, RefDes allocation, placement, ESR, and DC-bias verification remain controlled by `MAIN-AUTH-010`.

## Clock and debug dispositions

- No HSE is fitted. PH0/OSC_IN pin 12 and PH1/OSC_OUT pin 13 are explicit NC. The native schematic must contain no HSE crystal, oscillator, load capacitors, or optional HSE footprints.
- SiT1552 drives PC14/OSC32_IN pin 8 as `LSE_IN`. PC15/OSC32_OUT pin 9 is reserved internally by the RCC external-clock mode but is explicit external NC.
- PA13/SWDIO, PA14/SWCLK, and NRST remain accessible on the five-position STM32 SWD fixture contract. JTAG-only PB3 and PB4 are NC.

This authority must be checked again against the rendered native schematic and CubeMX pin report during Review A. Until the remaining capture authorities and signed Review A/B evidence are complete, PCB-MAIN and the production BOM remain blocked and not for manufacture.
