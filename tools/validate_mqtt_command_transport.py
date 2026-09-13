#!/usr/bin/env python3
"""QG-1 traceability check for signed MQTT command transport."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    codec = read("server/station/command_codec.py")
    bridge = read("server/station/mqtt_bridge.py")
    store = read("server/station/store.py")
    router = read("server/station/router.py")
    acl = read("server/deploy/mosquitto/station_acl.conf")
    compose = read("server/deploy/compose.ubuntu.yml")
    windows_tls = read("server/deploy/compose.windows.tls.yml")
    ubuntu_start = read("server/deploy/scripts/start_ubuntu.sh")
    dockerignore = read("server/.dockerignore")
    gitignore = read(".gitignore")
    production_broker = read("server/deploy/mosquitto/mosquitto.production.conf.example")
    requirements = read("server/requirements.txt")
    lock = read("server/requirements.lock.txt")
    icd = read("protocols/MQTT_TLS_ICD_v0_1.md")
    firmware_contract = read("firmware/BG95_MQTT_TLS_CONTRACT_REV_A.md")
    firmware_header = read("firmware/include/zs_command.h")
    firmware_codec = read("firmware/src/zs_command.c")
    firmware_test = read("firmware/tests/test_command_transport.c")
    vector_generator = read("tools/generate_mqtt_command_vector.py")
    vector_header = read("firmware/generated/zs_command_vector.h")
    tests = read("server/tests/test_mqtt_commands.py") + read(
        "server/tests/test_command_codec.py"
    )
    ci = read(".github/workflows/ci.yml")

    for token in (
        "Ed25519PrivateKey",
        "canonical=True",
        "MAX_COMMAND_BYTES = 2048",
        "MAX_ACK_BYTES = 128",
        "MAX_COMMAND_TTL_US = 15 * 60 * 1_000_000",
        "COMMAND_MESSAGE_TYPE = 4",
        "ACK_MESSAGE_TYPE = 5",
    ):
        require(token in codec, f"command codec contract missing: {token}")
    require("if signer is None" in bridge, "missing fail-closed signing-key guard")
    require("qos=1" in bridge and "retain=False" in bridge,
            "downstream is not fixed to QoS 1 / retain false")
    require("+/ack" in bridge and "decode_command_ack" in bridge,
            "bridge does not subscribe and decode ACK")
    require("manual_ack_set(True)" in bridge and "client.ack(message.mid, message.qos)" in bridge,
            "inbound QoS acknowledgement is not controlled by durable processing")
    require("retry_after_us" in bridge and "due_commands" in bridge,
            "application-ACK retry loop is absent")
    require("station_mismatch" in bridge and "topic_station_id" in bridge,
            "topic/payload/store station binding is absent")
    require("TENANT_PATTERN" in bridge and "str(station_id) != parts[3]" in bridge,
            "tenant wildcard or canonical uint32 topic guard is absent")

    for token in (
        "expires_us",
        "last_publish_us",
        "publish_count",
        "ack_result",
        "completed_us",
    ):
        require(token in store, f"durable command state missing: {token}")
    require("ack_command(station_id" in router,
            "bench HTTP ACK is not bound to station_id")
    require("cryptography>=46.0.0,<47.0.0" in requirements,
            "reviewed Ed25519 dependency constraint missing")
    require("cryptography==" in lock,
            "Ed25519 dependency missing from hashed runtime lock")

    require("ZS_COMMAND_SIGNING_KEY: /run/tls/command-signing.key" in compose,
            "production compose does not require command signing material")
    require("ZS_COMMAND_SIGNING_KEY: /run/tls/command-signing.key" in windows_tls,
            "Windows TLS compose does not require command signing material")
    require("stat -c '%a' tls/command-signing.key" in ubuntu_start and '"600"' in ubuntu_start,
            "Ubuntu launcher does not enforce owner-only signing-key mode")
    require("deploy/tls/" in dockerignore and "**/*.key" in dockerignore,
            "Docker build context can include private deployment keys")
    require("server/deploy/tls/" in gitignore,
            "generated command key material is not excluded from Git")
    require("require_certificate true" in production_broker and
            "use_identity_as_username true" in production_broker and
            "acl_file /mosquitto/config/station_acl.conf" in production_broker,
            "production broker example is not fail-closed mTLS/ACL")

    sections = {}
    current = None
    for raw_line in acl.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("user "):
            current = line.removeprefix("user ")
            require(current not in sections, f"duplicate ACL user: {current}")
            sections[current] = set()
        else:
            require(current is not None, "ACL rule appears before a user")
            sections[current].add(line)
    require(sections.get("bridge") == {
        "topic read zs/v1/evt/+/up",
        "topic read zs/v1/evt/+/status",
        "topic write zs/v1/evt/+/down",
        "topic read zs/v1/evt/+/ack",
    }, "bridge ACL has missing or excessive rights")
    for station_id in range(1, 21):
        user = f"station{station_id:02d}"
        require(sections.get(user) == {
            f"topic write zs/v1/evt/{station_id}/up",
            f"topic write zs/v1/evt/{station_id}/status",
            f"topic read zs/v1/evt/{station_id}/down",
            f"topic write zs/v1/evt/{station_id}/ack",
        }, f"station {station_id} ACL has missing or excessive rights")
    require(set(sections) == {"bridge"} | {f"station{i:02d}" for i in range(1, 21)},
            "unexpected MQTT ACL identity")

    for token in (
        "ZS_COMMAND_MAX_BYTES 2048u",
        "ZS_COMMAND_MAX_TTL_US UINT64_C(900000000)",
        "zs_command_signature_verify_fn",
        "zs_command_dedup_lookup_fn",
        "zs_command_decode_verify",
        "zs_command_encode_ack",
    ):
        require(token in firmware_header, f"firmware command API missing: {token}")
    for token in (
        "workspace[0] = 0xa9u",
        "memset(workspace, 0, signed_size)",
        "ZS_COMMAND_STATUS_TIME_UNTRUSTED",
        "ZS_COMMAND_STATUS_STATION_MISMATCH",
        "ZS_COMMAND_STATUS_SIGNATURE_REJECTED",
        "ZS_COMMAND_STATUS_DEDUP_STORAGE_ERROR",
    ):
        require(token in firmware_codec, f"firmware fail-closed path missing: {token}")
    for token in (
        "test_server_generated_ed25519_vector",
        "ZS_COMMAND_STATUS_DUPLICATE",
        "ZS_COMMAND_STATUS_INVALID_CBOR",
        "ZS_COMMAND_STATUS_INVALID_TTL",
        "zs_command_encode_ack",
    ):
        require(token in firmware_test, f"firmware command QG-2 case missing: {token}")
    require("TEST_PRIVATE_SEED" in vector_generator and
            "private_key.public_key().verify" in vector_generator and
            "--check" in vector_generator,
            "server/firmware deterministic Ed25519 vector generator is incomplete")
    require("Generated by tools/generate_mqtt_command_vector.py" in vector_header and
            "zs_command_vector_ack" in vector_header,
            "generated server/firmware command vector is absent")

    require("FIRMWARE_CODEC_IMPLEMENTED; TARGET_CRYPTO_AND_MODEM_BINDING_PENDING" in icd,
            "ICD does not report the bounded implementation status")
    require("target MQTT subscription binding, production Ed25519 backend" in firmware_contract,
            "firmware target gap is not explicit")
    for token in ("tamper", "retry", "ownership", "duplicate"):
        require(token in tests, f"negative/robustness test missing: {token}")
    require("validate_mqtt_command_transport.py" in ci,
            "QG-1 is not bound to CI")
    require("audit_mqtt_command_transport_technical.py" in ci,
            "QG-2 is not bound to CI")
    require("generate_mqtt_command_vector.py --check" in ci,
            "server/firmware vector freshness is not bound to CI")
    require("zs_command_transport_tests" in read("firmware/CMakeLists.txt"),
            "firmware command codec test is not bound to CTest")

    print("MQTT signed command transport QG-1: PASS")
    print("scope: server transport + portable firmware codec; target crypto/modem and hardware remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
