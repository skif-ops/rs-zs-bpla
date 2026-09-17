#!/usr/bin/env python3
"""QG-1 traceability check for protected full SIM identity heartbeat Rev.A."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    types = read("firmware/include/zs_types.h")
    protocol_header = read("firmware/include/zs_protocol.h")
    protocol_source = read("firmware/src/zs_protocol.c")
    bg95_header = read("firmware/include/zs_bg95.h")
    bg95_source = read("firmware/src/zs_bg95.c")
    bg95_test = read("firmware/tests/test_bg95_transport.c")
    c_test = read("firmware/tests/test_heartbeat_telemetry.c")
    server_schema = read("server/station/schemas.py")
    server_codec = read("server/station/cbor_codec.py")
    mqtt_bridge = read("server/station/mqtt_bridge.py")
    router = read("server/station/router.py")
    store = read("server/station/store.py")
    server_test = read("server/tests_core/test_cellular_telemetry.py")
    mqtt_test = read("server/tests/test_mqtt_bridge.py")
    http_test = read("server/tests/test_station_api.py")
    e2e = read("server/tools/test_firmware_packet.py")
    cmake = read("firmware/CMakeLists.txt")
    ci = read(".github/workflows/ci.yml")
    icd = read("protocols/MQTT_TLS_ICD_v0_1.md")
    policy = read("config/cellular/dual_sim_apn_profiles.yaml")
    decisions = read("docs/DECISION_LOG.csv")

    for token in ("zs_cellular_telemetry_t", "zs_heartbeat_t", "imsi[ZS_IMSI_CAPACITY]",
                  "iccid[ZS_ICCID_CAPACITY]", "settings_valid"):
        require(token in types, f"firmware telemetry type missing {token}")
    require("zs_protocol_encode_heartbeat" in protocol_header and
            "zs_protocol_encode_heartbeat" in protocol_source,
            "firmware heartbeat encoder is incomplete")
    for token in ("valid_digits(cell->imsi", "valid_digits(cell->iccid",
                  "cell->apn_source < 1u", "kvt(&c, 0u, cell->imsi)",
                  "kvt(&c, 1u, cell->iccid)"):
        require(token in protocol_source, f"heartbeat encoder guard missing {token}")
    require("zs_bg95_export_cellular_telemetry" in bg95_header and
            "zs_bg95_export_cellular_telemetry" in bg95_source,
            "BG95 telemetry export is not exposed")
    for token in ("zs_bg95_export_cellular_telemetry", "zs_protocol_encode_heartbeat",
                  "contains_bytes(encoded, encoded_size, full_imsi)",
                  "contains_bytes(encoded, encoded_size, full_iccid)"):
        require(token in bg95_test, f"BG95-to-heartbeat QG-2 link missing {token}")

    for token in ("class CellularTelemetry", "^[0-9]{14,16}$",
                  "^[0-9]{18,22}$", "cellular: CellularTelemetry | None"):
        require(token in server_schema, f"server identity schema missing {token}")
    for token in ("_MSG_HEARTBEAT = 3", "decode_heartbeat_obj",
                  "decode_heartbeat_cbor", "imsi=_text_field(cellular, 0",
                  "iccid=_text_field(cellular, 1",
                  "cellular.get(11) is not True",
                  "_integer_field(cellular, 10"):
        require(token in server_codec, f"server heartbeat decoder missing {token}")
    require("cellular identity telemetry requires mutual TLS" in mqtt_bridge,
            "MQTT mTLS identity interlock missing")
    require("invalid protected heartbeat" in mqtt_bridge,
            "MQTT validation errors may expose protected payload details")
    require("cellular identity is accepted only through mutual-TLS MQTT status" in router,
            "plain HTTP cellular identity interlock missing")
    for token in ("os.chmod(path, 0o600)", "imsi_redacted", "iccid_redacted",
                  "existing.cellular is not None and hb.cellular is None"):
        require(token in store, f"server identity persistence control missing {token}")

    for token in ("250011234567890", "89701012345678901234",
                  "settings_valid = false"):
        require(token in c_test, f"firmware QG-2 case missing {token}")
    for token in ("test_compact_heartbeat_decodes_full_cellular_identity",
                  "test_store_keeps_full_identity_internally_and_redacts_general_listing",
                  "test_legacy_heartbeat_does_not_erase_stored_cellular_identity",
                  "test_compact_cellular_fields_fail_closed_on_wrong_wire_types"):
        require(token in server_test, f"server QG-2 case missing {token}")
    require("test_full_cellular_identity_requires_mutual_tls" in mqtt_test,
            "MQTT mTLS QG-2 case missing")
    require("test_http_heartbeat_rejects_full_cellular_identity" in http_test,
            "HTTP identity rejection QG-2 case missing")
    require("decode_heartbeat_cbor" in e2e and "heartbeat.cellular.imsi" in e2e and
            "heartbeat.cellular.iccid" in e2e,
            "firmware-to-server heartbeat evidence missing")
    require("zs_heartbeat_telemetry_tests" in cmake and "zs_emit_heartbeat" in cmake,
            "heartbeat targets are not bound to CMake")
    require("zs_emit_detection zs_emit_heartbeat" in ci and
            "validate_cellular_heartbeat_contract_rev_a.py" in ci,
            "heartbeat controls are not bound to CI")

    require("mutual_tls_status_telemetry_only" in policy and
            "DEFERRED_UNTIL_STATIONS_ASSEMBLED" in policy,
            "protected identity/deferred EVT policy drift")
    require("full IMSI" in icd and "full ICCID" in icd and
            "DEFERRED_UNTIL_STATIONS_ASSEMBLED" in icd,
            "heartbeat ICD traceability drift")
    require("DEC-028" in decisions and "IMPLEMENTED_HOST_HARDWARE_DEFERRED" in decisions,
            "customer identity/timing decision missing")

    print("Protected cellular heartbeat QG-1 PASS")
    print("full IMSI/ICCID mTLS path traced; operator and 24-hour EVT deferred until assembly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
