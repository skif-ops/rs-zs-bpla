# BG95-M3 MQTT/TLS transport contract Rev.A

Status: `HOST CONTRACT PASS / MODEM AND END-TO-END EVIDENCE OPEN / NOT FOR RELEASE`

This contract extends the portable BG95 state machine from network registration to
an outbound MQTT/TLS session. It does not claim that a particular operator, SIM,
firmware revision, certificate bundle or pilot broker has passed on hardware.

## Controlled sequence

1. activate PDP context 1 with `AT+QIACT=1`;
2. select TLS 1.2 with `QSSLCFG sslversion=4`;
3. require server authentication with `QSSLCFG seclevel=2`;
4. bind a provisioned CA file to SSL context 1;
5. bind MQTT client 0 to SSL context 1;
6. open only port 443 or 8883, then wait for successful `+QMTOPEN`;
7. connect with the controlled client ID, then wait for successful `+QMTCONN`.

The API requires the caller to assert a public-APN profile. It rejects an explicit
private APN, unsupported plaintext port, oversized fields and CR/LF or quote
injection. Any AT error, negative open/connect result, MQTT status-loss URC or
120-second transport-stage timeout moves the state machine to `ERROR` and clears
the online flags.

## Double control

- QG-1: `tools/validate_bg95_transport_contract_rev_a.py` independently checks the
  policy, interface, command sequence, negative cases and CI binding.
- QG-2: `firmware/tests/test_bg95_transport.c` executes the positive state sequence,
  public/private APN policy, TLS-only ports, injection rejection, timeout and modem
  negative-result paths under the host build.

## Open evidence

- exact public APN values for each provisioned pilot SIM;
- certificate upload/provisioning and BG95 firmware-version compatibility;
- DNS, TLS hostname and certificate-failure tests against the pilot endpoint;
- QoS 1 publish/subscribe, downstream signature validation and store-and-forward;
- power-loss, network-loss, CGNAT, dual-SIM switching and 24-hour test logs;
- packet capture and broker/modem logs without secrets.

Until these items pass, FW-005 remains draft with partial host evidence only.
