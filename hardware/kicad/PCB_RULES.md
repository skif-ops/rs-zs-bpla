# EVT PCB routing rules v0.4

- Rev.A copper-layer authority: PCB-MAIN 6, PCB-PWR 4 and PCB-MIC 2 layers; see `hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv`.
- PCB-MAIN layer-function request basis: Signal/GND/Power/Signal/GND/Signal. Final dielectric construction, copper weights and numeric fabrication rules come from the selected PCB fabricator.
- PCB-PWR uses four copper layers for continuous return and thermal spreading. Outer 2 oz and inner 1 oz are request targets only until current-density, thermal and fabricator DFM acceptance close.
- Continuous GND reference under high-speed digital and RF routes. Do not split return paths under SPI/OCTOSPI/UART clocks.
- Keep cellular V_CELL current loop short and wide; modem bulk capacitance adjacent to BG95 VBAT pins.
- Separate cellular DC/DC, LTE antenna, and high-current switching from acoustic PCB and microphone rail.
- PDM clock/data matched sufficiently for common-clock capture; avoid parallel run next to cellular RF/high-current switch node.
- GNSS antenna at enclosure top with keepout and no solar-panel/metal obstruction above it.
- SX1262 RF network copied from Semtech/reference RF design and tuned on assembled enclosure.
- RF 50 ohm controlled impedance only after actual stackup is known; no guessed trace width in the schematic package.
- ESD at external solar, battery/service connectors, SIM and exposed antenna connectors as appropriate.
- Test points accessible without disassembling acoustic seals: SWD, NRST, V_CELL, V3V3, PPS, BG95 UART, LoRa DIO1.
- Creepage/clearance is low-voltage SELV; retain manufacturing margins and avoid routing beneath antenna keepouts.
