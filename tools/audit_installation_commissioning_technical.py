#!/usr/bin/env python3
"""QG-2 independent technical audit of portable installation commissioning."""
import hashlib
import os
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


def msvc_environment_script() -> Path | None:
    roots = (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    )
    candidates = []
    for root in roots:
        candidates.extend(root.glob("Microsoft Visual Studio/*/*/Common7/Tools/VsDevCmd.bat"))
    return sorted(candidates, reverse=True)[0] if candidates else None


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
        binary = Path(tmp) / ("installation_commissioning_qg2.exe" if os.name == "nt" else "installation_commissioning_qg2")
        sources = [
            str(ROOT / "firmware/src/zs_sha256.c"),
            str(ROOT / "firmware/src/zs_position_trust.c"),
            str(ROOT / "firmware/src/zs_installation_store.c"),
            str(ROOT / "firmware/src/zs_installation_commissioning.c"),
            str(ROOT / "firmware/tests/test_installation_commissioning.c"),
        ]
        compiler = os.environ.get("CC")
        if os.name == "nt" and not compiler:
            vsdevcmd = msvc_environment_script()
            require(vsdevcmd is not None, "Visual Studio C compiler environment not found")
            command = [
                "cl", "/nologo", "/std:c11", "/W4", "/WX",
                f"/I{ROOT / 'firmware/include'}", *sources, f"/Fe:{binary}",
            ]
            command_line = subprocess.list2cmdline(command)
            compile_script = Path(tmp) / "compile_msvc.cmd"
            compile_script.write_text(
                "@echo off\r\n"
                f'call "{vsdevcmd}" -arch=x64 >nul\r\n'
                "if errorlevel 1 exit /b %errorlevel%\r\n"
                f"{command_line}\r\n",
                encoding="utf-8",
            )
            subprocess.run(
                ["cmd.exe", "/d", "/c", str(compile_script)],
                check=True,
                cwd=tmp,
            )
        else:
            command = [
                compiler or "cc", "-std=gnu11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                f"-I{ROOT / 'firmware/include'}", *sources,
            ]
            if os.name != "nt":
                command.append("-lm")
            command.extend(("-o", str(binary)))
            subprocess.run(command, check=True, cwd=tmp)
        completed = subprocess.run([str(binary)], check=True, cwd=ROOT,
                                   text=True, capture_output=True)
        require("zs_installation_commissioning_tests: OK" in completed.stdout,
                "portable commissioning executable did not report PASS")

    print("Installation commissioning QG-2 independent technical audit: PASS")
    print("canonical SHA-256 vector, fail-closed order and strict C regression verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
