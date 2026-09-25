#!/usr/bin/env python3
"""PCB-PWR current-carrying evidence for Review B R1 findings 1, 3, 6 and 8 (ECO-005 candidate).

Run by .github/workflows/ci-apply.yml. Reads a board (default: the ECO-005 candidate) and writes
CURRENT_EVIDENCE.json next to it. Everything is recomputed from the board file:

  cases      per power net and return domain: source pad(s), sink pad(s), stated current and its
             basis; finite-difference path resistance on F.Cu + B.Cu with vias
             (tools/pcb_return_resistance_rev_a.py), delta-U and loss at +70 C;
  narrow     EVERY track group narrower than 1.0 mm on a power or return net (same-net tracks
             joined through each other or through vias). EVERY segment of the group (>= 0.1 mm) gets
             a cut through its middle; the solver gives the share of the case current crossing each
             cut (Review B R2.001: one cut in the longest segment missed the loaded path when the
             longest segment was a dead-end branch - 1V8_MIC read 0 A). Per segment and case: current,
             resistance, delta-U, loss, the IPC-2221 external 10 C current for THAT segment's width
             (project screen: 2.03 mm -> 4.0 A) and the clamped-bar heating; the group reports the
             worst segment and the sum of delta-U / loss along its segments. Groups no longer than
             SHORT_MM are conduction-dominated (both ends in wider copper): heating is the clamped-bar
             value dT = J^2 rho L^2 / (8 k) over the whole group length, accepted up to 1 C.
             Self-check: a group touching both the source and the sink pad of a case must carry
             current in that case (assert_loaded_paths);
  hot_loop   buck VIN stubs: DC share plus the full input RMS ripple Iout*sqrt(D(1-D)) assumed to
             flow through the stub (upper bound: the bulk C12/C20-side capacitors carry most of it);
  via_group  finding 1 wall basis: 20 um nominal / 18 um project minimum average, 1.6 mm +10 %;
  nt_bridge  NetTie-2_SMD_Pad0.5mm bridge 1.0 x 0.5 mm: resistance bounds and bar-model heating;
  budget_3v3 3V3_DIGITAL load budget (PCB-MAIN parts) -> the J2.3/J2.4 current class.

--check verifies that the JSON belongs to the board it names, that every narrow segment was screened,
the loaded-path guard, and runs tools/test_pcb_pwr_current_evidence_rev_a.py (R2.001 regression).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-005/PCB-PWR_ECO_005_CANDIDATE_REV_A.kicad_pcb"
BASE_011 = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
BASE_011_SHA256 = "cc2c3c9faf9fd4c40108f0313a562ca0e66d0f8c6e837613958f098ac2373578"

RHO_20C = 1.724e-8
TEMP_70C = 1.197
RHO_70C = RHO_20C * TEMP_70C
T_CU_M = 35e-6
VIN_MIN_V, EFFICIENCY_MIN = 10.0, 0.85          # POWER_DESIGN_BASELINE_REV_A.json input.working_min_v
Q1_SOURCE = [("Q1", "1"), ("Q1", "2"), ("Q1", "3")]
Q1_DRAIN = [("Q1", "5"), ("Q1", "6"), ("Q1", "7"), ("Q1", "8")]
I_3V3_PEAK, I_3V3_CONT = 1.0, 0.35               # budget_3v3 envelope below

# (id, net, source, sink, current A, basis)
CASES = [
    ("input_fused", "VBAT_FUSED", ("F1", "2"), Q1_SOURCE, 5.0,
     "5 A qualification/protection envelope (POWER_DESIGN_CALC_REV_A.md section 1)"),
    ("input_protected", "VBAT_PROTECTED", Q1_DRAIN, ("RSH1", "1"), 5.0,
     "5 A envelope; path includes the Q1 -> RSH1 via groups of finding 1"),
    ("vin_3v8", "VBAT_SYS", ("RSH1", "2"), ("U3", "1"), 3.8 * 4.0 / (EFFICIENCY_MIN * VIN_MIN_V),
     "U3 DC input at 4 A out, 10.0 V in, 85 % efficiency"),
    ("vin_3v3", "VBAT_SYS", ("RSH1", "2"), ("U4", "1"), 3.3 * 4.0 / (EFFICIENCY_MIN * VIN_MIN_V),
     "U4 DC input at 4 A out (rail rating), 10.0 V in, 85 % efficiency"),
    ("sw_3v8", "SW_3V8", ("U3", "3"), ("L1", "1"), 4.75,
     "4 A + half the 1.50 A p-p ripple at 14.6 V (POWER_DESIGN_CALC_REV_A.md)"),
    ("sw_3v3", "SW_3V3", ("U4", "3"), ("L2", "1"), 4.68,
     "4 A + half the 1.36 A p-p ripple at 14.6 V (POWER_DESIGN_CALC_REV_A.md)"),
    ("out_3v8", "3V8_MODEM", ("L1", "2"), ("J2", "1"), 3.3,
     "BG95-M3 0.6 A VBAT_BB + 2.7 A VBAT_RF peaks (PCB_MAIN_POWER_INTEGRITY_CALC_REV_A.md)"),
    ("out_3v3", "3V3_DIGITAL", ("L2", "2"), ("J2", "3"), I_3V3_PEAK, "3V3_DIGITAL budget envelope (budget_3v3)"),
    ("ldo_in", "3V3_DIGITAL", ("L2", "2"), ("U5", "1"), 0.3, "TPS7A20 rating"),
    ("out_1v8", "1V8_MIC", ("U5", "5"), ("J2", "5"), 0.3, "TPS7A20 rating"),
    ("ret_modem", "GND_MODEM", ("J2", "2"), ("NT1", "1"), 3.3, "return of out_3v8"),
    ("ret_digital", "GND_DIGITAL", ("J2", "4"), ("NT2", "1"), I_3V3_PEAK, "return of out_3v3"),
    ("ret_mic", "GND_MIC", ("J2", "6"), ("NT3", "1"), 0.3, "return of out_1v8"),
]
SHORT_MM, BAR_LIMIT_C, K_CU = 2.0, 1.0, 390.0
HOT_LOOP = {"U3": (3.8, 4.0), "U4": (3.3, 4.0)}   # regulator: (Vout, Iout) for the VIN-stub RMS bound

# finding 1: via barrel, mean diameter 0.3 mm (the reviewer's formula), resistance at +70 C
VIA_CASES = [("nominal", 20e-6, 1.6e-3), ("min_wall", 18e-6, 1.6e-3), ("min_wall_thick_board", 18e-6, 1.76e-3)]

# 3V3_DIGITAL consumers (PCB-MAIN, MAIN_COMPONENT_FREEZE_REV_A.csv): peak / continuous allowances, mA
BUDGET_3V3 = [
    ("U1", "STM32U585VIT6Q", 50, 30, "continuous", "allowance above the 160 MHz run mode; measure"),
    ("U10", "E22-900M22S", 120, 7, "TX burst = LoRa time on air (up to ~2 s at SF12), duty-cycle limited",
     "Ebyte E22-900M(M)22S specification: TX 119 mA instantaneous, RX 6.8 mA"),
    ("U9", "MAX-M10S-00B", 100, 30, "start-up inrush (ms)", "EVT_PRE_20_POWER_ARCHITECTURE.md: 100 mA start-up"),
    ("U11", "MDBT50Q-P1MV2", 25, 10, "BLE TX events", "allowance; measure"),
    ("U12", "SDCIT2/32GB", 200, 100, "write bursts; continuous logging allowance",
     "SD high-speed-mode card limit (3.3 V signalling, no UHS); vendor gives no figure; measure"),
    ("U2", "W25Q512JVFIQ", 25, 5, "program/erase", "allowance; measure"),
    ("misc", "sensors, translators, SIM mux, pull-ups", 10, 10, "continuous", "allowance"),
    ("U5 (PCB-PWR)", "TPS7A2018 -> 1V8_MIC (4x T5838, U7/U18 VCCA)", 300, 10, "LDO rating as the peak envelope",
     "TPS7A20 300 mA rating; realistic load a few mA"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deps() -> None:
    try:
        import kiutils  # noqa: F401
        import scipy.sparse  # noqa: F401
        import shapely  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "kiutils", "shapely>=2", "numpy", "scipy"],
                       check=True)


def ipc2221_external_a(width_mm: float, delta_t: float = 10.0) -> float:
    area_mil2 = (width_mm / 0.0254) * (T_CU_M / 25.4e-6)
    return 0.048 * delta_t ** 0.44 * area_mil2 ** 0.725


def via_barrel_ohm(wall_m: float, length_m: float) -> float:
    return RHO_70C * length_m / (math.pi * 0.3e-3 * wall_m)


def net_window(board, net: str) -> tuple:
    names = {n.number: n.name for n in board.nets}
    xs, ys = [], []
    for item in board.traceItems:
        if names.get(item.net) != net:
            continue
        pts = [item.position] if type(item).__name__ == "Via" else [item.start, item.end]
        xs += [p.X for p in pts]
        ys += [p.Y for p in pts]
    for zone in board.zones:
        if zone.netName == net:
            for f in zone.filledPolygons or []:
                xs += [c.X for c in f.coordinates]
                ys += [c.Y for c in f.coordinates]
    for fp in board.footprints:
        if any(p.net and p.net.name == net for p in fp.pads):
            xs.append(fp.position.X)
            ys.append(fp.position.Y)
    return (min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5)


def narrow_groups(board, net: str) -> list[dict]:
    from shapely.geometry import LineString, Point

    names = {n.number: n.name for n in board.nets}
    segs = [(item.layer, item.width, LineString([(item.start.X, item.start.Y), (item.end.X, item.end.Y)]))
            for item in board.traceItems
            if type(item).__name__ != "Via" and names.get(item.net) == net and item.width < 1.0]
    vias = [Point(v.position.X, v.position.Y) for v in board.traceItems
            if type(v).__name__ == "Via" and names.get(v.net) == net]
    parent = list(range(len(segs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, (la, _, ga) in enumerate(segs):
        for j in range(i + 1, len(segs)):
            lb, _, gb = segs[j]
            joined = (la == lb and ga.distance(gb) < 1e-3) or (
                la != lb and any(v.distance(ga) < 1e-3 and v.distance(gb) < 1e-3 for v in vias))
            if joined:
                parent[find(i)] = find(j)
    groups: dict = {}
    for i, seg in enumerate(segs):
        groups.setdefault(find(i), []).append(seg)
    sys.path.insert(0, str(ROOT / "tools"))
    from pcb_return_resistance_rev_a import _pad_geometry, _reference

    pads = [(f"{_reference(fp)}.{p.number}", _pad_geometry(fp, p)) for fp in board.footprints for p in fp.pads
            if p.net and p.net.name == net]
    out = []
    for members in groups.values():
        length = sum(g.length for _, _, g in members)
        width = min(w for _, w, _ in members)
        entry = {"layers": sorted({m[0] for m in members}), "segments": len(members),
                 "length_mm": round(length, 3), "min_width_mm": round(width, 4),
                 "pads": sorted({name for name, geom in pads if any(geom.distance(g) < 1e-3 for _, _, g in members)}),
                 "probes": [], "short_segments": []}
        for layer, w_seg, seg in sorted(members, key=lambda m: (m[0], m[2].coords[0], m[2].coords[-1])):
            if seg.length < 0.1:  # pad neck / joint: too short for a cut, screened with the group bound
                entry["short_segments"].append({"layer": layer, "width_mm": round(w_seg, 4),
                                                "length_mm": round(seg.length, 4)})
                continue
            (ax, ay), (bx, by) = seg.coords[0], seg.coords[-1]
            mx, my, d = (ax + bx) / 2, (ay + by) / 2, seg.length
            nx, ny, half = -(by - ay) / d, (bx - ax) / d, w_seg / 2 + 0.03
            entry["probes"].append({"layer": layer, "at_mm": [round(mx, 3), round(my, 3)],
                                    "segment_width_mm": round(w_seg, 4), "segment_length_mm": round(d, 3),
                                    "line": [[mx - nx * half, my - ny * half], [mx + nx * half, my + ny * half]]})
        out.append(entry)
    return sorted(out, key=lambda e: (-e["length_mm"]))


def segment_status(i_seg: float, width_mm: float, group_length_mm: float) -> tuple[str, float, float | None]:
    """Screen one segment: (status, IPC-2221 10 C current for its width, bar heating over the group).
    The clamped-bar model holds only for groups no longer than SHORT_MM (both ends in wider copper);
    for longer groups it is not applicable (None) and the IPC screen alone decides."""
    ipc = ipc2221_external_a(width_mm)
    bar = None
    if group_length_mm <= SHORT_MM:
        j = i_seg / (width_mm * 1e-3 * T_CU_M)
        bar = j ** 2 * RHO_70C * (group_length_mm * 1e-3) ** 2 / (8 * K_CU)
    if i_seg <= ipc:
        return "PASS", ipc, bar
    if bar is not None and bar <= BAR_LIMIT_C:
        return "PASS_SHORT_CONDUCTION", ipc, bar
    return "REVIEW", ipc, bar


STATUS_ORDER = {"PASS": 0, "PASS_SHORT_CONDUCTION": 1, "REVIEW": 2}


def summarise_group(group: dict, case_currents: dict, bound_a: float) -> dict:
    """case_currents: {case: [current of probe k, ...]} -> worst segment, per-case sums, status.
    Segments shorter than 0.1 mm carry no cut: each is screened at its own width with the largest
    current measured in the group, or with bound_a (largest case current of the net) when the
    group has no cut at all - never with zero. Pure function (no board), covered by
    tools/test_pcb_pwr_current_evidence_rev_a.py."""
    probes = group["probes"]
    segments = []
    for k, probe in enumerate(probes):
        w, l = probe["segment_width_mm"], probe["segment_length_mm"]
        r = RHO_70C * l * 1e-3 / (w * 1e-3 * T_CU_M)
        case, i_seg = max(((c, cur[k]) for c, cur in case_currents.items()), key=lambda t: t[1], default=(None, 0.0))
        status, ipc, bar = segment_status(i_seg, w, group["length_mm"])
        segments.append({"layer": probe["layer"], "at_mm": probe["at_mm"], "width_mm": w, "length_mm": l,
                         "worst_case": case, "i_a": round(i_seg, 4), "r_mohm_70c": round(r * 1e3, 3),
                         "ipc2221_10c_a": round(ipc, 3), "bar_delta_t_c": None if bar is None else round(bar, 4),
                         "status": status})
    measured = max((s["i_a"] for s in segments), default=None)
    i_short, basis = (measured, "GROUP_MAX_MEASURED") if segments else (bound_a, "NET_CASE_BOUND_NO_CUT")
    for short in group["short_segments"]:
        status, ipc, bar = segment_status(i_short, short["width_mm"], group["length_mm"])
        r = RHO_70C * short["length_mm"] * 1e-3 / (short["width_mm"] * 1e-3 * T_CU_M)
        segments.append({"layer": short["layer"], "at_mm": None, "width_mm": short["width_mm"],
                         "length_mm": short["length_mm"], "worst_case": None, "i_a": round(i_short, 4),
                         "current_basis": basis, "r_mohm_70c": round(r * 1e3, 4),
                         "ipc2221_10c_a": round(ipc, 3), "bar_delta_t_c": None if bar is None else round(bar, 4),
                         "status": status})
    per_case = []
    for c, cur in case_currents.items():
        du = sum(cur[k] * segments[k]["r_mohm_70c"] for k in range(len(probes)))
        p = sum(cur[k] ** 2 * segments[k]["r_mohm_70c"] for k in range(len(probes)))
        per_case.append({"case": c, "i_max_a": round(max(cur, default=0.0), 4),
                         "du_mv_along_segments": round(du, 3), "p_mw_along_segments": round(p, 3)})
    worst = max(segments, key=lambda s: (STATUS_ORDER[s["status"]], s["i_a"]), default=None)
    return {"segments_detail": segments, "cases": per_case,
            "worst_segment": worst, "i_branch_a": max((s["i_a"] for s in segments), default=0.0),
            "status": worst["status"] if worst else "PASS",
            "du_mv": max((c["du_mv_along_segments"] for c in per_case), default=0.0),
            "p_mw": max((c["p_mw_along_segments"] for c in per_case), default=0.0)}


def assert_loaded_paths(result: dict) -> list:
    """R2.001 regression guard: a narrow group that touches both the source and the sink pad of a
    case lies on that case's path and must carry current in it. Returns the checked rows."""
    rows = []
    for case in result["cases"]:
        ends_src, ends_snk = set(case["from"].split("+")), set(case["to"].split("+"))
        for g in result["narrow"]:
            if g["net"] != case["net"] or not (ends_src & set(g["pads"]) and ends_snk & set(g["pads"])):
                continue
            i_max = next(c["i_max_a"] for c in g["cases"] if c["case"] == case["id"])
            rows.append({"case": case["id"], "net": case["net"], "group_pads": g["pads"],
                         "case_current_a": case["current_a"], "group_i_max_a": i_max})
            assert i_max >= 0.01 * case["current_a"], (
                f"{case['id']}: narrow group {g['pads']} joins source and sink but reads {i_max} A")
    return rows


def evaluate(board_path: Path) -> dict:
    from kiutils.board import Board

    sys.path.insert(0, str(ROOT / "tools"))
    from pcb_return_resistance_rev_a import resistance

    board = Board.from_file(str(board_path))
    result = {"schema": "dioneya-pcb-pwr-current-evidence-v2", "board": str(board_path.relative_to(ROOT)),
              "board_sha256": sha256(board_path),
              "basis": {"outer_copper_um": 35, "rho_20c": RHO_20C, "temperature_factor_70c": TEMP_70C,
                        "via_70c_mohm_in_network": 1.75093, "cell_mm": 0.05,
                        "narrow_screen": "IPC-2221 external, delta-T 10 C (2.03 mm -> 4.0 A: project screen)",
                        "manufacturing_release": False},
              "cases": [], "narrow": [], "hot_loop": []}
    by_net: dict = {}
    for case_id, net, source, sink, amps, basis in CASES:
        by_net.setdefault(net, []).append((case_id, source, sink, amps, basis))
    for net, cases in by_net.items():
        window = net_window(board, net)
        groups = narrow_groups(board, net)
        probes = [(f"g{i}s{k}", p["layer"], p["line"]) for i, g in enumerate(groups) for k, p in enumerate(g["probes"])]
        case_currents = [dict() for _ in groups]
        for case_id, source, sink, amps, basis in cases:
            solved = resistance(str(board_path), net, source, sink, window, probes=probes)
            r = solved["r_mohm_70c"] / 1e3
            row = {"id": case_id, "net": net, "from": solved["from"], "to": solved["to"], "current_a": round(amps, 3),
                   "basis": basis, "vias_in_window": solved["vias_in_path_region"], "r_mohm_70c": solved["r_mohm_70c"],
                   "du_mv_70c": round(amps * r * 1e3, 2), "p_mw_70c": round(amps ** 2 * r * 1e3, 2)}
            if case_id == "input_protected":
                worst = resistance(str(board_path), net, source, sink, window,
                                   r_via_ohm=via_barrel_ohm(18e-6, 1.76e-3))
                row["r_mohm_70c_min_wall_thick_board"] = worst["r_mohm_70c"]
                row["du_mv_70c_min_wall_thick_board"] = round(amps * worst["r_mohm_70c"], 2)
            result["cases"].append(row)
            shares = solved.get("current_share", {})
            for i, g in enumerate(groups):
                case_currents[i][case_id] = [shares.get(f"g{i}s{k}", 0.0) * amps for k in range(len(g["probes"]))]
        for i, g in enumerate(groups):
            summary = summarise_group(g, case_currents[i], max(c[3] for c in cases))
            worst = summary["worst_segment"]
            r_branch = RHO_70C * g["length_mm"] * 1e-3 / (g["min_width_mm"] * 1e-3 * T_CU_M)
            g.update({"net": net, "probed_segments": len(g["probes"]), "cases": summary["cases"],
                      "segments_detail": summary["segments_detail"],
                      "worst_case": worst["worst_case"] if worst else None,
                      "worst_segment": {k: worst[k] for k in ("layer", "at_mm", "width_mm", "length_mm", "i_a",
                                                              "ipc2221_10c_a", "bar_delta_t_c", "status")} if worst else None,
                      "i_branch_a": summary["i_branch_a"], "r_branch_mohm_70c": round(r_branch * 1e3, 3),
                      "du_mv": summary["du_mv"], "p_mw": summary["p_mw"],
                      "ipc2221_10c_a_min_width": round(ipc2221_external_a(g["min_width_mm"]), 3),
                      "status": summary["status"]})
            stub_probes = g.pop("probes")
            result["narrow"].append(g)
            for reg, (vout, iout) in HOT_LOOP.items():
                if net == "VBAT_SYS" and f"{reg}.1" in g["pads"] and g["length_mm"] > 1.0:
                    duty = vout / VIN_MIN_V
                    i_ac = iout * math.sqrt(duty * (1 - duty))
                    case_id = f"vin_{'3v8' if reg == 'U3' else '3v3'}"
                    k_dc = max(range(len(stub_probes)), key=lambda k: case_currents[i][case_id][k])
                    i_dc = round(case_currents[i][case_id][k_dc], 4)
                    i_rms = math.hypot(i_dc, i_ac)
                    w_seg, l_seg = stub_probes[k_dc]["segment_width_mm"], stub_probes[k_dc]["segment_length_mm"]
                    r_seg = RHO_70C * l_seg * 1e-3 / (w_seg * 1e-3 * T_CU_M)
                    j_seg = i_rms / (w_seg * 1e-3 * T_CU_M)
                    bar = j_seg ** 2 * RHO_70C * (l_seg * 1e-3) ** 2 / (8 * K_CU)
                    ipc = ipc2221_external_a(w_seg)
                    result["hot_loop"].append({
                        "regulator": reg, "stub_pads": g["pads"], "stub_width_mm": w_seg, "stub_length_mm": l_seg,
                        "i_dc_a": i_dc, "i_ac_rms_bound_a": round(i_ac, 3), "i_rms_bound_a": round(i_rms, 3),
                        "r_stub_mohm_70c": round(r_seg * 1e3, 3), "p_mw_bound": round(i_rms ** 2 * r_seg * 1e3, 2),
                        "ipc2221_10c_a": round(ipc, 3), "bar_delta_t_c": round(bar, 3),
                        "status": "PASS" if i_rms <= ipc else (
                            "PASS_SHORT_CONDUCTION" if l_seg <= SHORT_MM and bar <= BAR_LIMIT_C else "REVIEW")})
    result["via_group"] = []
    for label, wall, length in VIA_CASES:
        r_via = via_barrel_ohm(wall, length)
        group = 2 * r_via / 7
        result["via_group"].append({"case": label, "wall_um": wall * 1e6, "length_mm": length * 1e3,
                                    "r_via_mohm_70c": round(r_via * 1e3, 4), "r_7plus7_mohm_70c": round(group * 1e3, 4),
                                    "du_mv_5a": round(5 * group * 1e3, 2), "p_mw_5a": round(25 * group * 1e3, 2)})
    bridge = []
    for tie, amps in (("NT1", 3.3), ("NT2", I_3V3_PEAK), ("NT3", 0.3)):
        for label, length in (("pad_edge_to_edge", 0.5e-3), ("pad_centre_to_centre", 1.0e-3)):
            area = 0.5e-3 * T_CU_M
            r = RHO_70C * length / area
            j = amps / area
            bridge.append({"tie": tie, "current_a": amps, "length_case": label, "r_mohm_70c": round(r * 1e3, 3),
                           "du_mv": round(amps * r * 1e3, 2), "p_mw": round(amps ** 2 * r * 1e3, 2),
                           "bar_model_delta_t_c": round(j ** 2 * RHO_70C * length ** 2 / (8 * K_CU), 3)})
    result["nt_bridge"] = bridge
    peak = sum(row[2] for row in BUDGET_3V3)
    cont = sum(row[3] for row in BUDGET_3V3)
    fwd = next(c for c in result["cases"] if c["id"] == "out_3v3")["r_mohm_70c"]
    ret = next(c for c in result["cases"] if c["id"] == "ret_digital")["r_mohm_70c"]
    result["budget_3v3"] = {
        "rows": [dict(zip(("ref", "part", "i_peak_ma", "i_cont_ma", "duration", "source"), row)) for row in BUDGET_3V3],
        "sum_peak_ma": peak, "sum_cont_ma": cont, "envelope_peak_a": I_3V3_PEAK, "envelope_cont_a": I_3V3_CONT,
        "r_forward_plus_return_mohm_70c": round(fwd + ret, 3),
        "du_peak_mv": round(I_3V3_PEAK * (fwd + ret), 2), "du_cont_mv": round(I_3V3_CONT * (fwd + ret), 2),
        "note": "regulation point is U4 (fixed 3.3 V, FB at the output); the J2 drop is uncompensated"}
    if board_path.resolve() != BASE_011.resolve() and sha256(BASE_011) == BASE_011_SHA256:
        result["returns_base_011"] = []
        for case_id, net, source, sink, amps, _ in CASES:
            if case_id.startswith("ret_"):
                base = Board.from_file(str(BASE_011))
                solved = resistance(str(BASE_011), net, source, sink, net_window(base, net))
                result["returns_base_011"].append({"id": case_id, "r_mohm_70c": solved["r_mohm_70c"],
                                                   "du_mv_70c": round(amps * solved["r_mohm_70c"], 2)})
    result["narrow_review"] = [g for g in result["narrow"] if g["status"] == "REVIEW"]
    result["loaded_path_check"] = assert_loaded_paths(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", default=str(DEFAULT_BOARD))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    board = Path(args.board).resolve()
    out = board.parent / "CURRENT_EVIDENCE.json"
    if args.check:
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["board_sha256"] == sha256(board), "CURRENT_EVIDENCE.json does not belong to the board"
        assert data["schema"] == "dioneya-pcb-pwr-current-evidence-v2", "evidence predates the R2.001 per-segment fix"
        assert all(g["probed_segments"] + len(g["short_segments"]) == g["segments"] for g in data["narrow"]), \
            "a narrow segment was neither probed nor screened as short"
        assert all(len(g["segments_detail"]) == g["segments"] for g in data["narrow"]), "segment screen incomplete"
        assert_loaded_paths(data)
        import test_pcb_pwr_current_evidence_rev_a as regression  # R2.001 regression tests
        regression.main()
        print(f"current evidence: {len(data['cases'])} cases, {len(data['narrow'])} narrow groups, "
              f"{len(data['narrow_review'])} for review")
        return 0
    deps()
    data = evaluate(board)
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=float) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(data["cases"]), "narrow": len(data["narrow"]),
                      "narrow_review": data["narrow_review"]}, default=float)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
