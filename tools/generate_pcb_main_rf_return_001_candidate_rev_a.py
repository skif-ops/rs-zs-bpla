#!/usr/bin/env python3
"""Generate the bounded PCB-MAIN cellular L2 return-plane candidate.

The accepted RF P0 copper uses the public JLC06161H-3313 L1-over-L2
engineering geometry.  GND_DIGITAL already occupies In1.Cu outside the
exclusive cellular allocation, but GND_MODEM currently exists only on In4.Cu.
This proposal adds one GND_MODEM zone on In1.Cu, wholly inside the existing
GND_DIGITAL cut-out for ZONE_CELL.  It changes no accepted footprint, trace,
via, rule area, net, outline, or existing zone.

The output is a review candidate only.  It does not close GNSS routeability,
RF/SI review, final stackup acceptance, Review B, or manufacturing release.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001"
    / "PCB-MAIN_RF_RETURN_BASE_REV_A.kicad_pcb"
)
DEFAULT_OUTPUT = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001"
    / "PCB-MAIN_RF_RETURN_CANDIDATE_REV_A.kicad_pcb"
)
BASE_SHA256 = "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
ZONE_NAME = "PCB_MAIN_GND_MODEM_CELL_In1_Cu"
ZONE_TSTAMP = "474ddbc4-d099-4dd3-9f8f-bc95779ae00a"

# The accepted GND_DIGITAL In1.Cu polygon leaves the cellular cavity bounded by
# x=9.8/36.2 and y=33.8/74.35 mm.  The new polygon follows the locked
# ZONE_CELL authority (x=10..36, y=34..74) and therefore retains 0.2 mm of
# explicit separation from the adjacent domain boundary.
ZONE_BLOCK = f'''  (zone (net 47) (net_name "GND_MODEM") (layer "In1.Cu") (tstamp {ZONE_TSTAMP}) (name "{ZONE_NAME}") (hatch edge 0.5)
    (connect_pads yes (clearance 0.1))
    (min_thickness 0.15) (filled_areas_thickness no)
    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy 10 34)
        (xy 36 34)
        (xy 36 74)
        (xy 10 74)
      )
    )
  )
'''


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(output: Path) -> dict[str, object]:
    require(BASE.is_file(), f"missing controlled RF-return base: {BASE}")
    require(sha256(BASE) == BASE_SHA256, "RF-return base SHA-256 drift")
    source = BASE.read_text(encoding="utf-8")
    require(ZONE_NAME not in source, "RF-return zone is already present in base")
    require(source.endswith(")\n"), "unexpected KiCad board terminator")
    candidate = source[:-2] + ZONE_BLOCK + ")\n"
    require(candidate.count(ZONE_NAME) == 1, "candidate zone insertion drift")
    require(candidate.startswith(source[:-2]), "accepted base bytes were modified")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(candidate, encoding="utf-8")
    return {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": sha256(output),
        "output": str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output),
        "added_zone": ZONE_NAME,
        "net": "GND_MODEM",
        "layer": "In1.Cu",
        "polygon_mm": [[10.0, 34.0], [36.0, 34.0], [36.0, 74.0], [10.0, 74.0]],
        "accepted_base_bytes_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = generate(args.output.resolve())
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
