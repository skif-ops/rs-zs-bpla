#!/usr/bin/env python3
"""QG-2 independent technical completeness audit of the Rev.A BOM.

Default mode records blockers without failing engineering CI. --strict is the actual
production-BOM release gate and must remain non-zero until the schematic-derived BOM,
exact system SKUs and verification evidence are complete.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
PROCUREMENT_BOM = ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"
LOT_SIZES = (4, 10, 20)


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def run_json_audit(script_name: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="evt-pre-20-bom-qg2-") as temp_dir:
        output = Path(temp_dir) / "audit.json"
        process = subprocess.run(
            [
                sys.executable,
                str(ROOT / f"tools/{script_name}"),
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0 or not output.is_file():
            return {
                "status": "ERROR",
                "error": process.stderr.strip() or process.stdout.strip() or f"exit {process.returncode}",
            }
        return json.loads(output.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", default="artifacts/evt_pre_20_bom_qg2.json")
    args = parser.parse_args()

    rows = read(BOM)
    by_id = {row["Item_ID"]: row for row in rows}
    blockers: list[str] = []
    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "pass": ok, "detail": detail})
        if not ok:
            blockers.append(detail)

    lot_errors: list[str] = []
    required_lot_fields = {
        "Spare_policy",
        *(
            field
            for lot_size in LOT_SIZES
            for field in (
                f"Qty_{lot_size}",
                f"Spares_{lot_size}",
                f"Procure_qty_{lot_size}",
            )
        ),
    }
    for row in rows:
        missing = sorted(field for field in required_lot_fields if field not in row)
        if missing:
            lot_errors.append(f"{row.get('Item_ID', '?')}:missing={','.join(missing)}")
            continue
        try:
            qty_per_station = int(row["Qty_per_station"])
            spares_20 = int(row["Spares_20"])
            for lot_size in LOT_SIZES:
                quantity = int(row[f"Qty_{lot_size}"])
                spares = int(row[f"Spares_{lot_size}"])
                procure = int(row[f"Procure_qty_{lot_size}"])
                if quantity != qty_per_station * lot_size or procure != quantity + spares:
                    lot_errors.append(f"{row['Item_ID']}:lot={lot_size}:arithmetic")
                policy = row["Spare_policy"]
                expected_spares = {
                    "NONE": 0,
                    "FIXED_LOT_MIN": spares_20,
                    "SCALE_CEIL_FROM_20_BASELINE": (spares_20 * lot_size + 19) // 20,
                }.get(policy)
                if expected_spares is None or spares != expected_spares:
                    lot_errors.append(f"{row['Item_ID']}:lot={lot_size}:spare_policy")
        except ValueError:
            lot_errors.append(f"{row.get('Item_ID', '?')}:non_integer_quantity")

    procurement_rows = read(PROCUREMENT_BOM) if PROCUREMENT_BOM.is_file() else []
    if not procurement_rows:
        lot_errors.append("procurement_rollup:missing_or_empty")
    else:
        procurement_ids = [row.get("Procurement_ID", "") for row in procurement_rows]
        if not all(procurement_ids) or len(set(procurement_ids)) != len(procurement_ids):
            lot_errors.append("procurement_rollup:duplicate_or_empty_id")
        represented = {
            item_id.strip()
            for row in procurement_rows
            for item_id in row.get("Item_IDs", "").split("|")
            if item_id.strip()
        }
        if represented != set(by_id):
            lot_errors.append("procurement_rollup:item_coverage")
        for lot_size in LOT_SIZES:
            try:
                detailed_total = sum(int(row[f"Procure_qty_{lot_size}"]) for row in rows)
                rollup_total = sum(int(row[f"Procure_qty_{lot_size}"]) for row in procurement_rows)
                rollup_formula_ok = all(
                    int(row[f"Procure_qty_{lot_size}"])
                    == int(row[f"Qty_{lot_size}"]) + int(row[f"Spares_{lot_size}"])
                    for row in procurement_rows
                )
                if detailed_total != rollup_total or not rollup_formula_ok:
                    lot_errors.append(f"procurement_rollup:lot={lot_size}:reconciliation")
            except (KeyError, ValueError):
                lot_errors.append(f"procurement_rollup:lot={lot_size}:invalid_quantity")
    check(
        "procurement_lots_4_10_20",
        not lot_errors,
        "BOM 4/10/20 lot or procurement-rollup mismatch: " + ", ".join(lot_errors)
        if lot_errors
        else "engineering and procurement BOM quantities independently reconcile for 4, 10 and 20 stations",
    )

    main_freeze = read(ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv")
    main_item_for_ref = {
        **{f"U{i}": f"U{i}" for i in (1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18)},
        "U14": "U14-U15", "U15": "U14-U15", "Q1": "Q-MODEM-PWRKEY",
        "Q2": "Q-MODEM-RESET", "Q3": "Q-SIM-MUX-EN", "X1": "X1",
    }
    main_mismatch = []
    for frozen in main_freeze:
        ref = frozen["RefDes"]
        item = main_item_for_ref.get(ref)
        if not item or item not in by_id or by_id[item]["MPN"] != frozen["MPN"]:
            main_mismatch.append(f"{ref}:{frozen['MPN']}")
    check("main_active_mpn_freeze", not main_mismatch,
          "PCB-MAIN active MPN freeze mismatch: " + ", ".join(main_mismatch) if main_mismatch else "all active MAIN MPNs match")

    passive_support = read(ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv")
    passive_support_mismatch = []
    for frozen in passive_support:
        ref = frozen["RefDes"]
        item = "X1" if ref == "X1" else f"MAIN-010-{ref}"
        row = by_id.get(item)
        expected_qty = "1" if frozen["Population"] == "FITTED" else "0"
        if (
            row is None
            or row["Assembly"] != "PCB-MAIN"
            or row["RefDes"] != ref
            or row["Manufacturer"] != frozen["Manufacturer"]
            or row["MPN"] != frozen["MPN"]
            or row["Package"] != frozen["Package"]
            or row["Value"] != frozen["Value"]
            or row["Population"] != frozen["Population"]
            or row["Temperature_C"] != frozen["Temperature_C"]
            or row["Qty_per_station"] != expected_qty
            or frozen["Pin_Map"] not in row["Notes"]
        ):
            passive_support_mismatch.append(ref)
    check(
        "main_passive_support_authority_bom",
        len(passive_support) == 211 and not passive_support_mismatch,
        "PCB-MAIN MAIN-AUTH-010 BOM mismatch: " + ", ".join(passive_support_mismatch)
        if passive_support_mismatch
        else "all 211 MAIN-AUTH-010 identities values populations ratings and physical pins are represented",
    )

    power_expected = {
        "PWR-REV-CTL": ("U1", "LM74700QDBVRQ1"),
        "PWR-REV-FET": ("Q1", "CSD18540Q5B"),
        "U-MON-01": ("U2", "INA226AIDGSR"),
        "U-PWR1": ("U3", "LMR604403SRAKR"),
        "U-PWR2": ("U4", "LMR604403SRAKR"),
        "U-PWR3": ("U5", "TPS7A2018PDBVR"),
        "R-SHUNT-01": ("RSH1", "WSK2512R0100FEA"),
        "PWR-TVS-01": ("D1", "SMBJ18A"),
        "PWR-FUSE-01": ("F1", "0451008.MRL"),
    }
    power_mismatch = [
        item for item, (ref, mpn) in power_expected.items()
        if item not in by_id or by_id[item]["RefDes"] != ref or by_id[item]["MPN"] != mpn
    ]
    check("power_identity_and_refdes", not power_mismatch,
          "PCB-PWR identity/RefDes mismatch: " + ", ".join(power_mismatch) if power_mismatch else "power IC/protection identity and RefDes match")

    pwr_passive_authority = read(ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv")
    pwr_passive_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for frozen in pwr_passive_authority:
        if frozen["BOM_Item_ID"]:
            pwr_passive_groups[frozen["BOM_Item_ID"]].append(frozen)
    pwr_passive_mismatch = []
    for item_id, frozen_rows in pwr_passive_groups.items():
        first = frozen_rows[0]
        row = by_id.get(item_id)
        population = first["Population"]
        expected_qty = "0" if population == "DNP" else str(len(frozen_rows))
        expected_refs = ";".join(item["RefDes"] for item in frozen_rows)
        if (
            row is None
            or row["Assembly"] != "PCB-PWR"
            or row["RefDes"] != expected_refs
            or row["Manufacturer"] != first["Manufacturer"]
            or row["MPN"] != first["MPN"]
            or row["Package"] != first["Package"]
            or row["Value"] != first["Value"]
            or row["Population"] != population
            or row["Temperature_C"] != first["Temperature_C"]
            or row["Qty_per_station"] != expected_qty
            or first["Footprint"] not in row["Notes"]
        ):
            pwr_passive_mismatch.append(item_id)
    dft_refs = {row["RefDes"] for row in pwr_passive_authority if not row["BOM_Item_ID"]}
    leaked_dft = sorted(
        ref for row in rows for ref in row["RefDes"].split(";") if ref in dft_refs
    )
    check(
        "power_passive_authority_bom",
        len(pwr_passive_authority) == 49 and len(pwr_passive_groups) == 17
        and not pwr_passive_mismatch and not leaked_dft,
        "PCB-PWR passive authority/BOM mismatch: "
        + ", ".join(pwr_passive_mismatch + leaked_dft)
        if pwr_passive_mismatch or leaked_dft
        else "all 39 BOM passives/net-ties match authority; 10 DFT pads remain non-procured",
    )

    mic_expected = {
        "MK1": "MMICT5838-00-012", "J-MIC": "5040500691",
        "C-MIC": "CGA2B3X7R1E104K050BB", "R-MIC": "ERJ-2GE0R00X",
    }
    mic_mismatch = [item for item, mpn in mic_expected.items() if item not in by_id or by_id[item]["MPN"] != mpn]
    check("mic_native_component_identity", not mic_mismatch,
          "PCB-MIC component identity mismatch: " + ", ".join(mic_mismatch) if mic_mismatch else "four native PCB-MIC fitted identities match")

    mic_native = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_sch"
    mic_legacy = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.sch"
    mic_native_text = mic_native.read_text(encoding="utf-8") if mic_native.is_file() else ""
    mic_native_mpn_ok = (
        mic_native.is_file()
        and "MMICT5838-00-012" in mic_native_text
        and "Dioneya:T5838_RevA" in mic_native_text
        and "Dioneya:Molex_5040500691" in mic_native_text
        and not mic_legacy.exists()
    )
    check(
        "mic_native_exact_orderable_mpn",
        mic_native_mpn_ok,
        "single native KiCad-9 PCB-MIC source binds exact MK1/J1 identities and controlled footprints"
        if mic_native_mpn_ok
        else "PCB-MIC KiCad-9 source/footprint identity is incomplete or a competing legacy .sch remains",
    )

    exact_fields_missing = []
    for row in rows:
        if row["Population"] != "FITTED":
            continue
        for field in ("Manufacturer", "MPN", "Package", "Temperature_C"):
            if row[field] in ("", "TBD", "OPEN"):
                exact_fields_missing.append(f"{row['Item_ID']}:{field}")
    check("fitted_line_exact_fields", not exact_fields_missing,
          "fitted lines missing exact production fields: " + ", ".join(exact_fields_missing) if exact_fields_missing else "all fitted lines have exact identity/package/rating")

    build_to_print_expected = {
        "ASM-MAIN": ("DIO-ASM-MAIN-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
        "PCB-MAIN": ("DIO-PCB-MAIN-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
        "ASM-PWR": ("DIO-ASM-PWR-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
        "PCB-PWR": ("DIO-PCB-PWR-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
        "ASM-MIC": ("DIO-ASM-MIC-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
        "PCB-MIC": ("DIO-PCB-MIC-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
        "HARNESS": ("DIO-HARNESS-SET-REV-A", "CONTROLLED_BUILD_TO_PRINT_IDENTITY"),
        "HSG-VC": ("DIO-HSG-VC-REV-A", "CONTROLLED_CUSTOMER_RFQ_SCOPE"),
    }
    build_to_print_errors = []
    for item_id, (mpn, disposition) in build_to_print_expected.items():
        row = by_id.get(item_id)
        if (
            row is None
            or row["Manufacturer"] != "Dioneya controlled design"
            or row["MPN"] != mpn
            or row["BOM_disposition"] != disposition
            or not row["Status"].startswith("CONTROLLED_INTERNAL_ARTICLE_")
            or not row["Package"]
        ):
            build_to_print_errors.append(item_id)

    rfq_rows = read(ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv")
    rfq_by_item = {row["BOM_Item_IDs"]: row for row in rfq_rows}
    for item_id, (mpn, _) in build_to_print_expected.items():
        row = rfq_by_item.get(item_id)
        if (
            row is None
            or row["Manufacturer"] != "Dioneya controlled design"
            or mpn not in row["MPN_or_spec"]
            or row["Status"] != "RFQ_REQUIRED"
            or row["Supplier"]
            or row["Quote_date"]
        ):
            build_to_print_errors.append(f"{item_id}:RFQ_BOUNDARY")
    check(
        "build_to_print_internal_article_identity",
        not build_to_print_errors,
        "build-to-print identity or customer-supplier boundary mismatch: "
        + ", ".join(build_to_print_errors)
        if build_to_print_errors
        else (
            "eight internal article identities are controlled while customer-selected "
            "supplier quote and legal-entity fields remain intentionally open"
        ),
    )

    passive_value_missing = [
        row["Item_ID"] for row in rows
        if row["Population"] in {"FITTED", "DNP"}
        and row["Category"] in {"Passive", "Shunt"}
        and not row["Value"]
    ]
    check("passive_values", not passive_value_missing,
          "passive lines missing explicit value: " + ", ".join(passive_value_missing) if passive_value_missing else "all passive values are explicit")

    blocked_rows = [row["Item_ID"] for row in rows if row["BOM_disposition"].startswith("BLOCKED")]
    check("bom_dispositions_released", not blocked_rows,
          "BOM identities or controlled procurement scopes still blocked: " + ", ".join(blocked_rows)
          if blocked_rows else "all BOM identities and customer-owned procurement scopes are controlled")

    # This independent list comes from the native PCB-PWR generator. Every physical
    # fitted/DNP designator must be represented before a factory BOM can be released.
    required_pwr_passives = {
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13",
        "C14", "C15", "C16", "C17", "C18", "C19", "C20", "C21",
        "L1", "L2", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12",
        "R13", "R14", "R15", "NT1", "NT2", "NT3",
    }
    represented_pwr_refs: set[str] = set()
    for row in rows:
        if row["Assembly"] != "PCB-PWR":
            continue
        for token in row["RefDes"].split(";"):
            ref = token.strip().removesuffix(" bank")
            if ref in required_pwr_passives:
                represented_pwr_refs.add(ref)
    missing_pwr_passives = sorted(required_pwr_passives - represented_pwr_refs)
    check("power_schematic_refdes_coverage", not missing_pwr_passives,
          "PCB-PWR BOM missing schematic RefDes: " + ", ".join(missing_pwr_passives) if missing_pwr_passives else "all PCB-PWR passive/net-tie RefDes represented")

    bank_rows = [row["Item_ID"] for row in rows if row["Assembly"] == "PCB-PWR" and " bank" in row["RefDes"]]
    check("power_cap_bank_native_expansion", not bank_rows,
          "PCB-PWR capacitor bank symbols still require individual native RefDes: " + ", ".join(bank_rows) if bank_rows else "all power capacitors have individual native RefDes")

    main_status_path = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
    main_status: dict[str, object] = {}
    main_status_error = ""
    try:
        main_status = json.loads(main_status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        main_status_error = str(exc)
    control_ok = (
        not main_status_error
        and main_status.get("schema_version") == 1
        and main_status.get("configuration") == "EVT-PRE-20 Rev.A"
        and main_status.get("assembly") == "PCB-MAIN"
        and main_status.get("manufacturing_release") is False
    )
    check("main_capture_status_control", control_ok,
          f"PCB-MAIN capture status is missing or invalid: {main_status_error or 'identity/release-state mismatch'}" if not control_ok else "PCB-MAIN capture status is explicit and release-blocked")

    readiness = main_status.get("capture_readiness", {}) if isinstance(main_status, dict) else {}
    open_authorities = readiness.get("open_authorities", []) if isinstance(readiness, dict) else []
    readiness_ok = (
        isinstance(readiness, dict)
        and readiness.get("complete") is True
        and not open_authorities
    )
    open_authority_ids = [item.get("id", "UNIDENTIFIED") for item in open_authorities if isinstance(item, dict)]
    check("main_capture_authority_complete", readiness_ok,
          "PCB-MAIN mechanical authority remains open: " + ", ".join(open_authority_ids) if open_authority_ids else "PCB-MAIN capture authority is complete")

    native_record = main_status.get("native_schematic", {}) if isinstance(main_status, dict) else {}
    native_relative = native_record.get("path", "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_sch") if isinstance(native_record, dict) else "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_sch"
    main_native = ROOT / str(native_relative)
    native_manifest: dict[str, object] = {}
    native_source_set_ok = False
    native_source_error = ""
    native_sources: list[Path] = []
    try:
        manifest_relative = native_record.get("manifest", "")
        manifest_path = ROOT / str(manifest_relative)
        native_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        hierarchy_sources = native_manifest.get("hierarchy_sources", [])
        if not isinstance(hierarchy_sources, list):
            raise ValueError("hierarchy_sources is not a list")
        if (native_manifest.get("hierarchy_pages") != 10 or
                native_manifest.get("hierarchy_functional_child_sheets") != 9 or
                len(hierarchy_sources) != 10):
            raise ValueError("hierarchy page/source count drift")
        for source in hierarchy_sources:
            if not isinstance(source, dict):
                raise ValueError("hierarchy source record is not an object")
            relative = str(source.get("path", ""))
            if not relative or Path(relative).name != relative:
                raise ValueError(f"invalid hierarchy source path: {relative!r}")
            path = main_native.parent / relative
            if not path.is_file():
                raise ValueError(f"missing hierarchy source: {relative}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != source.get("sha256"):
                raise ValueError(f"hierarchy source hash drift: {relative}")
            native_sources.append(path)
        if native_sources[0] != main_native:
            raise ValueError("hierarchy manifest root source is not PCB-MAIN.kicad_sch")
        native_source_set_ok = True
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        native_source_error = str(exc)
    native_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in native_sources
    )
    pin_rows = read(ROOT / "hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv")
    device_pin_rows = read(ROOT / "hardware/PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv")
    audio_logic_pin_rows = read(ROOT / "hardware/PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv")
    cellular_pin_rows = read(ROOT / "hardware/PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv")
    dual_sim_pin_rows = read(ROOT / "hardware/PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv")
    gnss_pin_rows = read(ROOT / "hardware/PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv")
    lora_pin_rows = read(ROOT / "hardware/PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv")
    ble_pin_rows = read(ROOT / "hardware/PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv")
    connector_fixture_pin_rows = read(ROOT / "hardware/PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv")
    passive_support_pin_nets = {
        assignment.split("=", 1)[1]
        for row in passive_support
        for assignment in row["Pin_Map"].split(";")
        if "=" in assignment and assignment.split("=", 1)[1] != "NC"
    }
    required_native_tokens = {
        "(kicad_sch",
        *(row["MPN"] for row in main_freeze),
        *(row["MPN"] for row in passive_support),
        *passive_support_pin_nets,
        *(row["RevA_Net"] for row in pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in device_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in audio_logic_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in cellular_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in dual_sim_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in gnss_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in lora_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in ble_pin_rows if row["RevA_Net"] != "NC"),
        *(row["RevA_Net"] for row in connector_fixture_pin_rows if row["RevA_Net"] != "NC"),
    }
    native_overlay_rows = read(ROOT / "hardware/PCB_MAIN_NATIVE_NET_OVERLAY_REV_A.csv")
    overlay_logical_nets = {row["Logical_Net"] for row in native_overlay_rows}
    required_native_tokens.difference_update(overlay_logical_nets)
    required_native_tokens.update(row["Native_Net"] for row in native_overlay_rows)
    # Pre-capture authorities use generic GND outside the modem domain. Native
    # capture resolves it through the controlled ground-domain authority.
    required_native_tokens.discard("GND")
    required_native_tokens.update({"GND_MODEM", "GND_DIGITAL", "GND_MIC"})
    native_tokens_missing = sorted(token for token in required_native_tokens if token not in native_text)
    native_ok = (
        main_native.is_file()
        and native_source_set_ok
        and isinstance(native_record, dict)
        and native_record.get("status") in {"PRESENT_REVIEW_PENDING", "REVIEW_A_PASS", "REVIEW_B_PASS"}
        and native_record.get("schematic_derived_bom") is True
        and not native_tokens_missing
    )
    check(
        "main_native_schematic_source",
        native_ok,
        (
            "native PCB-MAIN schematic, physical overlay/ground-domain tokens or declared "
            "schematic-derived BOM provenance are incomplete: "
            + (native_source_error + "; " if native_source_error else "")
            + ", ".join(native_tokens_missing)
        ) if not native_ok else (
            "all 10 native PCB-MAIN hierarchy sources contain the frozen MPNs, controlled "
            "physical-net overlay, three ground domains and schematic-derived BOM provenance"
        ),
    )

    review_a = main_status.get("review_a", {}) if isinstance(main_status, dict) else {}
    required_review_a_evidence = {
        "signed_checklist", "schematic_pdf", "cubemx_pin_report", "erc_report",
        "bom_diff", "net_name_diff",
    }
    review_a_evidence = review_a.get("evidence", {}) if isinstance(review_a, dict) else {}
    review_a_evidence_refs = {
        name: str(ref) for name, ref in review_a_evidence.items()
        if name in required_review_a_evidence and ref
    } if isinstance(review_a_evidence, dict) else {}
    evidence_available = all(
        ((ROOT / ref).is_file() and (ROOT / ref).stat().st_size > 0)
        if name == "signed_checklist"
        else ref.startswith("https://github.com/skif-ops/rs-zs-bpla/actions/runs/")
        for name, ref in review_a_evidence_refs.items()
    )
    review_a_ok = (
        isinstance(review_a, dict)
        and review_a.get("complete") is True
        and review_a.get("status") == "PASS"
        and all(review_a.get(field) for field in ("reviewer", "date", "commit_sha"))
        and set(review_a_evidence_refs) == required_review_a_evidence
        and evidence_available
    )
    check("main_review_a_complete", review_a_ok,
          "PCB-MAIN Review A is not complete with signed identity, commit and all required evidence" if not review_a_ok else "PCB-MAIN Review A complete with required evidence")

    system_ots_identity = run_json_audit(
        "audit_evt_system_ots_procurement_identity_rev_a.py"
    )
    system_ots_identity_ok = (
        system_ots_identity.get("status")
        == "PASS_DOCUMENTARY_PURCHASE_IDENTITY_PHYSICAL_VALIDATION_DURING_ASSEMBLY_EOL_EVT"
        and system_ots_identity.get("documentary_purchase_identity_complete") is True
        and system_ots_identity.get("controlled_item_count") == 8
        and system_ots_identity.get("standalone_preorder_qualification_unit_required") is False
        and system_ots_identity.get("receiving_hold_required") is False
        and system_ots_identity.get("physical_qualification_complete") is False
        and system_ots_identity.get("manufacturing_release") is False
    )
    check(
        "system_ots_documentary_procurement_identity",
        system_ots_identity_ok,
        "system OTS documentary purchase identity is missing or inconsistent: "
        + str(system_ots_identity.get("error", system_ots_identity.get("status", "MISSING")))
        if not system_ots_identity_ok
        else "eight exact system OTS MPNs have documentary purchase control; physical assembly/EOL/EVT validation remains open",
    )

    released_system_dispositions = {
        "CONTROLLED",
        "CONTROLLED_BUILD_TO_PRINT_IDENTITY",
        "CONTROLLED_CUSTOMER_RFQ_SCOPE",
    }
    system_open = [
        row["Item_ID"] for row in rows
        if row["Line_class"] in {"SYSTEM_ITEM", "MECHANICAL_OPTION"}
        and int(row["Qty_per_station"]) > 0
        and row["BOM_disposition"] not in released_system_dispositions
    ]
    check("system_sku_release", not system_open,
          "system/mechanical article identities not controlled: " + ", ".join(system_open)
          if system_open else "system SKUs and build-to-print article identities are controlled")

    result = {
        "gate": "QG-2",
        "status": "PASS" if not blockers else "BLOCKED",
        "production_bom_complete": not blockers,
        "checks": checks,
        "blockers": blockers,
        "system_ots_procurement_identity": system_ots_identity,
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"EVT-PRE-20 production BOM QG-2 technical gate: {result['status']}")
    for blocker in blockers:
        print(f"- {blocker}")
    print(f"report: {output.relative_to(ROOT) if output.is_relative_to(ROOT) else output}")
    return 1 if args.strict and blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
