#!/usr/bin/env python3
"""Audit the bounded PCB-PWR dual-buck placement ECO-001 proposal."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from kiutils.board import Board

import audit_pcb_pwr_placement_clearance_rev_a as placement_clearance


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = (
    ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-PLACEMENT-ECO-001"
)
BASE = CANDIDATE_DIR / "PCB-PWR_BUCK_PLACEMENT_ECO_001_BASE_REV_A.kicad_pcb"
CANDIDATE = (
    CANDIDATE_DIR / "PCB-PWR_BUCK_PLACEMENT_ECO_001_CANDIDATE_REV_A.kicad_pcb"
)
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
WARNING_REMEDIATION_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-PWR-BUCK-WARNING-REMEDIATION-001/"
    "PCB-PWR_BUCK_WARNING_REMEDIATION_001_CANDIDATE_REV_A.kicad_pcb"
)
GENERATOR = (
    ROOT / "tools/generate_pcb_pwr_buck_placement_eco_001_candidate_rev_a.py"
)
REVIEW = (
    ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_CANDIDATE_REV_A.json"
)
APPROVAL = (
    ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPROVAL_REV_A.json"
)
MAPPING = (
    ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_REVIEW_COMMIT_MAPPING.json"
)
APPLICATION = (
    ROOT / "hardware/reviews/PCB_PWR_BUCK_PLACEMENT_ECO_001_APPLICATION_REV_A.json"
)

BASE_SHA256 = "fdd53e669a167df8925c38e289993c38b818c231eddd0be54de378b51538bf48"
CANDIDATE_SHA256 = "9e67236d55b9429c78362b1540634f74ab22b50c0ec65c41e8be74488cfa1e37"
WARNING_REMEDIATION_CANDIDATE_SHA256 = (
    "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
)
BOOTSTRAP_CANDIDATE_SHA256 = "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
BOOTSTRAP_CANDIDATE = ROOT / "hardware/kicad/candidates/PCB-PWR-BUCK-BOOTSTRAP-ROUTING-001/PCB-PWR_BUCK_BOOTSTRAP_ROUTING_001_CANDIDATE_REV_A.kicad_pcb"
REVIEWED_GENERATOR_SHA256 = "5dcf33e2a13cc09a30f86e6405178d044cd741064e31f03a89805b0d10a690a7"
HISTORICAL_REGENERATOR_SHA256 = "9d73d2563acd16b75778c6f05b39856549b5a6f8c11047356d2bb24115df8b5e"
APPROVAL_SHA256 = "03a3c499b785ffdbe331f5bb442aecde31411bb6b3e65c88e0eaf2e0a62c8c7e"
MAPPING_SHA256 = "26b4376b851d4dd5082bfd02182e243d7d0d9161a7b72c53a7112db9c21c2c85"
REVIEWED_COMMIT = "38d629c2e7f9a9956a93c8b9666b17e69905eeb6"
REVIEWED_TREE = "b935ed765133297099dee6af4799f598df832ab2"
APPROVAL_COMMIT = "82dbcf2a0318d79c73ad4c59e1f58158b453605f"

EXPECTED_POSES = {
    "C4": ((53.0, 10.0, 0.0), (54.575, 16.4, 180.0)),
    "C6": ((53.0, 38.0, 0.0), (54.575, 44.4, 180.0)),
    "L1": ((62.0, 14.0, 0.0), (60.75, 14.0, 180.0)),
    "L2": ((62.0, 42.0, 0.0), (60.75, 42.0, 180.0)),
}
CHANNELS = {
    "3V8": {
        "controller": "U3",
        "bootstrap": "C4",
        "inductor": "L1",
        "output_caps": ("C3", "C14", "C15", "C16"),
    },
    "3V3": {
        "controller": "U4",
        "bootstrap": "C6",
        "inductor": "L2",
        "output_caps": ("C5", "C17", "C18", "C19"),
    },
}


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(first: float, second: float, tolerance: float = 1e-6) -> bool:
    return math.isclose(float(first), float(second), rel_tol=0.0,
                        abs_tol=tolerance)


def ref_of(footprint: Any) -> str:
    return placement_clearance.ref_of(footprint)


def pose_of(footprint: Any) -> tuple[float, float, float]:
    return (
        float(footprint.position.X),
        float(footprint.position.Y),
        float(footprint.position.angle or 0.0) % 360.0,
    )


def without_pose(footprint: Any) -> dict[str, Any]:
    return {
        key: value for key, value in footprint.__dict__.items()
        if key != "position"
    }


def rotate(local: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    x, y = local
    return (
        x * math.cos(angle) + y * math.sin(angle),
        -x * math.sin(angle) + y * math.cos(angle),
    )


def pad_positions(board: Board, reference: str, number: str) -> list[tuple[float, float]]:
    footprint = next(item for item in board.footprints if ref_of(item) == reference)
    result: list[tuple[float, float]] = []
    for pad in footprint.pads:
        if str(pad.number) != number:
            continue
        local = rotate(
            (float(pad.position.X), float(pad.position.Y)),
            float(footprint.position.angle or 0.0),
        )
        result.append((
            float(footprint.position.X) + local[0],
            float(footprint.position.Y) + local[1],
        ))
    require(result, f"{reference}.{number}: pad missing")
    return result


def minimum_pad_distance(
    board: Board,
    first_ref: str,
    first_pad: str,
    second_ref: str,
    second_pad: str,
) -> float:
    return min(
        math.dist(first, second)
        for first in pad_positions(board, first_ref, first_pad)
        for second in pad_positions(board, second_ref, second_pad)
    )


def fitted_clearance(board: Board) -> dict[str, object]:
    fitted = [
        placement_clearance.envelope_of(footprint)
        for footprint in board.footprints
        if "population=FITTED" in str(footprint.description)
    ]
    require(len(fitted) == 44, "candidate fitted-footprint inventory drift")
    distances: list[tuple[float, str, str]] = []
    conflicts: list[tuple[str, str, float]] = []
    for first, second in combinations(fitted, 2):
        distance, _, _ = placement_clearance.rectangle_distance(first, second)
        distances.append((distance, first.ref, second.ref))
        if (distance + placement_clearance.GEOMETRY_TOLERANCE_MM <
                placement_clearance.REQUIRED_CLEARANCE_MM):
            conflicts.append((first.ref, second.ref, distance))
    require(not conflicts, f"candidate fitted-courtyard conflicts: {conflicts}")

    overhangs = sorted(
        item.ref for item in fitted
        if item.xmin < 0.0 or item.ymin < 0.0
        or item.xmax > placement_clearance.BOARD_X_MM
        or item.ymax > placement_clearance.BOARD_Y_MM
    )
    require(overhangs == placement_clearance.EXPECTED_PROVISIONAL_EDGE_OVERHANGS,
            f"candidate edge-overhang set drift: {overhangs}")

    mounting_body_conflicts: list[tuple[str, str, float]] = []
    mounting_margins: list[float] = []
    for hole, (x, y) in placement_clearance.EXPECTED_MOUNTING_HOLES.items():
        for body in fitted:
            margin = placement_clearance.point_rectangle_distance(x, y, body) - \
                placement_clearance.MOUNTING_FITTED_EXCLUSION_RADIUS_MM
            mounting_margins.append(margin)
            if (margin + placement_clearance.GEOMETRY_TOLERANCE_MM <
                    placement_clearance.REQUIRED_CLEARANCE_MM):
                mounting_body_conflicts.append((hole, body.ref, margin))
    require(not mounting_body_conflicts,
            f"candidate mounting/body conflicts: {mounting_body_conflicts}")

    mounting_pad_conflicts: list[tuple[str, str, str, float]] = []
    electrical = [
        footprint for footprint in board.footprints
        if ref_of(footprint) not in placement_clearance.EXPECTED_MOUNTING_HOLES
    ]
    for hole, (x, y) in placement_clearance.EXPECTED_MOUNTING_HOLES.items():
        for footprint in electrical:
            for pad in footprint.pads:
                envelope = placement_clearance.pad_envelope(footprint, pad)
                margin = placement_clearance.point_rectangle_distance(
                    x, y, envelope
                ) - placement_clearance.MOUNTING_COPPER_EXCLUSION_RADIUS_MM
                if margin + placement_clearance.GEOMETRY_TOLERANCE_MM < 0.0:
                    mounting_pad_conflicts.append(
                        (hole, ref_of(footprint), str(pad.number), margin)
                    )
    require(not mounting_pad_conflicts,
            f"candidate mounting/pad conflicts: {mounting_pad_conflicts}")

    by_ref = {item.ref: item for item in fitted}
    controlled_pair_gaps: dict[str, float] = {}
    for first, second in (("C4", "U3"), ("C6", "U4"),
                          ("L1", "U3"), ("L2", "U4")):
        distance, _, _ = placement_clearance.rectangle_distance(
            by_ref[first], by_ref[second]
        )
        controlled_pair_gaps[f"{first}_{second}"] = round(distance, 6)

    return {
        "status": "PASS_FITTED_2D_AND_EVT_MOUNTING_CLEARANCE",
        "fitted_footprints": len(fitted),
        "minimum_clearance_mm": round(min(item[0] for item in distances), 6),
        "minimum_pair": list(min(distances)[1:]),
        "required_clearance_mm": placement_clearance.REQUIRED_CLEARANCE_MM,
        "component_conflicts": 0,
        "mounting_body_conflicts": 0,
        "mounting_pad_conflicts": 0,
        "minimum_mounting_body_margin_mm": round(min(mounting_margins), 6),
        "provisional_edge_overhangs": overhangs,
        "controlled_pair_gaps_mm": controlled_pair_gaps,
    }


def topology_metrics(base: Board, candidate: Board) -> dict[str, object]:
    results: dict[str, object] = {}
    for name, channel in CHANNELS.items():
        controller = str(channel["controller"])
        bootstrap = str(channel["bootstrap"])
        inductor = str(channel["inductor"])
        output_caps = tuple(str(item) for item in channel["output_caps"])

        def metrics(board: Board) -> dict[str, float]:
            output_distance = min(
                minimum_pad_distance(board, inductor, "2", cap, "1")
                for cap in output_caps
            )
            return {
                "controller_boot_to_cboot_mm": minimum_pad_distance(
                    board, controller, "4", bootstrap, "1"
                ),
                "controller_sw_to_cboot_mm": minimum_pad_distance(
                    board, controller, "3", bootstrap, "2"
                ),
                "controller_sw_to_inductor_mm": minimum_pad_distance(
                    board, controller, "3", inductor, "1"
                ),
                "inductor_to_nearest_output_cap_mm": output_distance,
            }

        first = metrics(base)
        second = metrics(candidate)
        require(second["controller_boot_to_cboot_mm"] <= 1.30,
                f"{name}: BOOT-to-CBOOT distance exceeds bounded target")
        require(second["controller_sw_to_cboot_mm"] <= 1.50,
                f"{name}: SW-to-CBOOT distance exceeds bounded target")
        require(second["controller_sw_to_inductor_mm"] <= 4.60,
                f"{name}: SW-to-inductor distance exceeds bounded target")
        require(second["inductor_to_nearest_output_cap_mm"] <= 5.50,
                f"{name}: inductor-to-output-bank distance exceeds target")
        for metric in second:
            require(second[metric] < first[metric],
                    f"{name}: candidate does not improve {metric}")
        results[name] = {
            "base_mm": {key: round(value, 6) for key, value in first.items()},
            "candidate_mm": {
                key: round(value, 6) for key, value in second.items()
            },
            "improvement_percent": {
                key: round(100.0 * (first[key] - value) / first[key], 3)
                for key, value in second.items()
            },
        }
    return results


def drc_inventory(path: Path) -> tuple[Counter[str], int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = Counter(
        item.get("type", "UNKNOWN")
        for item in data.get("violations", [])
        if item.get("severity") == "error"
    )
    return errors, len(data.get("violations", [])), \
        len(data.get("unconnected_items", []))


def audit_drc(base_path: Path, candidate_path: Path) -> dict[str, object]:
    base_errors, base_violations, base_unconnected = drc_inventory(base_path)
    candidate_errors, candidate_violations, candidate_unconnected = drc_inventory(
        candidate_path
    )
    added = {
        kind: candidate_errors[kind] - base_errors[kind]
        for kind in candidate_errors
        if candidate_errors[kind] > base_errors[kind]
    }
    require(not added,
            f"PCB-PWR buck placement ECO introduces KiCad 9 errors: {added}")
    require(candidate_unconnected == base_unconnected,
            "placement-only ECO changes unconnected-item count")
    return {
        "status": "PASS_NO_NEW_KICAD9_ERRORS_NO_CONNECTIVITY_REGRESSION",
        "base_violations": base_violations,
        "candidate_violations": candidate_violations,
        "base_unconnected": base_unconnected,
        "candidate_unconnected": candidate_unconnected,
        "new_error_counts": {},
    }


def audit(
    drc_base: Path | None = None,
    drc_candidate: Path | None = None,
) -> dict[str, object]:
    require(sha256(BASE) == BASE_SHA256,
            "PCB-PWR buck placement base SHA-256 drift")
    require(sha256(CANDIDATE) == CANDIDATE_SHA256,
            "PCB-PWR buck placement candidate SHA-256 drift")
    active_sha256 = sha256(ACTIVE)
    require(
        active_sha256 in {
            CANDIDATE_SHA256,
            WARNING_REMEDIATION_CANDIDATE_SHA256,
            BOOTSTRAP_CANDIDATE_SHA256,
            "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5",
            "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3",
            "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c",
        },
        "authoritative PCB-PWR is not an accepted buck-placement successor",
    )
    expected_active = {
        CANDIDATE_SHA256: CANDIDATE,
        WARNING_REMEDIATION_CANDIDATE_SHA256: WARNING_REMEDIATION_CANDIDATE,
        BOOTSTRAP_CANDIDATE_SHA256: BOOTSTRAP_CANDIDATE,
        "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5":
        ROOT / "hardware/kicad/candidates/PCB-PWR-LM74700-VCAP-ROUTING-002/PCB-PWR_LM74700_VCAP_ROUTING_002_CANDIDATE_REV_A.kicad_pcb",
        "05f20024abd369247cca50503ef9e211fe939dfe0be5dbf647628b6ba70826c3":
        ROOT / "hardware/kicad/candidates/PCB-PWR-VBAT-RAW-ROUTING-003/PCB-PWR_VBAT_RAW_ROUTING_003_CANDIDATE_REV_A.kicad_pcb",
        "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c":
        ROOT / "hardware/kicad/candidates/PCB-PWR-REV-GATE-ROUTING-004/PCB-PWR_REV_GATE_ROUTING_004_CANDIDATE_REV_A.kicad_pcb",
    }[active_sha256]
    require(ACTIVE.read_bytes() == expected_active.read_bytes(),
            "authoritative PCB-PWR accepted-successor byte identity drift")
    require(sha256(GENERATOR) == HISTORICAL_REGENERATOR_SHA256,
            "PCB-PWR buck placement historical regenerator SHA-256 drift")

    base = Board.from_file(str(BASE), encoding="utf-8")
    candidate = Board.from_file(str(CANDIDATE), encoding="utf-8")
    active = Board.from_file(str(ACTIVE), encoding="utf-8")
    base_footprints = {ref_of(item): item for item in base.footprints}
    candidate_footprints = {ref_of(item): item for item in candidate.footprints}
    require(base_footprints.keys() == candidate_footprints.keys(),
            "PCB-PWR candidate footprint set drift")

    changed: set[str] = set()
    for reference in base_footprints:
        first = base_footprints[reference]
        second = candidate_footprints[reference]
        require(without_pose(first) == without_pose(second),
                f"{reference}: non-placement footprint data changed")
        if pose_of(first) != pose_of(second):
            changed.add(reference)
    require(changed == set(EXPECTED_POSES),
            f"unexpected PCB-PWR moved footprints: {sorted(changed)}")
    for reference, (old, new) in EXPECTED_POSES.items():
        require(all(close(a, b) for a, b in zip(
                    pose_of(base_footprints[reference]), old)),
                f"{reference}: base pose drift")
        require(all(close(a, b) for a, b in zip(
                    pose_of(candidate_footprints[reference]), new)),
                f"{reference}: candidate pose drift")
    active_footprints = {ref_of(item): item for item in active.footprints}
    require(active_footprints.keys() == candidate_footprints.keys(),
            "active placement successor footprint set drift")
    for reference in candidate_footprints:
        require(
            all(close(a, b) for a, b in zip(
                pose_of(active_footprints[reference]),
                pose_of(candidate_footprints[reference]),
            )),
            f"{reference}: active placement successor pose drift",
        )
    require(len(active.traceItems) in {0, 2, 3, 4, 8} and len(active.zones) == 0,
            "active placement successor exceeds accepted REV_GATE copper")

    for field in (
        "version", "generator", "general", "paper", "titleBlock", "layers",
        "setup", "properties", "nets", "traceItems", "zones", "graphicItems",
        "dimensions", "targets", "groups",
    ):
        require(getattr(base, field) == getattr(candidate, field),
                f"candidate changes non-placement board field {field}")
    require(len(base.traceItems) == len(candidate.traceItems) == 0 and
            len(base.zones) == len(candidate.zones) == 0,
            "placement-only proposal contains routed copper")

    clearance = fitted_clearance(candidate)
    topology = topology_metrics(base, candidate)

    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    require(
        review.get("proposal_id") == "PCB-PWR-BUCK-PLACEMENT-ECO-001"
        and review.get("status") ==
        "STATIC_PROPOSAL_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and review.get("base", {}).get("board_sha256") == BASE_SHA256
        and review.get("candidate", {}).get("board_sha256") == CANDIDATE_SHA256
        and review.get("candidate", {}).get("generator_sha256") ==
        REVIEWED_GENERATOR_SHA256
        and review.get("decision_boundary", {}).get("proposal_only") is True
        and review.get("decision_boundary", {}).get(
            "applied_to_authoritative_board"
        ) is False
        and review.get("decision_boundary", {}).get(
            "manufacturing_release"
        ) is False,
        "PCB-PWR buck placement proposal boundary drift",
    )
    review_delta = {
        item["refdes"]: (
            (
                float(item["from"]["x_mm"]),
                float(item["from"]["y_mm"]),
                float(item["from"]["rotation_deg"]),
            ),
            (
                float(item["to"]["x_mm"]),
                float(item["to"]["y_mm"]),
                float(item["to"]["rotation_deg"]),
            ),
        )
        for item in review.get("bounded_placement_delta", [])
    }
    require(review_delta == EXPECTED_POSES,
            "PCB-PWR buck placement proposal pose manifest drift")
    static = review.get("static_validation", {})
    require(
        static.get("fitted_footprints") == clearance["fitted_footprints"]
        and close(static.get("required_clearance_mm"),
                  clearance["required_clearance_mm"])
        and close(static.get("minimum_observed_clearance_mm"),
                  clearance["minimum_clearance_mm"])
        and static.get("component_conflicts") == 0
        and static.get("mounting_body_conflicts") == 0
        and static.get("mounting_pad_conflicts") == 0
        and static.get("unrelated_footprints_moved") is False
        and static.get("copper_changed") is False,
        "PCB-PWR buck placement proposal static-result drift",
    )

    require(sha256(APPROVAL) == APPROVAL_SHA256,
            "PCB-PWR buck placement approval SHA-256 drift")
    require(sha256(MAPPING) == MAPPING_SHA256,
            "PCB-PWR buck placement review mapping SHA-256 drift")
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    application = json.loads(APPLICATION.read_text(encoding="utf-8"))
    authorization = approval.get("authorization", {})
    require(
        approval.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and approval.get("reviewed_tree_sha") == REVIEWED_TREE
        and approval.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and approval.get("reviewed_candidate_board_sha256") == CANDIDATE_SHA256
        and authorization.get(
            "apply_exact_hash_bound_c4_c6_l1_l2_placement_delta"
        ) is True
        and authorization.get("routing_complete") is False
        and authorization.get("cam_or_manufacturing_release") is False,
        "PCB-PWR buck placement approval identity or boundary drift",
    )
    require(
        mapping.get("reviewed_github_commit_sha") == REVIEWED_COMMIT
        and mapping.get("reviewed_tree_sha") == REVIEWED_TREE
        and mapping.get("candidate_board_sha256") == CANDIDATE_SHA256
        and mapping.get("generator_sha256") == REVIEWED_GENERATOR_SHA256
        and mapping.get("equivalence") == "EXACT_REVIEWED_TREE_AND_BLOBS"
        and mapping.get("cam_or_manufacturing_release") is False,
        "PCB-PWR buck placement review mapping drift",
    )
    require(
        application.get("approval_commit_sha") == APPROVAL_COMMIT
        and application.get("approval_sha256") == APPROVAL_SHA256
        and application.get("decision") ==
        "ACCEPT_PCB_PWR_BUCK_PLACEMENT_ECO_001_SUBGATE"
        and application.get("applied", {}).get("board_sha256") ==
        CANDIDATE_SHA256
        and application.get("applied", {}).get("exact_candidate_byte_identity")
        is True
        and application.get("machine_gate", {}).get("status") in {
            "PENDING_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
            "PASS_COMMIT_BOUND_CI_AND_PCB_NATIVE_GATE",
        }
        and application.get("routing_complete") is False
        and application.get("review_b_complete") is False
        and application.get("cam_or_manufacturing_release") is False,
        "PCB-PWR buck placement application identity or boundary drift",
    )

    report: dict[str, object] = {
        "status": "PASS_STATIC_ACCEPTED_AND_APPLIED",
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "reviewed_generator_sha256": REVIEWED_GENERATOR_SHA256,
        "historical_regenerator_sha256": HISTORICAL_REGENERATOR_SHA256,
        "moved_footprints": sorted(changed),
        "placement_clearance": clearance,
        "topology_metrics": topology,
        "routed_copper_added": False,
        "historical_proposal_authoritative_board_modified": False,
        "active_successor_sha256": active_sha256,
        "review_b_complete": False,
        "manufacturing_release": False,
    }
    require((drc_base is None) == (drc_candidate is None),
            "both comparative DRC paths are required together")
    if drc_base is not None and drc_candidate is not None:
        report["comparative_drc"] = audit_drc(drc_base, drc_candidate)
        report["status"] = (
            "PASS_KICAD9_COMPARATIVE_PROPOSAL_HUMAN_REVIEW_PENDING"
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drc-base", type=Path)
    parser.add_argument("--drc-candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.drc_base, args.drc_candidate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print("PCB-PWR buck placement ECO-001 candidate audit:", report["status"])
    print(
        f"candidate_sha256={CANDIDATE_SHA256} "
        f"moved={report['moved_footprints']} "
        f"minimum_clearance_mm="
        f"{report['placement_clearance']['minimum_clearance_mm']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
