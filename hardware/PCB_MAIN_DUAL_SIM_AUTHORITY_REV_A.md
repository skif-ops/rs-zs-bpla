# PCB-MAIN dual-SIM authority - EVT-PRE-20 Rev.A

Status: `DUAL_SIM_AUTHORITY_PASS / PCB REVIEW A NOT STARTED / NOT FOR MANUFACTURE`

This record closes only `MAIN-AUTH-005`. It freezes the electrical pin maps and safe-state topology for U13, U14, U15, J6, J7, and Q3. It does not release the exact passive MPN set, connector procurement, native capture, connector placement and service orientation, PCB Review A, PCB Review B, or the production BOM.

Machine authority: `hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv`.

Authority CSV SHA-256: `5709e9d3ae8af4f77865891e5db8104d3f66e597f38194af0f95280d234fc814`.

## Primary evidence

- Quectel `BG95 Series Hardware Design`, version 1.6, 14 August 2023. Retrieved document SHA-256: `6ff03aa31577971d02dc15eac11adee4d52b80077ae3fa3503978c1b12496e81`. Public document copy: `https://raw.githubusercontent.com/jamesmarrs/farseer/fd4425f955fb3ebf50f330afe9228b8911a85a86/datasheets/quectel_bg95_series_hardware_design_v1-6.pdf`. Canonical product page: `https://www.quectel.com/product/lpwa-bg95-cat-m1-cat-nb2-egprs-series/`.
- TI `TS3A27518E` datasheet SCDS260F, Revision F, December 2021: `https://www.ti.com/lit/ds/symlink/ts3a27518e.pdf`. Retrieved document SHA-256: `d87c216911176dca84cc9cee5efb6f45b18021977f94a97c7fae989484a73392`.
- ST `ESDALC6V1-5P6` datasheet, Revision 3, November 2007: `https://www.st.com/resource/en/datasheet/esdalc6v1-5p6.pdf`. Retrieved document SHA-256: `ea14ac3604fa4887d91b9fbc55ab9d04a23ba6597b22a817e64185d519fb9e28`.
- TE Connectivity product page for `2336582-1`: `https://www.te.com/en/product-2336582-1.html`. Retrieved page SHA-256: `ba9c628c235d6ff36473a360cfb55c4646b54327226a1720194036ce060a9e01`.
- TE controlled customer drawing `C-2336582`, Revision A2, released 14 March 2023: `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocNm=2336582&DocType=Customer%20Drawing&DocLang=English&DocFormat=pdf&PartCntxt=2336582-1`. Retrieved document SHA-256: `2bcf8b28017d5716a1659ad5ad401d6158b272458de43ed4b325a80c7f70d6fe`.
- TE product specification `108-115163`, Revision A, 24 April 2019: `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocNm=108-115163&DocType=Specification%20Or%20Standard&DocLang=English&DocFormat=pdf&PartCntxt=2336582-1`. Retrieved document SHA-256: `2c46e4e52a95fc72314526df579e752e65cd02521eb1b9a074949d2ded866760`.
- TE qualification report `501-115178`, Revision A, 31 May 2019: `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=srchrtrv&DocNm=501-115178&DocType=Specification%20Or%20Standard&DocLang=English&DocFormat=pdf&PartCntxt=2336582-1`. Retrieved document SHA-256: `8dcedfc032be7e4f7f41bf5bcd13728926fa3009e7833e6a04ff58de9227ce37`.
- Nexperia `MMBT3904` product data sheet, version 5, 8 April 2026: `https://assets.nexperia.com/documents/data-sheet/MMBT3904.pdf`.

TE specification `108-115163` states that the controlled product drawing takes precedence if the documents conflict. The older specification gives an operating minimum of -30 C, while the A2 drawing and current product page specify -40 to +85 C. The Rev.A freeze follows the higher-priority drawing and current product page, while connector procurement remains blocked because TE reports the part as active but not currently available.

## U8 interface resolution

- U8 pin 42 `USIM_DET` is NC. Quectel explicitly permits it to remain open when module hot-plug detection is not used.
- J6 and J7 card-detect switches instead drive independent MCU inputs `SIM1_DET` and `SIM2_DET`.
- U8 pin 43 `USIM_VDD`, pin 44 `USIM_RST`, pin 45 `USIM_DATA`, and pin 46 `USIM_CLK` connect to the common side of U13.
- U8 pin 47 `USIM_GND` connects directly to `GND_MODEM`. J6 and J7 card grounds are never routed through U13.
- Only 1.8 V SIM cards are supported. A 3 V or 5 V card is not a valid Rev.A population.

## U13 switch topology

The project-local `TI_PW0024A_TSSOP24` footprint follows TI 4220208/A: 24
1.50 x 0.45 mm R0.05 lands at 0.65 mm pitch with 5.80 mm between row
centers, equal-size stencil apertures, and 0.05 mm NSMD expansion. It replaces
the incorrect 0.50 mm-pitch KiCad pattern previously assigned to U13.

U13 is the exact `TS3A27518EPWR` 24-pin TSSOP. It is powered from `3V3_DIGITAL`. This satisfies TI's VCC-first sequencing rule because the 3.3 V domain is established before U8 presents any USIM analog signal, and it reduces the guaranteed worst-case single-channel resistance to 7.6 Ohm over -40 to +85 C.

Three channels are paralleled for the selected card's VDD path. The guaranteed worst-case equivalent resistance is therefore at most 2.54 Ohm before PCB resistance. Review A must measure the actual selected-card voltage and prove at least 1.62 V at the connector throughout card startup, attach, temperature, and brownout tests.

| U13 channels | Common net | SIM1 NC path | SIM2 NO path |
|---|---|---|---|
| 1, 4, 6 in parallel | `CELL_USIM_VDD_1V8` | `SIM1_VDD_1V8` | `SIM2_VDD_1V8` |
| 2 | `CELL_USIM_RST_1V8` | `SIM1_RST_1V8` | `SIM2_RST_1V8` |
| 3 | `CELL_USIM_CLK_1V8` | `SIM1_CLK_1V8` | `SIM2_CLK_1V8` |
| 5 | `CELL_USIM_DATA_1V8` | `SIM1_DATA_1V8` | `SIM2_DATA_1V8` |

- U13 pins 14 `IN2` and 24 `IN1` are tied to `SIM_MUX_SEL` with 100 kOhm to `GND_MODEM`.
- `SIM_MUX_SEL=LOW` selects all SIM1 NC paths. `SIM_MUX_SEL=HIGH` selects all SIM2 NO paths.
- U13 pin 20 `EN` is active HIGH for High-Z. It is not connected directly to the MCU.
- Pin 20 uses 47 kOhm to `3V3_DIGITAL`, so U13 is High-Z whenever Q3 is off.
- U13 pin 8 has a local 100 nF bypass to `GND_MODEM`.
- U13 package pin 3 is NC as specified by TI.
- Selection is never changed while U13 is enabled or while U8 is running.

## Q3 boot-safe enable

Q3 is Nexperia `MMBT3904,215` in SOT23 with pin 1 base, pin 2 emitter, and pin 3 collector.

- `SIM_MUX_EN` drives the base through 10 kOhm; 100 kOhm from base to emitter holds Q3 off during MCU reset.
- The emitter is connected to `GND_MODEM`.
- The collector drives `U13_EN_N`. With Q3 off, the 47 kOhm pull-up makes U13 EN HIGH and all paths High-Z.
- MCU `SIM_MUX_EN=HIGH` turns Q3 on, makes U13 EN LOW, and connects the slot selected by `SIM_MUX_SEL`.
- The guaranteed Q3 saturation limit of 0.2 V is below the U13 VIL maximum of 0.65 V.

This inversion preserves the active-HIGH meaning of the existing MCU net and prevents the reset-default LOW command from enabling a card.

## U14, U15, J6, and J7

U14 protects J6 and U15 protects J7. Each exact `ESDALC6V1-5P6` uses pin 2 as the low-inductance `GND_MODEM` return and the other five pins for VDD, RST, CLK, DATA, and card detect. The device is rated -40 to +125 C, has 5 V reverse standoff, 70 nA maximum leakage at 3 V, 15 pF maximum capacitance, and IEC 61000-4-2 ratings of 8 kV contact and 15 kV air discharge.

J6 and J7 are identical TE `2336582-1` push-push 4FF sockets. Each electrical contact map is:

| Authority position | TE contact | Rev.A net |
|---:|---|---|
| 1 | C1 VCC | slot VDD from the three parallel U13 paths |
| 2 | C2 RST | slot reset |
| 3 | C3 CLK | slot clock |
| 4 | C5 GND | direct `GND_MODEM` |
| 5 | C6 VPP | NC |
| 6 | C7 I/O | slot bidirectional data |
| 7 | CD | independent MCU card-detect input |

The TE card-detect switch is normally shorted to the grounded shell with no card and opens when a card is inserted. Therefore `SIM1_DET` and `SIM2_DET` each use 10 kOhm to `3V3_DIGITAL`, read LOW with no card, and read HIGH with a card inserted. Each input also uses 10 nF to `GND_MODEM` and at least 20 ms firmware debounce.

Each socket has 100 nF from its selected VDD contact to `GND_MODEM`. RST, CLK, and DATA retain populated 0 Ohm series tuning positions and DNP 33 pF shunt tuning positions. Their exact RefDes, orderable passive MPNs, physical paths and shunt population are frozen by `MAIN-AUTH-010`. U14 and U15 are placed at the connector side of these paths.

All shell and card-detect return solder features connect directly to `GND_MODEM`. Exact J6/J7 anchor geometry and southward card insertion direction are now frozen by `MAIN-AUTH-011`; service-cover fit and physical card-clearance validation remain open.

## Deterministic slot sequence

| Operation | Required sequence |
|---|---|
| Cold state | `SIM_MUX_EN=LOW`; Q3 off; `U13_EN_N=HIGH`; U13 High-Z; `EN_MODEM=LOW` |
| Select | While U13 is High-Z and U8 is off, set `SIM_MUX_SEL=LOW` for SIM1 or HIGH for SIM2; verify the selected independent DET input |
| Connect | Enable `3V8_MODEM`; wait for stable `PWR_GOOD` and at least 30 ms; set `SIM_MUX_EN=HIGH`; verify `U13_EN_N=LOW`; then issue the 700 ms PWRKEY pulse |
| Ready | Wait for `CELL_STATUS=HIGH`; read ICCID and verify that it belongs to the selected slot profile before attach |
| Disconnect | Complete `AT+QPOWD`; wait for `CELL_STATUS=LOW`; set `SIM_MUX_EN=LOW`; verify `U13_EN_N=HIGH`; then remove `EN_MODEM` |
| Change slot | Only after Disconnect, update `SIM_MUX_SEL` and repeat Connect; a brownout makes slot identity unknown until ICCID is read again |

Changing `SIM_MUX_SEL` with Q3 on, U13 enabled, or `CELL_STATUS=HIGH` is a firmware fault. Removing a card from the energized product is prohibited by the service procedure even though each physical detect input remains observable.

## Review A and EVT evidence still required

- Verify all 55 authority rows against the final native symbols and the TE A2 land pattern.
- Confirm both sockets are genuine `2336582-1`, or qualify one pin-, footprint-, temperature-, and lifecycle-compatible second source before lot release.
- Measure socket VDD, RST, CLK, DATA, DET, U13 EN, and both selection states at -40 C, room temperature, and the hot qualification point.
- Prove selected socket VDD remains at least 1.62 V, and prove the unselected VDD, RST, CLK, and DATA paths remain isolated.
- Prove Q3 makes U13 High-Z at reset, brownout, firmware crash, and modem-off states.
- Run ESD, edge-integrity, 5000 mechanical-cycle evidence review, and at least 100 powered slot-change cycles.
- Verify ICCID-to-slot mapping, public APN attach, DNS, TLS, queue recovery, and rejection of unauthorized slot switching.
- Complete the exact passive set, service mechanics, native ERC, BOM-from-schematic, and both independent PCB reviews before manufacturing release.
