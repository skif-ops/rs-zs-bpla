# STM32U585 target, EVT-PRE-20 Rev.A

This directory binds the firmware target to the exact `STM32U585VIT6Q` in
`LQFP100_14x14`. The generated C headers are derived from the locked Rev.A pin
map, the AAD configuration addendum and the locked no-HSE clock policy.

Regenerate and run both quality gates from the repository root:

```sh
python tools/generate_evt_pre_20_target_contract.py
python tools/validate_evt_pre_20_target_contract.py
python tools/audit_evt_pre_20_target_technical.py
python tools/validate_evt_pre_20_cubemx_ioc.py
python tools/audit_evt_pre_20_cubemx_ioc_technical.py
python tools/import_evt_pre_20_stm32_vendor.py --check
python tools/validate_evt_pre_20_stm32_scaffold.py
python tools/audit_evt_pre_20_stm32_scaffold_technical.py
python tools/validate_installation_store_contract.py
python tools/validate_installation_commissioning_contract.py
python tools/audit_installation_commissioning_technical.py
python tools/validate_event_outbox_contract.py
python tools/validate_event_receipt_contract.py
python tools/audit_event_receipt_technical.py
python tools/generate_event_receipt_vector.py --check
python tools/validate_dual_sim_failover_contract.py
python tools/audit_dual_sim_failover_technical.py
```

QG-1 checks completeness, ordering and SHA-256 traceability. QG-2 separately
checks package-pin uniqueness, critical peripheral mappings, voltage-domain
bindings and the clock-policy invariants. The second gate pair checks the pinned
STM32CubeU5/CMSIS provenance, the exact 142-entry STM32U585 vector table and the
engineering memory layout independently.

The generated `dioneya_evt_pre_20_rev_a.ioc` is a deterministic pinout import
candidate for STM32CubeMX 6.12.0 / DB.6.0.120. It contains all 67 locked
assignments, the DEC-022 EXTI split and the DEC-023 LoRa RF-switch controls:
LoRa DIO1 is on PC2/EXTI2, microphone wake is on PA8/EXTI8, TXEN is on PB15
and RXEN is on PD8. Both RF-switch enables initialize LOW. QG-1 verifies full source representation and provenance;
QG-2 independently rejects duplicate EXTI sources, HSE activation and critical
peripheral drift.

The GCC startup and CMSIS system template are byte-for-byte imports from the
CMSIS commit pinned by STM32CubeU5 v1.9.0. The linker covers the full 2 MiB flash,
the contiguous 768 KiB SRAM1-3 and the separate 16 KiB SRAM4 retained section,
but is restricted to TrustZone-disabled engineering bring-up. SRAM4 placement
does not claim low-power retention until PWR configuration is measured.

The target remains non-releasable. The generated `.ioc` must still be opened,
reviewed and regenerated with STM32CubeMX 6.12.0. Clock-tree, internal MCU power
supply mode and peripheral runtime parameters are deliberately not released by
the pinout generator. HAL/LL integration, measured clocks, secure boot, A/B OTA,
production target build and hardware evidence remain blockers.

The portable installation-position store now provides a two-slot atomic record,
CRC, last-write commit marker, monotonic recommission version and read-back. Its
QG-1/QG-2 host result does not define STM32 Flash page addresses or close target
power-loss/endurance testing; that binding remains a target-port blocker.

The portable commissioning boundary now rejects MQTT/HTTPS coordinate writes,
requires an authenticated local BLE peer and a physical 10-minute service
window, computes the canonical record SHA-256 on the station, and brackets each
write with audit intent/commit callbacks. The nRF52840 GATT implementation,
durable audit backend and target service-window timer remain open target work.

The portable downstream-command boundary now has a canonical fixed-memory CBOR
codec, a bounded public-key rotation adapter, and a power-loss-safe
accepted/completed journal that cannot encode an ACK before completion is
durable. The journal now has a portable erase-isolated NOR adapter with one
physical erase block per record and host-tested torn-commit restart recovery;
the shared layout/binding also proves it is disjoint from archive and outbox.
Target slot count, OCTOSPI binding and endurance remain open.
A portable application channel enforces verify → accept → idempotent
execute → complete → ACK and safely replays accepted/completed duplicates. Host
QG includes a real server-generated Ed25519 vector. A portable binary MQTT
adapter now enforces the exact tenant/station `down` topic, QoS 1 and non-retained
delivery before command parsing, then exposes the exact `ack` topic and CBOR
payload length after durable completion. The target still needs reviewed Ed25519
library binding, provisioned public keys, production journal slot-count/OCTOSPI/endurance evidence
and hardware integration. Portable BG95 AT binding now confirms pre-connect
length mode, subscribes to exact `down` at QoS 1, parses binary `QMTRECV` by
declared length and publishes the durable ACK with fixed-length `QMTPUB`. A
server retry after UART failure returns the journaled ACK without re-execution.
A portable 2304-byte raw-UART session now serializes both subscriptions, event
publish and command ACK with one TX owner, preserves length-delimited binary
URCs across arbitrary input chunks, queues one command behind an active publish
and records further frames as server-retry required. Target USART1 DMA/ISR/cache
integration, retain-policy verification, reviewed crypto/Flash binding and
assembled-station evidence remain open.

The portable event outbox now atomically commits complete schema-4 detection
CBOR with metadata CRC32 and payload SHA-256, orders pending events by priority
then FIFO, persists up to 128 transmission attempts in a one-way bitmap, and
never reclaims a pending event. Only a verified server application ACK may mark
delivery; a torn marker intentionally causes safe at-least-once redelivery. Host
fault-injection is QG-1/QG-2 evidence only. The server now persists the exact
detection-payload SHA-256 and processing state before publishing a canonical
station-bound receipt; a fixed-memory firmware parser verifies the receipt and
marks only the matching pending item delivered. A portable MQTT uplink adapter
persists each attempt before exposing the exact outbox payload, publishes only
to the canonical station `up` topic, ignores PUBACK for reclamation and can apply
a queued receipt after restart by durable event lookup. Target NOR/Flash
binding now has a portable adapter that dedicates one physical erase block to
each outbox slot, preventing reclaim from erasing a neighbour. The shared bind
now first validates exact W25Q512JV JEDEC `EF 40 20`, SFDP/BFPT 64 MiB density,
4-byte geometry and Status Register-2 QE, restoring QE with read-back if needed;
all returned interfaces remain zero on failure. A portable layout
planner gives the audio archive the aligned NOR prefix, command journal the next
erase-isolated partition, and event outbox the tail, proving non-overlap for both
accepted caller-supplied slot counts. The host reference case verifies 62.9375
MiB archive + 64 KiB/16-slot journal + 1 MiB/256-slot outbox on 64 MiB NOR. A
single fail-closed bind API creates all three adapters from that layout and caps
the archive-visible storage at the journal boundary. Production slot counts,
target memory-map/OCTOSPI binding and wear/endurance remain release blockers.
Real sample identity/QE and power-loss behavior remain hardware gates.
The portable dual-SIM controller now enforces the audited, queue-preserving
single-standby sequence: 20 ms DET debounce, three attempts per profile,
900-second hold, authenticated manual changes, graceful modem-off and mux
/High-Z confirmation before slot select, 30 ms stable power-good, exact full
provisioned ICCID and attach/DNS/TLS before resume. The target still needs the
STM32 GPIO/modem-power/audit/profile binding and assembled-station fault and
100-cycle evidence; operator and 24-hour EVT remain deferred until assembly.
The portable BG95 bridge closes the host-only modem handshake inside that
sequence: it sends `AT+QPOWD`, requires caller-confirmed `CELL_STATUS=LOW`,
clears volatile SIM identity, admits PWRKEY only from `OFF`, and gates ICCID/link
actions on full identity plus valid online APN/IP/gateway/DNS state. Actual
PD13 sampling and the remaining STM32 GPIO/rail implementation stay blocked.
The portable BG95 uplink now emits fixed-length `QMTPUB`, waits for the data
prompt and writes exact binary CBOR bytes; partial UART writes, wrong result URCs,
offline transitions and timeout retain the pending event. Broker success still
does not reclaim it. Portable BG95 transport до `QMTOPEN` настраивает direct
receive с обязательным payload length; receipt binding после connect требует
успех этого шага, выполняет exact QoS-1 subscription и передаёт
length-delimited binary `+QMTRECV` в application-receipt validator. В URC нет
retain-флага, поэтому init требует явный server-only/non-retained broker ACL
contract; это не является target-доказательством. Portable session уже
маршрутизирует fragmented line/prompt/binary input и сериализует MQTT TX, но
target USART1 DMA/ISR/cache wiring, реальная
форма URC выбранной версии modem firmware, broker-policy verification и
assembled-station recovery остаются release blockers.
