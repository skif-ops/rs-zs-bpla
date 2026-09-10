# PCB-MAIN LoRa authority - EVT-PRE-20 Rev.A

Status: `LORA_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-007`. It freezes the 22 U10 module pads, two J10 electrical contacts, separate MCU-controlled RF-switch enables, fail-closed startup states, the 3.3 V supply budget, and the RU868 board RF path. It does not release exact support-component MPNs, the supplier-specific antenna-interface option, the external cable/antenna, native capture, RF layout, regulatory limits, PCB Review A, PCB Review B, or the production BOM.

Machine authority: `hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `efb075342ac159d3c96a8d84cbd464d592156c6f3ad53e57875efcc5c7dd5d2a`.

## Primary evidence

- Ebyte `E22-M series user manual`, v1.2, 6 February 2026: `https://www.ebyte.com/Uploadfiles/Files/2026-2-7/2026271136241143.pdf`. Retrieved SHA-256: `c66665745ef6f4a04de77201026d92841066b69575f62a717fe02bc363df62bf`.
- Ebyte exact `E22-900M22S` product page: `https://www.ebyte.com/product/435.html`.
- Hirose exact U.FL receptacle product page: `https://www.hirose.com/en/product/p/CL0331-0472-2-60`.

The current Ebyte v1.2 family manual explicitly lists the exact 20 x 14 mm `E22-900M22S`, SX1262, 850 to 930 MHz, 22 dBm, SPI, 22-pad product. It supersedes the older product-manual control drawing where the current manual differs. The 10 x 10 mm `E22-900MM22S` is a different module and is forbidden as a silent substitute.

## Supply and oscillator contract

U10 VCC is `3V3_DIGITAL`. Ebyte specifies 1.8 to 3.7 V for the 22 dBm family and recommends at least 3.0 V for full output. The current manual gives 100 to 140 mA transmit current at 22 dBm, approximately 7 mA receive current, and approximately 0.18 uA software shutdown current. Applying Ebyte's 30 percent supply-headroom rule to 140 mA gives a minimum U10 branch capability of 182 mA.

U10 pin 9 has local 100 nF plus 10 uF ceramic decoupling. Review A and EVT must verify the final 3.3 V rail allocation, RF-burst droop, current and temperature rise. Exact capacitor MPNs and RefDes are frozen by `MAIN-AUTH-010`.

The exact 20 x 14 mm module uses an internal 32 MHz TCXO. Firmware must configure the SX1262 DIO3 TCXO supply to 2.2 V before radio operation. The passive-crystal exception in the current Ebyte manual applies to `E22-900MM22S`, not the selected `E22-900M22S`.

## RF-switch and reset safe states

The current Ebyte recommended circuit drives TXEN and RXEN separately from the host. Rev.A therefore uses:

| Function | U10 pad | STM32 endpoint | Reset state |
|---|---:|---|---|
| transmit enable | 7 `TXEN` | PB15 / package pin 54 `LORA_TXEN` | LOW through 100 kOhm pull-down |
| receive enable | 6 `RXEN` | PD8 / package pin 55 `LORA_RXEN` | LOW through 100 kOhm pull-down |
| radio interrupt | 13 `DIO1` | PC2 / EXTI2 `LORA_DIO1` | MCU input held LOW through 100 kOhm |
| busy status | 14 `BUSY` | PD9 `LORA_BUSY` | MCU input held LOW through 100 kOhm |
| reset | 15 `NRST` | PD10 `LORA_RESET_N` | HIGH through 10 kOhm and 100 nF reset capacitor |

The Ebyte truth table is locked: TX is TXEN=1/RXEN=0, RX is TXEN=0/RXEN=1, and CLOSE is TXEN=0/RXEN=0. TXEN=1/RXEN=1 is forbidden. Firmware sets CLOSE before reset, sleep, region validation, and every TX/RX transition. U10 DIO2 pad 8 is explicit NC; Rev.A does not enable DIO2 RF-switch control and does not short DIO2 to TXEN.

`LORA_NSS` has a 10 kOhm pull-up so the radio remains deselected while the MCU is in reset. NSS, SCK and MOSI have 22 Ohm source-series positions at the STM32; MISO has a 22 Ohm source-series position at U10. These values are topology inputs for `MAIN-AUTH-010`; final signal-integrity confirmation remains Review A evidence.

## RU868 RF path

Rev.A uses U10 castellated ANT pad 21, not a module-mounted IPEX connector. The exact Ebyte model name covers IPEX-1 and castellated antenna forms, so the purchase order, supplier quote or certificate of conformity must explicitly state the castellated-ANT option with no module-side IPEX fitted before production release.

The controlled board RF chain is:

`U10 pin 21 LORA_RF_MODULE -> pi network with populated 0 Ohm series baseline and two DNP shunts -> connector-side ultra-low-capacitance ESD -> J10 center LORA_RF_ANT`.

The route is 50 Ohm controlled impedance over uninterrupted RF ground. U10 pads 20 and 22, all other module grounds and the J10 shell use dense ground stitching. J10 is exact Hirose `U.FL-R-SMT-1(60)` and doubles as the conducted-test port; a tee test point or other RF stub is forbidden. Exact pi/ESD MPNs and RefDes are frozen by `MAIN-AUTH-010`. The cable and antenna remain separate unreleased system BOM lines.

All 20 pilot units use only the signed RU868 profile. Power, duty cycle, occupied bandwidth and channel mask remain fail-closed; no transmission is authorized merely by this electrical authority.

## Layout and firmware constraints

- Place U10, the pi network, ESD and J10 in one short RF chain away from DC/DC nodes, GNSS, cellular and PDM clocks.
- Do not route digital, analog or power traces under the module RF area. Use continuous ground and via fencing while preserving the exact Ebyte land pattern.
- Drive both RF-switch enables LOW before U10 reset or loss of a valid signed region profile. Assert only one enable after BUSY is LOW and before the corresponding radio command.
- Configure DIO3 for the internal 2.2 V TCXO supply before calibration or RF operation.
- Keep `config/lora/RU868.yaml` transmit-disabled until regulatory review, conducted power, occupied bandwidth, spurious emission and antenna VSWR evidence are signed.

## Review A and EVT evidence still required

- Verify all 24 authority rows against the final symbol, Ebyte land pattern, selected castellated module option and Hirose footprint.
- Measure reset timing, SPI integrity, TXEN/RXEN mutual exclusion, boot/brownout CLOSE state, BUSY/DIO1 behavior and 3.3 V burst droop over temperature.
- Measure conducted power, harmonics, occupied bandwidth, receiver sensitivity, cellular/GNSS coexistence and final cable/antenna VSWR.
- Capture supplier evidence that the delivered `E22-900M22S` has the castellated ANT interface and no fitted module-side IPEX connector.
- Complete exact support-component MPNs, native ERC, layout Review B, BOM-from-schematic provenance and both independent PCB reviews before manufacturing release.
