# BG95-M3 MQTT/TLS transport contract Rev.A

Status: `HOST CONTRACT + PORTABLE BINARY COMMAND PATH PASS / TARGET CRYPTO, BG95 AT BINDING AND END-TO-END EVIDENCE OPEN / NOT FOR RELEASE`

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
7. open only port 443 or 8883, then wait for successful `+QMTOPEN`;
8. connect with the controlled client ID, then wait for successful `+QMTCONN`.

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
  generation before a completed result is durable. The bounded trust adapter
  validates key IDs and enabled rotation entries before delegating to a mandatory
  Ed25519 backend; no production public key is embedded in portable source. The
  application channel joins verification, journal, idempotent executor and ACK in
  that fail-closed order and is tested for retry, rejection and completed replay.
  The binary MQTT boundary then binds an exact canonical tenant/station `down`
  topic to that channel and returns the exact `ack` topic plus payload length only
  after durable completion. It rejects wrong or non-canonical topics, retained
  delivery and non-QoS-1 delivery before command parsing, and its host test carries
  embedded NUL bytes without treating CBOR as a string.

## Open evidence

- exact PLMN permissions and public fallback APN values for each provisioned pilot SIM;
- `QCCID`, `CIMI`, `COPS?`, `CGNAPN` and `CGCONTRDP` response compatibility on the
  selected BG95 firmware revision and every pilot operator, after stations are assembled;
- certificate upload/provisioning and BG95 firmware-version compatibility;
- DNS, TLS hostname and certificate-failure tests against the pilot endpoint;
- reviewed Ed25519 backend and public-key provisioning, nonvolatile target-page
  binding/endurance, exact BG95 binary receive/publish framing, subscription and
  publish-prompt handling, and store-and-forward; the portable fixed-memory
  parser, topic/QoS/retain boundary, ACK codec and server-side canonical envelope,
  QoS 1 retry and station-bound ACK path have host tests;
- power-loss, network-loss, CGNAT, dual-SIM switching and 24-hour test logs after
  stations are assembled;
- packet capture and broker/modem logs without secrets.

Until these items pass, FW-005 remains draft with partial host evidence only.
