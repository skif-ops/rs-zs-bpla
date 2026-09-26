#!/usr/bin/env python3
"""PCB-MAIN candidate 004 (ci-apply): the Freerouting session applied to the authoritative board, KiCad-checked.

Inputs: the authoritative board (SHA-256 pinned: the applied 003 board) and the session
hardware/kicad/candidates/PCB-ROUTING-004/PCB-MAIN_ROUTED.ses of step 2 (its SHA-256 as recorded in AUTOROUTE.json).
Only new copper is taken from the session: wires and vias the router did not mark `fix` (the existing copper was
fixed in the router input), and none of the nets that were not autorouted (grounds, RF, USB, SMPS_SW). The session
units are 0.1 um with the y axis reversed.
The candidate is the authoritative board text plus one segment line per path step and one via line per via (textual
proof: removing the added lines gives the base). KiCad 9.0.9 then fills, runs DRC on base and candidate and dumps
the filled references; REFERENCE_MAP.json gives, per rerouted net and layer, the share over its own ground domain.
Output: hardware/kicad/candidates/PCB-ROUTING-004/ (candidate, SUMMARY.json, REFERENCE_MAP.json, DRC).
--check verifies SUMMARY.json and the reproducibility of the candidate from base + session.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as g2  # noqa: E402
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE_SHA256 = "30c6c93e5afbbc0888ed7c7e8693af6c6f0c7df8f5c4525e02c6d5a4c47b8739"
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-004"
SES = OUT / "PCB-MAIN_ROUTED.ses"
AUTOROUTE = OUT / "AUTOROUTE.json"
STEM = "PCB-MAIN_ROUTING_004_CANDIDATE_REV_A"
NAMESPACE = uuid.UUID("7d1e2c3b-4a5f-5e6d-8c9b-004a1b2c3d4e")
VIA_SIZE, VIA_DRILL = 0.5, 0.3
LAYERS = {"F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"}
# VCORE_1V1 is routed from L1, which 005 moves to the SMPS pins (46/49) of U1: its autorouted copper is left out
DEFERRED = {"VCORE_1V1"}
# nets whose autorouted copper failed KiCad DRC in the first candidate (e22680dc): the router misplaced the pads of
# the back-side test connectors (TP_EOL, TP_BLE_SWD, TP_MCU_SWD, TP_CELL_USB, TP_CELL_DBG) and of R62/FB1/L1; their
# new copper is left out whole and the connections stay open for the next routing step
REJECTED = OUT / "DRC_REJECTED_NETS.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sexp(text: str):
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack, cur = [], []
    for tok in tokens:
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            done, cur = cur, stack.pop()
            cur.append(done)
        else:
            cur.append(tok[1:-1] if tok.startswith('"') else tok)
    return cur[0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def session_copy(text: str, skip: set) -> dict:
    """{net: {"wires": [(layer, width_mm, [(x, y), ...])], "vias": [(x, y)]}} of the new copper."""
    root = sexp(text)
    routes = find(root, "routes")[0]
    res = find(routes, "resolution")[0]
    assert res[1] == "um", res
    scale = 1000.0 * float(res[2])  # units per mm
    out = {}
    for net in find(find(routes, "network_out")[0], "net"):
        name = net[1]
        if name in skip:
            continue
        entry = {"wires": [], "vias": []}
        for wire in find(net, "wire"):
            if any(t[1] == "fix" for t in find(wire, "type")):
                continue
            path = find(wire, "path")[0]
            layer, width = path[1], float(path[2]) / scale
            assert layer in LAYERS, layer
            nums = [float(v) for v in path[3:] if not isinstance(v, list)]
            pts = [(round(nums[i] / scale, 4), round(-nums[i + 1] / scale, 4)) for i in range(0, len(nums) - 1, 2)]
            entry["wires"].append((layer, round(width, 4), pts))
        for via in find(net, "via"):
            if any(t[1] == "fix" for t in find(via, "type")):
                continue
            x, y = float(via[2]), float(via[3])
            entry["vias"].append((round(x / scale, 4), round(-y / scale, 4)))
        if entry["wires"] or entry["vias"]:
            out[name] = entry
    return out


def build(base_text: str) -> tuple[str, dict]:
    info = json.loads(AUTOROUTE.read_text(encoding="utf-8"))
    assert info["session_sha256"] == sha256(SES), "session differs from the one recorded by step 2"
    rejected = set(json.loads(REJECTED.read_text(encoding="utf-8"))["nets"])
    skip = set(info["prep"]["not_autorouted"]) | DEFERRED | rejected
    copper = session_copy(SES.read_text(encoding="utf-8"), skip)
    number = {name: int(num) for num, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', base_text, re.M)}
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
            via_lines.append(f'  (via (at {x:.4f} {y:.4f}) (size {VIA_SIZE}) (drill {VIA_DRILL}) (layers "F.Cu" "B.Cu") '
                             f'(net {n}) (tstamp {uuid.uuid5(NAMESPACE, f"via|{net}|{x:.4f}|{y:.4f}")}))')
    lines = base_text.split("\n")
    last_via = max(i for i, line in enumerate(lines) if line.startswith("  (via "))
    last_seg = max(i for i, line in enumerate(lines) if line.startswith("  (segment "))
    assert last_seg < last_via
    out = lines[:last_via + 1] + via_lines + lines[last_via + 1:]
    out = out[:last_seg + 1] + seg_lines + out[last_seg + 1:]
    added = set(seg_lines) | set(via_lines)
    assert [line for line in out if line not in added] == lines, "candidate differs from the base outside additions"
    spec = {"nets": len(copper), "segments": len(seg_lines), "vias": len(via_lines),
            "by_layer": dict(Counter(layer for c in copper.values() for layer, _, pts in c["wires"]
                                     for _ in range(len(pts) - 1))),
            "session_sha256": info["session_sha256"], "not_autorouted": sorted(set(info["prep"]["not_autorouted"])),
            "deferred_to_005": sorted(DEFERRED), "drc_rejected": sorted(rejected)}
    return "\n".join(out), spec


def generate() -> None:
    g2.deps()
    assert sha256(BOARD) == BASE_SHA256, "authoritative PCB-MAIN is not the 003 board"
    candidate, spec = build(BOARD.read_text(encoding="utf-8"))
    cand = OUT / f"{STEM}.kicad_pcb"
    cand.write_text(candidate, encoding="utf-8")
    summary = {"schema": "dioneya-pcb-main-routing-004-candidate-v1", "base_board_sha256": BASE_SHA256,
               "candidate_sha256": sha256(cand), "delta": spec, "kicad_image": g2.KICAD_IMAGE,
               "manufacturing_release": False, "applied_to_authoritative_board": False}
    work = ROOT / "hardware/kicad/native/_r004_cand"
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
    print(f"PCB-MAIN routing 004 candidate: PASS {summary['candidate_sha256']}")


if __name__ == "__main__":
    check() if "--check" in sys.argv[1:] else generate()
