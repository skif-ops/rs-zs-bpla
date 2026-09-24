#!/usr/bin/env python3
"""Audit the EVT-PRE-20 EVT build release (hardware/EVT_BUILD_RELEASE_GATE_REV_A.md).

EVT build release = design-complete handoff of the 2x20+1 EVT program to PCB/PCBA
fabrication, housing manufacture and station assembly. Physical EVT evidence is
collected on the built lot and feeds the serial revision.

The audit reuses tools/audit_evt_pre_20_hardware_release.py unchanged:
- every failing design-release check blocks the EVT build unless it is listed in
  EVT_PHYSICAL_SCOPE;
- checks whose base interlock pins a historical PCB-PWR trace count are
  re-evaluated against the authoritative board, so routing steps never make
  this audit drift;
- EVT-build-only checks cover CAM, pad/outline containment, assembler part map,
  desk-closable BOM statuses, station mechanical BOM and the housing package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import audit_evt_pre_20_hardware_release as base  # noqa: E402

GATE = "hardware/EVT_BUILD_RELEASE_GATE_REV_A.md"
BOARDS = ("PCB-MAIN", "PCB-PWR", "PCB-MIC")

# Physical evidence collected on the built EVT lot, not an input of this gate.
EVT_PHYSICAL_SCOPE = frozenset(
    {
        "pcb_pwr_input_protection_release",
        "harness_manufacturing_release",
    }
)

# Base checks that pin a historical PCB-PWR trace count; re-evaluated here.
PWR_TRACE_PINNED_CHECKS = {
    "pcb_pwr_fitted_2d_placement_clearance": "audit_pcb_pwr_placement_clearance_rev_a.py",
    "pcb_pwr_pre_route_constraint_coverage": "audit_pcb_pwr_routing_authority_rev_a.py",
}

EVT_CAM_RELEASE_ROOT = "hardware/manufacturing/evt-build-release"
EVT_CAM_REQUIRED_FILES = (
    "gerber",
    "drill",
    "drc.json",
    "STATUS.json",
    "{board}_jlc_bom.csv",
    "{board}_jlc_cpl.csv",
    "FAB_NOTES.md",
)
EVT_ASSEMBLER_PART_MAP = "hardware/EVT_PRE_20_PCBA_ASSEMBLER_PART_MAP_REV_A.csv"
EVT_MECHANICAL_BOM = "hardware/EVT_PRE_20_MECHANICAL_BOM_REV_A.csv"
EVT_MECHANICAL_BOM_CATEGORIES = (
    "HOUSING_PART",
    "CABLE_GLAND",
    "ACOUSTIC_MEMBRANE",
    "SEAL",
    "FASTENER",
    "THREADED_INSERT",
    "INTER_MODULE_FUSE",
    "POWER_CABLE",
    "MOUNT",
)
DIM_EVT_CLOSURE = "mechanics/common/DIM_EVT_CLOSURE_REV_A.csv"
OTS_IDENTITY = "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.json"
# EVT operating range accepted by the customer on 2026-09-24 for EVT-PRE-20:
# -20..+60 C. The serial target stays DEC-019 (-40..+70 C, ENVIRONMENT_REV_A.md)
# and is revisited from EVT results.
ENVIRONMENT_STATION_RANGE_C = (-20.0, 60.0)
# Accepted EVT exceptions (customer decision 2026-09-24). PCB-PWR has no MPPT
# control line (J1 carries only VBAT_RAW/GND_PWR, J2 only the MAIN interface), so
# MCU-side charge inhibit is not available in Rev.A; the Smart Battery Sense stays
# and its -20..-10 C gap is verified on the built lot.
EVT_OTS_TEMPERATURE_EXCEPTIONS = {
    "MPPT-TEMP": (
        "ACCEPTED_FOR_EVT: SBS050150200 rated -10..+60 C; EVT test EVT-ENV-BATT-COLD must "
        "show charge inhibit at battery temperature < 0 C and the MPPT fallback to its "
        "internal sensor between -20 and -10 C"
    ),
}

EVT_PAPER_CLOSABLE_BOM_STATUSES = frozenset(
    {
        "SELECTED_PENDING_REVIEW_A",
        "LOCKED_CANDIDATE_PENDING_DERATING",
        "LOCKED_CANDIDATE",
    }
)


def native_board(board: str) -> Path:
    return ROOT / f"hardware/kicad/native/{board}/{board}.kicad_pcb"


def pads_outside_outline(path: Path) -> list[str]:
    """Footprint references whose pad copper crosses the Edge.Cuts bounding box.

    KiCad DRC does not report footprints lying wholly or partly outside a
    rectangular outline, so containment is checked explicitly.
    """
    from kiutils.board import Board

    board = Board.from_file(str(path))
    xs: list[float] = []
    ys: list[float] = []
    for item in board.graphicItems:
        if getattr(item, "layer", "") != "Edge.Cuts":
            continue
        for attribute in ("start", "end", "center"):
            point = getattr(item, attribute, None)
            if point is not None and hasattr(point, "X"):
                xs.append(point.X)
                ys.append(point.Y)
    if not xs:
        return ["NO_OUTLINE"]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    references: list[str] = []
    for footprint in board.footprints:
        angle = math.radians(footprint.position.angle or 0)
        if isinstance(footprint.properties, list):
            reference = next((p.value for p in footprint.properties if p.key == "Reference"), "?")
        else:
            reference = footprint.properties.get("Reference", "?")
        for pad in footprint.pads:
            x = footprint.position.X + pad.position.X * math.cos(angle) + pad.position.Y * math.sin(angle)
            y = footprint.position.Y - pad.position.X * math.sin(angle) + pad.position.Y * math.cos(angle)
            radius = max(pad.size.X, pad.size.Y) / 2
            if x - radius < x0 or x + radius > x1 or y - radius < y0 or y + radius > y1:
                references.append(reference)
    return references


def reevaluate_pwr_trace_pinned(name: str, script: str) -> tuple[bool, str]:
    """Same interlock as the base audit, bound to the live board trace count."""
    counts = base.board_copper_counts(native_board("PCB-PWR"))
    live_trace_items = counts["segments"] + counts["vias"]
    result = base.run_json_audit(script)
    board = result.get("board", {}) if isinstance(result.get("board"), dict) else {}
    if name == "pcb_pwr_fitted_2d_placement_clearance":
        summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
        passed = (
            summary.get("state") == "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE_DIM_003_ACCEPTED"
            and summary.get("fitted_footprints") == 44
            and summary.get("courtyard_footprints") == 44
            and summary.get("required_clearance_mm") == 0.2
            and summary.get("minimum_observed_clearance_mm", 0) >= 0.2
            and summary.get("clearance_conflicts") == 0
            and summary.get("mounting_holes") == 4
            and summary.get("mounting_to_fitted_body_conflicts") == 0
            and summary.get("mounting_to_existing_pad_conflicts") == 0
            and board.get("trace_items") == live_trace_items
            and board.get("copper_zones") == counts["zones"]
            and result.get("manufacturing_release") is False
        )
        state = str(summary.get("state", result.get("status", "MISSING")))
    else:
        passed = (
            result.get("status") == "PASS_PRE_ROUTE_CONSTRAINT_COVERAGE_ROUTING_OPEN"
            and result.get("authority", {}).get("row_count") == 31
            and board.get("net_count") == 31
            and board.get("trace_items") == live_trace_items
            and board.get("copper_zones") == counts["zones"]
            and result.get("dim_003") == "EVT_ENGINEERING_ACCEPTED_18_OF_18_SERIAL_REVALIDATION_REQUIRED"
            and result.get("routing_complete") is False
            and result.get("manufacturing_release") is False
        )
        state = str(result.get("status", "MISSING"))
    return passed, f"{state}; live trace_items={live_trace_items} zones={counts['zones']}"


def audit() -> dict[str, object]:
    base_result = base.audit()
    checks: list[dict[str, object]] = []
    blockers: list[str] = []

    def check(name: str, passed: bool, detail: str, blocker: str, source: str) -> None:
        checks.append({"name": name, "pass": passed, "detail": detail, "source": source})
        if not passed:
            blockers.append(blocker)

    moved: list[str] = []
    for item in base_result["checks"]:
        name = str(item["name"])
        if name in EVT_PHYSICAL_SCOPE:
            moved.append(name)
            continue
        if name == "mechanical_dimensions" and not item.get("pass"):
            # DIM rows closed for EVT by datasheet live in an overlay: the
            # OPEN_DIMENSIONS register is SHA-bound by accepted DIM-003 packets.
            closed = {
                row["ID"] for row in base.read_csv(DIM_EVT_CLOSURE)
                if row["EVT_status"].startswith("CLOSED_")
            } if (ROOT / DIM_EVT_CLOSURE).is_file() else set()
            still_open = [
                dim.strip() for dim in str(item["detail"]).removeprefix("open: ").split(",")
                if dim.strip() and dim.strip() not in closed
            ]
            detail = "open: " + ", ".join(still_open) if still_open else "all hardware dimensions closed"
            check(name, not still_open, detail, f"{name}: {detail}", "base-reevaluated")
            continue
        if name in PWR_TRACE_PINNED_CHECKS:
            passed, detail = reevaluate_pwr_trace_pinned(name, PWR_TRACE_PINNED_CHECKS[name])
            check(name, passed, detail, f"{name}: {detail}", "base-reevaluated")
            continue
        if item.get("blocks_hardware_design_release") or (
            item.get("pass") and item.get("name") not in {"purchase_lot_selection"}
        ):
            check(name, bool(item["pass"]), str(item["detail"]), f"{name}: {item['detail']}", "base")

    # CAM produced by tools/export_pcb_engineering_snapshot_rev_a.py in the same
    # layout as the engineering snapshot, under EVT_CAM_RELEASE_ROOT.
    cam_root = ROOT / EVT_CAM_RELEASE_ROOT
    sums_path = cam_root / "SHA256SUMS.json"
    cam_sums: dict[str, str] = {}
    if sums_path.is_file():
        for record in json.loads(sums_path.read_text(encoding="utf-8")):
            target = cam_root / record["path"]
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == record["sha256"]:
                cam_sums[record["path"]] = record["sha256"]
    for board in BOARDS:
        missing: list[str] = []
        board_dir = cam_root / board
        if not sums_path.is_file():
            missing.append(f"{EVT_CAM_RELEASE_ROOT}/SHA256SUMS.json")
        else:
            board_sha = hashlib.sha256(native_board(board).read_bytes()).hexdigest()
            if cam_sums.get(f"{board}/native/{board}.kicad_pcb") != board_sha:
                missing.append("native board copy differs from authoritative board")
            for pattern in EVT_CAM_REQUIRED_FILES:
                name = pattern.format(board=board)
                if not any(p == f"{board}/{name}" or p.startswith(f"{board}/{name}/") for p in cam_sums):
                    missing.append(name)
            drc_path = board_dir / "drc.json"
            if drc_path.is_file():
                drc = json.loads(drc_path.read_text(encoding="utf-8"))
                errors = [v for v in drc.get("violations", []) if v.get("severity") == "error"]
                if errors:
                    missing.append(f"DRC errors={len(errors)}")
                if drc.get("unconnected_items"):
                    missing.append(f"unconnected={len(drc['unconnected_items'])}")
            status_path = board_dir / "STATUS.json"
            status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.is_file() else {}
            if status.get("review_b") != "ACCEPTED":
                missing.append("review_b not ACCEPTED")
        check(
            f"{board.lower()}_evt_cam_package",
            not missing,
            "EVT CAM package complete, DRC clean and bound to native board" if not missing else "open: " + ", ".join(missing),
            f"{board} EVT CAM package is not ready: " + ", ".join(missing),
            "evt-build",
        )

    for board in BOARDS:
        outside = sorted(set(pads_outside_outline(native_board(board))))
        check(
            f"{board.lower()}_pads_within_outline",
            not outside,
            "all pads inside the board outline" if not outside else "pads cross or lie outside the outline: " + ", ".join(outside),
            f"{board} has pads crossing or outside the board outline: " + ", ".join(outside),
            "evt-build",
        )

    bom_rows = base.read_csv("hardware/EVT_PRE_20_BOM_REV_A.csv")
    fitted_pcba_items = sorted(
        {
            row["Item_ID"]
            for row in bom_rows
            if row["Assembly"] in BOARDS
            and row["Population"] == "FITTED"
            and row["Line_class"] == "ELECTRICAL_COMPONENT"
        }
    )
    if (ROOT / EVT_ASSEMBLER_PART_MAP).is_file():
        mapped = {
            row["Item_ID"]
            for row in base.read_csv(EVT_ASSEMBLER_PART_MAP)
            if row.get("Supply_mode", "").strip() == "CONSIGNED"
            or (
                row.get("Supply_mode", "").strip() == "LCSC"
                and re.fullmatch(r"C\d{3,9}", row.get("LCSC_ID", "").strip())
            )
        }
        unmapped = [item for item in fitted_pcba_items if item not in mapped]
    else:
        unmapped = fitted_pcba_items
    check(
        "evt_pcba_assembler_part_map",
        not unmapped,
        f"{len(fitted_pcba_items)} fitted PCBA lines mapped" if not unmapped
        else f"{len(unmapped)}/{len(fitted_pcba_items)} fitted PCBA lines lack LCSC ID or CONSIGNED mode",
        f"PCBA assembler part map is incomplete: {len(unmapped)} fitted lines unmapped",
        "evt-build",
    )

    paper_open = [
        row["Item_ID"]
        for row in bom_rows
        if row["Population"] in {"FITTED", "N/A"} and row["Status"] in EVT_PAPER_CLOSABLE_BOM_STATUSES
    ]
    check(
        "evt_bom_paper_closure",
        not paper_open,
        "no desk-closable BOM status remains" if not paper_open else f"{len(paper_open)} BOM lines await desk closure",
        f"BOM has {len(paper_open)} lines with desk-closable open status (review A, derating, tolerance)",
        "evt-build",
    )

    missing_categories = list(EVT_MECHANICAL_BOM_CATEGORIES)
    if (ROOT / EVT_MECHANICAL_BOM).is_file():
        present = {
            row.get("Category", "").strip()
            for row in base.read_csv(EVT_MECHANICAL_BOM)
            if row.get("MPN_or_drawing", "").strip() not in {"", "TBD"}
        }
        missing_categories = [c for c in EVT_MECHANICAL_BOM_CATEGORIES if c not in present]
    check(
        "evt_station_mechanical_bom",
        not missing_categories,
        "all required categories present" if not missing_categories else "missing categories: " + ", ".join(missing_categories),
        "station mechanical/installation BOM is incomplete: " + ", ".join(missing_categories),
        "evt-build",
    )

    # ENVIRONMENT_REV_A section 6 item 1 applied to the accepted EVT range: the
    # BOM must not contain parts whose rated range does not cover it.
    ots = json.loads((ROOT / OTS_IDENTITY).read_text(encoding="utf-8"))["targets"]
    uncovered = []
    accepted_exceptions: list[str] = []
    for item_id, target in ots.items():
        facts = target.get("controlled_facts", {})
        ranges = [facts[key] for key in facts if key.endswith("temperature_c") and key != "charge_temperature_c"]
        low = max(r[0] for r in ranges) if ranges else None
        high = min(r[1] for r in ranges) if ranges else None
        if low is None or low > ENVIRONMENT_STATION_RANGE_C[0] or high < ENVIRONMENT_STATION_RANGE_C[1]:
            if item_id in EVT_OTS_TEMPERATURE_EXCEPTIONS:
                accepted_exceptions.append(f"{item_id}: {EVT_OTS_TEMPERATURE_EXCEPTIONS[item_id]}")
            else:
                uncovered.append(f"{item_id} {target['mpn']} rated {low}..{high} C")
    check(
        "evt_ots_temperature_coverage",
        not uncovered,
        "system OTS items cover the EVT range {:g}..+{:g} C".format(*ENVIRONMENT_STATION_RANGE_C)
        + (" or are accepted EVT exceptions; accepted: " + "; ".join(accepted_exceptions) if accepted_exceptions else "")
        if not uncovered else "; ".join(uncovered),
        "system OTS items do not cover the EVT range {:g}..+{:g} C: ".format(*ENVIRONMENT_STATION_RANGE_C)
        + "; ".join(uncovered),
        "evt-build",
    )

    housing_dir = ROOT / "mechanics" / "vacuum_casting"
    housing_missing = [
        label
        for label, pattern in (("master STEP", "*.step"), ("drawing PDF", "*.pdf"), ("housing BOM", "HOUSING_BOM*.csv"))
        if not any(housing_dir.glob(pattern))
    ]
    check(
        "evt_housing_manufacturing_package",
        not housing_missing,
        "vacuum-casting housing package present" if not housing_missing else "missing: " + ", ".join(housing_missing),
        "vacuum-casting housing manufacturing package is incomplete: " + ", ".join(housing_missing),
        "evt-build",
    )

    ready = not blockers
    return {
        "schema": "dioneya-evt-build-release-audit-v1",
        "configuration": "EVT-PRE-20 Rev.A",
        "program": "2 x EVT-20 + 1 bench station",
        "gate": GATE,
        "evt_build_release": {
            "ready": ready,
            "status": "PASS" if ready else "BLOCKED",
            "meaning": (
                "design-complete handoff to PCB/PCBA fabrication, housing manufacture and "
                "station assembly; physical EVT evidence is collected on the built lot"
            ),
            "blockers": blockers,
        },
        "moved_to_evt_physical_scope": moved,
        "base_hardware_design_release": base_result["hardware_design_release"]["status"],
        "base_purchase_release": base_result["purchase_release"]["status"],
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="return non-zero until the EVT build release is ready")
    parser.add_argument("--output", default="artifacts/evt_pre_20_evt_build_release_audit.json")
    args = parser.parse_args()

    result = audit()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    release = result["evt_build_release"]
    print(f"EVT-PRE-20 EVT build release (fab/assembly/housing handoff): {release['status']}")
    for blocker in release["blockers"]:
        print(f"  - {blocker}")
    print("moved to EVT physical scope: " + ", ".join(result["moved_to_evt_physical_scope"]))
    try:
        display_output = output.relative_to(ROOT)
    except ValueError:
        display_output = output
    print(f"report: {display_output}")
    return 1 if args.strict and not release["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
