"""Compare KiCad and Altium PCB pads after a KiCad Import Wizard conversion.

Run with KiCad's bundled Python and olefile. The comparison covers component
reference, pad number, net, absolute position, size, and drill axes. It does not
cover copper shape, layers, mask expansion, or schematic parity.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct

import olefile
import pcbnew


UNITS_PER_MM = 393700.7874015748
TRANSFORMS = {
    "PCB-MAIN": (3.685, 75.025),
    "PCB-PWR": (0.0, 60.0),
    "PCB-MIC": (0.0, 22.0),
}
TOLERANCE_MM = 0.00025


def altium_nets(doc: olefile.OleFileIO) -> list[str]:
    data = doc.openstream(["Nets6", "Data"]).read()
    names = []
    offset = 0
    while offset < len(data):
        length = struct.unpack_from("<I", data, offset)[0]
        record = data[offset + 4 : offset + 4 + length].decode("latin1")
        fields = dict(part.split("=", 1) for part in record.split("|") if "=" in part)
        names.append(fields["NAME"])
        offset += 4 + length
    return names


def source_pads(path: Path, board_name: str) -> tuple[list[dict], list[dict]]:
    board = pcbnew.LoadBoard(str(path))
    dx, y_sum = TRANSFORMS[board_name]
    result = []
    components = []
    for footprint in board.GetFootprints():
        origin = footprint.GetPosition()
        components.append({
            "refdes": footprint.GetReference(),
            "x": origin.x / 1e6 + dx,
            "y": y_sum - origin.y / 1e6,
        })
        for pad in footprint.Pads():
            position = pad.GetPosition()
            size = pad.GetSize()
            drill = pad.GetDrillSize()
            result.append({
                "refdes": footprint.GetReference(),
                "number": pad.GetNumber(),
                "net": pad.GetNetname(),
                "x": position.x / 1e6 + dx,
                "y": y_sum - position.y / 1e6,
                "size": (size.x / 1e6, size.y / 1e6),
                "drill": tuple(sorted((drill.x / 1e6, drill.y / 1e6))),
            })
    return result, components


def imported_components(doc: olefile.OleFileIO, source: list[dict]) -> list[str]:
    data = doc.openstream(["Components6", "Data"]).read()
    offset = 0
    result = []
    remaining = source.copy()
    while offset < len(data):
        length = struct.unpack_from("<I", data, offset)[0]
        record = data[offset + 4 : offset + 4 + length].decode("latin1")
        fields = dict(part.split("=", 1) for part in record.split("|") if "=" in part)
        x = float(fields["X"].removesuffix("mil")) * 0.0254
        y = float(fields["Y"].removesuffix("mil")) * 0.0254
        match = next((item for item in remaining if close(x, item["x"]) and close(y, item["y"])), None)
        if match is None:
            raise ValueError(f"No unique source component at imported position {(x, y)}")
        remaining.remove(match)
        result.append(match["refdes"])
        offset += 4 + length
    expected_count = struct.unpack("<I", doc.openstream(["Components6", "Header"]).read())[0]
    if len(result) != expected_count or remaining:
        raise ValueError("Component count or origin mismatch")
    return result


def imported_pads(path: Path, source_components: list[dict]) -> list[dict]:
    with olefile.OleFileIO(str(path)) as doc:
        names = altium_nets(doc)
        components = imported_components(doc, source_components)
        data = doc.openstream(["Pads6", "Data"]).read()
        result = []
        offset = 0
        while offset < len(data):
            if data[offset] != 2:
                raise ValueError(f"Unexpected Pads6 record at {offset}")
            offset += 1
            subrecords = []
            for _ in range(6):
                length = struct.unpack_from("<I", data, offset)[0]
                subrecords.append(data[offset + 4 : offset + 4 + length])
                offset += 4 + length
            name_record, _, _, _, fixed, extended = subrecords
            number = name_record[1 : 1 + name_record[0]].decode("latin1")
            net_index = struct.unpack_from("<H", fixed, 3)[0]
            component_index = struct.unpack_from("<H", fixed, 7)[0]
            net = names[net_index] if net_index != 65535 else ""
            if component_index >= len(components):
                raise ValueError(f"Pad references invalid component {component_index}")
            x, y, sx, sy, hole = (
                struct.unpack_from("<i", fixed, at)[0] / UNITS_PER_MM
                for at in (13, 17, 21, 25, 45)
            )
            slot = hole
            if len(extended) >= 267 and extended[262] == 2:
                slot = struct.unpack_from("<i", extended, 263)[0] / UNITS_PER_MM
            result.append({
                "refdes": components[component_index],
                "number": number,
                "net": net,
                "x": x,
                "y": y,
                "size": (sx, sy),
                "drill": tuple(sorted((hole, slot))),
            })
        expected_count = struct.unpack("<I", doc.openstream(["Pads6", "Header"]).read())[0]
        if len(result) != expected_count:
            raise ValueError(f"Pads6 count mismatch: {len(result)} != {expected_count}")
        return result


def close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE_MM


def equivalent(source: dict, imported: dict) -> bool:
    return (
        source["refdes"] == imported["refdes"]
        and source["net"] == imported["net"]
        and (not source["number"] or source["number"] == imported["number"])
        and close(source["x"], imported["x"])
        and close(source["y"], imported["y"])
        and all(close(a, b) for a, b in zip(source["size"], imported["size"]))
        and all(close(a, b) for a, b in zip(source["drill"], imported["drill"]))
    )


def summarize(source: list[dict], imported: list[dict]) -> dict:
    remaining = imported.copy()
    missing = []
    unnamed = 0
    for pad in source:
        match = next((other for other in remaining if equivalent(pad, other)), None)
        if match is None:
            missing.append(pad)
        else:
            remaining.remove(match)
            if not pad["number"]:
                unnamed += 1
    return {
        "source_pad_count": len(source),
        "imported_pad_count": len(imported),
        "refdes_position_size_drill_net_and_named_pad_number_matches": len(source) - len(missing),
        "unnumbered_source_pads_matched_without_number_check": unnamed,
        "position_size_drill_tolerance_mm": TOLERANCE_MM,
        "missing_count": len(missing),
        "extra_count": len(remaining),
        "missing_examples": missing[:5],
        "extra_examples": remaining[:5],
        "scope_limitations": [
            "schematic pin/net mapping not verified",
            "pad shape, rotation, copper/mask layers, and solder mask expansion not verified",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--board", choices=TRANSFORMS, required=True)
    parser.add_argument("--pcb-file", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    original = args.root / "hardware/kicad/native" / args.board / f"{args.board}.kicad_pcb"
    source, components = source_pads(original, args.board)
    result = summarize(source, imported_pads(args.pcb_file, components))
    result["component_origin_matches"] = len(components)
    report = {args.board: result}
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
