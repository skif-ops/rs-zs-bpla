#!/usr/bin/env python3
"""PCB-MAIN-GROUND-DOMAIN-ROUTING-002 candidate (Review B R1 section 4, variant 1).

Run by .github/workflows/ci-apply.yml (docker available). Starts from the authoritative board
(SHA-256 pinned) and writes a candidate only; the authoritative board is not changed.
Output: hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-ROUTING-002/
  PCB-MAIN_GROUND_DOMAIN_ROUTING_002_CANDIDATE_REV_A.kicad_pcb   unfilled, like the native board
  SPEC.json          In4 zone polygons, stitching vias, every rule parameter
  REFERENCE_MAP.json net / domain -> signal layer -> reference copper, continuity along every
                     routed track (filled copper, base vs candidate), transitions and stitching,
                     cross-domain interfaces, inner-layer tracks
  drc_base.json / drc_candidate.json   KiCad 9.0.9 DRC after refill, project libraries present
  SUMMARY.json       SHA-256 before/after, comparative DRC fingerprints, unconnected counts,
                     preserved-geometry check, In4 island connectivity
Delta: the In4.Cu GND_MODEM zone is replaced by GND_MODEM zones over the modem region (priority 1)
plus one GND_DIGITAL In4.Cu zone over the In1.Cu digital outline (priority 0); GND_DIGITAL
through vias 0.5/0.3 are added next to digital signal transitions; a modem piece cut off from
the main modem copper (TP_CELL_DBG ground under U1) is tied back by a 0.3 mm GND_MODEM track on
In3.Cu (no plane on In3, a ground conductor, not a signal). Every other byte of the
board is kept (checked). Rules: tools/pcb_main_ground_domain_002_rev_a.py.
--check regenerates the candidate text and compares it byte for byte, and checks SUMMARY.json.
"""

from __future__ import annotations

import argparse
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
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

KICAD_IMAGE = "ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
NATIVE = ROOT / "hardware/kicad/native/PCB-MAIN"
BOARD = NATIVE / "PCB-MAIN.kicad_pcb"
BASE_SHA256 = "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
OUT = ROOT / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-ROUTING-002"
STEM = "PCB-MAIN_GROUND_DOMAIN_ROUTING_002_CANDIDATE_REV_A"
WORK = ROOT / "hardware/kicad/native/_gd002_work"  # sibling of PCB-MAIN: ${KIPRJMOD}/libs resolves
NAMESPACE = uuid.UUID("6f1c2d4e-0b7a-5c1e-9d02-3a5b7c9e1f20")
OLD_ZONE_HEAD = '  (zone (net 47) (net_name "GND_MODEM") (layer "In4.Cu")'
ZONE_BODY = """    (connect_pads yes (clearance 0.1))
    (min_thickness 0.15) (filled_areas_thickness no)
    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
"""


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
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "kiutils", "shapely>=2", "numpy", "scipy"],
                       check=True)


def net_number(text: str, name: str) -> int:
    return int(re.search(r'\(net (\d+) "' + re.escape(name) + r'"\)', text).group(1))


def zone_text(net: int, name: str, zone_name: str, points: list, priority: int | None) -> str:
    tstamp = uuid.uuid5(NAMESPACE, f"zone|{zone_name}")
    pts = "\n".join(f"        (xy {x:.4f} {y:.4f})" for x, y in points)
    head = (f'  (zone (net {net}) (net_name "{name}") (layer "In4.Cu") (tstamp {tstamp}) '
            f'(name "{zone_name}") (hatch edge 0.5)\n')
    prio = f"    (priority {priority})\n" if priority else ""
    return head + prio + ZONE_BODY + "    (polygon\n      (pts\n" + pts + "\n      )\n    )\n  )"


def build(text: str) -> tuple[str, dict]:
    board, domains = geo.load(BOARD)
    split = geo.split_in4(board, domains)
    added, stitch_report = geo.stitching_vias(board, domains, split)
    ties = geo.island_ties(board, split, added)
    assert all("points" in t for t in ties), f"modem island without an In3 tie: {ties}"
    gnd_digital, gnd_modem = net_number(text, "GND_DIGITAL"), net_number(text, "GND_MODEM")
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith(OLD_ZONE_HEAD))
    end = start
    while lines[end] != "  )":
        end += 1
    old_block = "\n".join(lines[start:end + 1])
    zones = [zone_text(gnd_digital, "GND_DIGITAL", "PCB_MAIN_GND_DIGITAL_In4_Cu",
                       list(split["digital_outline"].exterior.coords)[:-1], None)]
    for index, piece in enumerate(sorted(split["modem_pieces"], key=lambda p: -p.area)):
        pts = [(round(x, 4), round(y, 4)) for x, y in list(piece.simplify(0.02).exterior.coords)[:-1]]
        zones.append(zone_text(gnd_modem, "GND_MODEM", f"PCB_MAIN_GND_MODEM_In4_Cu_{index + 1}", pts, 1))
    via_lines = [f'  (via (at {x:.4f} {y:.4f}) (size {geo.VIA_SIZE}) (drill {geo.VIA_DRILL}) (layers "F.Cu" "B.Cu") '
                 f'(net {gnd_digital}) (tstamp {uuid.uuid5(NAMESPACE, f"via|{x:.4f}|{y:.4f}")}))' for x, y in added]
    tie_lines = []
    for tie in ties:
        for (xa, ya), (xb, yb) in zip(tie["points"], tie["points"][1:]):
            tie_lines.append(f'  (segment (start {xa:.4f} {ya:.4f}) (end {xb:.4f} {yb:.4f}) (width {tie["width"]}) '
                             f'(layer "{tie["layer"]}") (net {gnd_modem}) '
                             f'(tstamp {uuid.uuid5(NAMESPACE, f"tie|{xa:.4f}|{ya:.4f}|{xb:.4f}|{yb:.4f}")}))')
    last_via = max(i for i, line in enumerate(lines) if line.startswith("  (via "))
    last_segment = max(i for i, line in enumerate(lines) if line.startswith("  (segment "))
    assert last_segment < last_via < start, "unexpected board item order"
    new_lines = lines[:start] + "\n".join(zones).split("\n") + lines[end + 1:]
    new_lines = new_lines[:last_via + 1] + via_lines + new_lines[last_via + 1:]
    new_lines = new_lines[:last_segment + 1] + tie_lines + new_lines[last_segment + 1:]
    candidate = "\n".join(new_lines)
    # preserved-geometry proof: removing exactly what was added and restoring the old block gives the base
    restored = [line for line in new_lines if line not in via_lines and line not in tie_lines]
    z0 = restored.index(zones[0].split("\n")[0])
    z_len = sum(len(z.split("\n")) for z in zones)
    restored = restored[:z0] + old_block.split("\n") + restored[z0 + z_len:]
    assert "\n".join(restored) == text, "candidate differs from the base outside the declared delta"
    spec = {
        "rules": {k: getattr(geo, k) for k in ("CELL", "PROTECTED_ZONES", "DIGITAL_PRIORITY_REFS", "STITCH_TARGET_MM",
                                                "STITCH_SEARCH_MM", "VIA_SIZE", "VIA_DRILL", "CLEARANCE",
                                                "HOLE_CLEARANCE", "EDGE")},
        "removed_zone": {"net": "GND_MODEM", "layer": "In4.Cu", "text": old_block},
        "digital_zone": {"net": "GND_DIGITAL", "layer": "In4.Cu", "priority": 0,
                         "outline": [list(p) for p in list(split["digital_outline"].exterior.coords)[:-1]],
                         "area_mm2": round(split["digital_outline"].area, 1),
                         "effective_area_mm2": round(split["digital_effective"].area, 1)},
        "modem_zones": [{"net": "GND_MODEM", "layer": "In4.Cu", "priority": 1, "area_mm2": round(p.area, 1),
                         "outline": [list(c) for c in list(p.simplify(0.02).exterior.coords)[:-1]]}
                        for p in sorted(split["modem_pieces"], key=lambda p: -p.area)],
        "previous_in4_modem_area_mm2": round(split["old_in4_modem"].area, 1),
        "stitching_vias": [list(v) for v in added],
        "modem_island_ties": ties,
        "stitching_report": stitch_report,
    }
    return candidate, spec


def drc_fingerprints(report: dict) -> tuple[Counter, int]:
    prints = Counter()
    for violation in report.get("violations", []):
        items = tuple(sorted(item.get("description", "") for item in violation.get("items", [])))
        prints[(violation["severity"], violation["type"], items)] += 1
    return prints, len(report.get("unconnected_items", []))


def filled_references(dump: dict) -> dict:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    refs: dict = {}
    for fill in dump["fills"]:
        if len(fill["points"]) < 3:
            continue
        poly = Polygon(fill["points"], [h for h in fill["holes"] if len(h) >= 3]).buffer(0)
        refs.setdefault(fill["layer"], {}).setdefault(fill["net"], []).append(poly)
    return {layer: {net: unary_union(polys) for net, polys in nets.items()} for layer, nets in refs.items()}


def island_report(dump: dict, board) -> list:
    from shapely.geometry import Point, Polygon
    vias = [(item.net, Point(item.position.X, item.position.Y)) for item in board.traceItems
            if type(item).__name__ == "Via"]
    names = {n.number: n.name for n in board.nets}
    rows = []
    for fill in dump["fills"]:
        if fill["layer"] != "In4.Cu" or len(fill["points"]) < 3:
            continue
        poly = Polygon(fill["points"], [h for h in fill["holes"] if len(h) >= 3]).buffer(0)
        count = sum(1 for net, p in vias if names.get(net) == fill["net"] and poly.contains(p))
        rows.append({"net": fill["net"], "zone": fill["zone"], "area_mm2": round(poly.area, 2), "same_net_vias": count})
    return rows


def generate() -> None:
    deps()
    assert sha256(BOARD) == BASE_SHA256, "authoritative PCB-MAIN is not the reviewed base 2dd9bdf2"
    base_text = BOARD.read_text(encoding="utf-8")
    candidate, spec = build(base_text)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{STEM}.kicad_pcb").write_text(candidate, encoding="utf-8")
    (OUT / "SPEC.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {"schema": "dioneya-pcb-main-ground-domain-routing-002-candidate-v1",
               "proposal_id": "PCB-MAIN-GROUND-DOMAIN-ROUTING-002",
               "base_board_sha256": BASE_SHA256, "candidate_sha256": sha256(OUT / f"{STEM}.kicad_pcb"),
               "kicad_image": KICAD_IMAGE, "preserved_geometry_outside_delta": "PASS",
               "stitching_vias_added": len(spec["stitching_vias"]),
               "manufacturing_release": False, "applied_to_authoritative_board": False}
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    try:
        shutil.copytree(NATIVE / "libs", WORK / "libs")
        shutil.copyfile(NATIVE / "fp-lib-table", WORK / "fp-lib-table")
        for tag, source in (("base", BOARD), ("candidate", OUT / f"{STEM}.kicad_pcb")):
            shutil.copyfile(NATIVE / "PCB-MAIN.kicad_pro", WORK / f"{tag}.kicad_pro")
            shutil.copyfile(source, WORK / f"{tag}.kicad_pcb")
        rel = WORK.relative_to(ROOT)
        stage = "tools/pcb_main_ground_domain_002_stage_rev_a.py"
        steps = {}
        for tag in ("base", "candidate"):
            steps[f"fill_{tag}"] = docker("/usr/bin/python3", stage, "fill", f"{rel}/{tag}.kicad_pcb",
                                          f"{rel}/{tag}.kicad_pcb")
            steps[f"drc_{tag}"] = docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                                         "-o", f"{rel}/drc_{tag}.json", f"{rel}/{tag}.kicad_pcb")
            steps[f"dump_{tag}"] = docker("/usr/bin/python3", stage, "dump", f"{rel}/{tag}.kicad_pcb",
                                          f"{rel}/fills_{tag}.json")
        docker("chmod", "-R", "a+rwX", str(rel))
        summary["steps"] = {k: {"rc": v.returncode, "stderr": v.stderr[-600:] if v.returncode else ""}
                            for k, v in steps.items()}
        reports = {tag: json.loads((WORK / f"drc_{tag}.json").read_text(encoding="utf-8")) for tag in ("base", "candidate")}
        for tag in ("base", "candidate"):
            shutil.copyfile(WORK / f"drc_{tag}.json", OUT / f"drc_{tag}.json")
        (base_fp, base_unc), (cand_fp, cand_unc) = drc_fingerprints(reports["base"]), drc_fingerprints(reports["candidate"])
        new = sorted([list(k[:2]) + [list(k[2])] for k in cand_fp if cand_fp[k] > base_fp.get(k, 0)])
        gone = sorted([list(k[:2]) + [list(k[2])] for k in base_fp if base_fp[k] > cand_fp.get(k, 0)])
        by_type = lambda fp: dict(sorted(Counter(f"{k[0]}:{k[1]}" for k in fp.elements()).items()))  # noqa: E731
        summary["drc"] = {"base": {"by_type": by_type(base_fp), "unconnected": base_unc},
                          "candidate": {"by_type": by_type(cand_fp), "unconnected": cand_unc},
                          "new_fingerprints": new[:80], "new_fingerprint_count": len(new),
                          "removed_fingerprints": gone[:80], "removed_fingerprint_count": len(gone),
                          "new_errors": sum(1 for k in new if k[0] == "error")}
        dumps = {tag: json.loads((WORK / f"fills_{tag}.json").read_text(encoding="utf-8")) for tag in ("base", "candidate")}
        board, domains = geo.load(OUT / f"{STEM}.kicad_pcb")
        maps = {tag: geo.continuity_map(board, domains, filled_references(dumps[tag])) for tag in ("base", "candidate")}
        reference_map = {
            "layer_reference": {"F.Cu": "In1.Cu (GND_DIGITAL; GND_MODEM in ZONE_CELL)",
                                "B.Cu": "In4.Cu (GND_MODEM modem region, GND_DIGITAL elsewhere)",
                                "In2.Cu": "GND_MIC plane layer - not a signal layer",
                                "In3.Cu": "NOT DIGITAL: 0.1088 mm to In2 (GND_MIC), 0.55 mm to In4 (Review B R1 4)"},
            "continuity_filled_copper": {"base": maps["base"]["by_layer_domain"],
                                         "candidate": maps["candidate"]["by_layer_domain"]},
            "continuity_by_net_layer": maps["candidate"]["by_net_layer"],
            "transitions_and_stitching": spec["stitching_report"],
            "inner_layer_tracks_finding": {k: v for k, v in maps["candidate"]["by_net_layer"].items()
                                           if k.endswith("|In2.Cu") or k.endswith("|In3.Cu")},
            "cross_domain_interfaces": sorted(n for n, d in domains.items() if d.startswith("CROSS_")),
        }
        (OUT / "REFERENCE_MAP.json").write_text(json.dumps(reference_map, indent=1, ensure_ascii=False) + "\n",
                                                encoding="utf-8")
        summary["in4_islands"] = island_report(dumps["candidate"], board)
        summary["continuity_summary"] = {tag: {k: v["share"] for k, v in maps[tag]["by_layer_domain"].items()}
                                         for tag in ("base", "candidate")}
    finally:
        docker("rm", "-rf", str(WORK.relative_to(ROOT)))
        shutil.rmtree(WORK, ignore_errors=True)
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: summary.get(k) for k in ("candidate_sha256", "drc", "continuity_summary")},
                     ensure_ascii=False)[:2000])


def check() -> None:
    deps()
    summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
    candidate = OUT / f"{STEM}.kicad_pcb"
    assert summary["candidate_sha256"] == sha256(candidate), "candidate differs from SUMMARY.json"
    if sha256(BOARD) == BASE_SHA256:
        text, _ = build(BOARD.read_text(encoding="utf-8"))
        assert text == candidate.read_text(encoding="utf-8"), "candidate is not reproducible from the base"
    print(f"PCB-MAIN ground-domain 002 candidate: PASS {summary['candidate_sha256']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
