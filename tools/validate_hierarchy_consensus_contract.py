#!/usr/bin/env python3
"""QG-1 completeness check for the bounded 4-8-window hierarchy contract."""
from __future__ import annotations

import ast
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def settings_values() -> dict[str, object]:
    tree = ast.parse(read("server/config.py"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            values: dict[str, object] = {}
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    try:
                        values[item.target.id] = ast.literal_eval(item.value)
                    except (ValueError, TypeError):
                        pass
            return values
    raise AssertionError("Settings class not found")


def csv_ids(path: str) -> set[str]:
    with (ROOT / path).open(encoding="utf-8", newline="") as handle:
        return {str(row[0]) for row in csv.reader(handle) if row}


def main() -> int:
    config = settings_values()
    require(config.get("hierarchy_min_evidence_windows") == 4, "minimum hierarchy evidence drift")
    require(config.get("hierarchy_max_evidence_windows") == 8, "maximum hierarchy evidence drift")
    require(config.get("hierarchy_min_consensus_ratio") == 0.625, "hierarchy consensus threshold drift")
    require(config.get("temporal_type_window_seconds") == (4.0, 6.0, 8.0), "temporal horizons drift")

    model = json.loads(read("server/models/temporal_type_model_v07.json"))
    require(set(model.get("horizons", {})) == {"4.0", "6.0", "8.0"}, "checked-in model horizons drift")
    require(model.get("timing", {}).get("evidence_window_range") == [4, 8], "model evidence metadata drift")
    require(not model.get("type_readiness", {}).get("operational_validation_ready", True),
            "unvalidated type model must not permit an operational lock")

    schema = read("server/station/schemas.py")
    service = read("server/station/online_type_service.py")
    family = read("server/ml/acoustic_family.py")
    tests = read("server/tests/test_online_hierarchy_service.py")
    firmware_header = read("firmware/include/zs_classifier_consensus.h")
    firmware_source = read("firmware/src/zs_classifier_consensus.c")
    firmware_test = read("firmware/tests/test_classifier_consensus.c")
    cmake = read("firmware/CMakeLists.txt")
    ci = read(".github/workflows/ci.yml")
    for token in ("evidence_windows", "required_windows", "max_windows", "hierarchical_label"):
        require(token in schema, f"live hierarchy schema missing {token}")
    for token in ("seen_updates", "hierarchy_min_evidence_windows", "hierarchy_max_evidence_windows"):
        require(token in service, f"live evidence guard missing {token}")
    for token in ("UNKNOWN_PROP_PISTON_UAV", "UNKNOWN_TURBINE_JET_UAV", "UNKNOWN_ROTOR_ELECTRIC_UAV"):
        require(token in family, f"unknown UAV family branch missing {token}")
    for token in ("requires_four_unique_windows", "caps_consensus_at_latest_eight_windows"):
        require(token in tests, f"QG-2 scenario missing {token}")
    for token in ("ZS_CLASSIFICATION_MIN_WINDOWS 4u", "ZS_CLASSIFICATION_MAX_WINDOWS 8u"):
        require(token in firmware_header, f"firmware evidence contract missing {token}")
    for token in ("required_votes", "ZS_FAMILY_PROP_PISTON", "ZS_FAMILY_TURBINE_JET", "ZS_FAMILY_ROTOR_ELECTRIC"):
        require(token in firmware_source, f"firmware hierarchy implementation missing {token}")
    for token in ("ZS_CLASS_PISTON_UAV", "ZS_CLASS_REACTIVE_UAV", "ZS_CLASS_ELECTRIC_UAV"):
        require(token in firmware_test, f"firmware QG-2 branch missing {token}")
    require("zs_classifier_consensus_tests" in cmake and "classifier_consensus" in cmake,
            "firmware hierarchy test is not bound to CMake/CTest")
    require("validate_hierarchy_consensus_contract.py" in ci, "hierarchy QG-1 is not bound to CI")

    require("DEC-029" in csv_ids("docs/DECISION_LOG.csv"), "customer hierarchy decision missing")
    require("REQ-CLS-001" in csv_ids("docs/REQUIREMENTS_TRACEABILITY.csv"), "hierarchy traceability missing")

    print("Hierarchical 4-8-window QG-1 PASS")
    print("bounded unique-window evidence, unknown-family branches and fail-closed type readiness traced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
