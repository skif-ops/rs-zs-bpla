"""Prepare a fresh KiCad import copy with local labels on hierarchical-port wires.

This never changes the tracked KiCad sources. Each inserted label duplicates an
existing local net name on the same child sheet, allowing Altium's import to
connect that local net to its Port through a physical wire. Validate KiCad and
Altium netlists after import; this preparation is not equivalence proof.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import re
import shutil
import uuid

NUM = r"-?\d+(?:\.\d+)?"
LABEL_RE = re.compile(
    rf'^\s*\((hierarchical_label|label) "([^"]+)"[^\n]*\(at ({NUM}) ({NUM}) ({NUM})\)',
    re.MULTILINE,
)
WIRE_RE = re.compile(
    rf'^\s*\(wire \(pts \(xy ({NUM}) ({NUM})\) \(xy ({NUM}) ({NUM})\)\)',
    re.MULTILINE,
)
STEP = Decimal("1.27")  # KiCad 50 mil grid, one step inside a 400 mil port wire.


def fmt(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def on_segment(point, a, b) -> bool:
    x, y = point
    return (
        min(a[0], b[0]) <= x <= max(a[0], b[0])
        and min(a[1], b[1]) <= y <= max(a[1], b[1])
        and (a[0] == b[0] == x or a[1] == b[1] == y)
    )


def patch_sheet(path: Path) -> list[tuple[str, str, str]]:
    source = path.read_text(encoding="utf-8")
    labels: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
    ports: list[tuple[str, Decimal, Decimal]] = []
    for match in LABEL_RE.finditer(source):
        kind, name, x, y, _angle = match.groups()
        point = (Decimal(x), Decimal(y))
        if kind == "label":
            labels[name].append(point)
        else:
            ports.append((name, *point))
    wires = [
        ((Decimal(x1), Decimal(y1)), (Decimal(x2), Decimal(y2)))
        for x1, y1, x2, y2 in (m.groups() for m in WIRE_RE.finditer(source))
    ]
    additions = []
    report = []
    for name, x, y in ports:
        if name not in labels:
            continue
        point = (x, y)
        attached = [(a, b) for a, b in wires if a == point or b == point]
        if len(attached) != 1:
            raise ValueError(f"{path.name}: expected one port wire for {name} at {point}; found {len(attached)}")
        a, b = attached[0]
        other = b if a == point else a
        dx, dy = other[0] - x, other[1] - y
        if dx and dy:
            raise ValueError(f"{path.name}: diagonal port wire for {name}")
        distance = abs(dx or dy)
        if distance < STEP * 2:
            raise ValueError(f"{path.name}: short port wire for {name}: {distance}")
        if any(on_segment(p, a, b) for p in labels[name]):
            continue
        if dx:
            nx, ny = x + (STEP if dx > 0 else -STEP), y
            angle = 0 if dx > 0 else 180
        else:
            nx, ny = x, y + (STEP if dy > 0 else -STEP)
            angle = 270 if dy > 0 else 90
        identity = uuid.uuid5(uuid.NAMESPACE_URL, f"dioneya-altium-netlabel/{path.name}/{name}/{fmt(nx)}/{fmt(ny)}")
        additions.append(
            f'  (label "{name}" (at {fmt(nx)} {fmt(ny)} {angle})\n'
            '    (effects (font (size 1.1 1.1)) (justify bottom))\n'
            f'    (uuid {identity})\n'
            '  )\n'
        )
        report.append((name, fmt(nx), fmt(ny)))
    if additions:
        ending = source.rfind("\n)")
        if ending == -1 or source[ending:].strip() != ")":
            raise ValueError(f"{path.name}: cannot find top-level closing parenthesis")
        changed = source[:ending] + "\n" + "".join(additions) + source[ending:]
        path.write_text(changed, encoding="utf-8", newline="\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        raise SystemExit(f"Output already exists: {args.destination}")
    shutil.copytree(args.source, args.destination)
    grand_total = 0
    for board in ("PCB-PWR", "PCB-MAIN"):
        for path in sorted((args.destination / board).glob(f"{board}_*.kicad_sch")):
            report = patch_sheet(path)
            print(f"{path.name}: {len(report)} added local labels")
            for name, x, y in report:
                print(f"  {name} @ ({x}, {y}) mm")
            grand_total += len(report)
    print(f"Total added: {grand_total}")


if __name__ == "__main__":
    main()
