#!/usr/bin/env python3
"""QG-2 independent technical audit of portable installation commissioning."""
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASH = "9ad92b04c26e85a7f20c9259469774199348d98cfb47a563160bbab2154cea51"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def independent_record_hash() -> str:
    payload = bytearray(b"ZS-INSTALLATION-V1")
    payload += bytes((1, 1, 1, 0, 1, 1))
    payload += struct.pack(
        ">IiiiHHHHBBQ",
        1,
        557_550_000,
        376_150_000,
        1_800,
        5,
        25,
        75,
        250,
        3,
        10,
        2_000_000_000_000_001,
    )
    require(len(payload) == 58, "independent canonical record length drift")
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    source = (ROOT / "firmware/src/zs_installation_commissioning.c").read_text(encoding="utf-8")
    test = (ROOT / "firmware/tests/test_installation_commissioning.c").read_text(encoding="utf-8")
    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    require(independent_record_hash() == EXPECTED_HASH, "canonical commissioning hash drift")
    require(f"canonical record hash: {EXPECTED_HASH}" in test, "C known-answer vector drift")
    require(source.index("context->origin != ZS_COMMISSIONING_ORIGIN_BLE_LOCAL") <
            source.index("zs_installation_store_commit"),
            "remote-origin rejection must precede persistent mutation")
    require(source.index("append_audit(audit, ZS_COMMISSIONING_AUDIT_INTENT") <
            source.index("zs_installation_store_commit"),
            "durable mutation is possible before audit intent")
    require("NRF_GATT_PENDING" in target and "MISSING_BLOCKER" not in
            next(line for line in target.splitlines()
                 if "installation_position_ble_commissioning:" in line),
            "portable result or nRF/GATT boundary is not explicit")

    with tempfile.TemporaryDirectory(prefix="zs-commissioning-qg2-") as tmp:
        binary = Path(tmp) / "installation_commissioning_qg2"
        command = [
            "cc", "-std=gnu11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
            f"-I{ROOT / 'firmware/include'}",
            str(ROOT / "firmware/src/zs_sha256.c"),
            str(ROOT / "firmware/src/zs_position_trust.c"),
            str(ROOT / "firmware/src/zs_installation_store.c"),
            str(ROOT / "firmware/src/zs_installation_commissioning.c"),
            str(ROOT / "firmware/tests/test_installation_commissioning.c"),
            "-lm", "-o", str(binary),
        ]
        subprocess.run(command, check=True, cwd=ROOT)
        completed = subprocess.run([str(binary)], check=True, cwd=ROOT,
                                   text=True, capture_output=True)
        require("zs_installation_commissioning_tests: OK" in completed.stdout,
                "portable commissioning executable did not report PASS")

    print("Installation commissioning QG-2 independent technical audit: PASS")
    print("canonical SHA-256 vector, fail-closed order and strict C regression verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
