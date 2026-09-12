# BG95-M3 MQTT/TLS transport contract Rev.A

Status: `HOST CONTRACT PASS / MODEM AND END-TO-END EVIDENCE OPEN / NOT FOR RELEASE`

This contract extends the portable BG95 state machine from automatic SIM/network
discovery to an outbound MQTT/TLS session. It does not claim that a particular
operator, SIM, firmware revision, certificate bundle or pilot broker has passed
on hardware.

## Automatic network selection

1. wait for `CPIN READY` and the final command `OK` before issuing another AT
   command;
2. query `QCCID`, retain only its last four digits, then query `CIMI` without
   retaining the full IMSI;
3. match the IMSI against the longest approved five- or six-digit prefix in the
   in-memory public-APN catalog;
4. query `COPS?` for diagnostic operator/RAT metadata and `CGNAPN` for the
   network-provided APN;
5. use the network APN only when the matched public profile explicitly permits
   it, otherwise use that profile's controlled public fallback APN;
6. reject an unknown IMSI prefix, missing APN, non-public profile, invalid APN or
   active-context APN mismatch.

`QCCID` and `COPS?` are optional diagnostic queries: their command errors do not
prevent the essential IMSI/profile/APN selection. `CIMI`, profile authorization,
PDP activation and active-context verification are mandatory and fail closed.

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
  discovery policy, identity minimization, interface, command sequence, negative
  cases and CI binding.
- QG-2: `firmware/tests/test_bg95_transport.c` executes the positive state sequence,
  network APN and catalog-fallback paths, unknown-SIM/APN-mismatch rejection,
  identity minimization, public/private policy, TLS-only ports, timeout and modem
  negative-result paths under the host build.

## Open evidence

- exact PLMN permissions and public fallback APN values for each provisioned pilot SIM;
- `QCCID`, `CIMI`, `COPS?`, `CGNAPN` and `CGCONTRDP` response compatibility on the
  selected BG95 firmware revision and every pilot operator;
- certificate upload/provisioning and BG95 firmware-version compatibility;
- DNS, TLS hostname and certificate-failure tests against the pilot endpoint;
- QoS 1 publish/subscribe, downstream signature validation and store-and-forward;
- power-loss, network-loss, CGNAT, dual-SIM switching and 24-hour test logs;
- packet capture and broker/modem logs without secrets.

Until these items pass, FW-005 remains draft with partial host evidence only.
