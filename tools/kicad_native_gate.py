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
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "hardware" / "kicad" / "native"
ART = ROOT / "artifacts" / "kicad-native"
BOARDS = ("PCB-MAIN", "PCB-MIC", "PCB-PWR")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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
    if rc == 0 and pdf_rc == 0:
        return True, "CLI_ERC_PDF_PASS_REVIEW_A_PENDING"
    return False, f"CLI_ERC_FAIL_rc{rc}_PDF_rc{pdf_rc}"


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
            f"{name}: controlled dielectric {metadata['material']} absent from KiCad Gerber stackup {dielectric_materials}"
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

    # STEP is intentionally board-only at this gate. Controlled component 3D-model
    # links are a separate Review-B item; exporting a board-only STEP is sufficient for
    # mechanical fit/tolerance work without pretending secondary reference CAD is released.
    export_commands = [
        [cli, "pcb", "export", "gerbers", "-o", str(gerber), "--board-plot-params", str(pcb)],
        [cli, "pcb", "export", "drill", "-o", str(drill), "--format", "excellon", "--generate-map", str(pcb)],
        [cli, "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
         "-o", str(pos_path), str(pcb)],
        [cli, "pcb", "export", "ipcd356", "-o", str(out / f"{name}.d356"), str(pcb)],
        [cli, "pcb", "export", "step", "--board-only", "--force",
         "-o", str(out / f"{name}_board.step"), str(pcb)],
    ]
    export_rcs = [run(cmd, check=False) for cmd in export_commands]
    if any(export_rcs):
        return False, f"CLI_DRC_PASS_EXPORT_FAIL_{export_rcs}"

    try:
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
                ok, state = validate_pcb(cli, name, p["pcb"])
                report["boards"][name]["pcb_state"] = state
                if not ok:
                    cli_failures.append(f"{name}: {state}")
            if p["sch"].is_file():
                ok, state = validate_schematic(cli, name, p["sch"])
                report["boards"][name]["sch_state"] = state
                if not ok:
                    cli_failures.append(f"{name}: {state}")

    if not all_missing and not cli_failures:
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
