"""Compare native KiCad routing with diagnostic Altium PcbDoc OLE streams.

Requires olefile 0.47. This verifies only routed line segments, board net names,
and object counts. It does not establish manufacturing equivalence.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import json
import re
import struct

import olefile


ALTIUM_UNITS_PER_MM = 393700.7874015748
BOARD_TRANSFORMS = {
    "PCB-MAIN": (3.685, 75.025),
    "PCB-PWR": (0.0, 60.0),
    "PCB-MIC": (0.0, 22.0),
}
EXPECTED_LAYER = {
    "F.Cu": 1,
    "In1.Cu": 2,
    "In2.Cu": 3,
    "In3.Cu": 4,
    "In4.Cu": 5,
    "B.Cu": 32,
}
SEGMENT = re.compile(
    r'\(segment\s+\(start\s+([-\d.]+)\s+([-\d.]+)\)\s+'
    r'\(end\s+([-\d.]+)\s+([-\d.]+)\)\s+'
    r'\(width\s+([-\d.]+)\)\s+'
    r'(?:\(locked\s+yes\)\s+)?'
    r'\(layer\s+"([^"]+)"\)\s+\(net\s+(\d+)\)',
    re.S,
)
VIA = re.compile(
    r'\(via\s+\(at\s+([-\d.]+)\s+([-\d.]+)\)\s+'
    r'\(size\s+([-\d.]+)\)\s+\(drill\s+([-\d.]+)\)\s+'
    r'\(layers\s+"([^"]+)"\s+"([^"]+)"\)\s+'
    r'(?:\(locked\s+yes\)\s+)?\(net\s+(\d+)\)',
    re.S,
)


def count_header(doc: olefile.OleFileIO, stream: str) -> int:
    return struct.unpack("<I", doc.openstream([stream, "Header"]).read())[0]


def altium_nets(doc: olefile.OleFileIO) -> list[str]:
    data = doc.openstream(["Nets6", "Data"]).read()
    result = []
    offset = 0
    while offset < len(data):
        size = struct.unpack_from("<I", data, offset)[0]
        record = data[offset + 4 : offset + 4 + size].decode("latin1")
        match = re.search(r"\|NAME=([^|]*)", record)
        if not match:
            raise ValueError("Altium net record has no NAME")
        result.append(match.group(1))
        offset += 4 + size
    if len(result) != count_header(doc, "Nets6"):
        raise ValueError("Altium net stream count mismatch")
    return result


def route_key(x1: float, y1: float, x2: float, y2: float, width: float, net: str):
    endpoints = tuple(sorted(((round(x1, 4), round(y1, 4)), (round(x2, 4), round(y2, 4)))))
    return (endpoints, round(width, 4), net)


def source_routes(board: Path, dx: float, y_sum: float):
    source = board.read_text(encoding="utf-8")
    header = source.split("(footprint", 1)[0]
    names = {int(i): name for i, name in re.findall(r'(?m)^\s*\(net\s+(\d+)\s+"([^"]*)"\)', header)}
    routes = Counter()
    for x1, y1, x2, y2, width, layer, index in SEGMENT.findall(source):
        key = route_key(float(x1) + dx, y_sum - float(y1), float(x2) + dx, y_sum - float(y2), float(width), names[int(index)])
        routes[(key, layer)] += 1
    if sum(routes.values()) != source.count("(segment"):
        raise ValueError(f"Only parsed {sum(routes.values())}/{source.count('(segment')} source segments")
    vias = Counter()
    for x, y, size, drill, start_layer, end_layer, index in VIA.findall(source):
        key = (round(float(x) + dx, 4), round(y_sum - float(y), 4), round(float(size), 4), round(float(drill), 4), names[int(index)])
        vias[(key, start_layer, end_layer)] += 1
    if sum(vias.values()) != len(re.findall(r"\(via\s+\(at", source)):
        raise ValueError("Some source vias were not parsed")
    counts = {
        "components": len(re.findall(r'(?m)^\s*\(footprint\b', source)),
        "pads": len(re.findall(r'(?m)^\s*\(pad\b', source)),
        "vias": len(re.findall(r'(?m)^\s*\(via\b', source)),
        "zones": len(re.findall(r'(?m)^\s*\(zone\b', source)),
    }
    return routes, vias, set(names.values()) - {""}, counts


def imported_routes(doc: olefile.OleFileIO, names: list[str]):
    data = doc.openstream(["Tracks6", "Data"]).read()
    if len(data) % 54 or len(data) // 54 != count_header(doc, "Tracks6"):
        raise ValueError("Unexpected Altium Tracks6 record length/count")
    routes = Counter()
    for offset in range(0, len(data), 54):
        record = data[offset : offset + 54]
        if record[0] != 4 or struct.unpack_from("<I", record, 1)[0] != 49:
            raise ValueError("Unexpected Altium track record format")
        net = struct.unpack_from("<H", record, 8)[0]
        if net == 65535:
            continue
        if net >= len(names):
            raise ValueError(f"Track references invalid net {net}")
        x1, y1, x2, y2, width = (struct.unpack_from("<i", record, i)[0] / ALTIUM_UNITS_PER_MM for i in (18, 22, 26, 30, 34))
        routes[(route_key(x1, y1, x2, y2, width, names[net]), record[5])] += 1
    return routes


def imported_vias(doc: olefile.OleFileIO, names: list[str]):
    data = doc.openstream(["Vias6", "Data"]).read()
    vias = Counter()
    offset = 0
    while offset < len(data):
        if data[offset] != 3:
            raise ValueError("Unexpected Altium via record type")
        length = struct.unpack_from("<I", data, offset + 1)[0]
        record = data[offset : offset + 5 + length]
        if len(record) != 5 + length:
            raise ValueError("Truncated Altium via record")
        net = struct.unpack_from("<H", record, 8)[0]
        if net == 65535 or net >= len(names):
            raise ValueError(f"Via references invalid net {net}")
        x, y, diameter, drill = (round(struct.unpack_from("<i", record, i)[0] / ALTIUM_UNITS_PER_MM, 4) for i in (18, 22, 26, 30))
        vias[((x, y, diameter, drill, names[net]), record[34], record[35])] += 1
        offset += 5 + length
    if sum(vias.values()) != count_header(doc, "Vias6"):
        raise ValueError("Altium via stream count mismatch")
    return vias


def summarize_vias(source: Counter, imported: Counter):
    source_any = Counter()
    imported_any = Counter()
    expected = Counter()
    for (key, start_layer, end_layer), count in source.items():
        source_any[key] += count
        expected[(key, EXPECTED_LAYER[start_layer], EXPECTED_LAYER[end_layer])] += count
    for (key, start_layer, end_layer), count in imported.items():
        imported_any[key] += count
    return {
        "source_via_count": sum(source.values()),
        "imported_via_count": sum(imported.values()),
        "position_diameter_drill_net_matches": sum((source_any & imported_any).values()),
        "correct_layer_span": sum((expected & imported).values()),
        "incorrect_layer_span": sum((expected - imported).values()),
        "imported_layer_spans": {f"{start}-{end}": sum(count for (key, a, b), count in imported.items() if (a, b) == (start, end)) for key, start, end in imported},
    }


def summarize(source: Counter, imported: Counter, limit=5):
    source_any = Counter()
    imported_any = Counter()
    source_expected = Counter()
    for (key, layer), count in source.items():
        source_any[key] += count
        source_expected[(key, EXPECTED_LAYER[layer])] += count
    for (key, layer), count in imported.items():
        imported_any[key] += count
    missing = source_any - imported_any
    added = imported_any - source_any
    wrong_layer = source_expected - imported
    return {
        "source_route_count": sum(source.values()),
        "imported_route_count": sum(imported.values()),
        "geometry_width_net_matches": sum((source_any & imported_any).values()),
        "source_routes_missing": sum(missing.values()),
        "imported_routes_extra": sum(added.values()),
        "correct_copper_layer": sum((source_expected & imported).values()),
        "incorrect_copper_layer": sum(wrong_layer.values()),
        "source_layers": dict(sorted(Counter({layer: sum(n for (key, lay), n in source.items() if lay == layer) for key, layer in source}).items())),
        "imported_layers": dict(sorted(Counter({str(layer): sum(n for (key, lay), n in imported.items() if lay == layer) for key, layer in imported}).items())),
        "missing_examples": [str(key) for key in list(missing)[:limit]],
        "wrong_layer_examples": [str(key) for key in list(wrong_layer)[:limit]],
    }


def check_board(root: Path, board: str, pcb_dir: Path, pcb_file: Path | None = None):
    dx, y_sum = BOARD_TRANSFORMS[board]
    routes, source_vias, nets, counts = source_routes(root / "hardware/kicad/native" / board / f"{board}.kicad_pcb", dx, y_sum)
    path = pcb_file or pcb_dir / board / f"{board}.PcbDoc"
    with olefile.OleFileIO(str(path)) as doc:
        imported_names = altium_nets(doc)
        imported = imported_routes(doc, imported_names)
        vias = imported_vias(doc, imported_names)
        result = summarize(routes, imported)
        result.update({
            "source_board": str(Path("hardware/kicad/native") / board / f"{board}.kicad_pcb").replace("\\", "/"),
            "imported_board": str(path.relative_to(root) if path.is_relative_to(root) else path).replace("\\", "/"),
            "transform": {"x_offset_mm": dx, "y_reflection_sum_mm": y_sum},
            "source_counts": counts,
            "imported_counts": {"components": count_header(doc, "Components6"), "pads": count_header(doc, "Pads6"), "vias": count_header(doc, "Vias6"), "polygons": count_header(doc, "Polygons6")},
            "net_name_sets_equal": nets == set(imported_names),
            "source_net_count": len(nets),
            "imported_net_count": len(imported_names),
            "vias": summarize_vias(source_vias, vias),
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--pcb-dir", type=Path)
    parser.add_argument("--board", choices=BOARD_TRANSFORMS)
    parser.add_argument("--pcb-file", type=Path, help="An alternate PcbDoc for one selected board")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    pcb_dir = args.pcb_dir or root / "hardware/altium/diagnostic-import"
    if args.pcb_file and not args.board:
        parser.error("--pcb-file requires --board")
    boards = (args.board,) if args.board else BOARD_TRANSFORMS
    report = {board: check_board(root, board, pcb_dir, args.pcb_file) for board in boards}
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
