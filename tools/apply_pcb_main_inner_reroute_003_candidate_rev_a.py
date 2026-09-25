#!/usr/bin/env python3
"""PCB-MAIN candidate 003: OCTOSPI / SDIO / EN_MODEM off In2/In3, on the outer layers over GND_DIGITAL.

Option (a) of hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_002_CANDIDATE_REV_A.md (section 6). Run by
.github/workflows/ci-apply.yml (docker available). Builds from the authoritative board (SHA-256 pinned):
  1. R9 / R10 / R11 (OCTOSPI IO0/IO1/IO2 series resistors, 22 ohm 0402, identical) re-placed in one row right
     of R8 in U1 pin order, rotated 90 deg (pin 1 towards U1): tools/pcb_main_inner_reroute_003_rev_a.py
     RESISTOR_MOVES. R8 keeps its accepted ECO-002 position. Nets, parts and BOM are unchanged.
  2. the ground-domain 002 construction (In4 split, stitching vias, modem-island tie) with the In4 GND_DIGITAL
     corridor widened to the OCTOSPI chain U1 - R9..R12 - U2 (split_in4 corridor_refs);
  3. the reroute plan hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/REROUTE_PLAN.json (made by the router
     in tools/pcb_main_inner_reroute_003_rev_a.py on the stage-2 board, SHA-256 pinned in the plan): every In2/In3
     segment of the 12 nets, the fan-out of the re-placed resistors / U1 pins and the NCS run inside U1 removed;
     the planned F.Cu/B.Cu runs, their vias and the GND_DIGITAL return vias added. Every planned item is
     re-checked against exact geometry before it is written (0.20 mm copper, 0.25 mm holes, keep-outs, reference
     boundary, board edge).
The delta is proved textually: removing the added lines and restoring the removed ones gives the stage-2
board, and the stage-2 board differs from the authoritative one only by the three footprint positions and the
002 construction. KiCad 9.0.9 then fills, runs DRC on base and candidate and dumps the filled references.
Output: hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003/ (candidate, SUMMARY.json, REFERENCE_MAP.json, DRC,
placement rows for R9-R11). --check verifies SUMMARY.json and reproducibility.
"""

from __future__ import annotations

import argparse
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
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402
import pcb_main_inner_reroute_003_rev_a as rr  # noqa: E402

OUT = ROOT / "hardware/kicad/candidates/PCB-MAIN-INNER-REROUTE-003"
STEM = "PCB-MAIN_INNER_REROUTE_003_CANDIDATE_REV_A"
PLAN = OUT / "REROUTE_PLAN.json"
CORRIDOR = ("U1", "R9", "R10", "R11", "R12", "U2")
NAMESPACE = uuid.UUID("0c3a8f51-6d2e-5b7a-9e14-003a1b2c3d4e")
STAGE_FILE = ROOT / "build/pcb_main_003_stage/moved.kicad_pcb"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def move_resistors(text: str) -> str:
    """RESISTOR_MOVES: footprint (at x y rot) and the absolute angle of each of its pads."""
    lines = text.split("\n")
    done = set()
    for i, line in enumerate(lines):
        if not line.startswith("  (footprint "):
            continue
        ref, j = None, i
        while j < len(lines) and not (j > i and lines[j].startswith("  )")):
            m = re.search(r'\(fp_text reference "([^"]+)"', lines[j])
            if m:
                ref = m.group(1)
                break
            j += 1
        if ref not in rr.RESISTOR_MOVES:
            continue
        x, y, rot = rr.RESISTOR_MOVES[ref]
        for k in range(i, i + 6):
            if re.match(r"^\s*\(at [-\d.]+ [-\d.]+( [-\d.]+)?\)$", lines[k]):
                lines[k] = re.sub(r"\(at .*\)", f"(at {x} {y}{'' if not rot else f' {rot}'})", lines[k])
                done.add(ref)
                break
        k = i + 1
        while not lines[k].startswith("  )"):
            if rot and lines[k].lstrip().startswith("(pad "):
                lines[k] = re.sub(r"\(at ([-\d.]+) ([-\d.]+)\)", lambda mm: f"(at {mm.group(1)} {mm.group(2)} {rot})",
                                  lines[k], count=1)
            k += 1
    assert done == set(rr.RESISTOR_MOVES), f"re-placed footprints not found: {set(rr.RESISTOR_MOVES) - done}"
    return "\n".join(lines)


def stage_board(base_text: str) -> tuple[str, dict]:
    """Stage 2: moved resistors + the 002 construction with the OCTOSPI corridor."""
    moved = move_resistors(base_text)
    STAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STAGE_FILE.write_text(moved, encoding="utf-8")
    original_split, original_board = geo.split_in4, g2.BOARD
    geo.split_in4 = lambda board, domains: rr.split_in4_corridor(board, domains, CORRIDOR)
    g2.BOARD = STAGE_FILE
    try:
        stage, spec = g2.build(moved)
    finally:
        geo.split_in4, g2.BOARD = original_split, original_board
    return stage, spec


def _key_seg(net, layer, a, b):
    a, b = (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))
    return ("seg", net, layer) + tuple(sorted((a, b)))


def _key_via(net, p):
    return ("via", net, round(p[0], 3), round(p[1], 3))


def reroute(stage_text: str, plan: dict) -> tuple[str, dict]:
    STAGE_FILE.write_text(stage_text, encoding="utf-8")
    board, _ = geo.load(STAGE_FILE)
    number = {n.name: n.number for n in board.nets}
    # items to remove: In2/In3 runs of the 12 nets + removed fan-out / NCS partial run
    removed = rr.removed_items(board)
    remove = set()
    for net, kind, layer, g, raw in geo.items(board):
        if net not in rr.NETS:
            continue
        if (kind == "track" and layer in rr.INNER) or rr.is_removed(removed, net, kind, layer, g):
            if kind == "via":
                remove.add(_key_via(number[net], (g.x, g.y)))
            else:
                remove.add(_key_seg(number[net], layer, g.coords[0], g.coords[-1]))
    lines = stage_text.split("\n")
    seg_re = re.compile(r'^  \(segment \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\) \(width [-\d.]+\) '
                        r'\(layer "([^"]+)"\) \(net (\d+)\)')
    via_re = re.compile(r'^  \(via \(at ([-\d.]+) ([-\d.]+)\) .*\(net (\d+)\)')
    kept, removed_lines = [], []
    for line in lines:
        m, v = seg_re.match(line), via_re.match(line)
        key = None
        if m:
            key = _key_seg(int(m.group(6)), m.group(5), (float(m.group(1)), float(m.group(2))),
                           (float(m.group(3)), float(m.group(4))))
        elif v:
            key = _key_via(int(v.group(3)), (float(v.group(1)), float(v.group(2))))
        if key is not None and key in remove:
            removed_lines.append(line)
            remove.discard(key)
            continue
        kept.append(line)
    assert not remove, f"items to remove not found in the stage text: {sorted(remove)[:5]}"
    # items to add
    seg_lines, via_lines = [], []
    for net, run in sorted(plan["routed"].items()):
        n = number[net]
        for t in run["tracks"]:
            for a, b in zip(t["points"], t["points"][1:]):
                seg_lines.append(f'  (segment (start {a[0]:.4f} {a[1]:.4f}) (end {b[0]:.4f} {b[1]:.4f}) (width {t["width"]}) '
                                 f'(layer "{t["layer"]}") (net {n}) '
                                 f'(tstamp {uuid.uuid5(NAMESPACE, f"seg|{net}|{a[0]:.4f}|{a[1]:.4f}|{b[0]:.4f}|{b[1]:.4f}")}))')
        for v in run["vias"]:
            x, y = v["at"]
            via_lines.append(f'  (via (at {x:.4f} {y:.4f}) (size {rr.VIA_SIZE}) (drill {rr.VIA_DRILL}) '
                             f'(layers "F.Cu" "B.Cu") (net {n}) (tstamp {uuid.uuid5(NAMESPACE, f"via|{net}|{x:.4f}|{y:.4f}")}))')
    gnd = number["GND_DIGITAL"]
    for x, y in plan["gnd_return_vias"]:
        via_lines.append(f'  (via (at {x:.4f} {y:.4f}) (size {rr.VIA_SIZE}) (drill {rr.VIA_DRILL}) '
                         f'(layers "F.Cu" "B.Cu") (net {gnd}) (tstamp {uuid.uuid5(NAMESPACE, f"gnd|{x:.4f}|{y:.4f}")}))')
    last_via = max(i for i, line in enumerate(kept) if line.startswith("  (via "))
    last_seg = max(i for i, line in enumerate(kept) if line.startswith("  (segment "))
    assert last_seg < last_via, "unexpected board item order"
    out = kept[:last_via + 1] + via_lines + kept[last_via + 1:]
    out = out[:last_seg + 1] + seg_lines + out[last_seg + 1:]
    candidate = "\n".join(out)
    # textual proof: without the added lines and with the removed ones restored (as a multiset) -> stage text
    back = [line for line in out if line not in set(seg_lines) | set(via_lines)]
    assert Counter(back) + Counter(removed_lines) == Counter(lines), "candidate differs from stage 2 outside the delta"
    return candidate, {"removed_lines": len(removed_lines), "added_segments": len(seg_lines),
                       "added_vias": len(via_lines) - len(plan["gnd_return_vias"]),
                       "added_gnd_return_vias": len(plan["gnd_return_vias"])}


def verify_plan(stage_text: str, plan: dict) -> dict:
    """Exact-geometry re-check of every planned track and via on the stage-2 board."""
    STAGE_FILE.write_text(stage_text, encoding="utf-8")
    board, _ = geo.load(STAGE_FILE)
    router = rr.Router(board, lambda m: None)
    LineString, Point = geo._shapely()[0], geo._shapely()[1]
    runs = list(plan["routed"].values())
    gnd = [tuple(v) for v in plan["gnd_return_vias"]]
    problems = []
    for net, run in plan["routed"].items():
        others = [r for n, r in plan["routed"].items() if n != net]
        for t in run["tracks"]:
            strict = router.strict(net, t["layer"], others, gnd)
            body = LineString(t["points"]).buffer(t["width"] / 2)
            if body.intersects(strict):
                problems.append(f"{net} {t['layer']} track clearance")
        copper, holes = router.via_obstacles(net, others, gnd)
        for v in run["vias"]:
            p = Point(v["at"])
            if p.buffer(rr.VIA_SIZE / 2).distance(copper) < rr.CLEARANCE - 1e-4 or \
                    p.buffer(rr.VIA_DRILL / 2).distance(holes) < rr.HOLE_CLEARANCE - 1e-4:
                problems.append(f"{net} via {v['at']} clearance")
    copper, holes = router.via_obstacles("GND_DIGITAL", runs, [])
    for i, v in enumerate(gnd):
        p = Point(v)
        others = [Point(q) for j, q in enumerate(gnd) if j != i]
        if p.buffer(rr.VIA_SIZE / 2).distance(copper) < rr.CLEARANCE - 1e-4 or \
                p.buffer(rr.VIA_DRILL / 2).distance(holes) < rr.HOLE_CLEARANCE - 1e-4 or \
                any(p.distance(o) < rr.VIA_SIZE + rr.CLEARANCE for o in others):
            problems.append(f"GND_DIGITAL return via {v} clearance")
    assert not problems, f"reroute plan fails the exact geometry check: {problems[:10]}"
    return {"tracks": sum(len(r["tracks"]) for r in runs), "vias": sum(len(r["vias"]) for r in runs),
            "gnd_return_vias": len(gnd), "result": "PASS"}


def build(base_text: str) -> tuple[str, dict]:
    stage, spec = stage_board(base_text)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert sha256_text(stage) == plan["stage_sha256"], "stage-2 board differs from the one the plan was made on"
    check = verify_plan(stage, plan)
    candidate, delta = reroute(stage, plan)
    spec.update({"resistor_moves": rr.RESISTOR_MOVES, "corridor_refs": list(CORRIDOR), "plan_check": check,
                 "reroute_delta": delta, "stage_sha256": plan["stage_sha256"]})
    return candidate, spec


def placement_rows() -> list:
    rows = []
    for ref, (x, y, rot) in rr.RESISTOR_MOVES.items():
        rows.append({"RefDes": ref, "X_mm": x, "Y_mm": y, "Rotation_deg": rot,
                     "reason": "PCB-MAIN 003: OCTOSPI resistor row in U1 pin order (IO0, IO1, IO2 right of R8)"})
    return rows


def generate(local: bool = False) -> None:
    g2.deps()
    assert g2.sha256(g2.BOARD) == g2.BASE_SHA256, "authoritative PCB-MAIN is not the reviewed base 2dd9bdf2"
    base_text = g2.BOARD.read_text(encoding="utf-8")
    candidate, spec = build(base_text)
    OUT.mkdir(parents=True, exist_ok=True)
    cand_path = OUT / f"{STEM}.kicad_pcb"
    cand_path.write_text(candidate, encoding="utf-8")
    (OUT / "SPEC.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False, default=list) + "\n", encoding="utf-8")
    (OUT / "PLACEMENT_ROWS.json").write_text(json.dumps(placement_rows(), indent=1) + "\n", encoding="utf-8")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    summary = {"schema": "dioneya-pcb-main-inner-reroute-003-candidate-v1",
               "proposal_id": "PCB-MAIN-INNER-REROUTE-003",
               "base_board_sha256": g2.BASE_SHA256, "candidate_sha256": g2.sha256(cand_path),
               "stage_sha256": plan["stage_sha256"], "plan_sha256": g2.sha256(PLAN),
               "kicad_image": g2.KICAD_IMAGE, "preserved_geometry_outside_delta": "PASS",
               "plan_check": spec["plan_check"], "reroute_delta": spec["reroute_delta"],
               "resistor_moves": rr.RESISTOR_MOVES, "corridor_refs": list(CORRIDOR),
               # OCTOSPI U1 pin -> resistor -> U2 pin, track + 1.6 mm per F.Cu<->B.Cu transition
               "octospi_lengths_mm": {"base_board": plan["lengths_original"], "routed": plan["lengths_before"],
                                      "length_matched": plan["lengths_after"]},
               "manufacturing_release": False, "applied_to_authoritative_board": False}
    if local:
        (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({k: summary[k] for k in ("candidate_sha256", "plan_check", "reroute_delta")}, ensure_ascii=False))
        return
    work = g2.WORK
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        shutil.copytree(g2.NATIVE / "libs", work / "libs")
        shutil.copyfile(g2.NATIVE / "fp-lib-table", work / "fp-lib-table")
        for tag, source in (("base", g2.BOARD), ("candidate", cand_path)):
            shutil.copyfile(g2.NATIVE / "PCB-MAIN.kicad_pro", work / f"{tag}.kicad_pro")
            shutil.copyfile(source, work / f"{tag}.kicad_pcb")
        rel = work.relative_to(ROOT)
        stage = "tools/pcb_main_ground_domain_002_stage_rev_a.py"
        steps = {}
        for tag in ("base", "candidate"):
            steps[f"fill_{tag}"] = g2.docker("/usr/bin/python3", stage, "fill", f"{rel}/{tag}.kicad_pcb", f"{rel}/{tag}.kicad_pcb")
            steps[f"drc_{tag}"] = g2.docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                                            "-o", f"{rel}/drc_{tag}.json", f"{rel}/{tag}.kicad_pcb")
            steps[f"dump_{tag}"] = g2.docker("/usr/bin/python3", stage, "dump", f"{rel}/{tag}.kicad_pcb",
                                             f"{rel}/fills_{tag}.json")
        g2.docker("chmod", "-R", "a+rwX", str(rel))
        summary["steps"] = {k: {"rc": v.returncode, "stderr": v.stderr[-600:] if v.returncode else ""} for k, v in steps.items()}
        reports = {tag: json.loads((work / f"drc_{tag}.json").read_text(encoding="utf-8")) for tag in ("base", "candidate")}
        for tag in ("base", "candidate"):
            shutil.copyfile(work / f"drc_{tag}.json", OUT / f"drc_{tag}.json")
        (base_fp, base_unc), (cand_fp, cand_unc) = g2.drc_fingerprints(reports["base"]), g2.drc_fingerprints(reports["candidate"])
        new = sorted([list(k[:2]) + [list(k[2])] for k in cand_fp if cand_fp[k] > base_fp.get(k, 0)])
        gone = sorted([list(k[:2]) + [list(k[2])] for k in base_fp if base_fp[k] > cand_fp.get(k, 0)])
        by_type = lambda fp: dict(sorted(Counter(f"{k[0]}:{k[1]}" for k in fp.elements()).items()))  # noqa: E731
        summary["drc"] = {"base": {"by_type": by_type(base_fp), "unconnected": base_unc},
                          "candidate": {"by_type": by_type(cand_fp), "unconnected": cand_unc},
                          "new_fingerprints": new[:80], "new_fingerprint_count": len(new),
                          "removed_fingerprints": gone[:80], "removed_fingerprint_count": len(gone),
                          "new_errors": sum(1 for k in new if k[0] == "error")}
        dumps = {tag: json.loads((work / f"fills_{tag}.json").read_text(encoding="utf-8")) for tag in ("base", "candidate")}
        board, domains = geo.load(cand_path)
        base_board, _ = geo.load(g2.BOARD)
        maps = {"base": geo.continuity_map(base_board, domains, g2.filled_references(dumps["base"])),
                "candidate": geo.continuity_map(board, domains, g2.filled_references(dumps["candidate"]))}
        reference_map = {
            "continuity_filled_copper": {tag: maps[tag]["by_layer_domain"] for tag in maps},
            "continuity_by_net_layer": maps["candidate"]["by_net_layer"],
            "rerouted_nets": {k: v for k, v in maps["candidate"]["by_net_layer"].items() if k.split("|")[0] in rr.NETS},
            "inner_layer_tracks_left": {k: v for k, v in maps["candidate"]["by_net_layer"].items()
                                        if k.endswith("|In2.Cu") or k.endswith("|In3.Cu")},
        }
        (OUT / "REFERENCE_MAP.json").write_text(json.dumps(reference_map, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        summary["in4_islands"] = g2.island_report(dumps["candidate"], board)
        summary["continuity_summary"] = {tag: {k: v["share"] for k, v in maps[tag]["by_layer_domain"].items()} for tag in maps}
    finally:
        g2.docker("rm", "-rf", str(work.relative_to(ROOT)))
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(STAGE_FILE.parent, ignore_errors=True)
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary.get(k) for k in ("candidate_sha256", "drc", "continuity_summary")}, ensure_ascii=False)[:2500])


def check() -> None:
    g2.deps()
    summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
    cand = OUT / f"{STEM}.kicad_pcb"
    assert summary["candidate_sha256"] == g2.sha256(cand), "candidate differs from SUMMARY.json"
    assert summary["plan_sha256"] == g2.sha256(PLAN), "reroute plan changed after the candidate"
    if g2.sha256(g2.BOARD) == g2.BASE_SHA256:
        text, _ = build(g2.BOARD.read_text(encoding="utf-8"))
        assert text == cand.read_text(encoding="utf-8"), "candidate is not reproducible from the base"
    print(f"PCB-MAIN inner reroute 003 candidate: PASS {summary['candidate_sha256']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--local", action="store_true", help="build and verify without the KiCad steps")
    args = parser.parse_args()
    check() if args.check else generate(local=args.local)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
