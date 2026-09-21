#!/usr/bin/env python3
"""Audit the controlled EVT-PRE-20 external-response request bundle.

The default audit validates the source contract, preserves the accepted EVT
DIM-003 evidence and keeps every other external response pending. With --archive it independently compares every ZIP member
and byte against the controlled source set and validates the embedded SHA-256
manifest.  This is a request-package gate, never a manufacturing-release gate.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.json"

EXPECTED_GROUPS = {
    "PCB-MAIN-FAB": 22,
    "PCB-MAIN-ASSEMBLER": 14,
    "PCB-PWR-DIM003": 18,
    "PCB-PWR-FAB": 24,
    "PCB-MIC-DFM": 9,
    "HARNESS-SUPPLIER": 16,
}
PENDING_DISPOSITIONS = {
    "PENDING_EXTERNAL_RESPONSE",
    "PENDING_EXTERNAL_ACCEPTANCE",
}
ACCEPTED_DIM_003_DISPOSITION = "ACCEPTED_EVT_ENGINEERING"
EVIDENCE_FIELDS = {
    "Response_Value",
    "Response_Reference",
    "Responder",
    "Response_Date",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def controlled_paths(contract: dict) -> list[Path]:
    names = list(contract["common_files"])
    for group in contract["groups"]:
        names.extend(group["files"])
    unique = sorted(set(names), key=str.lower)
    excluded = tuple(contract["excluded_prefixes"])
    require(
        not any(name.startswith(excluded) for name in unique),
        "controlled source set contains an excluded prefix",
    )
    paths = [ROOT / name for name in unique]
    missing = [name for name, path in zip(unique, paths) if not path.is_file()]
    require(not missing, "missing controlled sources: " + ", ".join(missing))
    return paths


def audit_contract(contract: dict) -> dict:
    require(
        contract["schema"] == "dioneya-external-response-bundle-v1",
        "external-response schema drift",
    )
    require(contract["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(
        contract["status"] == "READY_TO_BUILD_EXTERNAL_RESPONSE_REQUEST_ARCHIVE",
        "request-bundle status drift",
    )
    require(contract["selected_station_quantity"] == 20, "selected lot drift")
    require(contract["primary_procurement_track"] == "FULL_PCBA", "primary track drift")
    require(
        contract["bare_pcb_track"]
        == "ALTERNATIVE_QUOTATION_ONLY_DO_NOT_COMBINE_WITH_FULL_PCBA",
        "bare-PCB alternative-track interlock drift",
    )
    require(
        contract["commercial_procurement_owner"] == "CUSTOMER"
        and contract["commercial_quote_or_availability_required_by_engineering"] is False
        and contract["job_specific_technical_manufacturing_responses_required"] is True,
        "customer commercial-procurement or technical-response boundary drift",
    )
    require(
        contract["hardware_design_release"] is False
        and contract["purchase_release"] is False
        and contract["manufacturing_release"] is False,
        "request bundle was incorrectly promoted to a release",
    )
    groups = {group["id"]: group for group in contract["groups"]}
    require(set(groups) == set(EXPECTED_GROUPS), "external-response group set drift")

    register_summary = {}
    for group_id, expected_rows in EXPECTED_GROUPS.items():
        group = groups[group_id]
        register = ROOT / group["response_register"]
        require(
            group["response_register"] in group["files"],
            f"{group_id}: response register is not included",
        )
        rows = read_csv(register)
        require(
            len(rows) == expected_rows,
            f"{group_id}: response rows={len(rows)} expected={expected_rows}",
        )
        accepted = group_id == "PCB-PWR-DIM003"
        for row in rows:
            gate_id = row.get("Gate_ID", "<missing>")
            populated = [field for field in EVIDENCE_FIELDS if row.get(field, "").strip()]
            if accepted:
                require(
                    row.get("Disposition") == ACCEPTED_DIM_003_DISPOSITION,
                    f"{group_id}/{gate_id}: EVT acceptance disposition differs",
                )
                require(
                    set(populated) == EVIDENCE_FIELDS,
                    f"{group_id}/{gate_id}: accepted row lacks attribution fields",
                )
                require(row.get("Blocking") == "NO",
                        f"{group_id}/{gate_id}: accepted EVT row remains blocking")
            else:
                require(
                    row.get("Disposition") in PENDING_DISPOSITIONS,
                    f"{group_id}/{gate_id}: non-pending disposition requires a returned-evidence release flow",
                )
                require(
                    not populated,
                    f"{group_id}/{gate_id}: pending row has populated evidence fields {populated}",
                )
                require(row.get("Blocking") == "YES", f"{group_id}/{gate_id}: blocker removed")
        register_summary[group_id] = {
            "rows": len(rows),
            "accepted": len(rows) if accepted else 0,
            "pending": 0 if accepted else len(rows),
        }

    rules = " ".join(contract["release_rules"])
    for token in ("not a purchase order", "unrouted", "pending", "Full-PCBA", "Review B", "18/18"):
        require(token in rules, f"release rule missing token: {token}")

    paths = controlled_paths(contract)
    return {
        "controlled_file_count": len(paths),
        "response_registers": register_summary,
        "controlled_paths": paths,
    }


def parse_manifest(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in payload.decode("ascii").splitlines():
        digest, separator, name = line.partition("  ")
        require(separator == "  ", f"invalid manifest line: {line!r}")
        require(len(digest) == 64, f"invalid SHA-256 in manifest: {digest!r}")
        require(name not in result, f"duplicate manifest path: {name}")
        result[name] = digest
    return result


def audit_archive(archive_path: Path, controlled: list[Path]) -> dict:
    require(archive_path.is_file(), f"archive missing: {archive_path}")
    expected_names = {
        str(path.relative_to(ROOT)).replace("\\", "/") for path in controlled
    }
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.namelist()
        require(len(members) == len(set(members)), "archive has duplicate members")
        require("BUNDLE_MANIFEST.sha256" in members, "archive manifest missing")
        for name in members:
            pure = PurePosixPath(name)
            require(not pure.is_absolute(), f"absolute archive member: {name}")
            require(".." not in pure.parts, f"archive traversal member: {name}")
        source_members = set(members) - {"BUNDLE_MANIFEST.sha256"}
        require(source_members == expected_names, "archive member set differs from contract")
        manifest = parse_manifest(archive.read("BUNDLE_MANIFEST.sha256"))
        require(set(manifest) == expected_names, "embedded manifest member set differs")
        for path in controlled:
            name = str(path.relative_to(ROOT)).replace("\\", "/")
            archive_payload = archive.read(name)
            source_payload = path.read_bytes()
            require(archive_payload == source_payload, f"archive/source byte drift: {name}")
            require(
                manifest[name] == sha256_bytes(archive_payload),
                f"embedded SHA-256 mismatch: {name}",
            )
    return {
        "path": str(archive_path),
        "sha256": sha256_file(archive_path),
        "members": len(expected_names) + 1,
        "source_members": len(expected_names),
    }


def audit_sums(sums_path: Path, archive_path: Path) -> dict:
    require(sums_path.is_file(), f"SHA256SUMS missing: {sums_path}")
    rows = {}
    for line in sums_path.read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        require(separator == "  ", f"invalid SHA256SUMS line: {line!r}")
        rows[name] = digest
    require(len(rows) == 3, "SHA256SUMS must bind exactly three current archives")
    require(archive_path.name in rows, "external-response archive absent from SHA256SUMS")
    require(
        rows[archive_path.name] == sha256_file(archive_path),
        "external-response archive SHA256SUMS mismatch",
    )
    return {"path": str(sums_path), "entries": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--sums", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require(not args.sums or args.archive, "--sums requires --archive")

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    control = audit_contract(contract)
    report = {
        "schema": "dioneya-external-response-bundle-audit-v1",
        "configuration": contract["configuration"],
        "status": "PASS_REQUEST_BUNDLE_CONTROL_DIM_003_ACCEPTED_OTHER_EXTERNAL_RESPONSES_PENDING_NOT_FOR_MANUFACTURE",
        "hardware_design_release": False,
        "purchase_release": False,
        "manufacturing_release": False,
        "selected_station_quantity": contract["selected_station_quantity"],
        "primary_procurement_track": contract["primary_procurement_track"],
        "commercial_procurement_owner": contract["commercial_procurement_owner"],
        "commercial_quote_or_availability_required_by_engineering": False,
        "job_specific_technical_manufacturing_responses_required": True,
        "controlled_file_count": control["controlled_file_count"],
        "response_registers": control["response_registers"],
        "archive": None,
        "sha256sums": None,
    }
    if args.archive:
        report["archive"] = audit_archive(args.archive, control["controlled_paths"])
    if args.sums:
        report["sha256sums"] = audit_sums(args.sums, args.archive)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        "EVT-PRE-20 external-response request bundle audit PASS: "
        f"{control['controlled_file_count']} files; "
        "DIM-003 accepted; other response registers remain pending; NOT FOR MANUFACTURE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
