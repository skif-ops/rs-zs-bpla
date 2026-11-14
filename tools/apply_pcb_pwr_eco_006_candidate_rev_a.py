#!/usr/bin/env python3
"""PCB-PWR ECO-006 candidate: DFM fixes accepted after Review B R2 (DFM-PWR-02 and DFM-PWR-03).

Run by .github/workflows/ci-apply.yml (docker available). Starts from the authoritative ECO-005 board
(SHA-256 pinned) and writes a candidate only; the authoritative board and library are not changed.

Delta (nothing else; checked line by line against the base):
  DFM-PWR-02  TestPoint_DFT_1.7mm_NoPaste solder-mask margin 0.20 -> 0.10 mm: the library footprint and
              the 10 placed pads TP1-TP10 (opening 2.1 -> 1.9 mm; 0.104 mm from the 3V8_MODEM track).
  DFM-PWR-03  every visible reference designator 0.8 / 0.12 mm -> 1.0 / 0.15 mm (JLCPCB legend minimum),
              re-placed 0.15 mm clear of every solder-mask opening (tools/pcb_pwr_eco_006_stage_rev_a.py).
Copper, placement, pads, nets, zones, outline and footprint graphics are unchanged (the board semantic
SHA-256, 842 trace items and 33 zones are asserted equal to the base).
Output: hardware/kicad/candidates/PCB-PWR-ECO-006/
  PCB-PWR_ECO_006_CANDIDATE_REV_A.kicad_pcb, TestPoint_DFT_1.7mm_NoPaste.kicad_mod (candidate library),
  REFS_REPORT.json, DRC.json (KiCad 9.0.9 with project rules and libraries), DFM_REGISTER.json
  (tools/apply_pcb_pwr_dfm_register_rev_a.py measurement of the candidate), SUMMARY.json
--check verifies SUMMARY.json against the candidate files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
MAIN_LIBS = ROOT / "hardware/kicad/native/PCB-MAIN/libs"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
BASE_SHA256 = "81f44a7068de6c8d7b3ae1a6951bc9d7a4bc6c2646cdbc4eccea4d9c79e35610"
LIB_NAME = "TestPoint_DFT_1.7mm_NoPaste.kicad_mod"
LIB = NATIVE / "libs/DioneyaPWR.pretty" / LIB_NAME
OUT = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-006"
STEM = "PCB-PWR_ECO_006_CANDIDATE_REV_A"
WORK_ROOT = ROOT / "build/eco006"
WORK = WORK_ROOT / "PCB-PWR"
MASK_OLD, MASK_NEW = "(solder_mask_margin 0.2)", "(solder_mask_margin 0.1)"
LIB_OLD, LIB_NEW = "(solder_mask_margin 0.20)", "(solder_mask_margin 0.10)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w",
                           KICAD_IMAGE, *argv], capture_output=True, text=True)


def deps() -> None:
    try:
        import kiutils  # noqa: F401
        import shapely  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "kiutils", "shapely>=2"], check=True)


def reference_blocks(lines: list[str]) -> list[bool]:
    """True for every line inside a footprint's (property "Reference" ...) block."""
    inside, flags, depth = False, [], 0
    for line in lines:
        if not inside and line.lstrip().startswith('(property "Reference"'):
            inside, depth = True, 0
        if inside:
            flags.append(True)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                inside = False
        else:
            flags.append(False)
    return flags


def delta_report(base: str, cand: str) -> dict:
    import difflib
    a, b = base.split("\n"), cand.split("\n")
    fa, fb = reference_blocks(a), reference_blocks(b)
    outside, mask_lines, ref_lines = [], 0, 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for k in range(i1, i2):
            if fa[k]:
                ref_lines += 1
            elif MASK_OLD in a[k]:
                mask_lines += 1
            else:
                outside.append(("-", k + 1, a[k].strip()[:120]))
        for k in range(j1, j2):
            if fb[k]:
                ref_lines += 1
            elif MASK_NEW in b[k]:
                pass
            else:
                outside.append(("+", k + 1, b[k].strip()[:120]))
    return {"changed_reference_lines": ref_lines, "changed_mask_lines": mask_lines, "outside_delta": outside[:40],
            "outside_delta_count": len(outside)}


def invariants(base_path: Path, cand_path: Path) -> dict:
    from kiutils.board import Board
    from audit_pcb_pwr_routing_authority_rev_a import semantic_board_sha256
    base, cand = Board.from_file(str(base_path)), Board.from_file(str(cand_path))
    same = lambda xs, ys: [x.to_sexpr() for x in xs] == [y.to_sexpr() for y in ys]  # noqa: E731
    return {"semantic_sha256_base": semantic_board_sha256(base), "semantic_sha256_candidate": semantic_board_sha256(cand),
            "trace_items": [len(base.traceItems), len(cand.traceItems)], "zones": [len(base.zones), len(cand.zones)],
            "trace_items_identical": same(base.traceItems, cand.traceItems),
            "zones_identical": same(base.zones, cand.zones),
            "tp_mask_margins": sorted({str(p.solderMaskMargin) for fp in cand.footprints for p in fp.pads
                                       if "TestPoint_DFT" in fp.libId})}


def generate() -> None:
    deps()
    assert sha256(BOARD) == BASE_SHA256, "authoritative PCB-PWR is not the ECO-005 board"
    shutil.rmtree(WORK_ROOT, ignore_errors=True)
    shutil.copytree(NATIVE, WORK)
    shutil.copytree(MAIN_LIBS, WORK_ROOT / "PCB-MAIN" / "libs")
    lib_text = LIB.read_text(encoding="utf-8")
    assert lib_text.count(LIB_OLD) == 1, "library TestPoint mask margin is not the reviewed 0.20 mm"
    (WORK / "libs/DioneyaPWR.pretty" / LIB_NAME).write_text(lib_text.replace(LIB_OLD, LIB_NEW), encoding="utf-8")
    base_text = BOARD.read_text(encoding="utf-8")
    assert base_text.count(MASK_OLD) == 10, "expected exactly the 10 TestPoint pads at 0.2 mm"
    masked = base_text.replace(MASK_OLD, MASK_NEW)
    (WORK / "PCB-PWR.kicad_pcb").write_text(masked, encoding="utf-8")
    rel = WORK.relative_to(ROOT)
    steps = {}
    try:
        steps["refs"] = docker("/usr/bin/python3", "tools/pcb_pwr_eco_006_stage_rev_a.py", "refs",
                               f"{rel}/PCB-PWR.kicad_pcb", f"{rel}/candidate.kicad_pcb", f"{rel}/refs.json")
        assert steps["refs"].returncode == 0, f"KiCad ECO-006 stage failed: {steps['refs'].stderr[-3000:]}"
        docker("chmod", "-R", "a+rwX", str(WORK_ROOT.relative_to(ROOT)))
        OUT.mkdir(parents=True, exist_ok=True)
        cand_path = OUT / f"{STEM}.kicad_pcb"
        shutil.copyfile(WORK / "candidate.kicad_pcb", cand_path)
        shutil.copyfile(WORK / "libs/DioneyaPWR.pretty" / LIB_NAME, OUT / LIB_NAME)
        shutil.copyfile(WORK / "refs.json", OUT / "REFS_REPORT.json")
        # DRC on the candidate with the project, rules and candidate libraries
        shutil.copyfile(cand_path, WORK / "PCB-PWR.kicad_pcb")
        steps["drc"] = docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                              "-o", f"{rel}/drc.json", f"{rel}/PCB-PWR.kicad_pcb")
        docker("chmod", "-R", "a+rwX", str(WORK_ROOT.relative_to(ROOT)))
        shutil.copyfile(WORK / "drc.json", OUT / "DRC.json")
        drc = json.loads((OUT / "DRC.json").read_text(encoding="utf-8"))
        by_type: dict = {}
        for violation in drc.get("violations", []):
            key = f"{violation['severity']}:{violation['type']}"
            by_type[key] = by_type.get(key, 0) + 1
        # DFM register of the candidate (same measurement as the R2 register)
        import apply_pcb_pwr_dfm_register_rev_a as dfm
        dfm.NATIVE, dfm.BOARD = WORK, WORK / "PCB-PWR.kicad_pcb"
        rows = dfm.measure(dfm.export())
        register = {"board_sha256": sha256(cand_path), "source": dfm.SOURCE,
                    "requirements": {k: {"value": v[0], "rule": v[1]} for k, v in dfm.REQ.items()},
                    "counts": {k: len(v) for k, v in sorted(rows.items())}, "measurements": dict(sorted(rows.items()))}
        (OUT / "DFM_REGISTER.json").write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    finally:
        docker("rm", "-rf", str(WORK_ROOT.relative_to(ROOT)))
        shutil.rmtree(WORK_ROOT, ignore_errors=True)
    cand_text = cand_path.read_text(encoding="utf-8")
    delta = delta_report(masked, cand_text)
    delta["changed_mask_lines"] = base_text.count(MASK_OLD)
    inv = invariants(BOARD, cand_path)
    refs_report = json.loads((OUT / "REFS_REPORT.json").read_text(encoding="utf-8"))
    summary = {
        "schema": "dioneya-pcb-pwr-eco-006-candidate-v1", "eco": "PCB-PWR ECO-006",
        "responds_to": "Review B R2.002 decisions: DFM-PWR-02 fix, DFM-PWR-03 fix (reference designators)",
        "base_sha256": BASE_SHA256, "candidate_sha256": sha256(cand_path),
        "library_base_sha256": sha256(LIB), "library_candidate_sha256": sha256(OUT / LIB_NAME),
        "delta": delta, "invariants": inv, "refs": {k: (len(v) if isinstance(v, list) else v) for k, v in refs_report.items()},
        "hidden_references": refs_report["hidden"],
        "drc": {"error_total": sum(n for k, n in by_type.items() if k.startswith("error:")),
                "unconnected_total": len(drc.get("unconnected_items", [])), "by_type": by_type},
        "dfm_counts": register["counts"],
        "steps": {k: {"rc": v.returncode, "stderr": v.stderr[-400:] if v.returncode else ""} for k, v in steps.items()},
        "manufacturing_release": False, "applied_to_authoritative_board": False,
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert delta["outside_delta_count"] == 0, f"candidate changes lines outside the declared delta: {delta['outside_delta']}"
    assert inv["semantic_sha256_base"] == inv["semantic_sha256_candidate"], "placement/pad/net semantics changed"
    assert inv["trace_items_identical"] and inv["zones_identical"], "copper changed"
    assert inv["tp_mask_margins"] == ["0.1"], f"TestPoint mask margins: {inv['tp_mask_margins']}"
    print(json.dumps({k: summary[k] for k in ("candidate_sha256", "delta", "refs", "drc", "dfm_counts")},
                     ensure_ascii=False)[:2500])


def check() -> None:
    summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["candidate_sha256"] == sha256(OUT / f"{STEM}.kicad_pcb"), "candidate differs from SUMMARY.json"
    assert summary["library_candidate_sha256"] == sha256(OUT / LIB_NAME), "candidate library differs from SUMMARY.json"
    assert summary["delta"]["outside_delta_count"] == 0 and summary["drc"]["error_total"] == 0
    assert summary["drc"]["unconnected_total"] == 0
    print(f"PCB-PWR ECO-006 candidate: PASS {summary['candidate_sha256']} DRC {summary['drc']['by_type']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
