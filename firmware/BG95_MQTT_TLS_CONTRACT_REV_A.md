# BG95-M3 MQTT/TLS transport contract Rev.A

Status: `HOST CONTRACT + PORTABLE BG95 BOUNDED RAW-UART SESSION, BINARY COMMAND/ACK, EVENT OUTBOX, FIXED-LENGTH EVENT UPLINK AND LENGTH-DELIMITED RECEIPT PASS / TARGET STORAGE, CRYPTO, USART-DMA, MODEM AND END-TO-END EVIDENCE OPEN / NOT FOR RELEASE`

This contract extends the portable BG95 state machine from automatic SIM/network
discovery to an outbound MQTT/TLS session. It does not claim that a particular
operator, SIM, firmware revision, certificate bundle or pilot broker has passed
on hardware.

## Automatic network selection

1. wait for `CPIN READY` and the final command `OK` before issuing another AT
   command;
2. query `QCCID` and `CIMI`, retain the full ICCID and IMSI in volatile runtime
   state for profile selection and protected telemetry;
3. match the IMSI against the longest approved five- or six-digit prefix in the
   in-memory public-APN catalog;
4. query `COPS?` for diagnostic operator/RAT metadata and `CGNAPN` for the
   network-provided APN;
5. use the network APN only when the matched public profile explicitly permits
   it, otherwise use that profile's controlled public fallback APN;
6. reject an unknown IMSI prefix, missing APN, non-public profile, invalid APN or
   active-context APN mismatch.

`COPS?` is an optional diagnostic query. `QCCID`, `CIMI`, profile authorization,
PDP activation and active-context verification are mandatory and fail closed.

## Protected identity telemetry

After active-context verification the BG95 state can be exported into compact
heartbeat schema 1. The LTE-only heartbeat carries the full IMSI and ICCID,
home PLMN, registered operator, APN source, active APN, local address, gateway,
DNS and access technology. It is published only to the station `status` topic
over mutually authenticated TLS. It is never part of the LoRa/P0 detection
summary.

The server stores the full identifiers in the restricted station record. The
general station-list API removes the full values and returns masked forms. The
plain HTTP heartbeat route rejects a payload containing cellular identity, and
the MQTT bridge rejects such a heartbeat in explicit insecure-bench mode.
Firmware and server error logs must not include raw modem response lines or
validation payloads containing IMSI/ICCID.

## Controlled sequence

1. activate PDP context 1 with `AT+QIACT=1`;
2. query `AT+CGCONTRDP=1` and require the selected APN, local address, gateway
   and primary DNS before opening any transport;
3. select TLS 1.2 with `QSSLCFG sslversion=4`;
4. require server authentication with `QSSLCFG seclevel=2`;
5. bind a provisioned CA file to SSL context 1;
6. bind MQTT client 0 to SSL context 1;
7. before opening MQTT, configure direct receive with mandatory payload length
   using `AT+QMTCFG="recv/mode",0,0,1`;
8. open only port 443 or 8883, then wait for successful `+QMTOPEN`;
9. connect with the controlled client ID, then wait for successful `+QMTCONN`.

The API requires the caller to assert a public-APN profile. It rejects an explicit
private APN, unsupported plaintext port, oversized fields and CR/LF or quote
injection. Essential AT errors, negative open/connect results, MQTT status-loss
URCs or 120-second command/transport timeouts move the state machine to `ERROR`
and clear online/network-valid flags.

## Double control

- QG-1: `tools/validate_bg95_transport_contract_rev_a.py` independently checks the
  discovery policy, protected identity handling, interface, command sequence, negative
  cases and CI binding.
- QG-2: `firmware/tests/test_bg95_transport.c` executes the positive state sequence,
  network APN and catalog-fallback paths, unknown-SIM/APN-mismatch rejection,
  full-identity export, public/private policy, TLS-only ports, timeout and modem
  negative-result paths under the host build.
- End-to-end QG-2: `server/tools/test_firmware_packet.py` decodes the actual
  firmware heartbeat and verifies both full identifiers survive the CBOR boundary;
  server tests verify validation, restricted persistence, API masking and mTLS
  enforcement.
- Command QG-1/QG-2: `tools/validate_mqtt_command_transport.py`, the independent
  runtime audit, the deterministic server-generated Ed25519 vector and
  `firmware/tests/test_command_transport.c` check canonical parsing, station/time
  binding, fail-closed signature callback handling, durable-dedup requirement and
  ACK encoding under the host build. `firmware/tests/test_command_journal.c`
  separately fault-injects the atomic accepted/completed journal and prevents ACK
  generation before a completed result is durable. Its portable NOR adapter
  gives every logical record a whole erase block, verifies range/alignment,
  preserves neighbouring records across reclaim, and recovers after a torn
  commit. The shared layout/binding below also keeps it disjoint from archive
  and event outbox; production slot count, OCTOSPI binding and endurance remain
  target work.
  The bounded trust adapter
  validates key IDs and enabled rotation entries before delegating to a mandatory
  Ed25519 backend; no production public key is embedded in portable source. The
  application channel joins verification, journal, idempotent executor and ACK in
  that fail-closed order and is tested for retry, rejection and completed replay.
  The binary MQTT boundary then binds an exact canonical tenant/station `down`
  topic to that channel and returns the exact `ack` topic plus payload length only
  after durable completion. It rejects wrong or non-canonical topics, retained
  delivery and non-QoS-1 delivery before command parsing, and its host test carries
  embedded NUL bytes without treating CBOR as a string. The BG95 command binding
  subscribes to that exact `down` topic after the pre-connect length mode is
  confirmed, parses complete binary `+QMTRECV` frames by declared byte count and
  starts fixed-length `QMTPUB` of the durable ACK. It sends ACK bytes only after
  `>`, treats `+QMTPUB` success only as broker delivery and reconstructs the ACK
  from the journal on server retry without repeating execution. Partial UART,
  timeout and mismatched result paths fail closed. The portable MQTT session is
  the sole caller of command, receipt and event bindings: it reconstructs raw
  fragmented line/prompt/length-delimited input in a 2304-byte bound, assigns a
  single transmit owner, performs ordered subscriptions, retains one command
  while transmit is occupied and exposes further arrivals as server-retry
  required. Disconnect clears the RAM queue and forces resubscription; durable
  completion still prevents re-execution.
  As with event receipts, `QMTRECV` does not expose retain, so initialization
  requires an external server-only/non-retained per-station ACL assertion.
- Store-and-forward QG-1/QG-2: `tools/validate_event_outbox_contract.py` and
  `firmware/tests/test_event_outbox.c` verify atomic event commit, metadata CRC,
  payload SHA-256, priority/FIFO selection, idempotent duplicate handling,
  bounded persistent retry count, full-queue behavior and torn-write recovery.
  `tools/validate_event_receipt_contract.py`, its independent runtime audit and
  `firmware/tests/test_event_receipt.c` additionally verify the canonical
  server-to-firmware application receipt, exact payload-SHA binding, duplicate
  replay and receipt-before-broker-ACK ordering. The portable uplink adapter
  persists each retry before returning the exact `up` topic/payload view and
  applies a queued receipt by durable lookup after restart. A W25Q-class adapter
  dedicates a complete erase block to each logical outbox slot and verifies
  partition bounds. Before exposing any storage interface, the shared binding
  requires the frozen W25Q512JV JEDEC ID `EF 40 20`, a valid SFDP/BFPT 64 MiB
  density, exact 4-byte geometry and verified Status Register-2 QE; it restores
  a cleared QE via `35h`/`31h` and read-back. A portable planner assigns the aligned NOR prefix to the
  audio archive, the next erase-isolated partition to a caller-supplied command
  journal slot count, and the tail to a caller-supplied outbox slot count;
  QG-1/QG-2 verify exact three-consumer non-overlap, including the 64 MiB / 4 KiB
  / 16 command / 256 outbox slot reference geometry. The shared binding creates
  all three adapters from this layout and caps archive-visible storage at the
  derived command-journal base. Production slot counts, target memory-map/OCTOSPI
  binding, sample identity/QE behavior and endurance remain open.
  The BG95 event-uplink binding follows the fixed-length data mode from Quectel
  `BG95&BG77&BG600L Series MQTT Application Note` v1.2 section 3.2.8: it writes
  `AT+QMTPUB` with exact topic/QoS/retain/message length, waits for `>`, then
  writes the exact binary CBOR bytes without a Ctrl+Z terminator. Partial UART
  writes, unexpected/mismatched `+QMTPUB`, timeout and offline transition fail
  closed while the outbox item remains pending. `+QMTPUB` success is recorded
  only as broker ACK and never as the server application receipt. Target UART
  routing and modem-firmware/hardware evidence remain open.
  The base BG95 state machine sends
  `AT+QMTCFG="recv/mode",<client>,0,1` before `QMTOPEN`; after connection the
  receipt binding refuses to proceed unless that step completed, then subscribes with
  `AT+QMTSUB=<client>,<msgID>,"<exact-receipt-topic>",1`. Its fixed-memory
  parser consumes one complete length-delimited `+QMTRECV` frame, uses the
  declared payload byte count rather than C-string termination and therefore
  preserves embedded NUL, quote, CR/LF and `0x1a`. A zero receive message ID is
  rejected as non-QoS-1; the setup requires an exact successful QoS-1 grant.
  Malformed framing, setup timeout and partial UART writes fail closed.
  Quectel's `+QMTRECV` URC does not expose the MQTT retain flag. Consequently,
  initialization requires an explicit external assertion that the provisioned
  station credential and per-station broker ACL admit only the server on this
  receipt route and reject retained receipt publication. This assertion is not
  modem evidence: target USART/DMA framing, broker-policy verification and the
  selected BG95 firmware revision remain open until tested on assembled units.

## Open evidence

- exact PLMN permissions and public fallback APN values for each provisioned pilot SIM;
- `QCCID`, `CIMI`, `COPS?`, `CGNAPN` and `CGCONTRDP` response compatibility on the
  selected BG95 firmware revision and every pilot operator, after stations are assembled;
- certificate upload/provisioning and BG95 firmware-version compatibility;
- DNS, TLS hostname and certificate-failure tests against the pilot endpoint;
- reviewed Ed25519 backend and public-key provisioning, nonvolatile storage
  selection/non-overlap/endurance, target USART/DMA/ISR integration and cache ownership for
  the host-tested command
  down/ACK and event receipt bindings,
  and outbox
  slot-count/OCTOSPI/endurance binding; the fixed-length
  event publish/prompt path, length-delimited receipt path, portable fixed-memory
  parser and single-owner MQTT session, topic/QoS/retain boundary, ACK codec and server-side canonical envelope,
  QoS 1 retry, command ACK path and event receipt path have host tests;
- power-loss, network-loss, CGNAT, dual-SIM switching and 24-hour test logs after
  stations are assembled;
- packet capture and broker/modem logs without secrets.

Until these items pass, FW-005 remains draft with partial host evidence only.
