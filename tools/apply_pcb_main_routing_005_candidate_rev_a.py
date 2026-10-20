#!/usr/bin/env python3
"""PCB-MAIN candidate 005 (ci-apply): candidate 004 + L1 at the SMPS pins + the third Freerouting session.

Built from the authoritative (003) board, deterministically:
1. candidate 004 (tools/apply_pcb_main_routing_004_candidate_rev_a.build) without the new copper of the two nets
   ripped for the L1 site (tools/apply_pcb_routing_005_autoroute_rev_a.RIPPED);
2. L1 moves to (53.75, 40.75), rotation 180 kept (footprint position line only; pads are relative);
3. the new copper of session C (PCB-MAIN_ROUTED_C.ses: wires/vias not marked fix, locked/emptied nets excluded,
   nets listed in DRC_REJECTED_NETS_C.json excluded).
Textual proof: the candidate minus the added lines, with the L1 line restored and the ripped lines re-added, is
candidate 004. KiCad 9.0.9 fills, runs DRC on the authoritative board and the candidate, dumps the fills; the
reference map is written. Output: hardware/kicad/candidates/PCB-ROUTING-005/. --check verifies reproducibility.
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
import apply_pcb_main_routing_004_candidate_rev_a as c4  # noqa: E402
import apply_pcb_routing_005_autoroute_rev_a as ar5  # noqa: E402
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

BOARD = c4.BOARD
BASE_SHA256 = c4.BASE_SHA256
OUT = ar5.OUT
STEM = "PCB-MAIN_ROUTING_005_CANDIDATE_REV_A"
REJECTED_C = OUT / "DRC_REJECTED_NETS_C.json"
NAMESPACE = uuid.UUID("5a2b3c4d-005e-5f6a-8b9c-005a1b2c3d4e")
L1_AT_OLD, L1_AT_NEW = "(at 52 19.75 180)", "(at 53.75 40.75 180)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_004(base_text: str, without: set) -> str:
    saved = set(c4.DEFERRED)
    c4.DEFERRED |= without
    try:
        return c4.build(base_text)[0]
    finally:
        c4.DEFERRED.clear()
        c4.DEFERRED |= saved


def move_l1(text: str) -> str:
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if line.startswith("  (footprint ")]
    for i in starts:
        j = i
        while not lines[j].startswith("  )"):
            if '(fp_text reference "L1"' in lines[j]:
                for k in range(i, i + 6):
                    if lines[k].strip() == L1_AT_OLD:
                        lines[k] = lines[k].replace(L1_AT_OLD, L1_AT_NEW)
                        return "\n".join(lines)
                raise AssertionError("L1 position line not found")
            j += 1
    raise AssertionError("L1 not found")


def build(base_text: str) -> tuple[str, dict]:
    info = json.loads(ar5.LOG.read_text(encoding="utf-8"))
    assert info["session_sha256"] == sha256(ar5.SES), "session C differs from AUTOROUTE_C.json"
    full_004 = text_004(base_text, set())
    stage = move_l1(text_004(base_text, set(ar5.RIPPED)))
    rejected = set(json.loads(REJECTED_C.read_text(encoding="utf-8"))["nets"]) if REJECTED_C.is_file() else set()
    copper = c4.session_copy(ar5.SES.read_text(encoding="utf-8"), set(info["prep"]["not_autorouted"]) | rejected)
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
    back = "\n".join(line for line in out if line not in added)
    assert back == stage, "candidate differs from the stage outside additions"
    restored = Counter(stage.replace(L1_AT_NEW, L1_AT_OLD).split("\n"))
    full = Counter(full_004.split("\n"))
    ripped_numbers = {number[net] for net in ar5.RIPPED}
    assert not restored - full, "stage has lines candidate 004 has not"
    assert all(re.search(r"\(net (\d+)\)", line) and int(re.search(r"\(net (\d+)\)", line).group(1)) in ripped_numbers
               and line.lstrip().startswith(("(segment ", "(via ")) for line in (full - restored).elements()), \
        "stage differs from candidate 004 beyond the ripped copper and L1"
    spec = {"base": "candidate 004 minus ripped nets, L1 moved", "ripped": sorted(ar5.RIPPED),
            "l1": [L1_AT_OLD, L1_AT_NEW], "nets": len(copper), "segments": len(seg_lines), "vias": len(via_lines),
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
    summary = {"schema": "dioneya-pcb-main-routing-005-candidate-v1", "base_board_sha256": BASE_SHA256,
               "candidate_sha256": sha256(cand), "delta": spec, "kicad_image": g2.KICAD_IMAGE,
               "manufacturing_release": False, "applied_to_authoritative_board": False}
    work = ROOT / "hardware/kicad/native/_r005_cand"
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
    print(f"PCB-MAIN routing 005 candidate: PASS {summary['candidate_sha256']}")


if __name__ == "__main__":
    check() if "--check" in sys.argv[1:] else generate()
