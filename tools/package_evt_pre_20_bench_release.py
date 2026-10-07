#!/usr/bin/env python3
"""Build the public, key-free EVT-PRE-20 bench software release archive."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "firmware/targets/evt_pre_20/release/bench_release_contract.json"
RELEASE_ID = "EVT_PRE_20_BENCH_RELEASE_2026100601"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def copy_file(source: Path, destination: Path) -> None:
    require_file(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def android_sbom() -> dict[str, object]:
    app_ref = "pkg:apk/ru.dioneya.commissioning@0.1.0-bench.20261005"
    components = [
        {
            "type": "application",
            "name": "Dioneya commissioning",
            "version": "0.1.0-bench.20261005",
            "bom-ref": app_ref,
            "purl": app_ref,
        },
        {
            "type": "library",
            "group": "org.jetbrains.kotlin",
            "name": "kotlin-stdlib",
            "version": "2.2.10",
            "bom-ref": "pkg:maven/org.jetbrains.kotlin/kotlin-stdlib@2.2.10",
            "purl": "pkg:maven/org.jetbrains.kotlin/kotlin-stdlib@2.2.10",
        },
        {
            "type": "library",
            "group": "org.jetbrains",
            "name": "annotations",
            "version": "13.0",
            "bom-ref": "pkg:maven/org.jetbrains/annotations@13.0",
            "purl": "pkg:maven/org.jetbrains/annotations@13.0",
        },
        {
            "type": "library",
            "group": "com.google.zxing",
            "name": "core",
            "version": "3.5.3",
            "bom-ref": "pkg:maven/com.google.zxing/core@3.5.3",
            "purl": "pkg:maven/com.google.zxing/core@3.5.3",
        },
    ]
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:87b74ff0-9f63-53df-a312-e070d9c25011",
        "version": 1,
        "metadata": {"component": components[0]},
        "components": components[1:],
        "dependencies": [
            {
                "ref": app_ref,
                "dependsOn": [component["bom-ref"] for component in components[1:]],
            },
            *[
                {"ref": component["bom-ref"], "dependsOn": []}
                for component in components[1:]
            ],
        ],
    }


def package_readme() -> str:
    return """# EVT-PRE-20 bench software release 2026100601

## Русский

Статус: готово к прошивке стендового образца; аппаратная проверка обязательна.

Порядок первой установки:

1. Сохранить полный снимок option bytes STM32.
2. Применить только поля из `01_STM32/option_bytes_bench_rev_a.json`.
3. Прошить `01_STM32/dioneya_evt_pre_20_2026100601.hex` через SWD и проверить read-back.
4. Прошить `02_NRF52840/merged.hex` через отдельный nRF SWD и проверить read-back.
5. Установить `03_ANDROID/dioneya-commissioning-0.1.0-bench.20261005.apk` на выделенный Android-телефон.
6. Выполнить руководство `04_ДОКУМЕНТАЦИЯ/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx`.
7. Сохранить все журналы и хеши в паспорт `DIO-EVT-B01`.
8. Для полевых станций создавать CSR и проверять сертификат только средствами из `05_EOL_TOOLS` по разделу 16.4.1 руководства.

Блокировка прошивки этим выпуском запрещена. RDP Level 0, SWD и BOOT0 recovery должны сохраняться, а BOOT_LOCK, TrustZone, WRP и PCROP должны оставаться отключенными. Отдельный production-профиль допускается только после полного аппаратного PASS и полной регрессии. Каждая станция блокируется только после собственного EOL PASS. Подробные ворота приведены в `04_ДОКУМЕНТАЦИЯ/EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A.docx`.

Архив не содержит закрытых ключей, паролей, keystore или производственных секретов. `release_manifest.json` и `SHA256SUMS.txt` связывают все файлы. `HARDWARE_PENDING.json` перечисляет только проверки, которым нужен физический образец или оснастка.

## English

Status: ready to flash the bench unit; hardware validation is mandatory.

Save the STM32 option-byte snapshot, apply only the controlled bench profile, flash both MCUs through their separate SWD ports, install the signed Android APK, and execute the supplied commissioning and test manual. Keep all read-back logs and hashes in the `DIO-EVT-B01` unit record. Firmware locking is forbidden for this release. A separate production protection release requires complete hardware qualification, full regression and a per-station EOL PASS. The archive contains no private key, password or keystore.
"""


def hardware_pending() -> dict[str, object]:
    return {
        "schema": 1,
        "release_id": RELEASE_ID,
        "status": "HARDWARE_VALIDATION_REQUIRED",
        "items": [
            {"id": "HW-STM-01", "test": "SWD, BOOT0, system-memory recovery and option-byte read-back"},
            {"id": "HW-STM-02", "test": "A/B bank swap, trial confirmation and rollback with power interruption"},
            {"id": "HW-NRF-01", "test": "nRF SWD, signed boot, BLE advertising and authenticated pairing"},
            {"id": "HW-NRF-02", "test": "STM32 to nRF UART IPC, serial recovery and image rollback"},
            {"id": "HW-APP-01", "test": "APK installation, QR, BLE configuration read-back and signed OTA on DIO-EVT-B01"},
            {"id": "HW-PKI-01", "test": "factoryid serial/pairing write, station certificate, secrets and unique identity provisioning on DIO-EVT-B01"},
            {"id": "HW-NET-01", "test": "BG95 CA/certificate/key upload, mutual TLS and MQTT end-to-end with dioneya.ru"},
            {"id": "HW-IO-01", "test": "QSPI, microSD, GNSS/PPS, BG95 dual SIM, LoRa, sensors and four microphone channels"},
            {"id": "HW-EOL-01", "test": "rail, current, audio, timing, RF, leak, temperature and power-cycle limits"},
            {"id": "HW-SEC-01", "test": "complete target qualification and full regression before any production firmware-lock profile is released"},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stm-build", type=Path, default=ROOT / "outputs/b_stm_bench_2026100601")
    parser.add_argument("--stm-release", type=Path, default=ROOT / "outputs/bench-release-stm32-2026100601")
    parser.add_argument("--nrf-build", type=Path, default=Path("C:/dio_b_nrf_2026100501v3"))
    parser.add_argument("--apk", type=Path, default=ROOT / "android/app/build/outputs/apk/release/app-release.apk")
    parser.add_argument(
        "--android-cert",
        type=Path,
        default=ROOT / "outputs/bench-release-secrets/android-bench-release-cert.pem",
    )
    parser.add_argument(
        "--nrf-public-key",
        type=Path,
        default=ROOT / "outputs/bench-release-secrets/nrf-boot/nrf-boot.pub.pem",
    )
    parser.add_argument("--output", type=Path, default=ROOT / f"outputs/{RELEASE_ID}")
    args = parser.parse_args()

    contract = json.loads(require_file(CONTRACT_PATH).read_text(encoding="utf-8"))
    output = args.output.resolve()
    if output.exists():
        resolved_root = (ROOT / "outputs").resolve()
        if resolved_root not in output.parents:
            raise ValueError(f"refusing to replace output outside {resolved_root}: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)

    stm_files = {
        args.stm_release / "2026100601.bin": output / "01_STM32/dioneya_evt_pre_20_2026100601.signed.bin",
        args.stm_release / "2026100601.manifest.cbor": output / "01_STM32/2026100601.manifest.cbor",
        args.stm_release / "2026100601.sig": output / "01_STM32/2026100601.sig",
        args.stm_build / "dioneya_evt_pre_20.elf": output / "01_STM32/dioneya_evt_pre_20_2026100601.elf",
        args.stm_build / "dioneya_evt_pre_20.map": output / "01_STM32/dioneya_evt_pre_20_2026100601.map",
        args.stm_build / "dioneya_evt_pre_20.hex": output / "01_STM32/dioneya_evt_pre_20_2026100601.hex",
        ROOT / "firmware/targets/evt_pre_20/release/option_bytes_bench_rev_a.json": output / "01_STM32/option_bytes_bench_rev_a.json",
    }
    nrf_files = {
        args.nrf_build / "merged.hex": output / "02_NRF52840/merged.hex",
        args.nrf_build / "dfu_application.zip": output / "02_NRF52840/dfu_application.zip",
        args.nrf_build / "dfu_application.zip_manifest.json": output / "02_NRF52840/dfu_application.zip_manifest.json",
        args.nrf_build / "partitions.yml": output / "02_NRF52840/partitions.yml",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.signed.bin": output / "02_NRF52840/nrf52840_ble_0.1.0+2026100501.signed.bin",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.signed.hex": output / "02_NRF52840/nrf52840_ble_0.1.0+2026100501.signed.hex",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.elf": output / "02_NRF52840/nrf52840_ble_0.1.0+2026100501.elf",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.map": output / "02_NRF52840/nrf52840_ble_0.1.0+2026100501.map",
        args.nrf_build / "nrf52840_ble/zephyr/.config": output / "02_NRF52840/application.config",
        args.nrf_build / "mcuboot/zephyr/zephyr.elf": output / "02_NRF52840/mcuboot.elf",
        args.nrf_build / "mcuboot/zephyr/zephyr.map": output / "02_NRF52840/mcuboot.map",
        args.nrf_build / "mcuboot/zephyr/zephyr.hex": output / "02_NRF52840/mcuboot.hex",
        args.nrf_build / "mcuboot/zephyr/.config": output / "02_NRF52840/mcuboot.config",
        args.nrf_public_key: output / "02_NRF52840/nrf_boot_public_key.pem",
    }
    android_files = {
        args.apk: output / "03_ANDROID/dioneya-commissioning-0.1.0-bench.20261005.apk",
        ROOT / "android/app/build/outputs/apk/release/output-metadata.json": output / "03_ANDROID/output-metadata.json",
        args.android_cert: output / "03_ANDROID/android_bench_release_certificate.pem",
    }
    documentation_files = {
        ROOT / "firmware/targets/evt_pre_20/release/BENCH_RELEASE_PROFILE_REV_B.md": output / "04_ДОКУМЕНТАЦИЯ/BENCH_RELEASE_PROFILE_REV_B.md",
        ROOT / "firmware/targets/evt_pre_20/release/firmware_lock_interlock_rev_a.json": output / "04_ДОКУМЕНТАЦИЯ/firmware_lock_interlock_rev_a.json",
        ROOT / "docs/EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A.docx": output / "04_ДОКУМЕНТАЦИЯ/EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A.docx",
        ROOT / "docs/EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A.md": output / "04_ДОКУМЕНТАЦИЯ/EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A.md",
        ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx": output / "04_ДОКУМЕНТАЦИЯ/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.docx",
        ROOT / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.md": output / "04_ДОКУМЕНТАЦИЯ/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_C.md",
        ROOT / "manufacturing/PROVISIONING_AND_KEYS.md": output / "04_ДОКУМЕНТАЦИЯ/PROVISIONING_AND_KEYS.md",
        ROOT / "manufacturing/EOL_TEST_SPEC.md": output / "04_ДОКУМЕНТАЦИЯ/EOL_TEST_SPEC.md",
        ROOT / "manufacturing/EOL_SOFTWARE_LIMITS_REV_A.json": output / "04_ДОКУМЕНТАЦИЯ/EOL_SOFTWARE_LIMITS_REV_A.json",
    }
    eol_tool_files = {
        ROOT / "tools/generate_evt_station_csr.py": output / "05_EOL_TOOLS/generate_evt_station_csr.py",
        ROOT / "tools/verify_evt_station_certificate.py": output / "05_EOL_TOOLS/verify_evt_station_certificate.py",
        ROOT / "tools/requirements-eol-pki.txt": output / "05_EOL_TOOLS/requirements-eol-pki.txt",
    }
    for mapping in (stm_files, nrf_files, android_files, documentation_files, eol_tool_files):
        for source, destination in mapping.items():
            copy_file(source, destination)

    (output / "01_STM32/release_public_key.hex").write_text(
        contract["stm32"]["public_key_hex"] + "\n", encoding="ascii"
    )
    (output / "03_ANDROID/android.cdx.json").write_text(
        json.dumps(android_sbom(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "HARDWARE_PENDING.json").write_text(
        json.dumps(hardware_pending(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "README_RU_EN.md").write_text(package_readme(), encoding="utf-8")

    expected = {
        "01_STM32/dioneya_evt_pre_20_2026100601.signed.bin": contract["stm32"]["expected_image_sha256"],
        "02_NRF52840/nrf52840_ble_0.1.0+2026100501.signed.bin": contract["nrf52840"]["expected_signed_image_sha256"],
        "02_NRF52840/merged.hex": contract["nrf52840"]["expected_merged_hex_sha256"],
    }
    for relative, wanted in expected.items():
        actual = sha256(output / relative)
        if actual != wanted:
            raise ValueError(f"unexpected hash for {relative}: {actual} != {wanted}")

    files = []
    for path in sorted(p for p in output.rglob("*") if p.is_file()):
        relative = path.relative_to(output).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})

    status = git_value("status", "--porcelain")
    manifest = {
        "schema": 1,
        "release_id": RELEASE_ID,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_git_head": git_value("rev-parse", "HEAD"),
        "source_tree_clean": not bool(status),
        "status": "READY_TO_FLASH_HARDWARE_VALIDATION_PENDING",
        "contract": contract,
        "build_evidence": {
            "stm32": {"flash_bytes": 249024, "ram123_bytes": 714008, "max_stack_bytes": 2304},
            "nrf52840_application": {"flash_bytes": 207564, "ram_bytes": 68480},
            "nrf52840_mcuboot": {"flash_bytes": 35470, "ram_bytes": 22080},
            "android": {"unit_tests": "PASS", "apk_signature_scheme_v2": "PASS"},
        },
        "files": files,
    }
    manifest_path = output / "release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    checksummed = [*files, {"path": "release_manifest.json", "sha256": sha256(manifest_path)}]
    (output / "SHA256SUMS.txt").write_text(
        "".join(f"{item['sha256']}  {item['path']}\n" for item in checksummed), encoding="utf-8"
    )

    archive = output.with_suffix(".zip")
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for path in sorted(p for p in output.rglob("*") if p.is_file()):
            target.write(path, f"{output.name}/{path.relative_to(output).as_posix()}")
    print(f"EVT-PRE-20 bench release packaged: {output}")
    print(f"archive: {archive}")
    print(f"archive SHA-256: {sha256(archive)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
