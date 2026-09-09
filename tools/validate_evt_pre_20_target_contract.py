#!/usr/bin/env python3
"""QG-1: validate completeness and traceability of the EVT-PRE-20 target contract."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIN_SOURCES = (
    "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
    "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
)
BOARD_HEADER = "firmware/targets/evt_pre_20/include/evt_pre_20_board_pins.h"
CLOCK_HEADER = "firmware/targets/evt_pre_20/include/evt_pre_20_clock_policy.h"
MANIFEST = "firmware/targets/evt_pre_20/target_contract_manifest.json"

ROW_PATTERN = re.compile(
    r"^\s*\{(?P<net>\"(?:\\.|[^\"])*\"),\s*"
    r"(?P<function>\"(?:\\.|[^\"])*\"),\s*'(?P<port>[A-H])',\s*"
    r"(?P<pin>\d+)u,\s*(?P<package>\d+)u,\s*"
    r"(?P<signal>\"(?:\\.|[^\"])*\"),\s*(?P<af>-?\d+),\s*"
    r"(?P<direction>EVT_PRE_20_DIRECTION_[A-Z_]+)\},$",
    re.MULTILINE,
)

DIRECTIONS = {
    "IN": "EVT_PRE_20_DIRECTION_IN",
    "OUT": "EVT_PRE_20_DIRECTION_OUT",
    "BIDIR": "EVT_PRE_20_DIRECTION_BIDIR",
    "OUT_OD": "EVT_PRE_20_DIRECTION_OUT_OD",
    "BIDIR_OD": "EVT_PRE_20_DIRECTION_BIDIR_OD",
}
SPECIAL_AF = {"GPIO": -1, "RCC": -2, "SYS": -3}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative in PIN_SOURCES:
        with (ROOT / relative).open(encoding="utf-8-sig", newline="") as source:
            rows.extend(csv.DictReader(source))
    return rows


def expected_row(row: dict[str, str]) -> tuple[object, ...]:
    pin_match = re.fullmatch(r"P([A-H])(\d{1,2})", row["MCU_Pin"])
    require(pin_match is not None, f"invalid source GPIO: {row['MCU_Pin']}")
    af_match = re.fullmatch(r"AF(\d{1,2})", row["AF"])
    alternate_function = int(af_match.group(1)) if af_match else SPECIAL_AF[row["AF"]]
    return (
        row["Net"],
        row["Function"],
        pin_match.group(1),
        int(pin_match.group(2)),
        int(row["LQFP100_Pin"]),
        row["CubeMX_Signal"],
        alternate_function,
        DIRECTIONS[row["Direction_at_MCU"]],
    )


def generated_rows(text: str) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for match in ROW_PATTERN.finditer(text):
        rows.append(
            (
                json.loads(match.group("net")),
                json.loads(match.group("function")),
                match.group("port"),
                int(match.group("pin")),
                int(match.group("package")),
                json.loads(match.group("signal")),
                int(match.group("af")),
                match.group("direction"),
            )
        )
    return rows


def main() -> None:
    for relative in (BOARD_HEADER, CLOCK_HEADER, MANIFEST):
        require((ROOT / relative).is_file(), f"target contract file missing: {relative}")

    source = source_rows()
    board_text = (ROOT / BOARD_HEADER).read_text(encoding="utf-8")
    generated = generated_rows(board_text)
    require(len(source) == 65, f"source pin assignment count is {len(source)}, expected 65")
    require(len(generated) == len(source), "generated header does not contain every source assignment")
    require(generated == [expected_row(row) for row in source], "generated pin order or content differs from sources")

    manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    require(manifest["configuration"] == "EVT-PRE-20", "manifest configuration mismatch")
    require(manifest["target"]["mcu"] == "STM32U585VIT6Q", "manifest MCU mismatch")
    require(manifest["target"]["package"] == "LQFP100_14x14", "manifest package mismatch")
    require(manifest["pin_assignment_count"] == len(source), "manifest pin count mismatch")

    manifest_sources = {item["path"]: item["sha256"] for item in manifest["source_inputs"]}
    for relative in (
        *PIN_SOURCES,
        "hardware/CLOCKING_REV_A.md",
        "firmware/targets/evt_pre_20/target_status.yaml",
    ):
        require(relative in manifest_sources, f"manifest source missing: {relative}")
        require(manifest_sources[relative] == sha256(ROOT / relative), f"manifest source hash mismatch: {relative}")

    manifest_outputs = {item["path"]: item["sha256"] for item in manifest["generated_outputs"]}
    for relative in (BOARD_HEADER, CLOCK_HEADER):
        require(relative in manifest_outputs, f"manifest output missing: {relative}")
        require(manifest_outputs[relative] == sha256(ROOT / relative), f"manifest output hash mismatch: {relative}")

    gates = manifest["quality_gates"]
    require(gates["qg1_completeness"] == "tools/validate_evt_pre_20_target_contract.py", "QG-1 path mismatch")
    require(gates["qg2_technical"] == "tools/audit_evt_pre_20_target_technical.py", "QG-2 path mismatch")
    require(manifest["release_gate"]["status"] == "BLOCKED", "incomplete target must remain blocked")
    require(len(manifest["release_gate"]["blockers"]) >= 8, "target blocker list is incomplete")

    status = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    require("status: TARGET_PORT_REQUIRED" in status, "target status prematurely claims completion")
    require("do_not_release: true" in status, "target release block is missing")
    require("target_contract_manifest.json" in status, "target status does not reference contract manifest")
    require("status: GENERATED_SOURCE_CONTRACT_QG1_QG2_PASS" in status, "target contract gate status mismatch")
    require("board_pins: GENERATED_EXACT_REV_A_CONTRACT_QG1_QG2_PASS_CUBEMX_PENDING" in status, "board-pin gate status mismatch")

    print("EVT-PRE-20 target contract QG-1 completeness/traceability: PASS")
    print(f"- 65/65 source assignments represented; {len(manifest_sources)} inputs hash-bound")


if __name__ == "__main__":
    main()
