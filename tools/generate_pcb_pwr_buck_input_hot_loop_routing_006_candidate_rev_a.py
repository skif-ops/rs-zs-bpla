#!/usr/bin/env python3
"""Generate isolated PCB-PWR dual buck input hot-loop routing candidate 006."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-INPUT-HOT-LOOP-ROUTING-006"
)
DEFAULT_BASE_OUTPUT = (
    CANDIDATE_DIR / "PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    CANDIDATE_DIR
    / "PCB-PWR_BUCK_INPUT_HOT_LOOP_ROUTING_006_CANDIDATE_REV_A.kicad_pcb"
)

BASE_SHA256 = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"
CANDIDATE_SHA256 = "9a836eeee73262ac26cf0ec18dae8fee0ecf443f3bafa9767c8f85910287dfd0"

# The VIN path is kept on F.Cu. The main 1210 input capacitor must escape
# around its own ground pad; the route then contracts visibly into the 0603
# CINHF and the controller VIN pad. PGND cannot escape the TI RAK pad 2 on
# F.Cu with the project clearance, so each channel uses the two optional
# via positions allowed by TI, implemented at the project-standard 0.60/0.30 mm
# geometry, plus one via at each input capacitor and one bounded In1.Cu local
# plane. This is a candidate-only count exception to the generic 12-via 5 A
# transition rule; it is not a via-current or thermal acceptance.
CHANNELS = {
    "3V8": {
        "y": 14.0,
        "main_cap": "C11",
        "hf_cap": "C20",
        "controller": "U3",
    },
    "3V3": {
        "y": 42.0,
        "main_cap": "C12",
        "hf_cap": "C21",
        "controller": "U4",
    },
}


def routes() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for channel, data in CHANNELS.items():
        y = float(data["y"])
        for index, (net, start, end, width, purpose) in enumerate(
            (
                ("VBAT_SYS", (47.525, y), (47.525, y + 2.7), 1.0,
                 "main-CIN pad exit"),
                ("VBAT_SYS", (47.525, y + 2.7), (50.8, y + 2.7), 2.0,
                 "main-CIN outer-copper body"),
                ("VBAT_SYS", (50.8, y + 2.7), (51.4, y + 2.7), 1.5,
                 "first contraction"),
                ("VBAT_SYS", (51.4, y + 2.7), (52.35, y + 0.775), 1.0,
                 "CINHF entry"),
                ("VBAT_SYS", (52.35, y + 0.775), (53.9, y + 0.75), 0.5,
                 "controller VIN pad entry"),
                ("GND_PWR", (50.475, y), (52.35, y - 0.775), 1.0,
                 "main-CIN to CINHF local return"),
            ),
            start=1,
        ):
            result.append(
                {
                    "channel": channel,
                    "index": index,
                    "net": net,
                    "start": start,
                    "end": end,
                    "width": width,
                    "purpose": purpose,
                }
            )
    # U4 is the fixed-output 3V3 channel and its EN pin is tied to VIN.
    result.append(
        {
            "channel": "3V3",
            "index": 7,
            "net": "VBAT_SYS",
            "start": (53.9, 42.75),
            "end": (53.875, 42.075),
            "width": 0.25,
            "purpose": "U4 VIN to EN tie",
        }
    )
    return result


def vias() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for channel, data in CHANNELS.items():
        y = float(data["y"])
        for role, at, size, drill in (
            ("main-CIN return", (50.475, y), 0.6, 0.3),
            ("CINHF return", (52.35, y - 0.775), 0.6, 0.3),
            ("TI PGND via A", (55.0, y - 0.075), 0.6, 0.3),
            ("TI PGND via B", (55.0, y + 0.525), 0.6, 0.3),
        ):
            result.append(
                {
                    "channel": channel,
                    "role": role,
                    "at": at,
                    "size": size,
                    "drill": drill,
                    "net": "GND_PWR",
                }
            )
    return result


def zones() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for channel, data in CHANNELS.items():
        y = float(data["y"])
        result.append(
            {
                "channel": channel,
                "net": "GND_PWR",
                "name": f"PCB_PWR_{channel}_LOCAL_HOT_LOOP_RETURN_In1_Cu",
                "layer": "In1.Cu",
                "points": (
                    (49.8, y - 1.6),
                    (55.35, y - 1.6),
                    (55.35, y + 1.6),
                    (49.8, y + 1.6),
                ),
            }
        )
    return result


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def net_number(source: str, net_name: str) -> str:
    found = re.search(rf'^\s*\(net (\d+) "{net_name}"\)$', source, re.M)
    require(found is not None, f"{net_name} net identity drift")
    return str(found.group(1))


def candidate_bytes(base_payload: bytes) -> bytes:
    require(
        sha256_bytes(base_payload) == BASE_SHA256,
        "authoritative PCB-PWR candidate-006 base SHA-256 drift",
    )
    source = base_payload.decode("utf-8")
    additions: list[str] = []

    for route in routes():
        net = str(route["net"])
        start = route["start"]
        end = route["end"]
        route_uuid = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "dioneya:pcb-pwr:routing-candidate-006:segment:"
            f"{route['channel']}:{route['index']}:{net}",
        )
        additions.append(
            "\t(segment\n"
            f"\t\t(start {number(start[0])} {number(start[1])})\n"
            f"\t\t(end {number(end[0])} {number(end[1])})\n"
            f"\t\t(width {number(float(route['width']))})\n"
            "\t\t(layer \"F.Cu\")\n"
            f"\t\t(net {net_number(source, net)})\n"
            f"\t\t(uuid \"{route_uuid}\")\n"
            "\t)"
        )

    for index, via in enumerate(vias(), start=1):
        at = via["at"]
        via_uuid = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "dioneya:pcb-pwr:routing-candidate-006:via:"
            f"{via['channel']}:{index}:{via['role']}",
        )
        additions.append(
            "\t(via\n"
            f"\t\t(at {number(at[0])} {number(at[1])})\n"
            f"\t\t(size {number(float(via['size']))})\n"
            f"\t\t(drill {number(float(via['drill']))})\n"
            "\t\t(layers \"F.Cu\" \"B.Cu\")\n"
            f"\t\t(net {net_number(source, str(via['net']))})\n"
            f"\t\t(uuid \"{via_uuid}\")\n"
            "\t)"
        )

    for zone in zones():
        zone_uuid = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "dioneya:pcb-pwr:routing-candidate-006:zone:"
            f"{zone['channel']}:{zone['name']}",
        )
        point_lines = "\n".join(
            f"\t\t\t\t(xy {number(x)} {number(y)})"
            for x, y in zone["points"]
        )
        additions.append(
            "\t(zone\n"
            f"\t\t(net {net_number(source, str(zone['net']))})\n"
            f"\t\t(net_name \"{zone['net']}\")\n"
            f"\t\t(layer \"{zone['layer']}\")\n"
            f"\t\t(uuid \"{zone_uuid}\")\n"
            f"\t\t(name \"{zone['name']}\")\n"
            "\t\t(hatch edge 0.5)\n"
            "\t\t(connect_pads yes\n"
            "\t\t\t(clearance 0.3)\n"
            "\t\t)\n"
            "\t\t(min_thickness 0.25)\n"
            "\t\t(fill yes\n"
            "\t\t\t(thermal_gap 0.3)\n"
            "\t\t\t(thermal_bridge_width 0.4)\n"
            "\t\t)\n"
            "\t\t(polygon\n"
            "\t\t\t(pts\n"
            f"{point_lines}\n"
            "\t\t\t)\n"
            "\t\t)\n"
            "\t)"
        )

    marker = "\n\t(embedded_fonts no)"
    require(source.count(marker) == 1, "cannot locate PCB insertion boundary")
    return source.replace(marker, "\n" + "\n".join(additions) + marker, 1).encode(
        "utf-8"
    )


def generate(base_output: Path, output: Path, check: bool) -> dict[str, object]:
    source_payload = SOURCE.read_bytes()
    require(
        sha256_bytes(source_payload) == BASE_SHA256,
        "authoritative PCB-PWR is not the controlled ECO-002 successor",
    )
    candidate_payload = candidate_bytes(source_payload)
    candidate_sha256 = sha256_bytes(candidate_payload)
    if CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(
            candidate_sha256 == CANDIDATE_SHA256,
            "PCB-PWR routing candidate 006 SHA-256 drift",
        )
    else:
        require(not check, "candidate SHA-256 has not been bound")

    if check:
        require(base_output.read_bytes() == source_payload, "committed base drift")
        require(output.read_bytes() == candidate_payload, "committed candidate drift")
    else:
        base_output.parent.mkdir(parents=True, exist_ok=True)
        base_output.write_bytes(source_payload)
        output.write_bytes(candidate_payload)

    route_lengths: dict[str, float] = {}
    for channel in CHANNELS:
        route_lengths[channel] = sum(
            math.dist(route["start"], route["end"])
            for route in routes()
            if route["channel"] == channel
        )
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha256,
        "routed_nets": ["VBAT_SYS", "GND_PWR"],
        "connections": [
            "C11-C20-U3 VIN/PGND",
            "C12-C21-U4 VIN/PGND and U4.EN",
        ],
        "added_segments": len(routes()),
        "added_vias": len(vias()),
        "added_local_planes": len(zones()),
        "route_lengths_mm": route_lengths,
        "authoritative_board_modified": False,
        "routing_complete": False,
        "review_b_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-output", type=Path, default=DEFAULT_BASE_OUTPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(generate(args.base_output.resolve(), args.output.resolve(), args.check))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
