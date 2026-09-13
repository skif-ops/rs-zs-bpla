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
durable. A portable application channel enforces verify → accept → idempotent
execute → complete → ACK and safely replays accepted/completed duplicates. Host
QG includes a real server-generated Ed25519 vector. A portable binary MQTT
adapter now enforces the exact tenant/station `down` topic, QoS 1 and non-retained
delivery before command parsing, then exposes the exact `ack` topic and CBOR
payload length after durable completion. The target still needs reviewed Ed25519
library binding, provisioned public keys, dedicated Flash pages/endurance evidence
and BG95 binary MQTT receive/publish AT framing integration.

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
allocation, wear/endurance, exact BG95 publish/receipt subscription/URC binding
and assembled-station recovery remain release blockers.
