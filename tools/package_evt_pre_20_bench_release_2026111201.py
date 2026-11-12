#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


RELEASE_ID = "EVT_PRE_20_BENCH_RELEASE_2026111201"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stm-build", type=Path, required=True)
    parser.add_argument("--stm-signed", type=Path, required=True)
    parser.add_argument("--nrf-build", type=Path, required=True)
    parser.add_argument("--nrf-public-key", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    output = args.output.resolve()
    package = output / RELEASE_ID
    archive = output / f"{RELEASE_ID}.zip"
    if package.exists() or archive.exists():
        raise RuntimeError("output already exists")

    contract_path = repo / "firmware/targets/evt_pre_20/release/bench_release_contract_2026111201.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract["release_id"] != RELEASE_ID:
        raise RuntimeError("release contract mismatch")

    files = {
        args.stm_signed / "2026111201.bin": package / "01_Прошивка_STM32/2026111201.bin",
        args.stm_signed / "2026111201.manifest.cbor": package / "01_Прошивка_STM32/2026111201.manifest.cbor",
        args.stm_signed / "2026111201.sig": package / "01_Прошивка_STM32/2026111201.sig",
        args.stm_signed / "release_public_key.hex": package / "01_Прошивка_STM32/release_public_key.hex",
        args.stm_signed / "signing_summary.json": package / "01_Прошивка_STM32/signing_summary.json",
        args.stm_build / "dioneya_evt_pre_20.elf": package / "01_Прошивка_STM32/dioneya_evt_pre_20.elf",
        args.stm_build / "dioneya_evt_pre_20.hex": package / "01_Прошивка_STM32/dioneya_evt_pre_20.hex",
        args.stm_build / "dioneya_evt_pre_20.map": package / "01_Прошивка_STM32/dioneya_evt_pre_20.map",
        args.nrf_build / "merged.hex": package / "02_Прошивка_nRF52840/merged.hex",
        args.nrf_build / "dfu_application.zip": package / "02_Прошивка_nRF52840/dfu_application.zip",
        args.nrf_build / "dfu_application.zip_manifest.json": package / "02_Прошивка_nRF52840/dfu_application.zip_manifest.json",
        args.nrf_build / "partitions.yml": package / "02_Прошивка_nRF52840/partitions.yml",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.signed.bin": package / "02_Прошивка_nRF52840/zephyr.signed.bin",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.signed.hex": package / "02_Прошивка_nRF52840/zephyr.signed.hex",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.elf": package / "02_Прошивка_nRF52840/zephyr.elf",
        args.nrf_build / "nrf52840_ble/zephyr/zephyr.map": package / "02_Прошивка_nRF52840/zephyr.map",
        args.nrf_build / "mcuboot/zephyr/zephyr.bin": package / "02_Прошивка_nRF52840/mcuboot.bin",
        args.nrf_build / "mcuboot/zephyr/zephyr.hex": package / "02_Прошивка_nRF52840/mcuboot.hex",
        args.nrf_build / "mcuboot/zephyr/zephyr.map": package / "02_Прошивка_nRF52840/mcuboot.map",
        args.nrf_public_key: package / "02_Прошивка_nRF52840/nrf-boot.pub.pem",
        args.apk: package / "03_Приложение_монтажника/Dioneya_Commissioning_0.1.1_bench_20261112.apk",
        repo / "android/release_build_evidence.json": package / "03_Приложение_монтажника/release_build_evidence.json",
        repo / "android/track_status.yaml": package / "03_Приложение_монтажника/track_status.yaml",
        repo / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx": package / "04_Инструкции/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.docx",
        repo / "docs/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.md": package / "04_Инструкции/EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D.md",
        contract_path: package / "05_Релизные_документы/bench_release_contract_2026111201.json",
        repo / "firmware/targets/evt_pre_20/release/BENCH_RELEASE_PROFILE_REV_C.md": package / "05_Релизные_документы/BENCH_RELEASE_PROFILE_REV_C.md",
        repo / "firmware/targets/evt_pre_20/release/option_bytes_bench_rev_a.json": package / "05_Релизные_документы/option_bytes_bench_rev_a.json",
        repo / "firmware/targets/evt_pre_20/release/firmware_lock_interlock_rev_a.json": package / "05_Релизные_документы/firmware_lock_interlock_rev_a.json",
        repo / "firmware/targets/evt_pre_20/target_status.yaml": package / "05_Релизные_документы/target_status.yaml",
        repo / "firmware/RELEASE_NOTES.md": package / "05_Релизные_документы/RELEASE_NOTES.md",
        repo / "tools/sign_evt_pre_20_stm32_release.py": package / "06_Открытые_инструменты_проверки/sign_evt_pre_20_stm32_release.py",
        repo / "tools/sign_lora_rf_profile.py": package / "06_Открытые_инструменты_проверки/sign_lora_rf_profile.py",
        repo / "tools/validate_mqtt_command_transport.py": package / "06_Открытые_инструменты_проверки/validate_mqtt_command_transport.py",
    }

    for source, destination in files.items():
        copy(source.resolve(), destination)

    expected = {
        package / "01_Прошивка_STM32/2026111201.bin": contract["stm32"]["expected_image_sha256"],
        package / "02_Прошивка_nRF52840/zephyr.signed.bin": contract["nrf52840"]["expected_signed_image_sha256"],
        package / "02_Прошивка_nRF52840/merged.hex": contract["nrf52840"]["expected_merged_hex_sha256"],
        package / "03_Приложение_монтажника/Dioneya_Commissioning_0.1.1_bench_20261112.apk": contract["android"]["apk_sha256"],
    }
    for path, expected_hash in expected.items():
        actual = sha256(path)
        if actual != expected_hash:
            raise RuntimeError(f"hash mismatch: {path.name}: {actual}")

    pending = {
        "release_id": RELEASE_ID,
        "source_commit": args.source_commit,
        "status": "HARDWARE_VALIDATION_PENDING",
        "field_lora_profile_in_package": False,
        "firmware_lock_allowed": False,
        "required_before_lora_field_activation": contract["lora_ru868"]["activation_requires"],
        "reflash_after_approved_rf_results_required": False,
    }
    (package / "05_Релизные_документы/HARDWARE_PENDING.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    readme = f"""# EVT-PRE-20, стендовый выпуск 2026111201

Статус: готов к прошивке стендового изделия. Аппаратная проверка обязательна и не выполнена программно.

Исходный commit: `{args.source_commit}`.

Порядок применения:

1. Проверить SHA256SUMS.txt.
2. Выполнить прошивку STM32 и nRF52840 по инструкции Rev D.
3. Установить подписанный APK приложения монтажника.
4. Выполнить электрический EOL, самотесты, BLE, обновление и откат.
5. Подключить LoRa к согласованной нагрузке 50 Ом и провести ограниченный радиотест из приложения монтажника.
6. Проверить RF-тракт, мощность, полосу, побочные излучения, скважность, установленную антенну и протокол LoRa.
7. Подписать протокол. После индивидуального EOL PASS установить отдельно выпущенный подписанный полевой профиль через приложение монтажника.

Повторная прошивка для включения LoRa после утвержденных испытаний не требуется. Полевой профиль в архив не включен намеренно. Закрытых ключей, паролей и keystore в архиве нет. Блокировка прошивки запрещена до полного аппаратного PASS, полной регрессии и индивидуального EOL PASS.

English summary

This package is ready for flashing the bench unit. Hardware validation remains mandatory. The installer application provides LoRa status, a time-limited conducted RF test, signed field-profile installation and a local operation log. The field profile is intentionally excluded. After approved RF results and per-station EOL PASS, it is installed through the application without reflashing. Firmware locking remains forbidden.
"""
    (package / "README_RU_EN.md").write_text(readme, encoding="utf-8")

    private_name_tokens = ("private", "secret", "keystore", ".p12", ".jks", ".key", "password")
    for path in package.rglob("*"):
        if path.is_file() and any(token in path.name.lower() for token in private_name_tokens):
            raise RuntimeError(f"private material candidate in package: {path.name}")

    manifest_files = []
    for path in sorted(p for p in package.rglob("*") if p.is_file()):
        manifest_files.append({
            "path": path.relative_to(package).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    manifest = {
        "schema": 1,
        "release_id": RELEASE_ID,
        "source_commit": args.source_commit,
        "status": "READY_TO_FLASH_HARDWARE_VALIDATION_PENDING",
        "private_material_in_package": False,
        "lora_field_profile_in_package": False,
        "files": manifest_files,
    }
    (package / "release_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    checksum_paths = sorted(p for p in package.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    checksum_text = "".join(f"{sha256(path)}  {path.relative_to(package).as_posix()}\n" for path in checksum_paths)
    (package / "SHA256SUMS.txt").write_text(checksum_text, encoding="utf-8")

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for path in sorted(p for p in package.rglob("*") if p.is_file()):
            target.write(path, f"{RELEASE_ID}/{path.relative_to(package).as_posix()}")

    print(f"package: {package}")
    print(f"archive: {archive}")
    print(f"files: {len(list(package.rglob('*')))}")
    print(f"archive_sha256: {sha256(archive)}")


if __name__ == "__main__":
    main()
