#!/usr/bin/env python3
"""QG-1 completeness and traceability check for the BG95 MQTT/TLS host contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    header = read("firmware/include/zs_bg95.h")
    source = read("firmware/src/zs_bg95.c")
    test = read("firmware/tests/test_bg95_transport.c")
    cmake = read("firmware/CMakeLists.txt")
    ci = read(".github/workflows/ci.yml")
    policy = read("config/cellular/dual_sim_apn_profiles.yaml")
    template = read("config/cellular/public_apn.example.yaml")
    icd = read("protocols/MQTT_TLS_ICD_v0_1.md")
    contract = read("firmware/BG95_MQTT_TLS_CONTRACT_REV_A.md")
    decisions = read("docs/DECISION_LOG.csv")

    for token in ("ZS_BG95_SIM_ICCID_QUERY", "ZS_BG95_SIM_IMSI_QUERY",
                  "ZS_BG95_OPERATOR_QUERY", "ZS_BG95_APN_DISCOVERING",
                  "ZS_BG95_PDP_ACTIVATING", "ZS_BG95_PDP_SETTINGS_QUERY",
                  "ZS_BG95_TLS_CONFIGURING",
                  "ZS_BG95_MQTT_OPENING", "ZS_BG95_MQTT_CONNECTING",
                  "ZS_BG95_ONLINE", "zs_bg95_apn_profile_t",
                  "zs_bg95_network_settings_t", "zs_bg95_configure_auto_network",
                  "zs_bg95_configure_mqtt_tls", "zs_bg95_start_mqtt",
                  "zs_bg95_get_network_settings", "zs_bg95_online"):
        require(token in header, f"BG95 interface missing {token}")

    for command in ('AT+QCCID', 'AT+CIMI', 'AT+COPS?', 'AT+CGNAPN',
                    'AT+QIACT=1', 'AT+CGCONTRDP=1', 'QSSLCFG=\\"sslversion\\"',
                    'QSSLCFG=\\"seclevel\\"', 'QSSLCFG=\\"cacert\\"',
                    'QMTCFG=\\"ssl\\"', 'AT+QMTOPEN=', 'AT+QMTCONN='):
        require(command in source, f"BG95 command sequence missing {command}")
    for guard in ("contains_private", "port != 443u && port != 8883u",
                  'strpbrk(src, "\\r\\n\\\"")', 'strstr(line, "+QMTSTAT:")',
                  "BG95_COMMAND_TIMEOUT_MS", "BG95_NO_PROFILE",
                  "strcmp(apn, m->apn) != 0", "network_settings.valid = false"):
        require(guard in source, f"BG95 fail-closed guard missing {guard}")

    for evidence in ("test_mqtt_tls_happy_path", "test_automatic_network_settings",
                     "test_catalog_fallback_and_unknown_sim", "bytes_contain",
                     "private.apn", "wrong.apn", "1883u", "pilot.example\\\"",
                     "+QMTOPEN: 0,3", "124000u"):
        require(evidence in test, f"BG95 QG-2 scenario missing {evidence}")
    require("zs_bg95_transport_tests" in cmake and "bg95_transport" in cmake,
            "BG95 host test is not bound to CMake/CTest")
    require("validate_bg95_transport_contract_rev_a.py" in ci,
            "BG95 QG-1 is not bound to CI")

    require("pilot_apn_policy: public_only" in policy and
            "allowed_in_pilot: false" in policy and
            "unknown_imsi_prefix: FAIL_CLOSED" in policy and
            "full_imsi_or_iccid_retention: FORBIDDEN" in policy,
            "automatic public-only APN policy drift")
    require("apn_mode: PUBLIC" in template and "mqtt_port: 443" in template and
            "alternate_mqtt_port: 8883" in template and
            "allow_network_provided_apn:" in template, "public APN template drift")
    require("TLS 1.2 minimum" in icd and "24 часа MQTT" in icd,
            "MQTT/TLS ICD gate drift")
    require("MODEM AND END-TO-END EVIDENCE OPEN" in contract and
            "FW-005 remains draft" in contract, "contract overclaims readiness")
    require("DEC-027" in decisions and "IMPLEMENTED_HOST_HARDWARE_PENDING" in decisions,
            "automatic network settings decision is not recorded")

    print("BG95 MQTT/TLS transport QG-1 PASS")
    print("automatic public APN + settings readback + TLS contract traced; hardware evidence OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
