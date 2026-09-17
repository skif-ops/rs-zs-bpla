#!/usr/bin/env python3
"""Audit PCB-PWR input-protection manufacturer source control.

This closes only PWR-IPQ-001. Vendor binaries are intentionally not committed;
the controlled record binds canonical URLs, retrieval metadata and exact hashes.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.json"
)
EVIDENCE_MD = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.md"
)
CONTRACT = ROOT / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_QUALIFICATION_REV_A.json"
MATRIX = ROOT / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError(f"{label}: {actual!r} != {expected!r}")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "artifacts/pcb_pwr_input_protection_primary_source_evidence_rev_a.json"
        ),
    )
    args = parser.parse_args()

    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    matrix = {row["Test_ID"]: row for row in read_csv(MATRIX)}
    evidence_md = EVIDENCE_MD.read_text(encoding="utf-8")
    evidence_sha256 = sha256(EVIDENCE)

    require(evidence["schema_version"] == 1, "source-evidence schema drift")
    require(evidence["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(evidence["assembly"] == "PCB-PWR", "assembly drift")
    require(evidence["retrieved_utc_date"] == "2026-09-17", "retrieval date drift")
    require(
        evidence["status"]
        == "PASS_SOURCE_CONTROL_EXACT_ORDERABLES_HASH_BOUND_NOT_FOR_MANUFACTURE",
        "source-control status drift",
    )
    policy = evidence["archive_policy"]
    require(policy["vendor_binaries_committed"] is False, "vendor-binary policy drift")
    require(policy["visual_pdf_review_complete"] is True, "PDF visual review not complete")
    require(policy["payloads_hash_bound"] == 6, "hash-bound payload count drift")

    sources = evidence["sources"]
    expected_payloads = {
        "littelfuse_451_453_datasheet": {
            "publisher": "Littelfuse",
            "canonical_url": "https://www.littelfuse.com/assetdocs/fuse-451-and-453-datasheet?assetguid=533cd5cc-956c-4243-867f-6ab5a62f6ba1",
            "media_type": "application/pdf",
            "sha256": "399d3cc9da991aa3192638f807fb568f137407d10a4b0d35d106a82b5c2bace2",
            "file_size_bytes": 491885,
            "pages": 4,
        },
        "littelfuse_smbj_datasheet": {
            "publisher": "Littelfuse",
            "canonical_url": "https://www.littelfuse.com/assetdocs/tvs-diodes-smbj-series-datasheet?assetguid=ba555e99-a12d-4f72-a0b6-86b06c67171e",
            "media_type": "application/pdf",
            "sha256": "d7df155be4b1f612085401e8c946f065e284d65a0e7de22b9225a7b73946e51b",
            "file_size_bytes": 947504,
            "pages": 6,
        },
        "molex_430450213_product_page": {
            "publisher": "Molex",
            "canonical_url": "https://www.molex.com/en-us/products/part-detail/430450213",
            "media_type": "text/html",
            "sha256": "d4afc5cdd0705422c61ff5b5698e3479f6e9e0c1022782af2fe41c8d51902d1c",
            "file_size_bytes": 387340,
        },
        "molex_430450213_sales_drawing": {
            "publisher": "Molex",
            "canonical_url": "https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43045/430450213_sd.pdf",
            "media_type": "application/pdf",
            "sha256": "85db6fbcbbd05643bfebded1b14e02911930151d0234b130d3711ee5fde78ec7",
            "file_size_bytes": 284379,
            "pages": 2,
        },
        "molex_430300038_product_page": {
            "publisher": "Molex",
            "canonical_url": "https://www.molex.com/en-us/products/part-detail/430300038",
            "media_type": "text/html",
            "sha256": "594fa3506fc506446c6a8256839d039a2eeea6b60378a3ff14c693d916db1717",
            "file_size_bytes": 384338,
        },
        "molex_430300038_sales_drawing": {
            "publisher": "Molex",
            "canonical_url": "https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/430/43030/430300038_sd.pdf",
            "media_type": "application/pdf",
            "sha256": "87fd5d112565f429a63f4350e1ba37a889fba8310696d541124d460df5bb017d",
            "file_size_bytes": 632077,
            "pages": 1,
        },
    }
    require(set(sources) == set(expected_payloads), "source payload set drift")
    for name, expected in expected_payloads.items():
        actual = sources[name]
        for key, value in expected.items():
            require(actual.get(key) == value, f"{name} {key} drift")
        require(len(actual["sha256"]) == 64, f"{name} invalid SHA-256")

    fuse = sources["littelfuse_451_453_datasheet"]
    fuse_orderable = fuse["claims"]["exact_orderable"]
    fuse_rating = fuse["claims"]["electrical_rating"]
    require(fuse["revision"] == "GD" and fuse["revision_date"] == "2025-12-01",
            "451/453 revision drift")
    require(fuse_orderable["pdf_page"] == 4, "fuse orderable page drift")
    require(fuse_orderable["orderable_part_number"] == "0451008.MRL",
            "fuse exact orderable drift")
    require(
        (fuse_orderable["series"], fuse_orderable["amp_code"],
         fuse_orderable["quantity_code"], fuse_orderable["packaging_code"],
         fuse_orderable["compliance_suffix"])
        == ("0451", "008.", "M", "R", "L"),
        "fuse part-number field binding drift",
    )
    close(fuse_rating["rating_a"], contract["fuse"]["target_rating_a"], "fuse rating")
    close(
        fuse_rating["interrupting_rating_a_at_32vdc"],
        contract["fuse"]["interrupting_rating_a_at_32vdc"],
        "fuse interrupt rating",
    )
    close(
        fuse_rating["nominal_cold_resistance_ohm"],
        contract["fuse"]["nominal_cold_resistance_ohm"],
        "fuse cold resistance",
    )
    close(
        fuse_rating["nominal_melting_i2t_a2s"],
        contract["fuse"]["nominal_melting_i2t_a2s"],
        "fuse melting I2t",
    )
    fuse_temperature = fuse["claims"]["temperature_and_continuous_use"]
    require(fuse_temperature["pdf_pages"] == [3, 4],
            "fuse temperature/derating evidence pages drift")
    close(
        fuse_temperature["continuous_current_derating_percent"],
        (1.0 - contract["fuse"]["standard_continuous_derating_fraction"]) * 100.0,
        "fuse continuous derating",
    )

    tvs = sources["littelfuse_smbj_datasheet"]
    tvs_orderable = tvs["claims"]["exact_orderable"]
    tvs_rating = tvs["claims"]["electrical_rating"]
    require(tvs["revision"] == "JC v4" and tvs["revision_date"] == "2025-07-04",
            "SMBJ revision drift")
    require(tvs_orderable["orderable_part_number"] == contract["tvs"]["target_evt_mpn"],
            "TVS exact orderable drift")
    require(tvs_orderable["package"] == "DO-214AA", "TVS package drift")
    for source_key, contract_key in (
        ("reverse_standoff_v", "reverse_standoff_v"),
        ("breakdown_min_v", "breakdown_min_v"),
        ("breakdown_max_v", "breakdown_max_v"),
        ("maximum_clamp_v", "maximum_clamp_v"),
        ("maximum_clamp_test_current_a", "maximum_clamp_test_current_a"),
        ("peak_pulse_power_w_10_1000us", "peak_pulse_power_w_10_1000us"),
    ):
        close(tvs_rating[source_key], contract["tvs"][contract_key], f"TVS {source_key}")

    header = sources["molex_430450213_product_page"]["claims"]
    header_drawing = sources["molex_430450213_sales_drawing"]
    require(header["numeric_part_number"] == "430450213", "header numeric identity drift")
    require(header["formatted_orderable_part_number"] == "43045-0213",
            "header formatted identity drift")
    require(header_drawing["document_number"] == "SD-43045-005" and
            header_drawing["revision"] == "G1", "header drawing identity drift")
    require(header_drawing["claims"]["orderable_part_number"] == "43045-0213",
            "header drawing orderable drift")
    require(header_drawing["claims"]["circuits"] == header["circuits"] == 2,
            "header circuit count drift")
    close(
        header["maximum_current_per_contact_a"],
        contract["input_connector"]["maximum_current_per_contact_a"],
        "header maximum current per contact",
    )
    require(header["operating_temperature_c"] == [-40, 125],
            "header operating-temperature range drift")

    terminal = sources["molex_430300038_product_page"]["claims"]
    terminal_drawing = sources["molex_430300038_sales_drawing"]
    require(terminal["numeric_part_number"] == "430300038", "terminal numeric identity drift")
    require(terminal["formatted_orderable_part_number"] == "43030-0038",
            "terminal formatted identity drift")
    require(terminal_drawing["document_number"] == "SD-43030-XXXX" and
            terminal_drawing["revision"] == "N10" and
            terminal_drawing["release_date"] == "2026-04-24",
            "terminal drawing identity drift")
    require(terminal_drawing["claims"]["orderable_part_number"] == "43030-0038",
            "terminal drawing orderable drift")
    require(terminal_drawing["claims"]["plating_code"] == "A" and
            terminal_drawing["claims"]["form"] == "CHAIN",
            "terminal drawing option drift")
    require(terminal["wire_awg"] == contract["input_connector"]["wire_awg"],
            "terminal AWG drift")
    close(
        terminal["wire_cross_section_mm2"],
        contract["input_connector"]["wire_cross_section_mm2"],
        "terminal wire cross-section",
    )
    close(
        terminal["maximum_current_per_contact_a"],
        contract["input_connector"]["maximum_current_per_contact_a"],
        "terminal maximum current per contact",
    )

    binding = evidence["qualification_binding"]
    require(binding == {
        "fuse_orderable": contract["fuse"]["target_evt_mpn"],
        "tvs_orderable": contract["tvs"]["target_evt_mpn"],
        "input_header_orderable": contract["input_connector"]["board_header_mpn"],
        "input_terminal_orderable": contract["input_connector"]["terminal_mpn"],
        "no_family_member_substitution": True,
    }, "qualification binding drift")

    source_control = contract["source_control"]
    require(source_control["complete"] is True, "contract source control is not complete")
    require(source_control["record"] == EVIDENCE_MD.relative_to(ROOT).as_posix(),
            "contract source-control Markdown path drift")
    require(source_control["machine_record"] == EVIDENCE.relative_to(ROOT).as_posix(),
            "contract source-control JSON path drift")
    require(source_control["independent_audit"] ==
            "tools/audit_pcb_pwr_input_protection_sources_rev_a.py",
            "contract source-control audit path drift")
    require(source_control["evidence_sha256"] == evidence_sha256,
            "contract source-control evidence SHA-256 drift")

    row = matrix["PWR-IPQ-001"]
    require(row["Status"] == "PASS", "PWR-IPQ-001 is not PASS")
    require(
        row["Result"]
        == "Official Littelfuse/Molex payloads hash-bound; exact 0451008.MRL SMBJ18A 43045-0213 and 43030-0038 identities and controlled ratings match",
        "PWR-IPQ-001 result drift",
    )
    require(row["Operator"] == "Codex primary-source archive audit",
            "PWR-IPQ-001 operator drift")
    require(row["Date"] == "2026-09-17", "PWR-IPQ-001 date drift")
    require(row["Artifact_SHA256"] == evidence_sha256,
            "PWR-IPQ-001 artifact SHA-256 drift")

    boundary = evidence["release_boundary"]
    require(boundary == {
        "source_control_complete": True,
        "physical_qualification_complete": False,
        "accepted_matrix_rows": 3,
        "required_matrix_rows": 20,
        "routing_authorized": False,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }, "source-control release boundary drift")
    require(contract["manufacturing_release"] is False,
            "qualification contract released manufacture")

    for token in (
        "0451008.MRL",
        "SMBJ18A",
        "43045-0213",
        "43030-0038",
        evidence_sha256,
        "3/20",
        "NOT FOR MANUFACTURE",
    ):
        require(token in evidence_md, f"Markdown evidence missing {token}")

    result = {
        "configuration": evidence["configuration"],
        "audit": "PCB-PWR Rev.A input-protection primary-source control",
        "status": "PASS_SOURCE_CONTROL_ONLY_PHYSICAL_QUALIFICATION_PENDING",
        "retrieved_utc_date": evidence["retrieved_utc_date"],
        "evidence_sha256": evidence_sha256,
        "payloads_hash_bound": policy["payloads_hash_bound"],
        "exact_orderables": [
            binding["fuse_orderable"],
            binding["tvs_orderable"],
            binding["input_header_orderable"],
            binding["input_terminal_orderable"],
        ],
        "accepted_matrix_rows": boundary["accepted_matrix_rows"],
        "required_matrix_rows": boundary["required_matrix_rows"],
        "physical_qualification_complete": False,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("PCB-PWR input-protection primary-source audit PASS")
    print("Exact orderables: " + ", ".join(result["exact_orderables"]))
    print(f"Evidence SHA-256: {evidence_sha256}")
    print("PWR-IPQ-001 PASS; physical qualification and release remain BLOCKED")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
