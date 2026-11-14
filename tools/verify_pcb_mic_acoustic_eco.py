"""Verify the intended semantic delta for the PCB-MIC acoustic ECO."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path


COORD_TO_MM = 0.0254 / 10000.0
ACOUSTIC_RULE = (
    "MK1_Internal_Acoustic_ClearanceInComponent('MK1')"
    "MK1_Internal_Acoustic_ClearanceInComponent('MK1')"
    "InComponent('MK1')MK1_Internal_Acoustic_Clearance"
)
LOCAL_RULE = "MK1_Manufacturer_Copper_0p125mm"
GLOBAL_RULE = "Clearence 0,2_NetClass"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def without(mapping: dict, *keys: str) -> dict:
    result = dict(mapping)
    for key in keys:
        result.pop(key, None)
    return result


def mm(coord: int | float) -> float:
    return coord * COORD_TO_MM


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path)
    parser.add_argument("final", type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    args = parser.parse_args()

    original = json.loads(args.original.read_text(encoding="utf-8"))
    final = json.loads(args.final.read_text(encoding="utf-8"))
    checks: list[dict] = []

    def check(name: str, condition: bool, detail: object) -> None:
        checks.append({"name": name, "pass": bool(condition), "detail": detail})

    old_board = deepcopy(original["board"])
    new_board = deepcopy(final["board"])
    old_board.pop("file", None)
    new_board.pop("file", None)
    check("board_geometry_and_stack_unchanged", old_board == new_board, {})
    check(
        "components_unchanged",
        original["components"] == final["components"],
        {"count": len(original["components"]["components"])},
    )
    check("classes_unchanged", original["classes"] == final["classes"], {})

    old_pads = original["pads"]["pads"]
    new_pads = final["pads"]["pads"]
    pad_deltas = []
    for index, (old, new) in enumerate(zip(old_pads, new_pads)):
        if old != new:
            pad_deltas.append(
                {
                    "index": index,
                    "component": old.get("comp"),
                    "pad": old.get("name"),
                    "before_coord": [old["x"], old["y"]],
                    "after_coord": [new["x"], new["y"]],
                    "before_mm": [mm(old["x"]), mm(old["y"])],
                    "after_mm": [mm(new["x"]), mm(new["y"])],
                    "only_xy_changed": without(old, "x", "y")
                    == without(new, "x", "y"),
                }
            )
    pad_identity_ok = (
        len(old_pads) == len(new_pads) == 53
        and len(pad_deltas) == 32
        and all(d["component"] == "MK1" and d["pad"] == "3" for d in pad_deltas)
        and all(d["only_xy_changed"] for d in pad_deltas)
    )
    old_changed = [old_pads[d["index"]] for d in pad_deltas]
    new_changed = [new_pads[d["index"]] for d in pad_deltas]
    center_x = sum(p["x"] for p in old_changed) / len(old_changed)
    center_y = sum(p["y"] for p in old_changed) / len(old_changed)
    radial = []
    for old, new in zip(old_changed, new_changed):
        before = mm(math.hypot(old["x"] - center_x, old["y"] - center_y))
        after = mm(math.hypot(new["x"] - center_x, new["y"] - center_y))
        radial.append({"before_mm": before, "after_mm": after, "delta_mm": after - before})
    radial_ok = all(abs(item["before_mm"] - 0.6625) <= 0.000003 for item in radial)
    radial_ok = radial_ok and all(
        abs(item["after_mm"] - 0.6725) <= 0.000003
        and abs(item["delta_mm"] - 0.0100) <= 0.000003
        for item in radial
    )
    check(
        "exactly_32_mk1_pad3_fragments_changed",
        pad_identity_ok,
        {"total_pads": len(old_pads), "changed_pads": len(pad_deltas)},
    )
    check(
        "mk1_pad3_fragments_moved_radially_outward_0p010mm",
        radial_ok,
        {
            "center_mm": [mm(center_x), mm(center_y)],
            "before_radius_mm": [min(x["before_mm"] for x in radial), max(x["before_mm"] for x in radial)],
            "after_radius_mm": [min(x["after_mm"] for x in radial), max(x["after_mm"] for x in radial)],
            "radial_delta_mm": [min(x["delta_mm"] for x in radial), max(x["delta_mm"] for x in radial)],
        },
    )

    old_copper = original["copper"]["copper"]
    new_copper = final["copper"]["copper"]
    copper_deltas = []
    for index, (old, new) in enumerate(zip(old_copper, new_copper)):
        if old != new:
            copper_deltas.append(
                {
                    "index": index,
                    "before": old,
                    "after": new,
                    "before_mm": [mm(v) for v in old["v"]],
                    "after_mm": [mm(v) for v in new["v"]],
                    "only_geometry_changed": without(old, "v") == without(new, "v"),
                }
            )
    expected_tracks = [
        ([12.7, 5.349999, 15.0, 5.349999, 0.3], [12.75, 5.349999, 15.0, 5.349999, 0.3]),
        ([11.37, 6.599999, 11.699999, 5.949998, 0.16], [11.37, 6.599999, 11.695001, 5.960001, 0.16]),
    ]

    def close_vector(actual: list[float], expected: list[float]) -> bool:
        return len(actual) == len(expected) and all(
            abs(a - e) <= 0.000004 for a, e in zip(actual, expected)
        )

    tracks_ok = (
        len(old_copper) == len(new_copper) == 106
        and len(copper_deltas) == 2
        and all(d["before"]["k"] == "track" for d in copper_deltas)
        and all(d["before"]["net"] == "GND" for d in copper_deltas)
        and all(d["only_geometry_changed"] for d in copper_deltas)
        and all(
            close_vector(delta["before_mm"], expected[0])
            and close_vector(delta["after_mm"], expected[1])
            for delta, expected in zip(copper_deltas, expected_tracks)
        )
    )
    check(
        "exactly_two_gnd_track_endpoints_changed",
        tracks_ok,
        {"total_copper_objects": len(old_copper), "changed_objects": len(copper_deltas)},
    )

    old_rules = {rule["name"]: rule for rule in original["rules"]["rules"]}
    new_rules = {rule["name"]: rule for rule in final["rules"]["rules"]}
    added = sorted(set(new_rules) - set(old_rules))
    removed = sorted(set(old_rules) - set(new_rules))
    modified = sorted(
        name for name in set(old_rules) & set(new_rules) if old_rules[name] != new_rules[name]
    )
    expected_rule_names = added == [LOCAL_RULE] and removed == [] and modified == [GLOBAL_RULE, ACOUSTIC_RULE]
    acoustic = new_rules.get(ACOUSTIC_RULE, {})
    local = new_rules.get(LOCAL_RULE, {})
    global_rule = new_rules.get(GLOBAL_RULE, {})
    rule_values_ok = (
        acoustic.get("priority") == 1
        and acoustic.get("scope1") == "IsPad && (Name = 'MK1-3')"
        and acoustic.get("scope2") == "IsPad && (Name = 'MK1-Un1')"
        and "Gap=0.1mm" in acoustic.get("descriptor", "")
        and local.get("priority") == 2
        and local.get("scope1") == "IsPad && (Name = 'MK1-3')"
        and local.get("scope2")
        == "IsPad && InComponent('MK1') && (Name <> 'MK1-3') && (Name <> 'MK1-Un1')"
        and "Gap=0.125mm" in local.get("descriptor", "")
        and global_rule.get("priority") == 3
        and global_rule.get("scope1") == "InNetClass('Default')"
        and global_rule.get("scope2") == "All"
        and "Gap=0.2mm" in global_rule.get("descriptor", "")
    )
    check(
        "only_expected_rule_records_changed",
        expected_rule_names,
        {"added": added, "removed": removed, "modified": modified},
    )
    check(
        "clearance_rule_scopes_values_and_priorities_match_baseline",
        rule_values_ok,
        {"acoustic": acoustic, "local_manufacturer": local, "global": global_rule},
    )

    passed = all(item["pass"] for item in checks)
    evidence = {
        "schema": "pcb-mic-acoustic-eco-semantic-compare-v1",
        "pass": passed,
        "inputs": {
            "original_layout_model": str(args.original),
            "original_layout_model_sha256": sha256(args.original),
            "final_layout_model": str(args.final),
            "final_layout_model_sha256": sha256(args.final),
        },
        "checks": checks,
        "pad_deltas": pad_deltas,
        "track_deltas": copper_deltas,
        "limits": [
            "This check compares the semantic model exposed by Altium for board, components, pads, copper, rules and classes.",
            "DRC results and schematic-to-PCB parity are separate release gates.",
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# PCB-MIC acoustic ECO semantic comparison",
        "",
        f"Result: **{'PASS' if passed else 'FAIL'}**",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    lines.extend(
        f"| {item['name']} | {'PASS' if item['pass'] else 'FAIL'} |" for item in checks
    )
    lines.extend(
        [
            "",
            "## Verified delta",
            "",
            f"- Changed MK1 pad-3 fragments: {len(pad_deltas)} of {len(old_pads)} pads.",
            f"- Changed GND track objects: {len(copper_deltas)} of {len(old_copper)} copper objects.",
            "- Added one local 0.125 mm manufacturer-copper rule.",
            "- Narrowed the 0.10 mm acoustic exception to MK1-3 versus MK1-Un1.",
            "- Moved the general 0.20 mm clearance rule to priority 3.",
            "- Board outline, stack, components, net classes and all other semantic objects are unchanged.",
            "",
            "## Limits",
            "",
            "This report does not by itself prove schematic-to-PCB parity or manufacturing-release readiness.",
        ]
    )
    args.markdown.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"pass": passed, "checks": len(checks), "json": str(args.json)}, ensure_ascii=False))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
