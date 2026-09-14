#!/usr/bin/env python3
"""Preflight and execute native KiCad checks for EVT-PRE-20 Rev.A.

PCB and schematic are checked independently as soon as each native file exists. During
engineering iterations the gate collects BOTH DRC and ERC reports before failing, so a
PCB violation cannot hide a schematic violation (or vice versa). Fabrication exports
are generated only after the corresponding DRC passes.

For PCB-MIC the KiCad 9 SWIG stackup descriptor is intentionally not used to write the
surface finish because that API is opaque on supported Linux builds. Instead, controlled
fabrication_metadata.json is verified against KiCad output and its standard Revision and
Finish values are written into the generated Gerber job metadata after the geometric
Gerbers have been produced. Gerber geometry is never rewritten by this step.

The overall release remains BLOCKED until MAIN/MIC/PWR each have SCH/PCB/PRO, all CLI
checks pass, and project Review A/B are complete.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware" / "kicad" / "native"
ART = ROOT / "artifacts" / "kicad-native"
BOARDS = ("PCB-MAIN", "PCB-MIC", "PCB-PWR")
PCB_MAIN_STATUS = ROOT / "hardware" / "PCB_MAIN_CAPTURE_STATUS_REV_A.json"
PCB_MIC_STATUS = ROOT / "hardware" / "PCB_MIC_CAPTURE_STATUS_REV_A.json"
PCB_PWR_STATUS = ROOT / "hardware" / "PCB_PWR_CAPTURE_STATUS_REV_A.json"
PRODUCTION_BOM = ROOT / "hardware" / "EVT_PRE_20_BOM_REV_A.csv"
PCB_MIC_REVIEW_B_AUDIT = ROOT / "tools" / "audit_pcb_mic_review_b_preflight_rev_a.py"

PCB_MIC_BOM_ITEMS = {
    "C1": "C-MIC",
    "J1": "J-MIC",
    "MK1": "MK1",
    "R1": "R-MIC",
}

PCB_MIC_NATIVE_COMPONENTS = {
    "C1": ("100nF X7R", "Capacitor_SMD:C_0402_1005Metric"),
    "J1": ("5040500691", "Dioneya:Molex_5040500691"),
    "MK1": ("MMICT5838-00-012", "Dioneya:T5838_RevA"),
    "R1": ("0R EVT_SI_TUNE", "Resistor_SMD:R_0402_1005Metric"),
}

BOARD_STATUS = {
    "PCB-MAIN": PCB_MAIN_STATUS,
    "PCB-MIC": PCB_MIC_STATUS,
    "PCB-PWR": PCB_PWR_STATUS,
}


def review_a_complete(name: str) -> bool:
    status_path = BOARD_STATUS[name]
    if not status_path.is_file():
        return False
    status = json.loads(status_path.read_text(encoding="utf-8"))
    review_a = status.get("review_a", {})
    return isinstance(review_a, dict) and review_a.get("complete") is True


def placement_candidate_audit(name: str) -> str | None:
    controls = {
        "PCB-MAIN": (
            PCB_MAIN_STATUS,
            "OPEN_PLACEMENT_CANDIDATE_ROUTING_AND_EVIDENCE_PENDING",
            "tools/audit_pcb_main_layout_candidate_rev_a.py",
        ),
        "PCB-PWR": (
            PCB_PWR_STATUS,
            "OPEN_PROVISIONAL_PLACEMENT_CANVAS_DIM_003_ROUTING_AND_EVIDENCE_PENDING",
            "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
        ),
    }
    if name not in controls:
        return None
    status_path, expected, audit = controls[name]
    if not status_path.is_file():
        return None
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("review_b", {}).get("status") != expected:
        return None
    return audit


def pcb_main_is_placement_candidate() -> bool:
    """Compatibility helper retained for external callers."""
    if not PCB_MAIN_STATUS.is_file():
        return False
    return placement_candidate_audit("PCB-MAIN") is not None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def run(cmd: list[str], *, check: bool = True) -> int:
    print("+", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, check=False, cwd=ROOT)
    if check and completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, cmd)
    return completed.returncode


def paths(name: str) -> dict[str, Path]:
    base = NATIVE / name / name
    return {
        "sch": base.with_suffix(".kicad_sch"),
        "pcb": base.with_suffix(".kicad_pcb"),
        "pro": base.with_suffix(".kicad_pro"),
    }


def prepare_cam_source(name: str, pcb: Path, out: Path) -> Path:
    """Archive a controlled CAM-only copy with drill guide flashes disabled.

    PCB-MIC Review A is signed against the committed native PCB. KiCad's saved
    ``drillshape 1`` plot preference adds 0.35 mm guide flashes to every plotted
    technical layer, including paste and mask. The manufacturing source itself must
    remain byte-for-byte unchanged, so only an archived CAM-input copy is changed and
    the exact one-field transform is recorded beside it.
    """
    if name != "PCB-MIC":
        return pcb

    source_text = pcb.read_text(encoding="utf-8")
    source_values = re.findall(r"\(drillshape\s+(\d+)\)", source_text)
    if source_values != ["1"]:
        raise RuntimeError(
            f"PCB-MIC: expected only pcbplotparams drillshape 1, got {source_values}"
        )
    pattern = re.compile(
        r"(?m)^(?P<prefix>[ \t]*\(drillshape[ \t]+)1(?P<suffix>\)[ \t]*)$"
    )
    derived_text, replacements = pattern.subn(r"\g<prefix>0\g<suffix>", source_text)
    if replacements != 1:
        raise RuntimeError(
            f"PCB-MIC: expected one pcbplotparams drillshape 1 field, found {replacements}"
        )
    if re.findall(r"\(drillshape\s+(\d+)\)", derived_text) != ["0"]:
        raise RuntimeError("PCB-MIC: CAM drillshape 0 verification failed")

    cam_dir = out / "cam-source"
    cam_dir.mkdir(parents=True, exist_ok=True)
    derived = cam_dir / pcb.name
    derived.write_text(derived_text, encoding="utf-8")

    transform = {
        "schema": "dioneya-controlled-cam-source-transform-v1",
        "board": name,
        "status": "CONTROLLED_CAM_PLOT_SETTINGS_TRANSFORM_NOT_A_DESIGN_CHANGE",
        "source_commit_sha": git_head(),
        "source_path": str(pcb.relative_to(ROOT)),
        "source_sha256": sha256(pcb),
        "derived_path": str(derived.relative_to(ART)),
        "derived_sha256": sha256(derived),
        "transformations": [
            {
                "field": "pcbplotparams.drillshape",
                "before": 1,
                "after": 0,
                "count": 1,
                "reason": (
                    "suppress non-design drill guide flashes in Gerber paste, mask, "
                    "silkscreen and profile layers"
                ),
            }
        ],
        "design_geometry_modified": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    (out / "cam_source_transform.json").write_text(
        json.dumps(transform, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "PCB-MIC: controlled CAM source PASS: drillshape 1 -> 0; "
        "signed native source unchanged"
    )
    return derived


def _kicad_bom_components(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise RuntimeError("PCB-MIC KiCad BOM has no header")
        rows = list(reader)

    by_ref: dict[str, dict[str, str]] = {}
    for row in rows:
        reference = (row.get("Reference") or "").strip()
        if not reference:
            raise RuntimeError(f"PCB-MIC KiCad BOM row has no Reference: {row}")
        if reference in by_ref:
            raise RuntimeError(f"PCB-MIC KiCad BOM duplicate reference: {reference}")
        by_ref[reference] = row
    return by_ref


def write_pcb_mic_manufacturing_bom(kicad_bom: Path, output: Path) -> None:
    native = _kicad_bom_components(kicad_bom)
    if set(native) != set(PCB_MIC_BOM_ITEMS):
        raise RuntimeError(
            "PCB-MIC KiCad BOM reference mismatch: "
            f"expected {sorted(PCB_MIC_BOM_ITEMS)}, got {sorted(native)}"
        )

    with PRODUCTION_BOM.open(encoding="utf-8-sig", newline="") as stream:
        production_rows = list(csv.DictReader(stream))
    production = {row["Item_ID"]: row for row in production_rows}

    materialized: list[dict[str, str]] = []
    for reference, item_id in PCB_MIC_BOM_ITEMS.items():
        native_row = native[reference]
        expected_value, expected_footprint = PCB_MIC_NATIVE_COMPONENTS[reference]
        if native_row.get("Value") != expected_value:
            raise RuntimeError(
                f"PCB-MIC {reference} KiCad BOM value {native_row.get('Value')!r} "
                f"!= {expected_value!r}"
            )
        if native_row.get("Footprint") != expected_footprint:
            raise RuntimeError(
                f"PCB-MIC {reference} KiCad BOM footprint {native_row.get('Footprint')!r} "
                f"!= {expected_footprint!r}"
            )
        if item_id not in production:
            raise RuntimeError(f"PCB-MIC production BOM item missing: {item_id}")
        authority = production[item_id]
        if authority.get("Assembly") != "PCB-MIC" or authority.get("Population") != "FITTED":
            raise RuntimeError(f"PCB-MIC production BOM authority invalid for {item_id}")
        materialized.append({
            "Reference": reference,
            "Quantity_per_board": "1",
            "Native_Value": expected_value,
            "Native_Footprint": expected_footprint,
            "Manufacturer": authority["Manufacturer"],
            "MPN": authority["MPN"],
            "Package": authority["Package"],
            "Procurement_Value": authority["Value"],
            "Qty_per_station": authority["Qty_per_station"],
            "Population": authority["Population"],
            "Source_Item_ID": item_id,
            "Source_BOM": str(PRODUCTION_BOM.relative_to(ROOT)),
        })

    fieldnames = list(materialized[0])
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)
    print("PCB-MIC: KiCad/native-to-procurement BOM materialization PASS: 4 fitted refs")


def validate_schematic(cli: str, name: str, sch: Path) -> tuple[bool, str]:
    out = ART / name
    out.mkdir(parents=True, exist_ok=True)
    rc = run(
        [cli, "sch", "erc", "--format", "json", "--severity-all", "--exit-code-violations",
         "-o", str(out / "erc.json"), str(sch)],
        check=False,
    )
    pdf_rc = run(
        [cli, "sch", "export", "pdf", "-o", str(out / f"{name}_schematic.pdf"), str(sch)],
        check=False,
    )
    bom_rc = 0
    bom_validation_ok = True
    if name == "PCB-MIC":
        kicad_bom = out / f"{name}_kicad_bom.csv"
        bom_rc = run(
            [
                cli, "sch", "export", "bom",
                "-o", str(kicad_bom),
                "--fields", "Reference,Value,Footprint,${QUANTITY}",
                "--labels", "Reference,Value,Footprint,Quantity",
                "--group-by", "Reference",
                "--sort-field", "Reference",
                "--sort-asc",
                "--exclude-dnp",
                str(sch),
            ],
            check=False,
        )
        if bom_rc == 0:
            try:
                write_pcb_mic_manufacturing_bom(
                    kicad_bom, out / f"{name}_manufacturing_bom.csv"
                )
            except Exception as exc:
                bom_validation_ok = False
                print(f"PCB-MIC: BOM materialization failure: {exc}", flush=True)

    if rc == 0 and pdf_rc == 0 and bom_rc == 0 and bom_validation_ok:
        review_state = "REVIEW_A_SIGNED" if review_a_complete(name) else "REVIEW_A_PENDING"
        deliverables = "ERC_PDF_BOM" if name == "PCB-MIC" else "ERC_PDF"
        return True, f"CLI_{deliverables}_PASS_{review_state}_REVIEW_B_PENDING"
    return False, (
        f"CLI_ERC_rc{rc}_PDF_rc{pdf_rc}_BOM_rc{bom_rc}_"
        f"BOM_VALID_{int(bom_validation_ok)}"
    )


def apply_fabrication_metadata(name: str, pcb: Path, out: Path, gerber: Path) -> None:
    metadata_path = pcb.parent / "fabrication_metadata.json"
    if not metadata_path.is_file():
        raise RuntimeError(f"{name}: missing controlled fabrication metadata: {metadata_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = {
        "board", "revision", "material", "surface_finish", "board_thickness_mm",
        "copper_layers", "status", "authority",
    }
    missing = sorted(required - set(metadata))
    if missing:
        raise RuntimeError(f"{name}: fabrication metadata fields missing: {missing}")
    if metadata["board"] != name:
        raise RuntimeError(f"{name}: fabrication metadata board mismatch: {metadata['board']}")

    job_path = gerber / f"{name}-job.gbrjob"
    if not job_path.is_file():
        raise RuntimeError(f"{name}: KiCad Gerber job file missing: {job_path}")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    specs = job.get("GeneralSpecs", {})

    actual_thickness = float(specs.get("BoardThickness", -1.0))
    expected_thickness = float(metadata["board_thickness_mm"])
    if abs(actual_thickness - expected_thickness) > 0.001:
        raise RuntimeError(
            f"{name}: Gerber-job thickness {actual_thickness} != controlled {expected_thickness} mm"
        )
    actual_layers = int(specs.get("LayerNumber", -1))
    expected_layers = int(metadata["copper_layers"])
    if actual_layers != expected_layers:
        raise RuntimeError(
            f"{name}: Gerber-job copper layers {actual_layers} != controlled {expected_layers}"
        )

    wanted_material = str(metadata["material"]).replace("-", "").lower()
    dielectric_materials = [
        str(item.get("Material", "")).replace("-", "").lower()
        for item in job.get("MaterialStackup", [])
        if item.get("Type") == "Dielectric"
    ]
    if wanted_material and not any(wanted_material in value for value in dielectric_materials):
        raise RuntimeError(
            f"{name}: controlled dielectric {metadata['material']} absent from "
            f"KiCad Gerber stackup {dielectric_materials}"
        )

    project_id = specs.setdefault("ProjectId", {})
    project_id["Revision"] = str(metadata["revision"])
    specs["Finish"] = str(metadata["surface_finish"])
    job["GeneralSpecs"] = specs
    job_path.write_text(json.dumps(job, indent=2) + "\n", encoding="utf-8")

    reread = json.loads(job_path.read_text(encoding="utf-8"))
    reread_specs = reread["GeneralSpecs"]
    if reread_specs["ProjectId"].get("Revision") != str(metadata["revision"]):
        raise RuntimeError(f"{name}: Gerber-job revision verification failed")
    if reread_specs.get("Finish") != str(metadata["surface_finish"]):
        raise RuntimeError(f"{name}: Gerber-job finish verification failed")

    controlled_copy = out / f"{name}_fabrication_metadata.json"
    shutil.copy2(metadata_path, controlled_copy)
    print(
        f"{name}: fabrication metadata PASS: Rev {metadata['revision']}, "
        f"{metadata['surface_finish']}, {expected_thickness:.3f} mm, "
        f"{expected_layers} layers, {metadata['material']}"
    )


def validate_position_export(name: str, pos_path: Path) -> None:
    with pos_path.open(encoding="utf-8-sig", newline="") as f:
        records = list(csv.DictReader(f))
    refs = [row.get("Ref", "") for row in records]
    if name == "PCB-MIC":
        expected = {"C1", "J1", "MK1", "R1"}
        actual = set(refs)
        if actual != expected:
            raise RuntimeError(
                f"PCB-MIC PnP reference set mismatch: expected {sorted(expected)}, got {sorted(actual)}"
            )
        if "H1" in actual or "H2" in actual:
            raise RuntimeError("PCB-MIC mechanical mounting holes leaked into PnP")
    print(f"{name}: PnP export verification PASS: refs={refs}")


def normalize_assembly_fabrication_pdf(
    name: str, export_path: Path, final_path: Path,
) -> None:
    """Normalize KiCad 9.0.x multipage PDF output across CLI packaging variants."""
    if export_path.is_file():
        generated = export_path
    elif export_path.is_dir():
        candidates = sorted(export_path.glob("*.pdf"))
        if len(candidates) != 1:
            raise RuntimeError(
                f"{name}: expected one multipage PDF in {export_path}, got {candidates}"
            )
        generated = candidates[0]
    else:
        raise RuntimeError(f"{name}: assembly/fabrication PDF export is missing: {export_path}")

    with generated.open("rb") as stream:
        header = stream.read(5)
    if generated.stat().st_size <= 1000 or header != b"%PDF-":
        raise RuntimeError(f"{name}: assembly/fabrication PDF is invalid: {generated}")
    generated.replace(final_path)
    if export_path.is_dir():
        export_path.rmdir()
    print(f"{name}: assembly/fabrication multipage PDF PASS: {final_path.name}")


def validate_pcb(cli: str, name: str, pcb: Path) -> tuple[bool, str]:
    out = ART / name
    out.mkdir(parents=True, exist_ok=True)
    rc = run(
        [cli, "pcb", "drc", "--format", "json", "--severity-all", "--exit-code-violations",
         "-o", str(out / "drc.json"), str(pcb)],
        check=False,
    )
    if rc != 0:
        return False, f"CLI_DRC_FAIL_rc{rc}_NO_FAB_EXPORT"

    gerber = out / "gerber"
    gerber.mkdir(exist_ok=True)
    drill = out / "drill"
    drill.mkdir(exist_ok=True)
    pos_path = out / f"{name}_pos.csv"

    try:
        cam_pcb = prepare_cam_source(name, pcb, out)
    except Exception as exc:
        print(f"{name}: controlled CAM source failure: {exc}", flush=True)
        return False, f"CLI_DRC_PASS_CAM_SOURCE_FAIL_{type(exc).__name__}"

    # STEP is intentionally board-only at this gate. Controlled component 3D-model
    # links are a separate Review-B item; exporting a board-only STEP is sufficient for
    # mechanical fit/tolerance work without pretending secondary reference CAD is released.
    export_commands = [
        [cli, "pcb", "export", "gerbers", "-o", str(gerber), "--board-plot-params", str(cam_pcb)],
        [cli, "pcb", "export", "drill", "-o", str(drill), "--format", "excellon", "--generate-map", str(pcb)],
        [cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
         "-o", str(pos_path), str(pcb)],
        [cli, "pcb", "export", "ipcd356", "-o", str(out / f"{name}.d356"), str(pcb)],
        [cli, "pcb", "export", "step", "--board-only", "--force",
         "-o", str(out / f"{name}_board.step"), str(pcb)],
    ]
    assembly_pdf_export: Path | None = None
    assembly_pdf_final: Path | None = None
    if name == "PCB-MIC":
        assembly_pdf_export = out / "assembly-fabrication-pdf-export"
        assembly_pdf_final = out / f"{name}_assembly_fabrication.pdf"
        export_commands.append([
            cli, "pcb", "export", "pdf",
            "-o", str(assembly_pdf_export),
            "--layers", "F.Fab,B.Fab,F.Silkscreen,B.Silkscreen",
            "--common-layers", "Edge.Cuts",
            "--mode-multipage",
            "--black-and-white",
            "--sketch-pads-on-fab-layers",
            "--include-border-title",
            "--drill-shape-opt", "2",
            str(pcb),
        ])
    export_rcs = [run(cmd, check=False) for cmd in export_commands]
    if any(export_rcs):
        return False, f"CLI_DRC_PASS_EXPORT_FAIL_{export_rcs}"

    try:
        if assembly_pdf_export is not None and assembly_pdf_final is not None:
            normalize_assembly_fabrication_pdf(
                name, assembly_pdf_export, assembly_pdf_final
            )
        apply_fabrication_metadata(name, pcb, out, gerber)
        validate_position_export(name, pos_path)
    except Exception as exc:
        print(f"{name}: fabrication metadata/PnP verification failure: {exc}", flush=True)
        return False, f"CLI_DRC_EXPORT_METADATA_FAIL_{type(exc).__name__}"

    return True, "CLI_DRC_FAB_EXPORT_METADATA_PASS_REVIEW_B_PENDING"


def artifact_files() -> list[Path]:
    return [
        p for p in sorted(ART.rglob("*"))
        if p.is_file() and p.name != "sha256_manifest.json"
    ]


def write_manifest() -> None:
    manifest = [
        {
            "path": str(p.relative_to(ART)),
            "sha256": sha256(p),
            "bytes": p.stat().st_size,
        }
        for p in artifact_files()
    ]
    (ART / "sha256_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def verify_manifest() -> None:
    manifest_path = ART / "sha256_manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_path = {str(rec["path"]): rec for rec in records}
    actual = {str(p.relative_to(ART)): p for p in artifact_files()}

    if set(by_path) != set(actual):
        missing = sorted(set(actual) - set(by_path))
        stale = sorted(set(by_path) - set(actual))
        raise RuntimeError(
            f"artifact manifest file-set mismatch: missing_records={missing} stale_records={stale}"
        )

    failures = []
    for rel, p in actual.items():
        rec = by_path[rel]
        current_hash = sha256(p)
        current_bytes = p.stat().st_size
        if rec.get("sha256") != current_hash or rec.get("bytes") != current_bytes:
            failures.append({
                "path": rel,
                "manifest_sha256": rec.get("sha256"),
                "actual_sha256": current_hash,
                "manifest_bytes": rec.get("bytes"),
                "actual_bytes": current_bytes,
            })
    if failures:
        raise RuntimeError(f"artifact SHA256 manifest verification failed: {failures}")
    print(f"SHA256 artifact manifest verification PASS: {len(actual)} files")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="require all three complete SCH/PCB/PRO native sets")
    ap.add_argument("--run-cli", action="store_true", help="run CLI checks for every available native PCB/SCH")
    args = ap.parse_args()

    ART.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "configuration": "EVT-PRE-20 Rev.A",
        "boards": {},
        "release": "BLOCKED_NOT_FOR_MANUFACTURE",
    }
    all_missing: list[str] = []
    complete_sets: list[str] = []
    cli_failures: list[str] = []

    for name in BOARDS:
        p = paths(name)
        missing = [str(x.relative_to(ROOT)) for x in p.values() if not x.is_file()]
        all_missing.extend(missing)
        if not missing:
            complete_sets.append(name)
        report["boards"][name] = {
            "source_files": {k: str(x.relative_to(ROOT)) for k, x in p.items()},
            "missing": missing,
            "pcb_state": "SOURCE_PRESENT_PENDING_CLI" if p["pcb"].is_file() else "MISSING",
            "sch_state": "SOURCE_PRESENT_PENDING_CLI" if p["sch"].is_file() else "MISSING",
            "project_state": "PRESENT" if p["pro"].is_file() else "MISSING",
        }

    if args.run_cli:
        cli = shutil.which("kicad-cli")
        if not cli:
            raise SystemExit("kicad-cli not found")
        run([cli, "version"])
        for name in BOARDS:
            p = paths(name)
            if p["pcb"].is_file():
                placement_audit = placement_candidate_audit(name)
                if placement_audit:
                    run(["python", placement_audit])
                    report["boards"][name]["pcb_state"] = \
                        "PLACEMENT_CANDIDATE_AUDIT_PASS_DRC_AND_FAB_EXPORT_PROHIBITED"
                else:
                    ok, state = validate_pcb(cli, name, p["pcb"])
                    report["boards"][name]["pcb_state"] = state
                    if not ok:
                        cli_failures.append(f"{name}: {state}")
            if p["sch"].is_file():
                ok, state = validate_schematic(cli, name, p["sch"])
                report["boards"][name]["sch_state"] = state
                if not ok:
                    cli_failures.append(f"{name}: {state}")

        mic = report["boards"]["PCB-MIC"]
        mic_pcb_ok = str(mic["pcb_state"]).startswith("CLI_DRC_FAB_EXPORT_METADATA_PASS")
        mic_sch_ok = str(mic["sch_state"]).startswith("CLI_ERC_PDF_BOM_PASS")
        if mic_pcb_ok and mic_sch_ok:
            audit_output = ART / "PCB-MIC" / "review_b_preflight_audit.json"
            audit_rc = run(
                [
                    sys.executable,
                    str(PCB_MIC_REVIEW_B_AUDIT.relative_to(ROOT)),
                    "--artifact-root", str(ART / "PCB-MIC"),
                    "--output", str(audit_output),
                    "--commit-sha", git_head(),
                ],
                check=False,
            )
            if audit_rc == 0:
                mic["review_b_preflight_state"] = (
                    "PASS_INTERNAL_CAM_PREFLIGHT_REVIEW_B_REMAINS_OPEN"
                )
            else:
                mic["review_b_preflight_state"] = f"FAIL_rc{audit_rc}"
                cli_failures.append(f"PCB-MIC: REVIEW_B_PREFLIGHT_FAIL_rc{audit_rc}")
        else:
            mic["review_b_preflight_state"] = "NOT_RUN_PREREQUISITE_CLI_FAILURE"

    if not all_missing and not cli_failures:
        if all(review_a_complete(name) for name in BOARDS):
            report["release"] = (
                "ALL_NATIVE_SOURCES_AND_CLI_PASS_REVIEW_B_AND_MANUFACTURING_RELEASE_STILL_REQUIRED"
            )
        else:
            report["release"] = "ALL_NATIVE_SOURCES_AND_CLI_PASS_REVIEW_A_B_STILL_REQUIRED"
    else:
        if all_missing:
            report["missing"] = all_missing
        if cli_failures:
            report["cli_failures"] = cli_failures

    (ART / "native_gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if args.run_cli:
        write_manifest()
        verify_manifest()

    print("Complete native sets:", ", ".join(complete_sets) if complete_sets else "none")
    print(f"Overall release gate remains BLOCKED; {len(all_missing)} required source files missing")
    if cli_failures:
        print("Native CLI failures:")
        for failure in cli_failures:
            print("-", failure)

    if cli_failures:
        return 5
    if args.strict and all_missing:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
