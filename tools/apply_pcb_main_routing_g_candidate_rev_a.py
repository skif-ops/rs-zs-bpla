#!/usr/bin/env python3
"""PCB-MAIN candidate G (ci-apply): the authoritative (003) board + L1 at the SMPS pins + the global session G.

Built deterministically: the authoritative board with L1 moved to (53.75, 40.75, 180) (one position line) plus the
new copper of session G (PCB-MAIN_ROUTED_G.ses: wires/vias not marked fix, locked/emptied nets excluded, nets
listed in DRC_REJECTED_NETS_G.json excluded). Textual proof: removing the added lines and restoring the L1 line gives
the authoritative board. KiCad 9.0.9 fills, runs DRC on the authoritative board and the candidate, dumps the fills;
the reference map is written. Output: hardware/kicad/candidates/PCB-ROUTING-G/. --check verifies reproducibility.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as g2  # noqa: E402
import apply_pcb_routing_global_g_rev_a as arg  # noqa: E402  (sets up the pinned routing modules)
import apply_pcb_main_routing_004_candidate_rev_a as c4  # noqa: E402
import apply_pcb_main_routing_005_candidate_rev_a as c5  # noqa: E402
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE_SHA256 = c4.BASE_SHA256
OUT = arg.OUT
STEM = "PCB-MAIN_ROUTING_G_CANDIDATE_REV_A"
REJECTED_G = OUT / "DRC_REJECTED_NETS_G.json"
NAMESPACE = uuid.UUID("9e8d7c6b-0a0b-5c0d-8e0f-0a0b1c2d3e4f")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(base_text: str) -> tuple[str, dict]:
    info = json.loads(arg.LOG.read_text(encoding="utf-8"))
    assert info["session_sha256"] == sha256(arg.SES), "session G differs from AUTOROUTE_G.json"
    stage = c5.move_l1(base_text)
    assert stage.replace(c5.L1_AT_NEW, c5.L1_AT_OLD) == base_text, "L1 move changed more than its position line"
    rejected = set(json.loads(REJECTED_G.read_text(encoding="utf-8"))["nets"]) if REJECTED_G.is_file() else set()
    copper = c4.session_copy(arg.SES.read_text(encoding="utf-8"), set(info["prep"]["not_autorouted"]) | rejected)
    number = {name: int(num) for num, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', stage, re.M)}
    seg_lines, via_lines = [], []
    for net in sorted(copper):
        n = number[net]
        for layer, width, pts in copper[net]["wires"]:
            for a, b in zip(pts, pts[1:]):
                if a == b:
                    continue
                key = f"seg|{net}|{layer}|{a[0]:.4f}|{a[1]:.4f}|{b[0]:.4f}|{b[1]:.4f}"
                seg_lines.append(f'  (segment (start {a[0]:.4f} {a[1]:.4f}) (end {b[0]:.4f} {b[1]:.4f}) (width {width}) '
                                 f'(layer "{layer}") (net {n}) (tstamp {uuid.uuid5(NAMESPACE, key)}))')
        for x, y in copper[net]["vias"]:
            via_lines.append(f'  (via (at {x:.4f} {y:.4f}) (size {c4.VIA_SIZE}) (drill {c4.VIA_DRILL}) (layers "F.Cu" "B.Cu") '
                             f'(net {n}) (tstamp {uuid.uuid5(NAMESPACE, f"via|{net}|{x:.4f}|{y:.4f}")}))')
    lines = stage.split("\n")
    last_via = max(i for i, line in enumerate(lines) if line.startswith("  (via "))
    last_seg = max(i for i, line in enumerate(lines) if line.startswith("  (segment "))
    out = lines[:last_via + 1] + via_lines + lines[last_via + 1:]
    out = out[:last_seg + 1] + seg_lines + out[last_seg + 1:]
    added = set(seg_lines) | set(via_lines)
    assert "\n".join(line for line in out if line not in added) == stage, "candidate differs from the L1-moved base outside additions"
    spec = {"base": "003 board, L1 moved", "l1": [c5.L1_AT_OLD, c5.L1_AT_NEW], "nets": len(copper), "segments": len(seg_lines), "vias": len(via_lines),
            "by_layer": dict(Counter(layer for c in copper.values() for layer, _, pts in c["wires"]
                                     for _ in range(len(pts) - 1))),
            "session_sha256": info["session_sha256"], "drc_rejected": sorted(rejected)}
    return "\n".join(out), spec


def generate() -> None:
    g2.deps()
    assert sha256(BOARD) == BASE_SHA256, "authoritative PCB-MAIN is not the 003 board"
    candidate, spec = build(BOARD.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    cand = OUT / f"{STEM}.kicad_pcb"
    cand.write_text(candidate, encoding="utf-8")
    summary = {"schema": "dioneya-pcb-main-routing-g-candidate-v1", "base_board_sha256": BASE_SHA256,
               "candidate_sha256": sha256(cand), "delta": spec, "kicad_image": g2.KICAD_IMAGE,
               "manufacturing_release": False, "applied_to_authoritative_board": False}
    work = ROOT / "hardware/kicad/native/_rG_cand"
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(ROOT / "hardware/kicad/native/PCB-MAIN", work)
    try:
        rel = work.relative_to(ROOT)
        shutil.copyfile(BOARD, work / "base.kicad_pcb")
        shutil.copyfile(cand, work / "candidate.kicad_pcb")
        for tag in ("base", "candidate"):
            shutil.copyfile(work / "PCB-MAIN.kicad_pro", work / f"{tag}.kicad_pro")
        stage = "tools/pcb_main_ground_domain_002_stage_rev_a.py"
        steps = {}
        for tag in ("base", "candidate"):
            steps[f"fill_{tag}"] = g2.docker("/usr/bin/python3", stage, "fill", f"{rel}/{tag}.kicad_pcb", f"{rel}/{tag}.kicad_pcb")
            steps[f"drc_{tag}"] = g2.docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                                            "-o", f"{rel}/drc_{tag}.json", f"{rel}/{tag}.kicad_pcb")
            steps[f"dump_{tag}"] = g2.docker("/usr/bin/python3", stage, "dump", f"{rel}/{tag}.kicad_pcb", f"{rel}/fills_{tag}.json")
        g2.docker("chmod", "-R", "a+rwX", str(rel))
        summary["steps"] = {k: {"rc": v.returncode, "stderr": v.stderr[-400:] if v.returncode else ""} for k, v in steps.items()}
        reports = {t: json.loads((work / f"drc_{t}.json").read_text(encoding="utf-8")) for t in ("base", "candidate")}
        shutil.copyfile(work / "drc_candidate.json", OUT / "drc_candidate.json")
        (bfp, bunc), (cfp, cunc) = g2.drc_fingerprints(reports["base"]), g2.drc_fingerprints(reports["candidate"])
        new = sorted([list(k[:2]) + [list(k[2])] for k in cfp if cfp[k] > bfp.get(k, 0)])
        by_type = lambda fp: dict(sorted(Counter(f"{k[0]}:{k[1]}" for k in fp.elements()).items()))  # noqa: E731
        summary["drc"] = {"base": {"by_type": by_type(bfp), "unconnected": bunc},
                          "candidate": {"by_type": by_type(cfp), "unconnected": cunc},
                          "new_fingerprint_count": len(new), "new_errors": sum(1 for k in new if k[0] == "error"),
                          "new_fingerprints": new[:150]}
        fills = json.loads((work / "fills_candidate.json").read_text(encoding="utf-8"))
        board, domains = geo.load(cand)
        cmap = geo.continuity_map(board, domains, g2.filled_references(fills))
        (OUT / "REFERENCE_MAP.json").write_text(json.dumps(cmap, indent=1) + "\n", encoding="utf-8")
        summary["continuity_summary"] = {k: v["share"] for k, v in cmap["by_layer_domain"].items()}
    finally:
        g2.docker("rm", "-rf", str(work.relative_to(ROOT)))
        shutil.rmtree(work, ignore_errors=True)
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary.get(k) for k in ("candidate_sha256", "delta", "drc")}, default=str)[:3000])


def check() -> None:
    summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
    cand = OUT / f"{STEM}.kicad_pcb"
    assert summary["candidate_sha256"] == sha256(cand), "candidate differs from SUMMARY.json"
    if sha256(BOARD) == BASE_SHA256:
        text, _ = build(BOARD.read_text(encoding="utf-8"))
        assert text == cand.read_text(encoding="utf-8"), "candidate is not reproducible"
    print(f"PCB-MAIN routing G candidate: PASS {summary['candidate_sha256']}")


if __name__ == "__main__":
    check() if "--check" in sys.argv[1:] else generate()
