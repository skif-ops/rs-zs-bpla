#!/usr/bin/env python3
"""Audit the controlled PCB-PWR fuse/TVS qualification packet.

Default mode validates that the exact EVT candidates, applied value-only ECO,
repeat-evidence gate, test matrix and manufacturing interlocks are internally consistent. Strict mode
is the physical qualification gate and remains non-zero until all matrix rows
carry attributable PASS evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_QUALIFICATION_REV_A.json"
MATRIX = ROOT / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv"
SOURCE_EVIDENCE = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.json"
)
SOURCE_EVIDENCE_MD = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.md"
)
PROCUREMENT_IDENTITY = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.json"
)
PROCUREMENT_IDENTITY_MD = (
    ROOT
    / "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.md"
)
FREEZE = ROOT / "hardware/POWER_COMPONENT_FREEZE_REV_A.csv"
BASELINE = ROOT / "hardware/POWER_DESIGN_BASELINE_REV_A.json"
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
PROCUREMENT = ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"
STATUS = ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json"
NATIVE_SCH = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR_01_INPUT_PROTECTION.kicad_sch"
NATIVE_PCB = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
SCH_GENERATOR = ROOT / "tools/generate_pcb_pwr_schematic_rev_a.py"
PCB_GENERATOR = ROOT / "tools/generate_pcb_pwr_layout_candidate_rev_a.py"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
CAPTURE_NETS = ROOT / "hardware/PCB_PWR_CAPTURE_NETS_REV_A.csv"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def close(actual: float, expected: float, tolerance: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise RuntimeError(
            f"{label}: actual={actual:.12g} expected={expected:.12g} "
            f"tolerance={tolerance:.12g}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/pcb_pwr_input_protection_qualification_rev_a.json",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    source_evidence = json.loads(SOURCE_EVIDENCE.read_text(encoding="utf-8"))
    source_evidence_sha256 = hashlib.sha256(SOURCE_EVIDENCE.read_bytes()).hexdigest()
    procurement_identity_evidence = json.loads(
        PROCUREMENT_IDENTITY.read_text(encoding="utf-8")
    )
    procurement_identity_sha256 = hashlib.sha256(
        PROCUREMENT_IDENTITY.read_bytes()
    ).hexdigest()
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    capture_status = json.loads(STATUS.read_text(encoding="utf-8"))
    matrix = read_csv(MATRIX)
    freeze = {row["Component_ID"]: row for row in read_csv(FREEZE)}
    bom = {row["Item_ID"]: row for row in read_csv(BOM)}
    procurement = read_csv(PROCUREMENT)

    require(contract["schema_version"] == 1, "qualification schema version drift")
    require(contract["configuration"] == "EVT-PRE-20 Rev.A", "configuration drift")
    require(contract["assembly"] == "PCB-PWR", "assembly drift")
    require(contract["manufacturing_release"] is False, "qualification packet released manufacture")
    require(
        source_evidence["status"]
        == "PASS_SOURCE_CONTROL_EXACT_ORDERABLES_HASH_BOUND_NOT_FOR_MANUFACTURE",
        "input-protection source-control evidence drift",
    )
    source_control = contract.get("source_control", {})
    require(source_control.get("complete") is True,
            "input-protection source control is not complete")
    require(source_control.get("record") == SOURCE_EVIDENCE_MD.relative_to(ROOT).as_posix(),
            "source-control Markdown path drift")
    require(source_control.get("machine_record") == SOURCE_EVIDENCE.relative_to(ROOT).as_posix(),
            "source-control JSON path drift")
    require(source_control.get("independent_audit") ==
            "tools/audit_pcb_pwr_input_protection_sources_rev_a.py",
            "source-control independent audit path drift")
    require(source_control.get("evidence_sha256") == source_evidence_sha256,
            "source-control evidence SHA-256 drift")
    require(source_control.get("exact_orderables") ==
            ["0451008.MRL", "SMBJ18A", "43045-0213", "43030-0038"],
            "source-control exact orderable set drift")
    require(source_control.get("no_family_member_substitution") is True,
            "source-control family-substitution interlock removed")
    require(
        procurement_identity_evidence["status"]
        == "PASS_DOCUMENTARY_PROCUREMENT_IDENTITY_NO_RECEIVING_HOLD",
        "input-protection procurement-identity evidence drift",
    )
    procurement_identity = contract.get("procurement_identity", {})
    require(procurement_identity.get("prepurchase_documentary_identity_complete") is True,
            "pre-purchase identity subgate is not complete")
    require(procurement_identity.get("standalone_engineering_sample_purchase_required") is False,
            "qualification contract still requires a sample-only purchase")
    require(
        procurement_identity.get(
            "qualification_batch_may_be_ordered_without_identity_samples"
        ) is True,
        "qualification batch still depends on identity samples",
    )
    require(
        procurement_identity.get("mandatory_receiving_quarantine_required") is False
        and procurement_identity.get(
            "mandatory_receiving_photography_required"
        ) is False
        and procurement_identity.get("mandatory_body_sampling_required") is False
        and procurement_identity.get("certificate_of_conformance_required") is False,
        "receiving identity burden reintroduced",
    )
    require(procurement_identity.get("record") ==
            PROCUREMENT_IDENTITY_MD.relative_to(ROOT).as_posix(),
            "procurement-identity Markdown path drift")
    require(procurement_identity.get("machine_record") ==
            PROCUREMENT_IDENTITY.relative_to(ROOT).as_posix(),
            "procurement-identity JSON path drift")
    require(procurement_identity.get("independent_audit") ==
            "tools/audit_pcb_pwr_input_protection_procurement_identity_rev_a.py",
            "procurement-identity independent audit path drift")
    require(procurement_identity.get("evidence_sha256") == procurement_identity_sha256,
            "procurement-identity evidence SHA-256 drift")
    require(procurement_identity.get("matrix_row") == "PWR-IPQ-002" and
            procurement_identity.get("matrix_status") == "PASS",
            "procurement-identity matrix binding drift")
    require(procurement_identity.get("exact_orderables") ==
            ["0451008.MRL", "SMBJ18A", "43045-0213", "43030-0038"],
            "procurement-identity exact orderable set drift")
    require(baseline["status"] == "CAPTURE_BASELINE_NOT_FOR_MANUFACTURE",
            "power baseline lost NOT FOR MANUFACTURE interlock")
    baseline_input = baseline.get("input_protection_qualification", {})
    require(baseline_input.get("status") ==
            "TARGET_EVT_CANDIDATES_SELECTED_NATIVE_VALUE_ECO_APPLIED_REPEAT_EVIDENCE_COMPLETE_PHYSICAL_QUALIFICATION_PENDING" and
            baseline_input.get("fuse", {}).get("native_value_eco_applied") is True and
            baseline_input.get("fuse", {}).get(
                "repeat_erc_pdf_human_hierarchy_review_complete") is True,
            "power baseline does not expose the completed post-ECO repeat-evidence gate")
    require(capture_status["manufacturing_release"] is False,
            "PCB-PWR capture status released manufacture")

    fuse = contract["fuse"]
    continuous_a = float(contract["system_continuous_current_a"])
    derating = float(fuse["standard_continuous_derating_fraction"])
    target_rating_a = float(fuse["target_rating_a"])
    required_rating_a = continuous_a / derating
    capacity_a = target_rating_a * derating
    loss_w = continuous_a * continuous_a * float(fuse["nominal_cold_resistance_ohm"])
    close(required_rating_a, float(fuse["minimum_nominal_rating_at_25c_a"]), 1e-9,
          "minimum nominal fuse rating")
    close(capacity_a, float(fuse["capacity_after_standard_derating_a"]), 1e-9,
          "standard-derated fuse capacity")
    close(loss_w, float(fuse["nominal_loss_at_5a_w"]), 1e-12,
          "5 A nominal cold fuse loss")
    require(fuse["signed_native_mpn"] == "0451005.MRL", "signed native fuse identity drift")
    require(fuse["target_evt_mpn"] == "0451008.MRL", "target fuse identity drift")
    require(float(fuse["signed_native_rating_a"]) * derating < continuous_a,
            "captured 5 A fuse is no longer proven inadequate")
    require(target_rating_a > required_rating_a and capacity_a > continuous_a,
            "target fuse lacks standard-derating headroom")
    require(fuse["temperature_rerating_required"] is True,
            "temperature rerating requirement was removed")
    require(fuse["package_land_pattern_change"] is False,
            "qualification packet unexpectedly changes F1 land pattern")

    connector = contract["input_connector"]
    require(connector["board_header_mpn"] == "43045-0213", "input header MPN drift")
    require(connector["terminal_mpn"] == "43030-0038", "input terminal MPN drift")
    require(float(connector["maximum_current_per_contact_a"]) == 8.5,
            "Molex maximum current fact drift")
    require(float(connector["maximum_current_per_contact_a"]) > target_rating_a,
            "fuse nominal rating is not below connector maximum")
    require(connector["qualification_at_plus70c_required"] is True,
            "+70 C connector qualification was removed")

    tvs = contract["tvs"]
    require(tvs["target_evt_mpn"] == "SMBJ18A", "TVS identity drift")
    require(float(tvs["reverse_standoff_v"]) > float(baseline["input"]["working_max_v"]),
            "TVS standoff is not above provisional input maximum")
    require(float(tvs["maximum_clamp_v"]) < float(tvs["project_candidate_clamp_limit_at_protected_node_v"]),
            "project clamp limit does not exceed tabulated TVS clamp")
    require(float(tvs["project_candidate_clamp_limit_at_protected_node_v"]) <
            float(tvs["buck_absolute_max_input_v"]),
            "project clamp limit does not preserve buck absolute-maximum margin")
    require(tvs["sustained_overvoltage_protection"] is False,
            "TVS was incorrectly declared a sustained-overvoltage protector")

    telemetry = contract["telemetry_scope"]
    full_scale = 32767.0 * float(telemetry["current_lsb_a"])
    close(full_scale, float(telemetry["signed_full_scale_a"]), 1e-12,
          "INA226 signed positive full scale")
    require(float(telemetry["normal_operating_current_max_a"]) == continuous_a,
            "INA226 normal range and project continuous current diverged")
    require(telemetry["ina226_not_fault_energy_instrument"] is True,
            "INA226 was incorrectly promoted to fault-energy instrument")

    frozen = freeze["PWR-FUSE-01"]
    require(frozen["Manufacturer"] == "Littelfuse", "frozen fuse manufacturer drift")
    require(frozen["MPN"] == fuse["target_evt_mpn"], "freeze/contract fuse MPN mismatch")
    require("CANDIDATE_SELECTED_FOR_EVT_QUALIFICATION" in frozen["Status"],
            "freeze does not identify selected qualification candidate")
    require("NATIVE_VALUE_ECO_APPLIED_REPEAT_EVIDENCE_PASS_PHYSICAL_QUALIFICATION_PENDING"
            in frozen["Status"],
            "freeze lost post-ECO repeat-evidence/physical-qualification interlock")

    bom_fuse = bom["PWR-FUSE-01"]
    require(bom_fuse["MPN"] == fuse["target_evt_mpn"], "engineering BOM fuse MPN mismatch")
    require(bom_fuse["BOM_disposition"] == "CONTROLLED_PENDING_VERIFICATION",
            "engineering BOM lost the controlled F1 verification interlock")
    procurement_fuse = [
        row for row in procurement
        if "PWR-FUSE-01" in row.get("Item_IDs", "").split("|")
    ]
    require(len(procurement_fuse) == 1, "procurement rollup must have one F1 row")
    require(procurement_fuse[0]["MPN"] == fuse["target_evt_mpn"],
            "procurement rollup fuse MPN mismatch")
    require(procurement_fuse[0]["BOM_disposition"] == "CONTROLLED_PENDING_VERIFICATION",
            "procurement rollup lost the controlled F1 verification interlock")

    native_eco = contract["native_value_eco"]
    require(native_eco == {
        "applied": True,
        "applied_date": "2026-09-17",
        "change": "0451005.MRL_TO_0451008.MRL",
        "topology_change": False,
        "footprint_change": False,
        "placement_change": False,
        "value_only_change": True,
        "signed_source_value_superseded": True,
        "pre_eco_pin_net_semantic_sha256":
            "fb31a1880037c2d15873ef7a003b74967e0427ed767bc16de256a790b5320b5a",
        "post_eco_pin_net_semantic_sha256":
            "fb31a1880037c2d15873ef7a003b74967e0427ed767bc16de256a790b5320b5a",
        "post_eco_board_semantic_sha256":
            "5f854a5276e8dfd6dc82516f61db1a158888b5343b82058e6024e5970b51e6c1",
        "repeat_native_kicad_9_erc_required": True,
        "repeat_native_kicad_9_erc_complete": True,
        "repeat_pdf_evidence_required": True,
        "repeat_pdf_evidence_complete": True,
        "repeat_independent_human_hierarchy_review_required": True,
        "repeat_independent_human_hierarchy_review_complete": True,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }, "native value ECO control drift")
    for path in (NATIVE_SCH, NATIVE_PCB, SCH_GENERATOR, PCB_GENERATOR):
        text = path.read_text(encoding="utf-8")
        require("0451008.MRL" in text,
                f"target 8 A value is not applied in active source: {path}")
        require("0451005.MRL CANDIDATE" not in text,
                f"superseded 5 A value remains in active source: {path}")

    placements = {row["RefDes"]: row for row in read_csv(PLACEMENT)}
    f1_placement = placements.get("F1", {})
    require((f1_placement.get("X_mm"), f1_placement.get("Y_mm"),
             f1_placement.get("Rotation_deg"), f1_placement.get("Side")) ==
            ("13.00", "29.00", "0", "TOP"),
            "F1 placement authority changed during value-only ECO")
    capture_nets = {row["Net"]: row for row in read_csv(CAPTURE_NETS)}
    require(capture_nets.get("VBAT_RAW", {}).get("To") == "F1.1" and
            capture_nets.get("VBAT_FUSED", {}).get("From") == "F1.2",
            "F1 capture topology authority changed during value-only ECO")

    status_eco = capture_status.get("input_protection_candidate_eco", {})
    require(status_eco.get("state") ==
            "TARGET_8A_NATIVE_VALUE_ECO_RETAINED_ACTIVE_CINHF_ECO_REPEAT_EVIDENCE_HUMAN_ACCEPTED_PHYSICAL_QUALIFICATION_PENDING",
            "PCB-PWR capture status does not expose the post-ECO review gate")
    require(status_eco.get("target_fuse_mpn") == fuse["target_evt_mpn"],
            "PCB-PWR capture status target fuse mismatch")
    require(status_eco.get("signed_native_fuse_mpn") == fuse["signed_native_mpn"],
            "PCB-PWR capture status signed fuse mismatch")
    require(status_eco.get("native_value_eco_applied") is True and
            status_eco.get("value_only_change_verified") is True,
            "PCB-PWR capture status does not record the bounded value-only ECO")
    require(status_eco.get("pin_net_semantic_sha256_before") ==
            native_eco["pre_eco_pin_net_semantic_sha256"] and
            status_eco.get("pin_net_semantic_sha256_after") ==
            native_eco["post_eco_pin_net_semantic_sha256"],
            "PCB-PWR capture status ECO semantic proof drift")
    active_hierarchy_evidence = capture_status.get("human_readable_hierarchy", {}).get(
        "current_evidence", {})
    active_evidence_complete = active_hierarchy_evidence.get("status") == \
        "PASS_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED"
    require(status_eco.get("repeat_native_kicad_9_erc_complete") is active_evidence_complete and
            status_eco.get("repeat_pdf_evidence_complete") is active_evidence_complete and
            status_eco.get("repeat_independent_human_hierarchy_review_complete") is active_evidence_complete,
            "PCB-PWR capture status repeat-evidence boundary drift")
    require(status_eco.get("source_control_complete") is True and
            status_eco.get("source_control_record") == source_control["record"] and
            status_eco.get("source_control_machine_record") == source_control["machine_record"] and
            status_eco.get("source_control_audit") == source_control["independent_audit"] and
            status_eco.get("source_control_evidence_sha256") == source_evidence_sha256,
            "PCB-PWR capture status source-control binding drift")
    require(status_eco.get("prepurchase_identity_complete") is True and
            status_eco.get("standalone_engineering_sample_purchase_required") is False and
            status_eco.get("documentary_procurement_identity_complete") is True and
            status_eco.get("receiving_identity_hold_required") is False and
            status_eco.get("procurement_identity_record") ==
            procurement_identity["record"] and
            status_eco.get("procurement_identity_machine_record") ==
            procurement_identity["machine_record"] and
            status_eco.get("procurement_identity_audit") ==
            procurement_identity["independent_audit"] and
            status_eco.get("procurement_identity_evidence_sha256") ==
            procurement_identity_sha256,
            "PCB-PWR capture status procurement-identity binding drift")
    require(status_eco.get("pcba_procurement_authorized") is False,
            "PCB-PWR capture status prematurely authorizes procurement")
    require(status_eco.get("manufacturing_release") is False,
            "PCB-PWR capture status prematurely releases manufacture")

    required_ids = [f"PWR-IPQ-{index:03d}" for index in range(1, 21)]
    require(len(matrix) == 20, f"qualification matrix row count drift: {len(matrix)}")
    require([row["Test_ID"] for row in matrix] == required_ids,
            "qualification matrix IDs/order drift")
    require(all(row["Blocking"] == "YES" for row in matrix),
            "every qualification row must remain blocking")
    allowed_status = {"PENDING_EVIDENCE", "PENDING_PHYSICAL_TEST", "PASS", "FAIL"}
    require(all(row["Status"] in allowed_status for row in matrix),
            "qualification matrix contains unsupported status")
    for row in matrix:
        if row["Status"].startswith("PENDING"):
            require(not any(row[field] for field in
                            ("Result", "Operator", "Date", "Artifact_SHA256")),
                    f"{row['Test_ID']}: pending row carries unaudited result metadata")
        if row["Status"] == "PASS":
            require(all(row[field] for field in
                        ("Result", "Operator", "Date", "Artifact_SHA256")),
                    f"{row['Test_ID']}: PASS lacks attributable evidence")

    matrix_by_id = {row["Test_ID"]: row for row in matrix}
    require(matrix_by_id["PWR-IPQ-001"]["Status"] == "PASS" and
            matrix_by_id["PWR-IPQ-001"]["Result"] ==
            "Official Littelfuse/Molex payloads hash-bound; exact 0451008.MRL SMBJ18A 43045-0213 and 43030-0038 identities and controlled ratings match" and
            matrix_by_id["PWR-IPQ-001"]["Operator"] ==
            "Codex primary-source archive audit" and
            matrix_by_id["PWR-IPQ-001"]["Date"] == "2026-09-17" and
            matrix_by_id["PWR-IPQ-001"]["Artifact_SHA256"] ==
            source_evidence_sha256,
            "PWR-IPQ-001 primary-source evidence drift")
    require(matrix_by_id["PWR-IPQ-002"]["Gate"] ==
            "DOCUMENTARY_PROCUREMENT_IDENTITY" and
            matrix_by_id["PWR-IPQ-002"]["Status"] == "PASS" and
            "Current official manufacturer data" in
            matrix_by_id["PWR-IPQ-002"]["Required_Input"] and
            "no sample-only order" in
            matrix_by_id["PWR-IPQ-002"]["Pass_Criteria"] and
            "receiving quarantine" in
            matrix_by_id["PWR-IPQ-002"]["Pass_Criteria"] and
            matrix_by_id["PWR-IPQ-002"]["Artifact_SHA256"] ==
            procurement_identity_sha256,
            "PWR-IPQ-002 documentary procurement control drift")
    require(matrix_by_id["PWR-IPQ-003"]["Status"] == "PASS" and
            matrix_by_id["PWR-IPQ-003"]["Result"] ==
            "F1=0451008.MRL in all active sources; pin/net and board semantic digests retained; post-ECO ERC/PDF artifact archived" and
            matrix_by_id["PWR-IPQ-003"]["Operator"] ==
            "GitHub Actions run 35197150159 + Codex independent audit" and
            matrix_by_id["PWR-IPQ-003"]["Date"] == "2026-09-17" and
            matrix_by_id["PWR-IPQ-003"]["Artifact_SHA256"] ==
            "bf80f07c9b20d93d610c3e8c124887becb4209f8d688f085fe68bac53e0ad0b9",
            "PWR-IPQ-003 native-value ECO evidence drift")
    require(matrix_by_id["PWR-IPQ-004"]["Status"] == "PASS" and
            matrix_by_id["PWR-IPQ-004"]["Result"] ==
            "Source e32c0aa9e510e8321e24ebb3ee2056100c5f3a1a and PDF 7abb5e83e5d8cc72178c37fbf559bd77ca0d915b1c92f94e12ed278ce83bf130 accepted hierarchy-only" and
            matrix_by_id["PWR-IPQ-004"]["Operator"] ==
            "GitHub Actions run 35217048575 + reviewer Скиф" and
            matrix_by_id["PWR-IPQ-004"]["Date"] == "2026-09-17" and
            matrix_by_id["PWR-IPQ-004"]["Artifact_SHA256"] ==
            "f29dfa4e0be9c25f8023e7d5218a97a28db70b0a1059eaca0141f699f46e64d3",
            "PWR-IPQ-004 repeat hierarchy evidence drift")

    accepted_rows = sum(row["Status"] == "PASS" for row in matrix)
    failed_rows = [row["Test_ID"] for row in matrix if row["Status"] == "FAIL"]
    repeat_gate_complete = all((
        native_eco["repeat_native_kicad_9_erc_complete"],
        native_eco["repeat_pdf_evidence_complete"],
        native_eco["repeat_independent_human_hierarchy_review_complete"],
    ))
    complete = (accepted_rows == 20 and not failed_rows and native_eco["applied"]
                and repeat_gate_complete)
    require(contract["test_matrix"]["required_rows"] == 20,
            "contract qualification row count drift")
    require(contract["test_matrix"]["accepted_rows"] == 4,
            "contract accepted-row count does not match controlled evidence")
    require(status_eco.get("accepted_test_rows") == accepted_rows == 4,
            "capture-status qualification accepted-row count drift")
    require(contract["test_matrix"]["complete"] is False,
            "contract claims physical qualification complete")

    result = {
        "configuration": contract["configuration"],
        "audit": "PCB-PWR Rev.A input-protection qualification control",
        "status": (
            "PASS_QUALIFIED_FOR_RELEASE"
            if complete
            else "PASS_CONTROLLED_QUALIFICATION_PLAN_PHYSICAL_EVIDENCE_PENDING"
        ),
        "fuse": {
            "signed_native_mpn": fuse["signed_native_mpn"],
            "target_evt_mpn": fuse["target_evt_mpn"],
            "continuous_current_a": continuous_a,
            "minimum_nominal_rating_at_25c_a": required_rating_a,
            "target_capacity_after_standard_derating_a": capacity_a,
            "nominal_loss_at_5a_w": loss_w,
        },
        "tvs": {
            "target_evt_mpn": tvs["target_evt_mpn"],
            "maximum_clamp_v": tvs["maximum_clamp_v"],
            "project_candidate_clamp_limit_v": tvs[
                "project_candidate_clamp_limit_at_protected_node_v"
            ],
            "buck_absolute_max_input_v": tvs["buck_absolute_max_input_v"],
        },
        "native_value_eco_applied": native_eco["applied"],
        "value_only_change_verified": True,
        "pin_net_semantic_sha256": native_eco["post_eco_pin_net_semantic_sha256"],
        "board_semantic_sha256": native_eco["post_eco_board_semantic_sha256"],
        "repeat_erc_pdf_human_review_complete": repeat_gate_complete,
        "source_control_complete": source_control["complete"],
        "source_control_evidence_sha256": source_evidence_sha256,
        "prepurchase_documentary_identity_complete": procurement_identity[
            "prepurchase_documentary_identity_complete"
        ],
        "standalone_engineering_sample_purchase_required": False,
        "procurement_identity_evidence_sha256": procurement_identity_sha256,
        "receiving_identity_hold_required": False,
        "accepted_rows": accepted_rows,
        "required_rows": 20,
        "failed_rows": failed_rows,
        "physical_qualification_complete": complete,
        "pcba_procurement_authorized": False,
        "manufacturing_release": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print("PCB-PWR input-protection qualification packet audit PASS")
    print(
        f"F1 target={fuse['target_evt_mpn']} "
        f"standard-derated capacity={capacity_a:.3f} A; "
        f"D1 target={tvs['target_evt_mpn']}"
    )
    print(
        f"Native value ECO applied={native_eco['applied']}; "
        f"qualification evidence={accepted_rows}/20 PASS"
    )
    print("Documentary procurement identity PASS; no sample-only order or receiving identity hold")
    print("PCBA procurement and manufacturing release remain BLOCKED")
    print(args.output)

    if args.strict and not complete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
