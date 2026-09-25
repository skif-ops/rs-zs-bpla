#!/usr/bin/env python3
"""PCB-PWR DFM register (Review B R2.002): measured pad, mask, paste, legend and hole geometry against
the published JLCPCB rigid-PCB capabilities, as a list of concrete deviations for the reviewer.

Run by .github/workflows/ci-apply.yml (docker available). The pinned KiCad 9.0.9 image exports the exact
geometry (tools/pcb_pwr_dfm_stage_rev_a.py); this script measures it and writes
hardware/reviews/PCB_PWR_DFM_REGISTER_REV_A.json. The board is not changed.

This register replaces the Rev A wording of ECO-005 (record section 9) that justified the 0.125 mm SMD
pad gap of U3/U4 with the 0.09 mm multilayer TRACK spacing: that number is not a pad rule. The pad rule
is "SMD pad to pad clearance (different nets) 0.15 mm". The order-time DFM check stays a separate stage.

--check verifies the register belongs to the current board and requirement table.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
NATIVE = ROOT / "hardware/kicad/native/PCB-PWR"
BOARD = NATIVE / "PCB-PWR.kicad_pcb"
OUT = ROOT / "hardware/reviews/PCB_PWR_DFM_REGISTER_REV_A.json"
WORK = ROOT / "build/pcb_pwr_dfm"
SOURCE = {"url": "https://jlcpcb.com/capabilities/Capabilities", "retrieved": "2026-09-25",
          "profile": "rigid FR-4, multilayer, 1 oz outer, green LPI mask (PCB_PWR_STACKUP_COPPER_REQUEST_REV_A)"}
REQ = {
    "smd_pad_to_pad_mm": (0.15, "SMD pad to pad clearance (different nets) 0.15 mm"),
    "pad_to_track_mm": (0.10, "Pad to track clearance 0.1 mm"),
    "mask_dam_mm": (0.10, "Soldermask bridge, 1 oz green: min. pad spacing 0.10 mm; narrower dams are not made"),
    "mask_opening_to_trace_mm": (0.09, "Keep at least 0.09 mm between soldermask openings and neighbouring traces"),
    "legend_line_mm": (0.15, "Legend minimum line width 0.15 mm"),
    "legend_text_height_mm": (1.0, "Legend minimum text height 1.0 mm"),
    "legend_to_pad_mm": (0.15, "Pad to silkscreen 0.15 mm"),
    "pad_hole_to_hole_mm": (0.45, "Pad hole-to-hole spacing 0.45 mm"),
    "via_hole_to_hole_mm": (0.20, "Via hole-to-hole spacing 0.2 mm"),
    "stencil_area_ratio": (0.66, "IPC-7525 area ratio >= 0.66 (stencil design guideline, not a JLC PCB rule)"),
}
STENCIL_T_MM = (0.12, 0.10)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deps() -> None:
    try:
        import shapely  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "shapely>=2"], check=True)


def geom(rows: list):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    parts = [Polygon(r["points"], [h for h in r["holes"] if len(h) >= 3]).buffer(0) for r in rows if len(r["points"]) >= 3]
    return unary_union(parts) if parts else Polygon()


def export() -> dict:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    try:
        for name in ("PCB-PWR.kicad_pcb", "PCB-PWR.kicad_pro", "PCB-PWR.kicad_dru", "fp-lib-table"):
            if (NATIVE / name).exists():
                shutil.copy2(NATIVE / name, WORK / name)
        shutil.copytree(NATIVE / "libs", WORK / "libs")
        rel = WORK.relative_to(ROOT)
        run = subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                              "/usr/bin/python3", "tools/pcb_pwr_dfm_stage_rev_a.py", "dump",
                              f"{rel}/PCB-PWR.kicad_pcb", f"{rel}/dfm.json"], capture_output=True, text=True)
        assert run.returncode == 0, f"KiCad DFM stage failed: {run.stderr[-3000:]}"
        subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                        "chmod", "-R", "a+rwX", str(rel)], capture_output=True)
        return json.loads((WORK / "dfm.json").read_text(encoding="utf-8"))
    finally:
        subprocess.run(["docker", "run", "--rm", "--user", "root", "-v", f"{ROOT}:/w", "-w", "/w", KICAD_IMAGE,
                        "rm", "-rf", str(WORK.relative_to(ROOT))], capture_output=True)
        shutil.rmtree(WORK, ignore_errors=True)


def measure(data: dict) -> dict:
    from shapely.strtree import STRtree

    rows: dict = defaultdict(list)
    for side in ("F", "B"):
        pads = [(p, geom(p["copper"][side])) for p in data["pads"] if side in p["copper"]]
        masks = [(p, geom(p["mask"][side])) for p in data["pads"] if side in p["mask"]]
        copper = [(c, geom(c["polys"])) for c in data["copper"] if c["side"] == side]
        name = lambda p: f"{p['ref']}.{p['pad'] or '-'}"  # noqa: E731
        # A. SMD pad to pad, different nets (pads without a net count as their own net)
        tree = STRtree([g for _, g in pads])
        for i, (pa, ga) in enumerate(pads):
            for j in tree.query(ga.buffer(0.2)):
                pb, gb = pads[j]
                if j <= i or (pa["net"] and pa["net"] == pb["net"]):
                    continue
                if not (pa["smd"] and pb["smd"]):
                    continue
                gap = ga.distance(gb)
                if gap < REQ["smd_pad_to_pad_mm"][0]:
                    rows["A_smd_pad_to_pad"].append({"side": side, "a": name(pa), "b": name(pb), "net_a": pa["net"],
                                                     "net_b": pb["net"], "gap_mm": round(gap, 4)})
        # B. pad to track / zone copper of another net
        ctree = STRtree([g for _, g in copper])
        for pa, ga in pads:
            for k in ctree.query(ga.buffer(0.15)):
                c, gc = copper[k]
                if c["net"] == pa["net"] or c["kind"] == "zone" and not gc.area:
                    continue
                gap = ga.distance(gc)
                if gap < REQ["pad_to_track_mm"][0]:
                    rows["B_pad_to_copper"].append({"side": side, "pad": name(pa), "net": pa["net"], "other": c["kind"],
                                                    "other_net": c["net"], "gap_mm": round(gap, 4)})
        # C. mask dams between openings of different nets; opening to other-net copper
        mtree = STRtree([g for _, g in masks])
        for i, (pa, ga) in enumerate(masks):
            for j in mtree.query(ga.buffer(0.15)):
                pb, gb = masks[j]
                if j <= i or (pa["net"] and pa["net"] == pb["net"]) or ga.is_empty or gb.is_empty:
                    continue
                dam = ga.distance(gb)
                if dam < REQ["mask_dam_mm"][0]:
                    rows["C_mask_dam"].append({"side": side, "a": name(pa), "b": name(pb), "net_a": pa["net"],
                                               "net_b": pb["net"], "dam_mm": round(dam, 4),
                                               "expansion_mm": [pa["mask_expansion_mm"].get(side),
                                                                pb["mask_expansion_mm"].get(side)]})
            for k in ctree.query(ga.buffer(0.1)):
                c, gc = copper[k]
                if c["net"] == pa["net"] or c["kind"] == "via" or ga.is_empty:
                    continue
                gap = ga.distance(gc)
                if gap < REQ["mask_opening_to_trace_mm"][0]:
                    rows["C_mask_opening_to_copper"].append({"side": side, "opening": name(pa), "net": pa["net"],
                                                             "other": c["kind"], "other_net": c["net"],
                                                             "gap_mm": round(gap, 4)})
        # D. paste apertures and coverage of large pads
        for p in data["pads"]:
            if side not in p["paste"]:
                continue
            g = geom(p["paste"][side])
            for part in getattr(g, "geoms", [g]):
                if part.is_empty:
                    continue
                ratios = {f"t{t:.2f}": round(part.area / (part.length * t), 3) for t in STENCIL_T_MM}
                row = {"side": side, "aperture": name(p), "net": p["net"], "area_mm2": round(part.area, 4),
                       "min_side_mm": round(min(_rect_sides(part)), 4), "area_ratio": ratios}
                rows["D_paste_all"].append(row)
                if ratios["t0.12"] < REQ["stencil_area_ratio"][0]:
                    rows["D_paste_area_ratio"].append(row)
        paste_all = geom([poly for p in data["pads"] if side in p["paste"] for poly in p["paste"][side]])
        for pa, ga in pads:
            if ga.area > 2.0:
                covered = ga.intersection(paste_all).area
                rows["D_large_pad_paste_coverage"].append({"side": side, "pad": name(pa), "net": pa["net"],
                                                           "pad_area_mm2": round(ga.area, 3),
                                                           "coverage": round(covered / ga.area, 3)})
        # E. legend
        opening_union = geom([poly for p in data["pads"] if side in p["mask"] for poly in p["mask"][side]])
        for s in data["silk"]:
            if s["side"] != side or not s["visible"]:
                continue
            label = f"{s['owner']}:{s['class']}" + (f":{s['text']}" if s.get("text") else "")
            if s.get("stroke_mm") and s["stroke_mm"] < REQ["legend_line_mm"][0]:
                rows["E_legend_line"].append({"side": side, "item": label, "stroke_mm": s["stroke_mm"]})
            if "text_height_mm" in s and s["text_height_mm"] < REQ["legend_text_height_mm"][0]:
                rows["E_legend_text_height"].append({"side": side, "item": label, "height_mm": s["text_height_mm"],
                                                     "stroke_mm": s.get("stroke_mm")})
            g = geom(s["polys"])
            if not g.is_empty and not opening_union.is_empty:
                gap = g.distance(opening_union)
                if gap < REQ["legend_to_pad_mm"][0]:
                    rows["E_legend_to_opening"].append({"side": side, "item": label, "gap_mm": round(gap, 4),
                                                        "over_opening_mm2": round(g.intersection(opening_union).area, 4)})
    # F. holes
    holes = data["holes"]
    for i, a in enumerate(holes):
        for b in holes[i + 1:]:
            edge = math.dist(a["at"], b["at"]) - (a["d_mm"] + b["d_mm"]) / 2
            if a["kind"] == b["kind"] == "via":
                limit, key = REQ["via_hole_to_hole_mm"][0], "F_via_hole_to_hole"
            else:
                limit, key = REQ["pad_hole_to_hole_mm"][0], "F_pad_hole_to_hole"
            if edge < limit:
                rows[key].append({"a": a["owner"], "b": b["owner"], "edge_mm": round(edge, 4)})
    return rows


def _rect_sides(part) -> list:
    rect = part.minimum_rotated_rectangle
    xs = list(rect.exterior.coords)
    return [math.dist(xs[0], xs[1]), math.dist(xs[1], xs[2])]


def generate() -> None:
    deps()
    data = export()
    rows = measure(data)
    register = {
        "schema": "dioneya-pcb-pwr-dfm-register-v1", "responds_to": "Review B R2.002",
        "board": str(BOARD.relative_to(ROOT)), "board_sha256": sha256(BOARD),
        "kicad": data["kicad_version"], "api_methods": data["api_methods"],
        "source": SOURCE, "requirements": {k: {"value": v[0], "rule": v[1]} for k, v in REQ.items()},
        "stencil_thickness_mm": list(STENCIL_T_MM),
        "counts": {k: len(v) for k, v in sorted(rows.items())},
        "measurements": {k: v for k, v in sorted(rows.items())},
        "order_time_dfm": "separate stage: JLC/JLCDFM check of the ordered Gerbers, not replaced by this register",
        "manufacturing_release": False,
    }
    OUT.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"counts": register["counts"], "methods": data["api_methods"]}, ensure_ascii=False))


def check() -> None:
    register = json.loads(OUT.read_text(encoding="utf-8"))
    assert register["board_sha256"] == sha256(BOARD), "DFM register does not belong to the current PCB-PWR board"
    assert register["requirements"] == {k: {"value": v[0], "rule": v[1]} for k, v in REQ.items()}, "requirement table drift"
    print(f"PCB-PWR DFM register: PASS {register['counts']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
