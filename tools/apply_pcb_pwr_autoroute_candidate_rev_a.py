#!/usr/bin/env python3
"""Generate the PCB-PWR autoroute candidate 011 (run by .github/workflows/ci-apply.yml).

Pipeline (the authoritative board is NOT modified):
1. copy native PCB-PWR board and project to a work directory; the project gets
   the net classes of the accepted 35 um routing basis
   (hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json);
2. KiCad 9.0.9 (pinned image) locks all accepted copper, adds the GND_PWR plane
   on In1.Cu and exports Specctra DSN;
3. Freerouting 2.4.1 (pinned SHA-256, headless) routes the open nets;
4. KiCad imports the session, refills zones, runs DRC;
5. candidate board, project, DRC report and SUMMARY.json are written to
   hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011/ for review.

--check verifies that the committed summary matches the committed candidate.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = "PCB-PWR"
NATIVE_DIR = ROOT / "hardware/kicad/native/PCB-PWR"
BASIS = ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
OUT_DIR = ROOT / "hardware/kicad/candidates/PCB-PWR-AUTOROUTE-011"
WORK = ROOT / "build/autoroute/PCB-PWR"
STEM = "PCB-PWR_AUTOROUTE_011_CANDIDATE_REV_A"
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
FREEROUTING_URL = "https://github.com/freerouting/freerouting/releases/download/v2.4.1/freerouting-2.4.1-linux-x64.zip"
FREEROUTING_SHA256 = "3ad5a956ab474b12f331d24195feadac90e8344b8e013c6a4ab26e203ce51519"
PLANES = [{"net": "GND_PWR", "layer": "In1.Cu", "inset_mm": 0.5}]
PASSES = 60


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], **kwargs) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)
    return result.stdout


def docker(*args: str) -> str:
    return run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE, *args])


def project_with_netclasses(source: Path) -> dict:
    project = json.loads(source.read_text(encoding="utf-8"))
    basis = json.loads(BASIS.read_text(encoding="utf-8"))
    template = {
        "bus_width": 12, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
        "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6,
    }
    classes = [dict(template, name="Default", clearance=0.2, track_width=0.25,
                    via_diameter=0.6, via_drill=0.3, priority=2147483647)]
    for index, numeric in enumerate(basis["numeric_classes"]):
        classes.append(dict(
            template,
            name=numeric["name"],
            clearance=numeric["clearance_mm"],
            track_width=numeric["selected_width_mm"],
            via_diameter=numeric.get("via_diameter_mm", 0.6),
            via_drill=numeric.get("via_drill_mm", 0.3),
            priority=index,
        ))
    patterns = [
        {"netclass": cls, "pattern": net}
        for cls, nets in basis["netclass_assignments"].items()
        for net in nets
    ]
    project["net_settings"] = {
        "classes": classes,
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": patterns,
    }
    return project


def freerouting() -> Path:
    cache = ROOT / "build/tools"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "freerouting-2.4.1-linux-x64.zip"
    if not archive.is_file():
        urllib.request.urlretrieve(FREEROUTING_URL, archive)
    assert sha256(archive) == FREEROUTING_SHA256, "Freerouting archive SHA-256 mismatch"
    target = cache / "freerouting"
    if not target.is_dir():
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(target)
    binary = next(target.glob("*/bin/freerouting"))
    binary.chmod(0o755)
    for helper in target.glob("*/lib/runtime/bin/*"):
        helper.chmod(0o755)
    return binary


def summarize(drc_path: Path, candidate: Path, native_sha: str, log_tail: str, stage: dict) -> dict:
    report = json.loads(drc_path.read_text(encoding="utf-8"))
    by_type = collections.Counter(
        (v["severity"], v["type"]) for v in report.get("violations", [])
    )
    unconnected_nets = collections.Counter()
    for item in report.get("unconnected_items", []):
        match = re.search(r"\[([^\]]+)\]", item["items"][0].get("description", ""))
        unconnected_nets[match.group(1) if match else "?"] += 1
    return {
        "schema": "dioneya-pcb-pwr-autoroute-candidate-v1",
        "status": "CANDIDATE_FOR_REVIEW_NOT_APPLIED",
        "native_board_sha256": native_sha,
        "candidate_sha256": sha256(candidate),
        "kicad_image": KICAD_IMAGE,
        "freerouting": {"url": FREEROUTING_URL, "sha256": FREEROUTING_SHA256, "passes": PASSES},
        "planes_added": PLANES,
        "stage": stage,
        "drc": {
            "errors": {t: n for (s, t), n in sorted(by_type.items()) if s == "error"},
            "warnings": {t: n for (s, t), n in sorted(by_type.items()) if s == "warning"},
            "error_total": sum(n for (s, _), n in by_type.items() if s == "error"),
            "unconnected_total": len(report.get("unconnected_items", [])),
            "unconnected_by_net": dict(sorted(unconnected_nets.items())),
        },
        "freerouting_log_tail": log_tail,
        "manufacturing_release": False,
    }


def generate() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    board = WORK / f"{STEM}.kicad_pcb"
    project = WORK / f"{STEM}.kicad_pro"
    native_board = NATIVE_DIR / f"{BOARD}.kicad_pcb"
    shutil.copy2(native_board, board)
    project.write_text(json.dumps(project_with_netclasses(NATIVE_DIR / f"{BOARD}.kicad_pro"), indent=2) + "\n",
                       encoding="utf-8")
    for extra in (f"{BOARD}.kicad_dru",):
        if (NATIVE_DIR / extra).is_file():
            shutil.copy2(NATIVE_DIR / extra, WORK / f"{STEM}.kicad_dru")
    rel = lambda path: str(path.relative_to(ROOT))  # noqa: E731
    dsn, ses = WORK / f"{STEM}.dsn", WORK / f"{STEM}.ses"
    exported = docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "export", rel(board), rel(dsn), json.dumps(PLANES))
    binary = freerouting()
    env = dict(os.environ, JAVA_TOOL_OPTIONS="-Xmx3g")
    routed = subprocess.run(
        [str(binary), "--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true",
         "-de", str(dsn), "-do", str(ses), "-mp", str(PASSES)],
        capture_output=True, text=True, env=env, timeout=3000,
    )
    log_tail = "\n".join((routed.stdout + routed.stderr).splitlines()[-40:])
    assert ses.is_file(), "Freerouting produced no session:\n" + log_tail
    candidate = WORK / f"{STEM}.routed.kicad_pcb"
    imported = docker("/usr/bin/python3", "tools/kicad_autoroute_stage_rev_a.py", "import", rel(board), rel(ses), rel(candidate))
    shutil.move(candidate, board)
    drc = WORK / "drc.json"
    docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", rel(drc), rel(board))
    stage = {"export": json.loads(exported.strip().splitlines()[-1]), "import": json.loads(imported.strip().splitlines()[-1])}
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    for source in (board, project, drc):
        shutil.copy2(source, OUT_DIR / source.name)
    summary = summarize(OUT_DIR / "drc.json", OUT_DIR / board.name, sha256(native_board), log_tail, stage)
    (OUT_DIR / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary["drc"], ensure_ascii=False))


def generate_reporting_failures() -> None:
    """Runner logs are not visible to the reviewer: a failure is written to
    OUT_DIR/FAILURE.json (traceback and process output) and committed instead."""
    import traceback

    try:
        generate()
    except Exception as error:  # noqa: BLE001
        detail = {"error": repr(error), "traceback": traceback.format_exc()}
        if isinstance(error, subprocess.CalledProcessError):
            detail["cmd"] = error.cmd
            detail["stdout_tail"] = (error.stdout or "")[-4000:]
            detail["stderr_tail"] = (error.stderr or "")[-4000:]
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        OUT_DIR.mkdir(parents=True)
        (OUT_DIR / "FAILURE.json").write_text(json.dumps(detail, indent=2, default=str) + "\n", encoding="utf-8")
        print("autoroute failed; FAILURE.json written")


def check() -> None:
    if (OUT_DIR / "FAILURE.json").is_file():
        print("PCB-PWR autoroute candidate 011: FAILURE report present")
        return
    summary = json.loads((OUT_DIR / "SUMMARY.json").read_text(encoding="utf-8"))
    candidate = OUT_DIR / f"{STEM}.kicad_pcb"
    assert candidate.is_file() and sha256(candidate) == summary["candidate_sha256"], "candidate/summary mismatch"
    assert (OUT_DIR / "drc.json").is_file(), "DRC report missing"
    print(f"PCB-PWR autoroute candidate 011: PRESENT {summary['candidate_sha256']} "
          f"errors={summary['drc']['error_total']} unconnected={summary['drc']['unconnected_total']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate_reporting_failures()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
