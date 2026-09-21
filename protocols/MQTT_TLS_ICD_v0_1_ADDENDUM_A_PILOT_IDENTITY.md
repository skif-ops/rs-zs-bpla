# MQTT/TLS ICD v0.1 - Addendum A: identity and tenants for the 41-unit pilot

Status: `DRAFT / SERVER PKI IMPLEMENTED (server/pki) / TARGET mTLS PENDING`

Applies on top of `MQTT_TLS_ICD_v0_1.md`; the base document is unchanged until its next revision folds this addendum in.

## A.1 Pilot composition

| Lot | Serials | station_id | tenant |
|---|---|---|---|
| EVT-LOT-1 (register `EVT-PRE-20`) | DIO-EVT-001 .. DIO-EVT-020 | 1 .. 20 | `pilot1` |
| EVT-LOT-2 (register `EVT-PRE-20-LOT-2`) | DIO-EVT-021 .. DIO-EVT-040 | 21 .. 40 | `pilot2` |
| BENCH | DIO-EVT-B01 | 901 | `bench` |

`station_id` is the decimal number of the serial; the bench unit is fixed at 901 so it can never collide with a field unit. Topics keep the base ICD form `zs/v1/{tenant}/{station_id}/...`; the two lots and the bench unit therefore never share topics or ACL entries.

## A.2 Certificate identity

- Station client certificate: `CN = <serial>` (e.g. `DIO-EVT-021`), `OU = <lot>`, `O = Dioneya`, ECDSA P-256, issued by `Dioneya Issuing CA 1` (signed by the offline `Dioneya Root CA`).
- mosquitto: `require_certificate true`, `use_identity_as_username true`, `allow_anonymous false`, `crlfile` present. The MQTT username is therefore the serial; the previous `station01`-style names are retired.
- Server-side bridge: client certificate `CN = bridge`; one bridge process per tenant (`--tenant pilot1|pilot2|bench`), see `server/deploy/compose.ubuntu.yml`.
- The ACL is generated from the station registry (`python -m pki.cli mosquitto-acl`) and contains only stations whose certificate is active; `server/deploy/mosquitto/station_acl.conf` is the expected final state for all 41 units and must be regenerated after every issue or revoke.
- Server certificate SAN must list every host name / IP literal stations connect to; its SHA-256 fingerprint is pinned in the station configuration (`server_fingerprint`, see `STATION_CONFIG_CBOR_v0_1.md`).

## A.3 Station-side binding

The station loads `ca-chain.pem` (UFS name = `ca_reference`), its certificate and key into the BG95 in service mode (`zs_bg95_provision`), binds `QSSLCFG clientcert/clientkey`, and derives `mqtt_host`, `mqtt_port`, `ca_reference`, `tenant` and the client id `dioneya-{station_id}-{boot_id}` from the persistent station configuration record.

## A.4 Open items

- `zs_bg95.c` TLS steps still configure `cacert` only; the client certificate binding is performed by `zs_bg95_provision` until the base driver is extended.
- Multi-tenant bridge in one process is not implemented; deployment runs one bridge per tenant.
- Hardware mTLS handshake against mosquitto with the issued certificates: pending target validation.
