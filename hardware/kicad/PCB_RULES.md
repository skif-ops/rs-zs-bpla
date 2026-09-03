# EVT PCB routing rules v0.3

- Main board target: 6 layers for EVT. Recommended stack: Signal/GND/Power/Signal/GND/Signal. Final stackup from PCB fabricator.
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
