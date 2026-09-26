#!/usr/bin/env python3
"""PCB-MAIN experiment P2 (ci-apply): the session-G router input with Freerouting fan-out enabled.

P1 (pogo rows moved off U1) gave no gain (148 vs 144 unrouted in the router, 136 vs 131 open before the DRC filter),
so MAIN-AUTH-011 stays closed. P2 changes one variable against G: the fan-out stage (escape stub + via at each SMD
pin) is enabled; the grounds have no pins, so only signal/power pins are fanned out. Placement = G (L1 moved).
The P1 description below is kept for the shared code.

Measurement only: MAIN-AUTH-011 (pogo coordinates) and the authoritative board are unchanged. Candidate G showed
that 42 of its 161 open connections end at an isolated U1 pin; the bottom pogo pads TP_EOL 5-13 (y 23, along the U1
top pin row) and TP_CELL_DBG (y 30, under the U1 body) occupy the B.Cu escape of U1. P1 moves
  TP_EOL      (33, 23) -> (47.5, 9.0)   13 pads, 2.54 mm pitch, north of U1 (7.5 mm from the U1 area)
  TP_CELL_DBG (47, 30) -> (22.5, 28.0)  5 pads, west of U1 next to TP_CELL_USB (8.3 mm from the U1 area)
(free bottom strips: 0.3 mm to base B.Cu copper/pads/vias, 4 mm around the mounting holes, 1 mm from the edge),
removes the base copper that ended on the moved pads (BOOT0, 16 items; three ground vias on TP_EOL.1 and
TP_CELL_DBG.5), keeps L1 at the SMPS pins, and reruns the session-G router input with these changes.
Output under hardware/kicad/candidates/PCB-ROUTING-P1: router input/session/log, candidate, SUMMARY.json (KiCad
fill + DRC vs the authoritative board, reference map).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_ground_domain_routing_002_candidate_rev_a as g2  # noqa: E402
import apply_pcb_routing_global_g_rev_a as arg  # noqa: E402  (pinned routing modules)
import apply_pcb_main_routing_004_candidate_rev_a as c4  # noqa: E402
import apply_pcb_main_routing_005_candidate_rev_a as c5  # noqa: E402
import pcb_main_ground_domain_002_rev_a as geo  # noqa: E402

BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
BASE_SHA256 = c4.BASE_SHA256
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-P2"
INPUT, SES, LOG = OUT / "PCB-MAIN_ROUTE_INPUT_P2.dsn", OUT / "PCB-MAIN_ROUTED_P2.ses", OUT / "AUTOROUTE_P2.json"
STEM = "PCB-MAIN_FANOUT_P2_CANDIDATE_REV_A"
NAMESPACE = uuid.UUID("2a3b4c5d-6e7f-5081-9a2b-3c4d5e6f7a8b")
PASSES, TIME_LIMIT_S = 10, 200 * 60
MOVES = {}
RIP_NETS = set()
# KiCad DRC points of the first candidate run (39d343f1): only the connected pieces of new copper that contain a
# flagged track/via are left out; the rest of the same net stays
REJECTED_ITEMS = OUT / "DRC_REJECTED_ITEMS_P2.json"


def drop_flagged(copper: dict) -> tuple[dict, int]:
    from shapely.geometry import LineString, Point
    if not REJECTED_ITEMS.is_file():
        return copper, 0
    flags = json.loads(REJECTED_ITEMS.read_text(encoding="utf-8"))["items"]
    dropped = 0
    for net, entry in copper.items():
        pts = [Point(f["x"], f["y"]) for f in flags if f["net"] == net]
        if not pts:
            continue
        parts = [("w", w) for w in entry["wires"]] + [("v", v) for v in entry["vias"]]
        geom = [LineString(w[2]).buffer(w[1] / 2) if k == "w" and len(set(w[2])) > 1 else
                (Point(w[2][0]).buffer(w[1] / 2) if k == "w" else Point(w).buffer(c4.VIA_SIZE / 2)) for k, w in parts]
        layer = [w[0] if k == "w" else None for k, w in parts]
        parent = list(range(len(parts)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(parts)):
            for j in range(i + 1, len(parts)):
                if (layer[i] is None or layer[j] is None or layer[i] == layer[j]) and geom[i].intersects(geom[j]):
                    parent[find(i)] = find(j)
        bad = {find(i) for i in range(len(parts)) if any(geom[i].distance(p) < 0.02 for p in pts)}
        keep_w = [w for i, (k, w) in enumerate(parts) if k == "w" and find(i) not in bad]
        keep_v = [w for i, (k, w) in enumerate(parts) if k == "v" and find(i) not in bad]
        dropped += len(parts) - len(keep_w) - len(keep_v)
        entry["wires"], entry["vias"] = keep_w, keep_v
    return {n: e for n, e in copper.items() if e["wires"] or e["vias"]}, dropped


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fmt(v: float) -> str:
    return f"{v:g}"


def ripped_tstamps(board) -> set:
    """Base copper of RIP_NETS and ground copper touching the moved pads (old positions)."""
    def ref(fp):
        for g in fp.graphicItems:
            if getattr(g, "type", None) == "reference":
                return g.text
    pads = [(p.net.name if p.net else None, geo.pad_geometry(fp, p)) for fp in board.footprints
            if ref(fp) in MOVES for p in fp.pads]
    out = set()
    for net, kind, layer, g, raw in geo.items(board):
        body = g.buffer(raw.size / 2) if kind == "via" else g.buffer(raw.width / 2)
        if net in RIP_NETS or any(net == pn and body.intersects(pg) for pn, pg in pads):
            out.add(str(raw.tstamp))
    return out


def board_stage(base_text: str) -> tuple[str, dict]:
    text = c5.move_l1(base_text)
    for ref, ((x0, y0), (x1, y1)) in MOVES.items():
        i = text.index(f'(fp_text reference "{ref}"')
        s = text.rfind("\n  (footprint ", 0, i)
        old, new = f"\n    (at {fmt(x0)} {fmt(y0)})\n", f"\n    (at {fmt(x1)} {fmt(y1)})\n"
        assert text[s:i].count(old) == 1, ref
        text = text[:s] + text[s:i].replace(old, new) + text[i:]
    board, _ = geo.load(BOARD)
    rip = ripped_tstamps(board)
    lines = text.split("\n")
    kept = [line for line in lines if not (line.startswith(("  (segment ", "  (via "))
                                           and any(f"(tstamp {t})" in line for t in rip))]
    assert len(lines) - len(kept) == len(rip), "ripped items not found as single lines"
    return "\n".join(kept), {"moves": {k: [list(a), list(b)] for k, (a, b) in MOVES.items()},
                             "ripped_items": len(rip), "ripped_nets": sorted(RIP_NETS)}


def route_input(board) -> tuple[str, dict]:
    text, prep = arg.route_input_g()
    for ref, ((x0, y0), (x1, y1)) in MOVES.items():
        old = f"(place {ref} {x0 * 1000:.6f} {-y0 * 1000:.6f} "
        new = f"(place {ref} {x1 * 1000:.6f} {-y1 * 1000:.6f} "
        assert text.count(old) == 1, ref
        text = text.replace(old, new)
    rip = ripped_tstamps(board)
    coords = []
    for net, kind, layer, g, raw in geo.items(board):
        if str(raw.tstamp) in rip:
            coords.append((net, kind, [(round(x * 1000), round(-y * 1000)) for x, y in g.coords] if kind != "via"
                           else [(round(g.x * 1000), round(-g.y * 1000))]))
    lines, removed = text.split("\n"), 0
    start = next(i for i, line in enumerate(lines) if line.startswith("  (wiring"))
    keep = lines[:start + 1]
    for line in lines[start + 1:]:
        m = re.search(r"\(net \"?([^\s\")]+)\"?\)", line)
        if m and line.lstrip().startswith(("(wire", "(via")):
            nums = [round(float(v)) for v in re.findall(r"-?\d+(?:\.\d+)?", line.split("(net")[0].split(")")[0].split(" ", 3)[-1])]
            pts = set(zip(nums[0::2], nums[1::2]))
            if m.group(1) in RIP_NETS or any(m.group(1) == n and set(c) <= pts for n, k, c in coords):
                removed += 1
                continue
        keep.append(line)
    prep.update({"moves": {k: [list(a), list(b)] for k, (a, b) in MOVES.items()}, "removed_wiring": removed})
    return "\n".join(keep), prep


def route() -> dict:
    board, _ = geo.load(BOARD)
    text, prep = route_input(board)
    INPUT.write_text(text, encoding="utf-8")
    jar = Path("/tmp/freerouting-2.4.1.jar")
    if not jar.is_file():
        urllib.request.urlretrieve(arg.step2.JAR_URL, jar)
    assert sha256(jar) == arg.step2.JAR_SHA256
    started = time.time()
    try:
        done = subprocess.run([arg.step2.java25(), "-Xmx6g", "-jar", str(jar), "-de", str(INPUT), "-do", str(SES),
                               "-mp", str(PASSES), "--gui.enabled=false", "--router.fanout.enabled=true",
                               "--router.optimizer.enabled=false"], capture_output=True, text=True, timeout=TIME_LIMIT_S)
        rc, log = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as exc:
        rc, log = "timeout", (exc.stdout or b"").decode(errors="replace") + (exc.stderr or b"").decode(errors="replace")
    info = {"rc": rc, "seconds": round(time.time() - started), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in log.splitlines() if "Analytics" not in line and re.search(
                r"pass #|stage completed|error|exception", line, re.I)][-14:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    return info


def build(base_text: str) -> tuple[str, dict]:
    info = json.loads(LOG.read_text(encoding="utf-8"))
    assert info["session_sha256"] == sha256(SES)
    stage, stage_spec = board_stage(base_text)
    copper = c4.session_copy(SES.read_text(encoding="utf-8"), set(info["prep"]["not_autorouted"]))
    copper, dropped = drop_flagged(copper)
    stage_spec = dict(stage_spec, drc_dropped_items=dropped)
    number = {name: int(num) for num, name in re.findall(r'^  \(net (\d+) "([^"]*)"\)', stage, re.M)}
    seg_lines, via_lines = [], []
    for net in sorted(copper):
        n = number[net]
        for layer, width, pts in copper[net]["wires"]:
            for a, b in zip(pts, pts[1:]):
                if a != b:
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
    assert "\n".join(line for line in out if line not in added) == stage
    return "\n".join(out), dict(stage_spec, nets=len(copper), segments=len(seg_lines), vias=len(via_lines))


def main() -> int:
    if "--check" in sys.argv[1:]:
        summary = json.loads((OUT / "SUMMARY.json").read_text(encoding="utf-8"))
        if "candidate_sha256" in summary:  # no session -> only the log is recorded
            assert summary["candidate_sha256"] == sha256(OUT / f"{STEM}.kicad_pcb")
        print("PCB-MAIN fan-out P2: recorded")
        return 0
    g2.deps()
    assert sha256(BOARD) == BASE_SHA256
    OUT.mkdir(parents=True, exist_ok=True)
    info = json.loads(LOG.read_text(encoding="utf-8")) if (REJECTED_ITEMS.is_file() and SES.is_file()) else route()
    summary = {"schema": "dioneya-pcb-main-fanout-p2-v1", "measurement_only": True, "autoroute": info}
    if info["session_sha256"]:
        candidate, spec = build(BOARD.read_text(encoding="utf-8"))
        cand = OUT / f"{STEM}.kicad_pcb"
        cand.write_text(candidate, encoding="utf-8")
        summary.update(candidate_sha256=sha256(cand), delta=spec)
        work = ROOT / "hardware/kicad/native/_rP2_cand"
        shutil.rmtree(work, ignore_errors=True)
        shutil.copytree(ROOT / "hardware/kicad/native/PCB-MAIN", work)
        try:
            rel = work.relative_to(ROOT)
            shutil.copyfile(BOARD, work / "base.kicad_pcb")
            shutil.copyfile(cand, work / "candidate.kicad_pcb")
            for tag in ("base", "candidate"):
                shutil.copyfile(work / "PCB-MAIN.kicad_pro", work / f"{tag}.kicad_pro")
            stage = "tools/pcb_main_ground_domain_002_stage_rev_a.py"
            for tag in ("base", "candidate"):
                g2.docker("/usr/bin/python3", stage, "fill", f"{rel}/{tag}.kicad_pcb", f"{rel}/{tag}.kicad_pcb")
                g2.docker("kicad-cli", "pcb", "drc", "--format", "json", "--severity-all", "-o", f"{rel}/drc_{tag}.json",
                          f"{rel}/{tag}.kicad_pcb")
            g2.docker("/usr/bin/python3", stage, "dump", f"{rel}/candidate.kicad_pcb", f"{rel}/fills_candidate.json")
            g2.docker("chmod", "-R", "a+rwX", str(rel))
            reports = {t: json.loads((work / f"drc_{t}.json").read_text(encoding="utf-8")) for t in ("base", "candidate")}
            shutil.copyfile(work / "drc_candidate.json", OUT / "drc_candidate.json")
            (bfp, bunc), (cfp, cunc) = g2.drc_fingerprints(reports["base"]), g2.drc_fingerprints(reports["candidate"])
            new = sorted([list(k[:2]) + [list(k[2])] for k in cfp if cfp[k] > bfp.get(k, 0)])
            summary["drc"] = {"base_unconnected": bunc, "candidate_unconnected": cunc, "new_fingerprint_count": len(new),
                              "new_errors": sum(1 for k in new if k[0] == "error"),
                              "new_by_type": dict(Counter(f"{k[0]}:{k[1]}" for k in new))}
            fills = json.loads((work / "fills_candidate.json").read_text(encoding="utf-8"))
            board, domains = geo.load(cand)
            cmap = geo.continuity_map(board, domains, g2.filled_references(fills))
            summary["continuity_summary"] = {k: v["share"] for k, v in cmap["by_layer_domain"].items()}
        finally:
            g2.docker("rm", "-rf", str(work.relative_to(ROOT)))
            shutil.rmtree(work, ignore_errors=True)
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: summary.get(k) for k in ("candidate_sha256", "drc")}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
