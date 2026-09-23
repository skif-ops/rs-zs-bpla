#!/usr/bin/env python3
"""Validate locked EVT-PRE-20 configuration and hardware baseline using stdlib only."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SERIALS = [f"DIO-EVT-{index:03d}" for index in range(1, 21)]
EXPECTED_PROGRAM_EXTENSION_SERIALS = [
    *[f"DIO-EVT-{index:03d}" for index in range(21, 41)],
    "DIO-EVT-B01",
]


def read_csv(relative_path: str) -> list[dict[str, str]]:
    path = ROOT / relative_path
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_csv_shapes() -> None:
    for path in sorted(ROOT.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
        require(bool(rows), f"empty CSV: {path.relative_to(ROOT)}")
        width = len(rows[0])
        for line_number, row in enumerate(rows[1:], start=2):
            require(
                len(row) == width,
                f"CSV width mismatch: {path.relative_to(ROOT)}:{line_number}",
            )


def validate_lot() -> None:
    lot = read_csv("manufacturing/LOT_SERIAL_REGISTER.csv")
    require([row["Serial"] for row in lot] == EXPECTED_SERIALS, "maximum-capacity serial range mismatch")
    require(len({row["Serial"] for row in lot}) == 20, "reserved serials are not unique")
    require(
        all(row["Housing_Technology"] == "VACUUM_CASTING_PRIMARY" for row in lot),
        "reserved serial capacity does not retain the primary vacuum-casting process",
    )
    require(
        all(row["Status"] == "SELECTED_EVT_LOT_AWAITING_BUILD" for row in lot),
        "selected EVT-20 serial assignment is incomplete or incorrectly released",
    )
    require(all(row["APN_Mode"] == "PUBLIC_ONLY" for row in lot), "pilot APN is not PUBLIC_ONLY")
    require(all(row["LoRa_Profile"] == "RU868_LOCKED" for row in lot), "selected-lot LoRa is not RU868")

    program_extension = read_csv("manufacturing/LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv")
    require(
        [row["Serial"] for row in program_extension] == EXPECTED_PROGRAM_EXTENSION_SERIALS,
        "second-set and bench serial range mismatch",
    )
    require(
        len({row["Serial"] for row in [*lot, *program_extension]}) == 41,
        "program serial identities are not unique across 2x20+1",
    )
    second_set = program_extension[:20]
    bench = program_extension[20:]
    require(
        all(row["Lot"] == "EVT-PRE-20-LOT-2" for row in second_set),
        "second EVT-20 set is not bound to its own lot",
    )
    require(
        all(row["Housing_Technology"] == "VACUUM_CASTING_PRIMARY" for row in second_set),
        "second EVT-20 set does not retain the primary vacuum-casting process",
    )
    require(
        all(row["Status"] == "SECOND_GROUP_RESERVED_AWAITING_BUILD" for row in second_set),
        "second EVT-20 serial reservation is incomplete or incorrectly released",
    )
    require(
        len(bench) == 1
        and bench[0]["Lot"] == "BENCH"
        and bench[0]["Housing_Technology"] == "BENCH_FIXTURE"
        and bench[0]["Status"] == "BENCH_UNIT_RESERVED",
        "bench serial reservation differs from the controlled program",
    )
    require(
        all(row["APN_Mode"] == "PUBLIC_ONLY" for row in program_extension),
        "second-set or bench APN is not PUBLIC_ONLY",
    )
    require(
        all(row["LoRa_Profile"] == "RU868_LOCKED" for row in program_extension),
        "second-set or bench LoRa profile is not RU868",
    )

    housing = read_csv("manufacturing/HOUSING_LOT_PLAN.csv")
    require([row["Serial"] for row in housing] == EXPECTED_SERIALS, "housing capacity serial range mismatch")
    require(sum(int(row["Primary_Qty"]) for row in housing) == 20, "primary housing capacity is not 20")
    require(
        sum(int(row["Fallback_Qty_if_Activated"]) for row in housing) == 20,
        "maximum 3D fallback capacity is not 20",
    )
    require(all(row["Primary_Process"] == "VACUUM_CASTING" for row in housing), "primary process mismatch")
    require(all(row["Fallback_Process"] == "3D_PRINT" for row in housing), "fallback process mismatch")
    require(
        all(row["Injection_Molding_Scope"] == "SOURCE_DATA_AND_DFM_ONLY" for row in housing),
        "injection molding exceeds source-data-only scope",
    )
    require(
        all(row["Status"] == "SELECTED_EVT_LOT_PRIMARY_NOT_RELEASED" for row in housing),
        "selected EVT-20 housing assignment is incomplete or incorrectly released",
    )

    scenarios = read_csv("manufacturing/EVT_LOT_SELECTION_REV_A.csv")
    require([row["Station_Qty"] for row in scenarios] == ["4", "10", "20"], "EVT lot options are not 4 10 20")
    expected_selection = {4: "NOT_SELECTED", 10: "NOT_SELECTED", 20: "SELECTED"}
    for row in scenarios:
        quantity = int(row["Station_Qty"])
        require(row["Serial_Start"] == "DIO-EVT-001", f"{quantity}-station lot does not start at serial 001")
        require(row["Serial_End"] == f"DIO-EVT-{quantity:03d}", f"{quantity}-station lot serial end mismatch")
        require(row["BOM_Quantity_Column"] == f"Qty_{quantity}", f"{quantity}-station BOM quantity binding mismatch")
        require(row["BOM_Procurement_Column"] == f"Procure_qty_{quantity}", f"{quantity}-station BOM procurement binding mismatch")
        require(row["Procurement_Status"] == "RFQ_READY", f"{quantity}-station RFQ is not ready")
        require(
            row["Selection_Status"] == expected_selection[quantity],
            f"{quantity}-station selection status does not match locked EVT-20 decision",
        )
    selected = [row for row in scenarios if row["Selection_Status"] == "SELECTED"]
    require(len(selected) == 1 and selected[0]["Scenario_ID"] == "EVT-20", "EVT-20 is not the single selected lot")


def validate_procurement() -> None:
    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_REV_A.csv")}
    for lot_size in (4, 10, 20):
        require(
            bom["HSG-VC"][f"Qty_{lot_size}"] == str(lot_size),
            f"BOM vacuum housing quantity is not {lot_size} for lot {lot_size}",
        )
        require(
            bom["HSG-VC"][f"Procure_qty_{lot_size}"] == str(lot_size),
            f"BOM vacuum housing procurement quantity is not {lot_size}",
        )
        require(
            bom["HSG-3D"][f"Procure_qty_{lot_size}"] == "0",
            f"3D fallback was ordered before activation for lot {lot_size}",
        )
        require(
            bom["HSG-IM"][f"Procure_qty_{lot_size}"] == "0",
            f"injection-molding pilot hardware was ordered for lot {lot_size}",
        )

    rfq = {row["RFQ_ID"]: row for row in read_csv("hardware/CHINA_PROCUREMENT_RFQ.csv")}
    for lot_size in (4, 10, 20):
        require(
            rfq["RFQ-017"][f"Required_qty_{lot_size}"] == str(lot_size),
            f"vacuum-casting RFQ quantity is not {lot_size}",
        )
        require(
            rfq["RFQ-018"][f"Required_qty_{lot_size}"] == "0",
            f"3D fallback procurement is active for lot {lot_size}",
        )
        require(
            rfq["RFQ-019"][f"Required_qty_{lot_size}"] == "0",
            f"injection-molding procurement is active for lot {lot_size}",
        )
    require(rfq["RFQ-006"]["Manufacturer"] == "Raytac", "RFQ BLE manufacturer is stale")
    require(rfq["RFQ-006"]["MPN_or_spec"] == "MDBT50Q-P1MV2", "RFQ BLE MPN is stale")
    require(rfq["RFQ-016"]["MPN_or_spec"] == "2336582-1", "RFQ SIM connector MPN is stale")


def validate_decisions_and_tests() -> None:
    decisions = {row["Decision_ID"]: row for row in read_csv("docs/DECISION_LOG.csv")}
    for decision_id in (
        "DEC-015", "DEC-016", "DEC-017", "DEC-018", "DEC-037", "DEC-038",
        "DEC-039", "DEC-040", "DEC-041", "DEC-042", "DEC-045",
    ):
        require(decisions[decision_id]["Status"] == "LOCKED", f"{decision_id} is not locked")
    require(
        "3e215e26e0d4cb160b309de3d3fd5a3145a756bf" in decisions["DEC-039"]["Decision"],
        "initial PCB-MIC Review-A decision binding is missing",
    )
    require(
        "cb69c0bbc1457b498ee4f44ee7da1d566033c23f" in decisions["DEC-040"]["Decision"]
        and "ECO_REQUIRED" in decisions["DEC-040"]["Impact"],
        "PCB-MIC baseline copper ECO decision binding is missing",
    )
    require(
        "e17a86bc78ba979f74c5549b378e94f7f3447fe4" in decisions["DEC-041"]["Decision"],
        "repeat PCB-MIC Review-A decision binding is missing",
    )
    require(
        "7aeec13aa0c7ba1b3cd9095b800c6d08755912a3" in decisions["DEC-042"]["Decision"]
        and "copper-return subgate" in decisions["DEC-042"]["Decision"],
        "PCB-MIC copper-return acceptance binding is missing",
    )
    require(
        decisions["DEC-043"]["Status"] == "IMPLEMENTED_EXTERNAL_ACCEPTANCE_PENDING",
        "PCB-MIC manufacturing-handoff separation decision is missing",
    )
    require(
        decisions["DEC-044"]["Status"] == "IMPLEMENTED_2D_CLEARANCE_PASS"
        and "MAIN-AUTH-011" in decisions["DEC-044"]["Decision"],
        "PCB-MAIN placement-clearance ECO decision is missing",
    )
    require(
        "61cbe796de2f87560342a44b063ff6283a8ce1e8" in decisions["DEC-045"]["Decision"]
        and "5ef7d0390da97796febbef6a69f0206a06efe00782e238bf7c8f32bf29d08fc1"
        in decisions["DEC-045"]["Decision"]
        and "ACCEPT_LIMITED_MECHANICAL_ECO" in decisions["DEC-045"]["Source"],
        "PCB-MAIN limited mechanical ECO acceptance binding is missing",
    )
    require(
        decisions["DEC-046"]["Status"] == "IMPLEMENTED_2D_CLEARANCE_PASS"
        and "225-reference manifest" in decisions["DEC-046"]["Decision"]
        and "227 controlled courtyards" in decisions["DEC-046"]["Impact"],
        "PCB-MAIN deterministic placement-repack decision is missing",
    )
    require(
        decisions["DEC-047"]["Status"] == "IMPLEMENTED_PRE_ROUTE_CONSTRAINT_PASS"
        and "all 186 PCB-MAIN native nets" in decisions["DEC-047"]["Decision"]
        and "numeric RF/USB geometry" in decisions["DEC-047"]["Impact"],
        "PCB-MAIN pre-route constraint decision is missing or over-released",
    )
    require(
        decisions["DEC-048"]["Status"] == "IMPLEMENTED_TWO_FABRICATOR_RESPONSES_PENDING"
        and "fabricator acceptance and routing authority" in decisions["DEC-048"]["Decision"]
        and "two independent fabricators" in decisions["DEC-048"]["Impact"]
        and "manufacturing release open" in decisions["DEC-048"]["Impact"],
        "PCB-MAIN stackup-request/fabricator-acceptance separation decision is missing",
    )
    require(
        decisions["DEC-049"]["Status"] == "IMPLEMENTED_SELECTED_ASSEMBLER_RESPONSE_PENDING"
        and "internal assembler-request readiness" in decisions["DEC-049"]["Decision"]
        and "bounded 14-question request" in decisions["DEC-049"]["Impact"]
        and "paste export USB SI whole-board DFM Review B and manufacturing release open"
        in decisions["DEC-049"]["Impact"],
        "PCB-MAIN assembler-request/process-acceptance separation decision is missing",
    )
    require(
        decisions["DEC-054"]["Status"] == "IMPLEMENTED_DIM_003_EXTERNAL_ACCEPTANCE_PENDING"
        and "mechanical acceptance and routing authority" in decisions["DEC-054"]["Decision"]
        and "18-row" in decisions["DEC-054"]["Impact"]
        and "0/18" in decisions["DEC-054"]["Impact"],
        "PCB-PWR DIM-003 request/mechanical-acceptance separation decision is missing",
    )
    require(
        decisions["DEC-097"]["Status"] ==
        "ACCEPTED_EVT_DIM_003_SERIAL_REVALIDATION_REQUIRED"
        and "DIM-003 18/18" in decisions["DEC-097"]["Impact"]
        and "four round" in decisions["DEC-097"]["Impact"]
        and "serial enclosure revalidation" in decisions["DEC-097"]["Impact"],
        "PCB-PWR DIM-003 EVT acceptance or serial-revalidation boundary is missing",
    )
    require(
        decisions["DEC-055"]["Status"] == "IMPLEMENTED_TWO_FABRICATOR_RESPONSES_PENDING"
        and "fabricator acceptance and numeric power geometry"
        in decisions["DEC-055"]["Decision"]
        and "24-row" in decisions["DEC-055"]["Impact"]
        and "two independent fabricators" in decisions["DEC-055"]["Impact"]
        and "0/24" in decisions["DEC-055"]["Impact"],
        "PCB-PWR stackup/copper request and numeric-geometry separation decision is missing",
    )
    require(
        decisions["DEC-098"]["Status"] ==
        "LOCKED_NUMERIC_EVT_ENGINEERING_INPUT_FINAL_JOB_ACCEPTANCE_PENDING"
        and "JLC04161H-3313" in decisions["DEC-098"]["Impact"]
        and "all 31 nets" in decisions["DEC-098"]["Impact"]
        and "4.0 mm at 5 A" in decisions["DEC-098"]["Impact"]
        and "3.0 mm at 4 A" in decisions["DEC-098"]["Impact"]
        and "do not populate FAB-A or FAB-B rows" in decisions["DEC-098"]["Impact"],
        "PCB-PWR conservative numeric EVT routing decision is missing or over-released",
    )
    require(
        decisions["DEC-110"]["Status"] ==
        "PASS_EVT_ENGINEERING_STACKUP_PROFILE_ROUTING_INPUT_AUTHORIZED_JOB_DFM_PENDING"
        and "JLC04161H-3313 1.6 mm outer 2 oz inner 1 oz"
        in decisions["DEC-110"]["Impact"]
        and "35 um routing calculation lower bound"
        in decisions["DEC-110"]["Impact"]
        and "job-specific DFM deviation channel"
        in decisions["DEC-110"]["Impact"]
        and "manufacturing blocks" in decisions["DEC-110"]["Impact"],
        "PCB-PWR EVT stackup/order profile decision is missing or over-released",
    )
    require(
        decisions["DEC-111"]["Status"] ==
        "STATIC_CANDIDATE_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "U3.4 to C4.1" in decisions["DEC-111"]["Impact"]
        and "U4.4 to C6.1" in decisions["DEC-111"]["Impact"]
        and "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
        in decisions["DEC-111"]["Impact"]
        and "authoritative board unchanged" in decisions["DEC-111"]["Impact"]
        and "exact human acceptance before application" in decisions["DEC-111"]["Impact"]
        and "Review B CAM and manufacturing blocks" in decisions["DEC-111"]["Impact"],
        "PCB-PWR bootstrap routing candidate boundary is missing or over-released",
    )
    require(
        decisions["DEC-112"]["Status"] ==
        "PASS_COMMIT_BOUND_KICAD9_GATE_HUMAN_SUBGATE_PENDING"
        and "1c7c3704" in decisions["DEC-112"]["Reason"]
        and "86 to 86" in decisions["DEC-112"]["Reason"]
        and "126 to 124" in decisions["DEC-112"]["Reason"]
        and "ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE"
        in decisions["DEC-112"]["Impact"]
        and "authoritative PCB-PWR board unchanged" in decisions["DEC-112"]["Impact"]
        and "Review B CAM and manufacturing blocks" in decisions["DEC-112"]["Impact"],
        "PCB-PWR bootstrap routing machine-gate closure is missing or over-released",
    )
    require(
        decisions["DEC-113"]["Status"] ==
        "ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE_APPLICATION_PENDING"
        and "ACCEPT_PCB_PWR_BUCK_BOOTSTRAP_ROUTING_001_SUBGATE"
        in decisions["DEC-113"]["Reason"]
        and "U3.4-C4.1" in decisions["DEC-113"]["Impact"]
        and "U4.4-C6.1" in decisions["DEC-113"]["Impact"]
        and "fresh commit-bound application gate" in decisions["DEC-113"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-113"]["Impact"],
        "PCB-PWR bootstrap routing acceptance boundary is missing",
    )
    require(
        decisions["DEC-114"]["Status"] ==
        "APPLICATION_EXACT_BOOTSTRAP_DELTA_COMMIT_BOUND_GATE_PENDING"
        and "57d7b571" in decisions["DEC-114"]["Reason"]
        and "a8782a437b7ca6ea4929bd839fb3244c4a05e0a12bd4908321d6cc3a7ae05236"
        in decisions["DEC-114"]["Impact"]
        and "fresh commit-bound CI and PCB Native application gate"
        in decisions["DEC-114"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-114"]["Impact"],
        "PCB-PWR bootstrap routing application boundary is missing",
    )
    require(
        decisions["DEC-115"]["Status"] ==
        "PASS_EXACT_BOOTSTRAP_APPLICATION_REMAINING_ROUTING_NEXT"
        and "ca27482a" in decisions["DEC-115"]["Reason"]
        and "CI 598" in decisions["DEC-115"]["Reason"]
        and "PCB Native 325" in decisions["DEC-115"]["Reason"]
        and "86 to 86" in decisions["DEC-115"]["Reason"]
        and "126 to 124" in decisions["DEC-115"]["Reason"]
        and "neither overall routing nor Review B CAM DFM thermal or manufacturing complete"
        in decisions["DEC-115"]["Impact"],
        "PCB-PWR bootstrap routing application closure is missing or over-released",
    )
    require(
        decisions["DEC-116"]["Status"] ==
        "STATIC_CANDIDATE_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_002_CREATION_SUBGATE"
        in decisions["DEC-116"]["Reason"]
        and "U1.1-C1.1" in decisions["DEC-116"]["Impact"]
        and "3d779f947f882c23edec277ab9e898c87cfa960ec69eacf2170cd18d28fab2e5"
        in decisions["DEC-116"]["Impact"]
        and "prohibit a narrow substitute" in decisions["DEC-116"]["Impact"]
        and "exact human acceptance before application" in decisions["DEC-116"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-116"]["Impact"],
        "PCB-PWR routing candidate 002 boundary is missing or over-released",
    )
    require(
        decisions["DEC-117"]["Status"] ==
        "PASS_COMMIT_BOUND_KICAD9_GATE_HUMAN_SUBGATE_PENDING"
        and "186ad093" in decisions["DEC-117"]["Reason"]
        and "86 to 86" in decisions["DEC-117"]["Reason"]
        and "124 to 123" in decisions["DEC-117"]["Reason"]
        and "ACCEPT_PCB_PWR_LM74700_VCAP_ROUTING_002_SUBGATE"
        in decisions["DEC-117"]["Impact"]
        and "authoritative PCB-PWR board unchanged" in decisions["DEC-117"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-117"]["Impact"],
        "PCB-PWR routing candidate 002 machine-gate closure is missing",
    )
    require(
        decisions["DEC-118"]["Status"] ==
        "ACCEPT_PCB_PWR_LM74700_VCAP_ROUTING_002_SUBGATE_APPLICATION_PENDING"
        and "ACCEPT_PCB_PWR_LM74700_VCAP_ROUTING_002_SUBGATE"
        in decisions["DEC-118"]["Reason"]
        and "U1.1-C1.1" in decisions["DEC-118"]["Impact"]
        and "do not authorize a narrow switch-node substitute"
        in decisions["DEC-118"]["Impact"]
        and "fresh commit-bound application gate" in decisions["DEC-118"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-118"]["Impact"],
        "PCB-PWR routing candidate 002 acceptance boundary is missing",
    )
    require(
        decisions["DEC-119"]["Status"] ==
        "APPLICATION_EXACT_LM74700_VCAP_DELTA_COMMIT_BOUND_GATE_PENDING"
        and "b4b1ca81" in decisions["DEC-119"]["Reason"]
        and "U1.1-C1.1" in decisions["DEC-119"]["Impact"]
        and "prohibit narrow SW_3V8 or SW_3V3 substitution"
        in decisions["DEC-119"]["Impact"]
        and "fresh commit-bound CI and PCB Native application gate"
        in decisions["DEC-119"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-119"]["Impact"],
        "PCB-PWR routing candidate 002 application boundary is missing",
    )
    require(
        decisions["DEC-120"]["Status"] ==
        "PASS_EXACT_LM74700_VCAP_APPLICATION_REMAINING_ROUTING_NEXT"
        and "328457c6" in decisions["DEC-120"]["Reason"]
        and "CI 606" in decisions["DEC-120"]["Reason"]
        and "PCB Native 333" in decisions["DEC-120"]["Reason"]
        and "PCB-PWR Schematic 81" in decisions["DEC-120"]["Reason"]
        and "86 to 86" in decisions["DEC-120"]["Reason"]
        and "124 to 123" in decisions["DEC-120"]["Reason"]
        and "U1.1-C1.1" in decisions["DEC-120"]["Impact"]
        and "separate exact human gate" in decisions["DEC-120"]["Impact"]
        and "Review B CAM DFM thermal or manufacturing"
        in decisions["DEC-120"]["Impact"],
        "PCB-PWR routing candidate 002 application closure is missing",
    )
    require(
        decisions["DEC-121"]["Status"] ==
        "STATIC_CANDIDATE_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_003_CREATION_SUBGATE"
        in decisions["DEC-121"]["Reason"]
        and "J1.1-F1.1" in decisions["DEC-121"]["Impact"]
        and "4.0 mm F.Cu" in decisions["DEC-121"]["Impact"]
        and "exact human acceptance" in decisions["DEC-121"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-121"]["Impact"],
        "PCB-PWR routing candidate 003 creation boundary is missing",
    )
    require(
        decisions["DEC-122"]["Status"] ==
        "PASS_COMMIT_BOUND_KICAD9_GATE_HUMAN_SUBGATE_PENDING"
        and "4a1114ff" in decisions["DEC-122"]["Reason"]
        and "CI 612" in decisions["DEC-122"]["Reason"]
        and "PCB-PWR Schematic 86" in decisions["DEC-122"]["Reason"]
        and "PCB Native 339" in decisions["DEC-122"]["Reason"]
        and "86 to 86" in decisions["DEC-122"]["Reason"]
        and "123 to 122" in decisions["DEC-122"]["Reason"]
        and "ACCEPT_PCB_PWR_VBAT_RAW_ROUTING_003_SUBGATE"
        in decisions["DEC-122"]["Impact"]
        and "authoritative PCB-PWR board unchanged"
        in decisions["DEC-122"]["Impact"]
        and "buck hot-loop switch-node Kelvin return Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-122"]["Impact"],
        "PCB-PWR routing candidate 003 machine-gate closure is missing",
    )
    require(
        decisions["DEC-123"]["Status"] ==
        "ACCEPT_PCB_PWR_VBAT_RAW_ROUTING_003_SUBGATE_APPLICATION_PENDING"
        and "ACCEPT_PCB_PWR_VBAT_RAW_ROUTING_003_SUBGATE"
        in decisions["DEC-123"]["Reason"]
        and "J1.1-F1.1" in decisions["DEC-123"]["Impact"]
        and "do not authorize buck hot-loop or switch-node routing"
        in decisions["DEC-123"]["Impact"]
        and "fresh commit-bound application gate"
        in decisions["DEC-123"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-123"]["Impact"],
        "PCB-PWR routing candidate 003 acceptance boundary is missing",
    )
    require(
        decisions["DEC-124"]["Status"] ==
        "APPLICATION_EXACT_VBAT_RAW_DELTA_COMMIT_BOUND_GATE_PENDING"
        and "4356f40d" in decisions["DEC-124"]["Reason"]
        and "J1.1-F1.1" in decisions["DEC-124"]["Impact"]
        and "do not authorize buck hot-loop or switch-node routing"
        in decisions["DEC-124"]["Impact"]
        and "fresh commit-bound CI and PCB Native application gate"
        in decisions["DEC-124"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-124"]["Impact"],
        "PCB-PWR routing candidate 003 application boundary is missing",
    )
    require(
        decisions["DEC-125"]["Status"] ==
        "PASS_EXACT_VBAT_RAW_APPLICATION_REMAINING_ROUTING_NEXT"
        and "514696e8" in decisions["DEC-125"]["Reason"]
        and "CI 621" in decisions["DEC-125"]["Reason"]
        and "PCB-PWR Schematic 89" in decisions["DEC-125"]["Reason"]
        and "PCB Native 342" in decisions["DEC-125"]["Reason"]
        and "86 to 86" in decisions["DEC-125"]["Reason"]
        and "123 to 122" in decisions["DEC-125"]["Reason"]
        and "J1.1-F1.1" in decisions["DEC-125"]["Impact"]
        and "separate exact human gate" in decisions["DEC-125"]["Impact"]
        and "Review B CAM DFM thermal or manufacturing"
        in decisions["DEC-125"]["Impact"],
        "PCB-PWR routing candidate 003 application closure is missing",
    )
    require(
        decisions["DEC-126"]["Status"] ==
        "STATIC_CANDIDATE_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_004_CREATION_SUBGATE"
        in decisions["DEC-126"]["Reason"]
        and "U1.5-Q1.4" in decisions["DEC-126"]["Impact"]
        and "four 0.5 mm F.Cu segments" in decisions["DEC-126"]["Impact"]
        and "86 to 86" in decisions["DEC-126"]["Impact"]
        and "122 to 121" in decisions["DEC-126"]["Impact"]
        and "exact human acceptance" in decisions["DEC-126"]["Impact"]
        and "input load copper buck hot-loop switch-node Kelvin feedback return Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-126"]["Impact"],
        "PCB-PWR routing candidate 004 creation boundary is missing",
    )
    require(
        decisions["DEC-127"]["Status"] ==
        "PASS_COMMIT_BOUND_KICAD9_GATE_HUMAN_SUBGATE_PENDING"
        and "987a8fd4" in decisions["DEC-127"]["Reason"]
        and "CI 623" in decisions["DEC-127"]["Reason"]
        and "PCB-PWR Schematic 91" in decisions["DEC-127"]["Reason"]
        and "PCB Native 344" in decisions["DEC-127"]["Reason"]
        and "86 to 86" in decisions["DEC-127"]["Reason"]
        and "122 to 121" in decisions["DEC-127"]["Reason"]
        and "ACCEPT_PCB_PWR_REV_GATE_ROUTING_004_SUBGATE"
        in decisions["DEC-127"]["Impact"]
        and "authoritative PCB-PWR board unchanged"
        in decisions["DEC-127"]["Impact"]
        and "input load copper buck hot-loop switch-node Kelvin feedback return Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-127"]["Impact"],
        "PCB-PWR routing candidate 004 machine-gate closure is missing",
    )
    require(
        decisions["DEC-128"]["Status"] ==
        "ACCEPT_PCB_PWR_REV_GATE_ROUTING_004_SUBGATE_APPLICATION_PENDING"
        and "ACCEPT_PCB_PWR_REV_GATE_ROUTING_004_SUBGATE"
        in decisions["DEC-128"]["Reason"]
        and "f5978882" in decisions["DEC-128"]["Reason"]
        and "CI 624" in decisions["DEC-128"]["Reason"]
        and "PCB-PWR Schematic 92" in decisions["DEC-128"]["Reason"]
        and "PCB Native 345" in decisions["DEC-128"]["Reason"]
        and "four 0.5 mm F.Cu segments U1.5-Q1.4" in decisions["DEC-128"]["Impact"]
        and "do not authorize power-input load copper buck hot-loop switch-node Kelvin or feedback routing"
        in decisions["DEC-128"]["Impact"]
        and "fresh commit-bound application gate" in decisions["DEC-128"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-128"]["Impact"],
        "PCB-PWR routing candidate 004 acceptance boundary is missing",
    )
    require(
        decisions["DEC-129"]["Status"] ==
        "APPLICATION_EXACT_REV_GATE_DELTA_COMMIT_BOUND_GATE_PENDING"
        and "15e2a253" in decisions["DEC-129"]["Reason"]
        and "de211f42" in decisions["DEC-129"]["Reason"]
        and "f5978882" in decisions["DEC-129"]["Reason"]
        and "four 0.5 mm F.Cu segments U1.5-Q1.4"
        in decisions["DEC-129"]["Impact"]
        and "zero vias" in decisions["DEC-129"]["Impact"]
        and "fresh commit-bound CI and PCB Native application gate"
        in decisions["DEC-129"]["Impact"]
        and "86 to 86" in decisions["DEC-129"]["Impact"]
        and "122 to 121" in decisions["DEC-129"]["Impact"]
        and "Review B CAM DFM thermal and manufacturing blocks"
        in decisions["DEC-129"]["Impact"],
        "PCB-PWR routing candidate 004 exact application boundary is missing",
    )
    require(
        decisions["DEC-130"]["Status"] ==
        "PASS_EXACT_REV_GATE_APPLICATION_REMAINING_ROUTING_NEXT"
        and "b33de676" in decisions["DEC-130"]["Reason"]
        and "57011fb5" in decisions["DEC-130"]["Reason"]
        and "CI 641" in decisions["DEC-130"]["Reason"]
        and "PCB-PWR Schematic 94" in decisions["DEC-130"]["Reason"]
        and "PCB Native 347" in decisions["DEC-130"]["Reason"]
        and "86 to 86" in decisions["DEC-130"]["Reason"]
        and "122 to 121" in decisions["DEC-130"]["Reason"]
        and "U1.5-Q1.4 REV_GATE" in decisions["DEC-130"]["Impact"]
        and "neither overall routing nor Review B CAM DFM thermal or manufacturing complete"
        in decisions["DEC-130"]["Impact"]
        and "separate exact human gate" in decisions["DEC-130"]["Impact"],
        "PCB-PWR routing candidate 004 application closure is missing",
    )
    require(
        decisions["DEC-131"]["Status"] ==
        "ACCEPTED_EVT_ENGINEERING_BASELINE_EXTERNAL_REPLIES_NOT_REQUIRED"
        and "close 85 of 85 historical response rows"
        in decisions["DEC-131"]["Impact"]
        and "keep checkout DFM routing DRC CAM Review B first-article and physical EVT gates open"
        in decisions["DEC-131"]["Impact"],
        "EVT engineering-baseline decision is missing or over-released",
    )
    require(
        decisions["DEC-132"]["Status"] ==
        "ACCEPTED_PROGRAM_2X20_PLUS_1_TOTAL_41_TWO_RESERVE_POOLS"
        and "two lots of 20 plus one bench station"
        in decisions["DEC-132"]["Impact"]
        and "two independent EVT-20 reserve pools"
        in decisions["DEC-132"]["Impact"]
        and "serials and travellers" in decisions["DEC-132"]["Impact"],
        "2x20+1 program decision is missing or incomplete",
    )
    require(
        decisions["DEC-133"]["Status"] ==
        "STATIC_CANDIDATE_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "ACCEPT_PCB_PWR_ROUTING_CANDIDATE_005_CREATION_SUBGATE"
        in decisions["DEC-133"]["Reason"]
        and "full 2.1 mm copper cannot terminate" in decisions["DEC-133"]["Reason"]
        and "fourteen F.Cu segments" in decisions["DEC-133"]["Impact"]
        and "U3.3-C4.2-L1.1" in decisions["DEC-133"]["Impact"]
        and "U4.3-C6.2-L2.1" in decisions["DEC-133"]["Impact"]
        and "5d135a38774c4e223c1db8d6a3fc0e8c9c492fe3ba24f5e2ec4c1b00ab2166d7"
        in decisions["DEC-133"]["Impact"]
        and "86 to 86" in decisions["DEC-133"]["Impact"]
        and "121 to 117" in decisions["DEC-133"]["Impact"]
        and "pad-entry thermal qualification" in decisions["DEC-133"]["Impact"],
        "PCB-PWR routing candidate 005 creation boundary is missing",
    )
    require(
        decisions["DEC-134"]["Status"] ==
        "PASS_MACHINE_GATE_PAD_ENTRY_REJECTED_SUPERSEDED_NO_APPLICATION"
        and "ed93386d" in decisions["DEC-134"]["Reason"]
        and "CI 652" in decisions["DEC-134"]["Reason"]
        and "PCB Native 352" in decisions["DEC-134"]["Reason"]
        and "86 to 86" in decisions["DEC-134"]["Reason"]
        and "121 to 117" in decisions["DEC-134"]["Reason"]
        and "4.578427 mm of 0.5 mm copper" in decisions["DEC-134"]["Reason"]
        and "Do not accept or apply" in decisions["DEC-134"]["Impact"]
        and "do not authorize production EVT" in decisions["DEC-134"]["Impact"],
        "PCB-PWR routing candidate 005 pad-entry rejection is missing",
    )
    require(
        decisions["DEC-135"]["Status"] ==
        "PASS_STATIC_ECO_002_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "project owner directed continue" in decisions["DEC-135"]["Reason"]
        and "eliminates the former 4.578427 mm external 0.5 mm neck"
        in decisions["DEC-135"]["Reason"]
        and "U3 U4 C4 C6 C20 C21 L1 and L2" in decisions["DEC-135"]["Impact"]
        and "dd4c38c191b3087be8a58e9a4b7de4f7974de89797fba4583edbe674340ebda8"
        in decisions["DEC-135"]["Impact"]
        and "minimum external SW routed width is 2.1 mm"
        in decisions["DEC-135"]["Impact"]
        and "15.042756 mW" in decisions["DEC-135"]["Impact"]
        and "commit-bound KiCad 9 exact acceptance and application"
        in decisions["DEC-135"]["Impact"]
        and "physical plus70C first-article" in decisions["DEC-135"]["Impact"],
        "PCB-PWR buck power-stage ECO-002 creation boundary is missing",
    )
    require(
        decisions["DEC-136"]["Status"] ==
        "REJECTED_COMMIT_BOUND_KICAD9_DRC_NOT_FOR_APPLICATION"
        and "85f50d0" in decisions["DEC-136"]["Reason"]
        and "PCB Native run 353" in decisions["DEC-136"]["Reason"]
        and "violations 86 to 124" in decisions["DEC-136"]["Reason"]
        and "unconnected items 121 to 116" in decisions["DEC-136"]["Reason"]
        and "Do not accept or apply" in decisions["DEC-136"]["Impact"]
        and "do not authorize production EVT" in decisions["DEC-136"]["Impact"]
        and "without relaxing DRC" in decisions["DEC-136"]["Impact"],
        "PCB-PWR ECO-002 rejected serialization evidence is missing",
    )
    require(
        decisions["DEC-137"]["Status"] ==
        "PASS_STATIC_ECO_002_ROTATION_SERIALIZATION_REMEDIATION_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "project owner directed continue" in decisions["DEC-137"]["Reason"]
        and "pad property and footprint-text" in decisions["DEC-137"]["Reason"]
        and "516a2e0b99f2855e0b1542559b1f844d10e694893896568ef054095b79a5fa3d"
        in decisions["DEC-137"]["Impact"]
        and "0e52d4cbc80104691e3793a579c7c7a8570e3640fabc2fb02bd7ea2e65643555"
        in decisions["DEC-137"]["Impact"]
        and "relax no DRC rule" in decisions["DEC-137"]["Impact"]
        and "121 to 117" in decisions["DEC-137"]["Impact"]
        and "new exact human acceptance" in decisions["DEC-137"]["Impact"],
        "PCB-PWR ECO-002 rotation-serialization remediation boundary is missing",
    )
    require(
        decisions["DEC-100"]["Status"] ==
        "STATIC_PROPOSAL_READY_COMMIT_BOUND_KICAD9_GATE_PENDING"
        and "C4 C6 L1 and L2" in decisions["DEC-100"]["Impact"]
        and "77.362 percent" in decisions["DEC-100"]["Impact"]
        and "56.630 percent" in decisions["DEC-100"]["Impact"]
        and "add no copper" in decisions["DEC-100"]["Impact"]
        and "human subgate acceptance" in decisions["DEC-100"]["Impact"],
        "PCB-PWR buck placement ECO proposal decision is missing or over-released",
    )
    require(
        decisions["DEC-107"]["Status"] ==
        "ACCEPT_PCB_PWR_BUCK_WARNING_REMEDIATION_001_SUBGATE_APPLICATION_PENDING"
        and "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
        in decisions["DEC-107"]["Impact"]
        and "fresh commit-bound application gate" in decisions["DEC-107"]["Impact"],
        "PCB-PWR warning-remediation acceptance boundary is missing",
    )
    require(
        decisions["DEC-108"]["Status"] ==
        "APPLICATION_EXACT_WARNING_REMEDIATION_COMMIT_BOUND_GATE_PENDING"
        and "54083a35" in decisions["DEC-108"]["Reason"]
        and "b1d221d50c379e3b47df7a52b25846892e8fb028a5535bd93f567dd19a940957"
        in decisions["DEC-108"]["Impact"]
        and "preserve every component pose" in decisions["DEC-108"]["Impact"]
        and "fresh commit-bound CI and PCB Native" in decisions["DEC-108"]["Impact"],
        "PCB-PWR warning-remediation application boundary is missing",
    )
    require(
        decisions["DEC-109"]["Status"] ==
        "PASS_EXACT_WARNING_REMEDIATION_APPLICATION_ROUTING_AND_REVIEW_B_OPEN"
        and "d22eb808" in decisions["DEC-109"]["Reason"]
        and "f027aea4" in decisions["DEC-109"]["Reason"]
        and "CI 592" in decisions["DEC-109"]["Reason"]
        and "PCB Native 319" in decisions["DEC-109"]["Reason"]
        and "violations 90 to 86" in decisions["DEC-109"]["Impact"]
        and "unconnected 126 to 126" in decisions["DEC-109"]["Impact"]
        and "Review B CAM and manufacturing blocks"
        in decisions["DEC-109"]["Impact"],
        "PCB-PWR warning-remediation application closure is missing or over-released",
    )
    require(
        decisions["DEC-069"]["Status"] ==
        "LOCKED_CUSTOMER_PROCUREMENT_BOUNDARY_TECHNICAL_GATES_RETAINED"
        and "commercial procurement execution to the customer"
        in decisions["DEC-069"]["Decision"]
        and "job-specific stackup DFM stencil panel harness and mechanical technical responses"
        in decisions["DEC-069"]["Impact"],
        "customer procurement boundary decision is missing or weakens technical gates",
    )
    require(
        decisions["DEC-070"]["Status"] ==
        "LOCKED_PUBLIC_NUMERIC_ENGINEERING_BASIS_FINAL_FABRICATOR_ACCEPTANCE_PENDING"
        and "JLC06161H-3313" in decisions["DEC-070"]["Decision"]
        and "0.1509 mm" in decisions["DEC-070"]["Impact"]
        and "0.1537 mm" in decisions["DEC-070"]["Impact"]
        and "0.2032 mm" in decisions["DEC-070"]["Impact"]
        and "do not populate FAB-A or FAB-B response rows"
        in decisions["DEC-070"]["Impact"],
        "PCB-MAIN public numeric routing-basis decision is missing or over-released",
    )
    require(
        decisions["DEC-071"]["Status"] ==
        "ENGINEERING_HOLD_CELLULAR_L2_CANDIDATE_READY_GNSS_ECO_PENDING"
        and "RF/SI return-path review as ECO_REQUIRED"
        in decisions["DEC-071"]["Decision"]
        and "PCB-MAIN-RF-RETURN-001" in decisions["DEC-071"]["Impact"]
        and "GNSS U9/FL1/C64 placement and routing ECO separate"
        in decisions["DEC-071"]["Impact"]
        and "manufacturing blocks" in decisions["DEC-071"]["Impact"],
        "PCB-MAIN RF/SI ECO split decision is missing or over-released",
    )
    require(decisions["DEC-009"]["Status"] == "SUPERSEDED", "fixed 20-station LoRa decision remains active")
    require(decisions["DEC-010"]["Status"] == "SUPERSEDED", "old housing decision remains active")
    require(decisions["DEC-012"]["Status"] == "SUPERSEDED", "old private APN decision remains active")
    require(decisions["DEC-014"]["Status"] == "SUPERSEDED", "fixed 20-housing decision remains active")

    inputs = {row["Input_ID"]: row for row in read_csv("docs/OPEN_INPUTS_FOR_FREEZE.csv")}
    require(inputs["IN-004"]["Status"] == "LOCKED", "three housing source packages are not locked")
    require(inputs["IN-005"]["Status"] == "LOCKED", "housing lot allocation is not locked")
    require("EVT-20 is selected" in inputs["IN-005"]["Required_Input"], "20-station lot input is not explicit")

    tests = {row["Test_ID"]: row for row in read_csv("tests/EVT_MATRIX.csv")}
    require(
        tests["EVT-MECH-VC"]["Population"] == "SELECTED_EVT_LOT_ALL_UNITS",
        "vacuum housing EVT does not cover every selected-lot unit",
    )
    require(tests["EVT-MECH-IM"]["Population"] == "Source_package_only", "TPA test scope is not source-only")
    require("reject private APN" in tests["EVT-CELL-04"]["Method"], "private APN rejection test missing")


def validate_deliverable_register() -> None:
    rows = read_csv("docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv")
    ids = [row["ID"] for row in rows]
    require(len(ids) == len(set(ids)), "deliverable register contains duplicate IDs")
    deliverables = {row["ID"]: row for row in rows}
    require(deliverables["CM-002"]["QG-1 полнота"] == "PASS", "selectable-lot baseline is not QG-1 PASS")
    require(
        deliverables["HW-M-000"]["Статус"] == "CONTROLLED_ECO_APPLIED"
        and deliverables["HW-M-000"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-M-000"]["QG-2 техника"] == "OPEN"
        and "controlled full repack pass strict 2D clearance"
        in deliverables["HW-M-000"]["Критерий выпуска"],
        "PCB-MAIN mechanical authority does not record the controlled repack clearance state",
    )
    main_layout = deliverables["HW-M-002"]["Критерий выпуска"]
    require(
        "Six-layer native candidate" in main_layout
        and "strict 2D placement-clearance PASS" in main_layout
        and "constraints for all 186 nets" in main_layout
        and "JLC06161H-3313 numeric RF/USB geometry is accepted for EVT" in main_layout
        and "1023 trace items and eight copper zones" in main_layout
        and "remaining connector and pair-aware routing" in main_layout
        and "checkout DFM" in main_layout
        and "Review B remain open" in main_layout,
        "PCB-MAIN deliverable does not match the accepted stackup and active routing state",
    )
    require(
        deliverables["HW-M-011"]["Статус"] ==
        "EVT_ENGINEERING_BASELINE_ACCEPTED"
        and deliverables["HW-M-011"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-M-011"]["QG-2 техника"] == "PASS"
        and "Official JLC06161H-3313 controls EVT"
        in deliverables["HW-M-011"]["Критерий выпуска"]
        and "all 22 historical response rows are project engineering closures"
        in deliverables["HW-M-011"]["Критерий выпуска"]
        and "routing RF/SI DRC CAM checkout DFM Review B and manufacture are separate gates"
        in deliverables["HW-M-011"]["Критерий выпуска"],
        "PCB-MAIN accepted stackup/impedance deliverable is missing or stale",
    )
    require(
        deliverables["HW-M-012"]["Статус"] == "EVT_ENGINEERING_BASELINE_ACCEPTED"
        and deliverables["HW-M-012"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-M-012"]["QG-2 техника"] == "PASS"
        and "All 14 bounded" in deliverables["HW-M-012"]["Критерий выпуска"]
        and "two-board first-article baseline" in deliverables["HW-M-012"]["Критерий выпуска"]
        and "paste export still waits for native DRC and controlled CAM"
        in deliverables["HW-M-012"]["Критерий выпуска"],
        "PCB-MAIN accepted assembler-process deliverable is missing or stale",
    )
    pwr_layout = deliverables["HW-P-002"]["Критерий выпуска"]
    require(
        deliverables["HW-P-002"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-P-002"]["QG-2 техника"] == "OPEN"
        and "applied REV_GATE routing 004 total eight trace items" in pwr_layout
        and "zero vias and zero copper zones" in pwr_layout
        and "remaining routing DRC CAM checkout DFM" in pwr_layout,
        "PCB-PWR deliverable does not match the active eight-segment routing state",
    )
    require(
        deliverables["HW-P-005"]["Статус"] == "EVT_ENGINEERING_BASELINE_ACCEPTED"
        and deliverables["HW-P-005"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-P-005"]["QG-2 техника"] == "PASS"
        and "All 24 historical response rows are project engineering closures"
        in deliverables["HW-P-005"]["Критерий выпуска"]
        and "JLC04161H-3313A" in deliverables["HW-P-005"]["Критерий выпуска"]
        and "minimum 18 um hole wall plating"
        in deliverables["HW-P-005"]["Критерий выпуска"]
        and "physical thermal drop fault DRC CAM checkout DFM Review B and manufacture remain separate gates"
        in deliverables["HW-P-005"]["Критерий выпуска"],
        "PCB-PWR accepted stackup/copper deliverable is missing or stale",
    )
    require(
        deliverables["HW-P-006"]["Статус"] == "CONTROLLED_ENGINEERING_INPUT"
        and deliverables["HW-P-006"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-P-006"]["QG-2 техника"] == "OPEN"
        and "all 31 nets to eight numeric classes"
        in deliverables["HW-P-006"]["Критерий выпуска"]
        and "4.0 mm at 5 A" in deliverables["HW-P-006"]["Критерий выпуска"]
        and "Selected JLC04161H-3313 1.6 mm outer 2 oz inner 1 oz"
        in deliverables["HW-P-006"]["Критерий выпуска"]
        and "manufacture remain open" in deliverables["HW-P-006"]["Критерий выпуска"],
        "PCB-PWR numeric EVT routing-basis deliverable is missing or over-released",
    )
    require(
        deliverables["HW-P-007"]["Статус"] ==
        "CONTROLLED_WARNING_REMEDIATION_GATE_PASS_ROUTING_OPEN"
        and deliverables["HW-P-007"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-P-007"]["QG-2 техника"] == "OPEN"
        and "placement candidate moved only C4 C6 L1 L2"
        in deliverables["HW-P-007"]["Критерий выпуска"]
        and "successor b1d221d5 is accepted and applied byte-for-byte"
        in deliverables["HW-P-007"]["Критерий выпуска"]
        and "passed fresh CI 592 schematic 70 and Native 319"
        in deliverables["HW-P-007"]["Критерий выпуска"]
        and "warning-only closure is credited"
        in deliverables["HW-P-007"]["Критерий выпуска"]
        and "manufacture remain open"
        in deliverables["HW-P-007"]["Критерий выпуска"],
        "PCB-PWR buck placement ECO deliverable is missing or over-released",
    )
    require(
        deliverables["HW-A-002"]["Статус"] == "DRAFT"
        and deliverables["HW-A-002"]["QG-1 полнота"] == "PASS"
        and deliverables["HW-A-002"]["QG-2 техника"] == "OPEN"
        and "manufacturing release remain open"
        in deliverables["HW-A-002"]["Критерий выпуска"],
        "PCB-MIC candidate CAM deliverable state is stale or over-released",
    )
    require(
        "2x20 плюс стендовый образец" in deliverables["PROC-001"]["Поставочный объект"]
        and deliverables["PROC-001"]["QG-1 полнота"] == "PASS"
        and deliverables["PROC-001"]["QG-2 техника"] == "PASS"
        and "41 stations" in deliverables["PROC-001"]["Критерий выпуска"]
        and "two EVT-20 reserve pools" in deliverables["PROC-001"]["Критерий выпуска"],
        "production BOM deliverable is not bound to the 2x20+1 program",
    )
    require(
        deliverables["MFG-008"]["QG-1 полнота"] == "PASS",
        "selected-lot housing plan is not QG-1 PASS",
    )
    risks = {row["Risk_ID"]: row for row in read_csv("docs/RISK_REGISTER.csv")}
    require(
        "audited 186-net pre-route authority" in risks["R-025"]["Mitigation"]
        and "selected JLC06161H-3313 geometry" in risks["R-025"]["Mitigation"]
        and "controlled U9 paste implementation" in risks["R-025"]["Mitigation"]
        and "checkout DFM" in risks["R-025"]["Mitigation"]
        and "checkout stackup mismatch" in risks["R-025"]["Trigger"]
        and "unresolved portal DFM error" in risks["R-025"]["Trigger"]
        and "premature U9 paste" in risks["R-025"]["Trigger"],
        "PCB-MAIN production-layout risk does not match the accepted EVT baseline",
    )
    require(
        "selected EVT lot" in risks["R-018"]["Mitigation"],
        "RU868 configuration risk still assumes a fixed 20-unit build",
    )
    require(
        "selected JLC04161H-3313A construction" in risks["R-027"]["Mitigation"]
        and "controlled current-geometry table" in risks["R-027"]["Mitigation"]
        and "checkout DFM" in risks["R-027"]["Mitigation"]
        and "stackup mismatch" in risks["R-027"]["Trigger"],
        "PCB-PWR stackup/copper acceptance risk is not explicit",
    )
    require(
        "JLC04161H-3313A 1.6 mm outer 2 oz inner 1 oz"
        in risks["R-032"]["Mitigation"]
        and "35 um as the width-screen lower bound" in risks["R-032"]["Mitigation"]
        and "hole-wall plating below 18 um" in risks["R-032"]["Trigger"]
        and "manufacturing output generated without Review B"
        in risks["R-032"]["Trigger"],
        "PCB-PWR engineering-basis promotion risk is not controlled",
    )
    require(
        "hash-bound C4 C6 L1 L2 ECO" in risks["R-034"]["Mitigation"]
        and "CI 592 schematic 70 and Native 319"
        in risks["R-034"]["Mitigation"]
        and "exact four-warning closure" in risks["R-034"]["Mitigation"]
        and "eight accepted bootstrap VCAP VBAT_RAW and REV_GATE segments"
        in risks["R-034"]["Mitigation"]
        and "CI 641 and PCB Native 347 exact application evidence"
        in risks["R-034"]["Mitigation"]
        and "change outside the accepted eight segments"
        in risks["R-034"]["Trigger"]
        and "REV_GATE application identity regression" in risks["R-034"]["Trigger"]
        and "any unrelated footprint move" in risks["R-034"]["Trigger"],
        "PCB-PWR dual-buck placement-before-routing risk is not controlled",
    )


def validate_pinmap() -> None:
    pinmap = read_csv("hardware/EVT_PRE_20_PIN_MAP_REV_A.csv")
    require(len(pinmap) >= 50, "Rev.A pin map is unexpectedly incomplete")

    mcu_pins = [row["MCU_Pin"] for row in pinmap]
    duplicates = sorted({pin for pin in mcu_pins if mcu_pins.count(pin) > 1})
    require(not duplicates, f"MCU pins are assigned more than once: {duplicates}")

    forbidden_absent = {"PB12", "PE1", "PC4", "PC5"}
    used_forbidden = sorted(forbidden_absent.intersection(mcu_pins))
    require(not used_forbidden, f"pins absent from STM32U585VITxQ Q-package are used: {used_forbidden}")

    by_net = {row["Net"]: row for row in pinmap}
    expected = {
        "PDM_CLK": ("PE9", "MDF1_CCK0"),
        "PDM_DATA1": ("PB1", "MDF1_SDI0"),
        "PDM_DATA2": ("PD6", "MDF1_SDI1"),
        "PDM_DATA3": ("PE7", "MDF1_SDI2"),
        "PDM_DATA4": ("PE4", "MDF1_SDI3"),
        "NOR_CLK": ("PE10", "OCTOSPIM_P1_CLK"),
        "NOR_NCS": ("PE11", "OCTOSPIM_P1_NCS"),
        "NOR_IO0": ("PE12", "OCTOSPIM_P1_IO0"),
        "NOR_IO1": ("PE13", "OCTOSPIM_P1_IO1"),
        "NOR_IO2": ("PE14", "OCTOSPIM_P1_IO2"),
        "NOR_IO3": ("PE15", "OCTOSPIM_P1_IO3"),
        "SD_D0": ("PC8", "SDMMC1_D0"),
        "SD_D1": ("PC9", "SDMMC1_D1"),
        "SD_D2": ("PC10", "SDMMC1_D2"),
        "SD_D3": ("PC11", "SDMMC1_D3"),
        "SD_CK": ("PC12", "SDMMC1_CK"),
        "SD_CMD": ("PD2", "SDMMC1_CMD"),
        "GNSS_TX": ("PA2", "USART2_TX"),
        "GNSS_RX": ("PA3", "USART2_RX"),
        "GNSS_PPS": ("PA0", "TIM2_CH1"),
        "LORA_NSS": ("PA4", "SPI1_NSS"),
        "LORA_SCK": ("PA5", "SPI1_SCK"),
        "LORA_MISO": ("PA6", "SPI1_MISO"),
        "LORA_MOSI": ("PA7", "SPI1_MOSI"),
        "LORA_DIO1": ("PC2", "GPIO"),
        "CELL_TX": ("PB6", "USART1_TX"),
        "CELL_RX": ("PB7", "USART1_RX"),
        "BLE_TX": ("PB10", "USART3_TX"),
        "BLE_RX": ("PB11", "USART3_RX"),
        "I2C2_SCL": ("PB13", "I2C2_SCL"),
        "I2C2_SDA": ("PB14", "I2C2_SDA"),
        "USB_DM": ("PA11", "USB_OTG_FS_DM"),
        "USB_DP": ("PA12", "USB_OTG_FS_DP"),
        "SWDIO": ("PA13", "DEBUG_JTMS-SWDIO"),
        "SWCLK": ("PA14", "DEBUG_JTCK-SWCLK"),
    }
    for net, (pin, signal) in expected.items():
        require(net in by_net, f"required net missing from Rev.A pin map: {net}")
        require(by_net[net]["MCU_Pin"] == pin, f"{net} expected on {pin}, got {by_net[net]['MCU_Pin']}")
        require(by_net[net]["CubeMX_Signal"] == signal, f"{net} signal mismatch")

    pdm = [by_net["PDM_CLK"], *(by_net[f"PDM_DATA{i}"] for i in range(1, 5))]
    require(all(row["External_Domain"] == "1V8" for row in pdm), "PDM external voltage domain must be 1V8")
    require(by_net["CELL_TX"]["External_Domain"] == "1V8", "BG95 main UART must remain a 1V8 external domain")
    require(by_net["CELL_RX"]["External_Domain"] == "1V8", "BG95 main UART must remain a 1V8 external domain")
    require("nRF52840" in by_net["BLE_TX"]["External_Device"], "BLE TX is not bound to nRF52840 module")
    require("nRF52840" in by_net["BLE_RX"]["External_Device"], "BLE RX is not bound to nRF52840 module")
    require("BLE_DFU_REQ" in by_net, "nRF52840 DFU request line missing")
    require(not any("ESP32-C3" in row["External_Device"] for row in pinmap), "ESP32-C3 remains active in Rev.A pin map")
    require(by_net["MIC_WAKE"]["MCU_Pin"] == "PA8", "MIC_WAKE must remain on PA8/EXTI8")
    require(by_net["LORA_DIO1"]["LQFP100_Pin"] == "17", "LORA_DIO1 PC2 package pin mismatch")
    require(by_net["MIC_WAKE"]["MCU_Pin"][2:] != by_net["LORA_DIO1"]["MCU_Pin"][2:], "MIC_WAKE and LORA_DIO1 share an EXTI line")

    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    require("source: hardware/EVT_PRE_20_PIN_MAP_REV_A.csv" in target, "firmware target does not bind Rev.A pin map")
    require("forbidden_absent_gpio: [PB12, PE1, PC4, PC5]" in target, "exact-package absent GPIO guard is missing")


def validate_hardware_baseline() -> None:
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    kicad_readme = (ROOT / "hardware/kicad/README.md").read_text(encoding="utf-8")
    capture_spec = (ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md").read_text(encoding="utf-8")
    pwr_addendum = (ROOT / "hardware/kicad/REV_A_CAPTURE_ADDENDUM_002_PWR12_INA226.md").read_text(encoding="utf-8")
    gate = (ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md").read_text(encoding="utf-8")

    require("mcu_exact_mpn: STM32U585VIT6Q" in baseline, "baseline MCU is not STM32U585VIT6Q")
    require("mcu: STM32U585VIT6Q" in target, "firmware target MCU does not match baseline")
    require("package: LQFP100_14x14" in target, "firmware target package does not match baseline")
    require("exact_pin_database_ref: STM32U585VITxQ" in target, "exact Q-package pin database ref missing")
    require("MCU: `STM32U585VIT6Q`" in kicad_readme, "KiCad active MCU is not explicit")
    require("MDBT50Q-P1MV2" in kicad_readme and "nRF52840" in kicad_readme, "KiCad active BLE module is not nRF52840")
    require("ESP32-C3-MINI-1-N4` is superseded" in kicad_readme, "superseded ESP32-C3 history is not documented")
    require("STM32U585CIU6" in kicad_readme and "superseded" in kicad_readme, "superseded 48-pin MCU history is not documented")
    require("Do not reintroduce" in kicad_readme and "BQ24650/CN3791" in kicad_readme, "obsolete charger prohibition is missing")
    require(
        "eight accepted bootstrap/VCAP/VBAT_RAW/REV_GATE segments" in kicad_readme
        and "REV_GATE` routing 004 application gate is closed" in kicad_readme,
        "KiCad overview does not match the active PCB-PWR REV_GATE successor",
    )
    active_pwr_docs = {
        ROOT / "README.md": (
            "8 принятых сегментов",
            "`REV_GATE` routing 004 применены",
        ),
        ROOT / "BRANCH_SCOPE.md": (
            "`REV_GATE` сегмента — всего восемь",
            "application gate 004",
        ),
        ROOT / "hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md": (
            "exactly eight accepted trace segments",
            "`REV_GATE` routing 004 application gate is closed",
        ),
        ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.md": (
            "EIGHT CONTROLLED ROUTING SEGMENTS APPLIED",
            "f5978882f4bac90acb0a2b5b74b92b71885a7db35367dda686366e2a665a4f0c",
        ),
        ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.md": (
            "eight accepted F.Cu segments",
            "exact `REV_GATE` application gate is closed",
        ),
    }
    for path, markers in active_pwr_docs.items():
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            require(marker in text, f"{path.relative_to(ROOT)} missing {marker!r}")
    require("STM32U585VIT6Q" in capture_spec, "capture spec missing current MCU")
    require("12-pin" in pwr_addendum and "INA226" in pwr_addendum, "Rev.A 12-pin/INA226 capture addendum missing")
    require("Review A" in gate and "Review B" in gate, "double-review PCB gate is incomplete")
    require("FOR_MANUFACTURE" in gate, "PCB release state is not defined")

    main_status = json.loads(
        (ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json").read_text(encoding="utf-8")
    )
    require(main_status["assembly"] == "PCB-MAIN", "PCB-MAIN release-status identity mismatch")
    require(main_status["review_b"]["complete"] is False
            and main_status["manufacturing_release"] is False,
            "PCB-MAIN was advanced by a pre-route stackup request")
    main_hierarchy = main_status.get("human_readable_hierarchy", {})
    main_hierarchy_control = main_hierarchy.get("control", {})
    require(
        main_hierarchy.get("generator") ==
        "tools/materialize_pcb_main_hierarchy_rev_a.py"
        and main_hierarchy.get("connectivity_reader") ==
        "tools/pcb_main_schematic_hierarchy.py"
        and main_hierarchy.get("independent_audit") ==
        "tools/audit_pcb_main_hierarchy_rev_a.py"
        and main_hierarchy.get("review_record") ==
        "hardware/reviews/PCB_MAIN_HIERARCHY_REVIEW_REV_A.md"
        and main_hierarchy_control.get("state") ==
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_"
        "NATIVE_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED"
        and main_hierarchy_control.get("pages") == 10
        and main_hierarchy_control.get("functional_child_sheets") == 9
        and main_hierarchy_control.get("symbols") == 248
        and main_hierarchy_control.get("physical_symbols") == 247
        and main_hierarchy_control.get("logical_pad_numbers") == 1066
        and main_hierarchy_control.get("physical_pad_occurrences") == 1077
        and main_hierarchy_control.get("repeated_logical_pad_numbers") == 7
        and main_hierarchy_control.get("duplicate_pad_occurrences") == 11
        and main_hierarchy_control.get("wire_segments") == 1073
        and main_hierarchy_control.get("connected_pin_wires") == 905
        and main_hierarchy_control.get("explicit_nc") == 169
        and main_hierarchy_control.get("cross_sheet_nets") == 75
        and main_hierarchy_control.get("hierarchical_labels") == 168
        and main_hierarchy_control.get("pin_net_semantic_sha256") ==
        "d320bdd98712a65f9736bd520a8f9197d4f53fedb4be3b798086810e7a8f4bf6"
        and main_hierarchy_control.get("pin_net_review_a_retained") is True,
        "PCB-MAIN human-readable hierarchy/electrical-equivalence control has drifted",
    )
    require(
        all(main_hierarchy_control.get(key) is True for key in (
            "native_kicad_9_erc_pass",
            "committed_erc_evidence",
            "committed_pdf_evidence",
            "independent_human_review_complete",
        ))
        and all(main_hierarchy_control.get(key) is False for key in (
            "routing_authorized",
            "manufacturing_release",
        )),
        "PCB-MAIN hierarchy evidence, review, routing or release state has drifted",
    )
    main_hierarchy_sources = [
        ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_sch",
        *(ROOT / "hardware/kicad/native/PCB-MAIN" /
          f"PCB-MAIN_{index:02d}_{suffix}.kicad_sch"
          for index, suffix in enumerate((
              "POWER", "MCU", "AUDIO", "GNSS", "CELLULAR", "LORA", "BLE",
              "STORAGE_SENSORS", "CONNECTORS_TEST",
          ), start=1)),
    ]
    require(all(path.is_file() for path in main_hierarchy_sources),
            "PCB-MAIN hierarchy source set is incomplete")
    require((ROOT / main_hierarchy["review_record"]).is_file(),
            "PCB-MAIN hierarchy review record is missing")
    main_handoff = main_status["review_b"].get("evidence", {}).get(
        "stackup_impedance_handoff", {}
    )
    require(
        main_handoff.get("status") == "EVT_PUBLIC_STANDARD_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED"
        and main_handoff.get("internal_packet_complete") is True
        and main_handoff.get("complete") is True
        and main_handoff.get("required_fabricator_slots") == []
        and main_handoff.get("accepted_fabricator_response_count") == 0
        and main_handoff.get("accepted_response_rows") == 22
        and main_handoff.get("selected_fabricator_slot") is None
        and main_handoff.get("selected_public_standard") == "JLC06161H-3313"
        and main_handoff.get("external_reply_required") is False,
        "PCB-MAIN EVT stackup/impedance baseline is not accepted",
    )
    require(
        all(main_handoff.get(key) is True for key in (
            "stackup_accepted",
            "rf_50ohm_numeric_geometry_accepted",
            "usb_90ohm_numeric_geometry_accepted",
            "routing_authorized",
        ))
        and main_handoff.get("review_b_complete") is False
        and main_handoff.get("manufacturing_release") is False,
        "PCB-MAIN routing baseline or release boundary drifted",
    )
    for relative in (
        main_handoff.get("packet"),
        main_handoff.get("machine_contract"),
        main_handoff.get("response_register"),
    ):
        require(isinstance(relative, str) and (ROOT / relative).is_file(),
                f"PCB-MAIN stackup/impedance handoff file is missing: {relative}")
    main_responses = read_csv(main_handoff["response_register"])
    require(len(main_responses) == 22
            and {row["Fabricator_Slot"] for row in main_responses} == {"FAB-A", "FAB-B"}
            and all(row["Disposition"] == "CLOSED_EVT_ENGINEERING_BASELINE"
                    and row["Blocking"] == "NO" for row in main_responses),
            "PCB-MAIN stackup response register is not closed by the EVT baseline")

    main_assembler_handoff = main_status["review_b"].get("evidence", {}).get(
        "assembler_dfm_stencil_handoff", {}
    )
    require(
        main_assembler_handoff.get("status") ==
        "EVT_STANDARD_PCBA_PROCESS_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED"
        and main_assembler_handoff.get("internal_packet_complete") is True
        and main_assembler_handoff.get("complete") is True
        and main_assembler_handoff.get("required_scope_references") ==
        ["U2", "U25", "U26", "U9"]
        and main_assembler_handoff.get("required_response_rows") == 14
        and main_assembler_handoff.get("accepted_response_rows") == 14
        and main_assembler_handoff.get("selected_assembler_legal_entity") is None
        and main_assembler_handoff.get("selected_manufacturing_site") is None
        and main_assembler_handoff.get("assembler_selection_nonblocking_customer_action") is True
        and main_assembler_handoff.get("external_reply_required") is False,
        "PCB-MAIN standard PCBA baseline is not accepted",
    )
    require(
        all(main_assembler_handoff.get(key) is True for key in (
            "u2_land_mask_stencil_accepted",
            "u25_u26_land_mask_stencil_accepted",
            "u9_stencil_reflow_inspection_accepted",
            "pnp_polarity_accepted",
            "first_article_plan_accepted",
            "blocker_critical_dfm_closed",
        ))
        and all(main_assembler_handoff.get(key) is False for key in (
            "paste_export_authorized", "review_b_complete", "manufacturing_release",
        )),
        "PCB-MAIN PCBA process or paste/release boundary drifted",
    )
    for relative in (
        main_assembler_handoff.get("packet"),
        main_assembler_handoff.get("machine_contract"),
        main_assembler_handoff.get("response_register"),
    ):
        require(isinstance(relative, str) and (ROOT / relative).is_file(),
                f"PCB-MAIN assembler DFM/stencil handoff file is missing: {relative}")
    main_assembler_responses = read_csv(
        main_assembler_handoff["response_register"]
    )
    require(
        len(main_assembler_responses) == 14
        and len({row["Gate_ID"] for row in main_assembler_responses}) == 14
        and all(
            row["Gate_ID"].startswith("ASM-MAIN-")
            and row["Assembler_Slot"] == "ASM-MAIN-CANDIDATE"
            and row["Required_Party"] == "SELECTED_ASSEMBLER"
            and row["Disposition"] == "CLOSED_EVT_ENGINEERING_BASELINE"
            and row["Blocking"] == "NO"
            and all(row[field] for field in (
                "Response_Value", "Response_Reference", "Responder", "Response_Date"
            ))
            for row in main_assembler_responses
        ),
        "PCB-MAIN assembler response register lacks 14 EVT engineering closures",
    )

    pwr_status = json.loads(
        (ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json").read_text(encoding="utf-8")
    )
    require(pwr_status["assembly"] == "PCB-PWR", "PCB-PWR release-status identity mismatch")
    require(
        pwr_status["review_b"]["complete"] is False
        and pwr_status["manufacturing_release"] is False,
        "PCB-PWR was advanced by a pre-route stackup/copper request",
    )
    pwr_hierarchy = pwr_status.get("human_readable_hierarchy", {})
    pwr_hierarchy_control = pwr_hierarchy.get("control", {})
    pwr_current_evidence = pwr_hierarchy.get("current_evidence", {})
    pwr_evidence_complete = pwr_current_evidence.get("status") == \
        "PASS_COMMIT_BOUND_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED"
    expected_pwr_hierarchy_state = (
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_CINHF_ECO_"
        "NATIVE_KICAD_9_ERC_PDF_EVIDENCE_HUMAN_ACCEPTED"
        if pwr_evidence_complete else
        "PASS_HUMAN_READABLE_HIERARCHY_ELECTRICAL_EQUIVALENCE_CINHF_ECO_"
        "NATIVE_KICAD_9_ERC_PDF_EVIDENCE_PENDING_HUMAN_REVIEW_PENDING"
    )
    require(
        pwr_status.get("native_schematic", {}).get("page_count") == 5
        and pwr_status.get("native_schematic", {}).get("functional_child_sheets") == 4
        and pwr_hierarchy.get("generator") ==
        "tools/materialize_pcb_pwr_hierarchy_rev_a.py"
        and pwr_hierarchy.get("connectivity_reader") ==
        "tools/pcb_pwr_schematic_hierarchy.py"
        and pwr_hierarchy.get("independent_audit") ==
        "tools/audit_pcb_pwr_hierarchy_rev_a.py"
        and pwr_hierarchy.get("review_record") ==
        "hardware/reviews/PCB_PWR_HIERARCHY_REVIEW_REV_A.md"
        and (ROOT / pwr_hierarchy["review_record"]).is_file()
        and pwr_hierarchy_control.get("state") == expected_pwr_hierarchy_state
        and pwr_hierarchy_control.get("pages") == 5
        and pwr_hierarchy_control.get("functional_child_sheets") == 4
        and pwr_hierarchy_control.get("symbols") == 65
        and pwr_hierarchy_control.get("physical_symbols") == 62
        and pwr_hierarchy_control.get("wire_segments") == 189
        and pwr_hierarchy_control.get("cross_sheet_nets") == 9
        and pwr_hierarchy_control.get("hierarchical_labels") == 26
        and pwr_hierarchy_control.get("pin_net_semantic_sha256") ==
        "84a35aa607bac3ee65b5d8f60684e958277b2fa5a7ed01f810af32f0b52b73f7"
        and pwr_hierarchy_control.get("pin_net_review_a_retained") is True,
        "PCB-PWR human-readable hierarchy/electrical-equivalence control has drifted",
    )
    require(
        pwr_hierarchy_control.get("prior_evidence_superseded_by_f1_value_eco") is True
        and pwr_hierarchy_control.get("prior_evidence_superseded_by_legibility_remediation") is True
        and pwr_hierarchy_control.get("prior_evidence_superseded_by_cinhf_eco") is True
        and all(pwr_hierarchy_control.get(key) is pwr_evidence_complete for key in (
            "native_kicad_9_erc_pass",
            "committed_erc_evidence",
            "committed_pdf_evidence",
        ))
        and pwr_hierarchy_control.get("independent_human_review_complete") is True
        and all(pwr_hierarchy_control.get(key) is False for key in (
            "routing_authorized",
            "manufacturing_release",
        )),
        "PCB-PWR hierarchy evidence, accepted human review or routing/release state has drifted",
    )
    for relative in (
        pwr_status.get("native_schematic", {}).get("path"),
        *pwr_status.get("native_schematic", {}).get("child_paths", []),
    ):
        require(
            isinstance(relative, str) and (ROOT / relative).is_file(),
            f"PCB-PWR hierarchy source is missing: {relative}",
        )
    pwr_stackup = pwr_status.get("stackup_copper_handoff", {})
    pwr_stackup_control = pwr_stackup.get("control", {})
    require(
        pwr_stackup_control.get("state") ==
        "PASS_EVT_PUBLIC_STANDARD_AND_CALCULATED_GEOMETRY_ACCEPTED"
        and pwr_stackup_control.get("required_fabricator_slots") == 0
        and pwr_stackup_control.get("required_response_rows") == 24
        and pwr_stackup_control.get("accepted_fabricator_slots") == 0
        and pwr_stackup_control.get("accepted_response_rows") == 24
        and pwr_stackup_control.get("selected_fabricator_slot") is None
        and pwr_stackup_control.get("complete") is True
        and pwr_stackup_control.get("external_reply_required") is False,
        "PCB-PWR EVT stackup/copper baseline is not accepted",
    )
    require(
        all(pwr_stackup_control.get(key) is True for key in (
            "stackup_accepted",
            "copper_weights_and_plating_accepted",
            "numeric_power_geometry_authorized",
            "routing_authorized",
        ))
        and pwr_stackup_control.get("review_b_complete") is False
        and pwr_stackup_control.get("manufacturing_release") is False,
        "PCB-PWR numeric routing baseline or manufacturing-release boundary drifted",
    )
    for relative in (
        pwr_stackup.get("request_packet"),
        pwr_stackup.get("machine_contract"),
        pwr_stackup.get("response_register"),
    ):
        require(isinstance(relative, str) and (ROOT / relative).is_file(),
                f"PCB-PWR stackup/copper handoff file is missing: {relative}")
    pwr_stackup_responses = read_csv(pwr_stackup["response_register"])
    require(
        len(pwr_stackup_responses) == 24
        and {row["Fabricator_Slot"] for row in pwr_stackup_responses} == {"FAB-A", "FAB-B"}
        and all(
            row["Required_Party"] == "FABRICATOR"
            and row["Disposition"] == "CLOSED_EVT_ENGINEERING_BASELINE"
            and row["Blocking"] == "NO"
            and all(row[field] for field in (
                "Response_Value", "Response_Reference", "Responder", "Response_Date"
            ))
            for row in pwr_stackup_responses
        ),
        "PCB-PWR stackup/copper register lacks 24 EVT engineering closures",
    )
    pwr_evt_basis = pwr_status.get("evt_routing_basis", {})
    pwr_evt_basis_control = pwr_evt_basis.get("control", {})
    require(
        pwr_evt_basis.get("record") ==
        "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.md"
        and pwr_evt_basis.get("machine_contract") ==
        "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json"
        and pwr_evt_basis.get("rule_manifest") ==
        "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv"
        and pwr_evt_basis.get("independent_audit") ==
        "tools/audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py"
        and pwr_evt_basis_control.get("state") ==
        "PASS_EVT_ENGINEERING_STACKUP_AND_NUMERIC_ROUTING_INPUT_JOB_DFM_PENDING"
        and pwr_evt_basis_control.get("public_dielectric_reference") == "JLC04161H-3313"
        and pwr_evt_basis_control.get("screen_finished_copper_um") == 35.0
        and pwr_evt_basis_control.get("screen_temperature_rise_c") == 10.0
        and pwr_evt_basis_control.get("net_count") == 31
        and pwr_evt_basis_control.get("numeric_class_count") == 8
        and pwr_evt_basis_control.get("engineering_routing_candidate_authorized") is True
        and pwr_evt_basis_control.get("evt_ordering_profile_selected") is True
        and all(pwr_evt_basis_control.get(key) is False for key in (
            "final_stackup_accepted",
            "final_numeric_power_geometry_authorized",
            "routing_complete",
            "review_b_complete",
            "manufacturing_release",
        )),
        "PCB-PWR bounded EVT routing basis is missing, drifted or over-released",
    )
    for relative in (
        pwr_evt_basis.get("record"),
        pwr_evt_basis.get("machine_contract"),
        pwr_evt_basis.get("rule_manifest"),
    ):
        require(isinstance(relative, str) and (ROOT / relative).is_file(),
                f"PCB-PWR EVT routing-basis file is missing: {relative}")

    mic_status = json.loads((ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json").read_text(encoding="utf-8"))
    require(mic_status["assembly"] == "PCB-MIC", "PCB-MIC release-status identity mismatch")
    require(mic_status["manufacturing_release"] is False, "PCB-MIC was released without Review A/B evidence")
    mic_review_a = mic_status["review_a"]
    require(mic_status["review_b"]["complete"] is False, "PCB-MIC Review B was marked complete without manufacturing evidence")
    if mic_status["release_state"] == "REVIEW_A_PASS":
        require(mic_review_a["complete"] is True and mic_review_a["status"] == "PASS",
                "PCB-MIC Review A is not a signed PASS")
        require(all(mic_review_a.get(field) for field in ("reviewer", "date", "commit_sha")),
                "PCB-MIC signed Review A lacks reviewer/date/commit SHA")
        require(re.fullmatch(r"[0-9a-f]{40}", mic_review_a["commit_sha"]) is not None,
                "PCB-MIC signed Review A commit SHA is invalid")
        require(
            mic_review_a["structural_audit_status"] ==
            "PASS_STRUCTURAL_EVIDENCE_REVIEW_A_SIGNED_PASS",
            "PCB-MIC independent structural audit status does not match signed Review A",
        )
        require(
            mic_review_a["geometry_audit_status"] ==
            "PASS_COMMIT_MATCHED_REMOTE_ARCHIVE_REVIEW_A_SIGNED_PASS",
            "PCB-MIC independent geometry audit status does not match signed Review A",
        )
        mic_review_a_evidence = mic_review_a.get("evidence", {})
        required_mic_review_a_evidence = {
            "signed_checklist", "workflow_run", "artifact", "schematic_pdf",
            "erc_report", "committed_geometry_audit",
            "materialized_geometry_audit", "sha256_manifest",
        }
        require(
            isinstance(mic_review_a_evidence, dict) and
            all(mic_review_a_evidence.get(key) for key in required_mic_review_a_evidence),
            "PCB-MIC signed Review A evidence links are incomplete",
        )
    else:
        require(mic_status["release_state"] == "REVIEW_A_REQUIRED_AFTER_COPPER_ECO",
                "PCB-MIC release state is neither signed nor an explicit post-ECO candidate")
        require(mic_review_a["complete"] is False
                and mic_review_a["status"] == "REVIEW_REQUIRED_AFTER_COPPER_ECO",
                "PCB-MIC post-ECO Review A is not explicitly open")
        require(all(mic_review_a.get(field) is None for field in ("reviewer", "date", "commit_sha")),
                "PCB-MIC post-ECO Review A retains an active signature")
        require(
            mic_review_a["structural_audit_status"] ==
            "PASS_STRUCTURAL_EVIDENCE_ECO_CANDIDATE_REPEAT_REVIEW_A_REQUIRED",
            "PCB-MIC post-ECO structural audit state mismatch",
        )
        require(
            mic_review_a["geometry_audit_status"] ==
            "PASS_ECO_CANDIDATE_GEOMETRY_REPEAT_REVIEW_A_REQUIRED",
            "PCB-MIC post-ECO geometry audit state mismatch",
        )
        prior = mic_review_a.get("superseded_signature", {})
        require(prior.get("status") == "SUPERSEDED_BY_COPPER_ECO_BOARD_BYTE_CHANGE",
                "PCB-MIC prior Review-A signature is not explicitly superseded")
        require(re.fullmatch(r"[0-9a-f]{40}", str(prior.get("commit_sha", ""))) is not None,
                "PCB-MIC superseded Review-A commit SHA is invalid")
        require(re.fullmatch(r"[0-9a-f]{64}", str(prior.get("board_sha256", ""))) is not None,
                "PCB-MIC superseded Review-A board hash is invalid")
        required_evidence = mic_review_a.get("required_evidence", {})
        require(required_evidence.get("status") in {
            "PENDING_COMMIT_BOUND_CI", "PASS_COMMIT_BOUND_CI_READY_FOR_REVIEW_A"
        }, "PCB-MIC post-ECO evidence state is invalid")
        mic_review_b = mic_status["review_b"]
        require(mic_review_b["status"] == "BLOCKED_PENDING_REPEAT_REVIEW_A_AFTER_COPPER_ECO",
                "PCB-MIC Review B is not blocked on repeat Review A")
        copper_gate = mic_review_b.get("copper_return_gate", {})
        require(copper_gate.get("decision") == "ECO_REQUIRED"
                and copper_gate.get("reviewer") and copper_gate.get("date"),
                "PCB-MIC ECO_REQUIRED decision traceability is incomplete")
    mic_handoff = mic_status["review_b"].get("manufacturing_handoff", {})
    require(
        mic_handoff.get("status") == "EVT_STANDARD_PROCESS_ACCEPTED_EXTERNAL_REPLY_NOT_REQUIRED"
        and mic_handoff.get("internal_packet_complete") is True
        and mic_handoff.get("complete") is True
        and mic_handoff.get("accepted_response_rows") == 9
        and mic_handoff.get("external_reply_required") is False,
        "PCB-MIC manufacturing baseline is not accepted",
    )
    require(
        all(mic_handoff.get(key) is True for key in (
            "fabricator_dfm_acceptance",
            "assembler_dfm_acceptance",
            "panelization_acceptance",
            "depanel_acceptance",
            "assembler_process_keepout_acceptance",
        ))
        and mic_handoff.get("review_b_complete") is False
        and mic_handoff.get("manufacturing_release") is False,
        "PCB-MIC process baseline or release boundary drifted",
    )
    for relative in (
        mic_handoff.get("packet"),
        mic_handoff.get("machine_contract"),
        mic_handoff.get("response_register"),
    ):
        require(isinstance(relative, str) and (ROOT / relative).is_file(),
                f"PCB-MIC manufacturing handoff file is missing: {relative}")
    require(
        mic_status["native_source"]["independent_schematic_audit"] ==
        "artifacts/pcb_mic_native_schematic_rev_a.json",
        "PCB-MIC independent schematic audit artifact path mismatch",
    )
    require(
        (ROOT / "tools/audit_pcb_mic_native_schematic_rev_a.py").is_file(),
        "PCB-MIC independent native schematic audit source is missing",
    )
    mic_metadata = json.loads(
        (ROOT / "hardware/kicad/native/PCB-MIC/fabrication_metadata.json").read_text(encoding="utf-8")
    )
    mic_authority = ROOT / mic_metadata["authority"]
    require(mic_authority.is_file(), "PCB-MIC fabrication metadata authority is unresolved")
    require(
        mic_metadata["authority"] == mic_status["mechanical_contract"]["authority"],
        "PCB-MIC mechanical authority differs between release status and fabrication metadata",
    )

    bom = {row["Item_ID"]: row for row in read_csv("hardware/EVT_PRE_20_BOM_DRAFT.csv")}
    require(bom["U1"]["MPN"] == "STM32U585VIT6Q", "BOM MCU does not match baseline")
    require(bom["U11"]["MPN"] == "MDBT50Q-P1MV2", "BOM BLE module does not match locked nRF52840 module")
    require("nRF52840" in bom["U11"]["Package"], "BOM BLE module package does not identify nRF52840")
    require(bom["MK1"]["MPN"] == "MMICT5838-00-012", "BOM microphone does not match exact orderable baseline")
    require(bom["U-MON-01"]["MPN"] == "INA226AIDGSR", "BOM total battery monitor is not INA226AIDGSR")
    require(bom["J-PWR-MAIN"]["MPN"] == "43045-1202", "PCB-MAIN PWR connector is not 12-pin Micro-Fit")
    require(bom["J-PWR-PWR"]["MPN"] == "43045-1202", "PCB-PWR MAIN connector is not 12-pin Micro-Fit")

    harness = read_csv("hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv")
    for index in range(1, 5):
        ref = f"J_MIC{index}"
        rows = [row for row in harness if row["Connector_Ref"] == ref]
        require([row["Pin"] for row in rows] == ["1", "2", "3", "4", "5", "6"], f"{ref} pin order mismatch")
        require(rows[0]["Net"] == "1V8_MIC" and rows[1]["Net"] == "GND", f"{ref} power pinout mismatch")
        require(rows[2]["Net"] == "PDM_CLK", f"{ref} clock pinout mismatch")
        require(rows[3]["Net"] == f"PDM_DATA{index}", f"{ref} data pinout mismatch")
        require(rows[4]["Net"] == f"MIC_WAKE{index}", f"{ref} AAD WAKE pinout mismatch")
        require(rows[5]["Net"] == "AAD_CFG", f"{ref} shared AAD_CFG/THSEL pinout mismatch")

    main_pwr = [row for row in harness if row["Interface"] == "MAIN_PWR"]
    require([row["Pin"] for row in main_pwr] == [str(i) for i in range(1, 13)], "MAIN-PWR is not the frozen 12-pin contract")
    require(main_pwr[10]["Net"] == "I2C2_SCL", "MAIN-PWR pin 11 must be I2C2_SCL")
    require(main_pwr[11]["Net"] == "I2C2_SDA", "MAIN-PWR pin 12 must be I2C2_SDA")
    require("INA226" in main_pwr[10]["Notes"] and "INA226" in main_pwr[11]["Notes"], "MAIN-PWR I2C rows are not bound to INA226")


def validate_policy_text() -> None:
    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    require("pilot_apn_policy: public_only" in baseline, "baseline public-only APN policy missing")
    require("maximum_station_quantity: 20" in baseline, "baseline maximum serial capacity missing")
    require("supported_procurement_quantities: [4, 10, 20]" in baseline, "baseline 4 10 20 procurement options missing")
    require("selected_evt_quantity: 20" in baseline, "baseline does not select the locked 20-station EVT lot")
    require("program_total_station_quantity: 41" in baseline,
            "baseline does not control the 2x20+1 total")
    require("program_structure: TWO_EVT20_PRODUCTION_SETS_PLUS_ONE_BENCH" in baseline,
            "baseline program structure differs")
    require("program_spare_rule: TWO_EVT20_RESERVE_POOLS_BENCH_ADDS_NO_THIRD_RESERVE_POOL" in baseline,
            "baseline program spare rule differs")
    require("program_serial_register: manufacturing/LOT_SERIAL_REGISTER_LOT2_AND_BENCH.csv" in baseline
            and "program_serial_status: RESERVED_DIO_EVT_021_THROUGH_040_AND_DIO_EVT_B01" in baseline
            and "program_traveller_status: REQUIRED_BEFORE_BUILD" in baseline
            and "program_serial_and_traveller_status: SERIALS_RESERVED_TRAVELLERS_REQUIRED_BEFORE_BUILD" in baseline,
            "baseline second-set/bench traceability control differs")
    require("selection_status: LOCKED_CURRENT_CUSTOMER_EVT_20" in baseline, "EVT-20 selection status is not locked")
    require("pilot_primary_quantity: 20" in baseline, "baseline vacuum quantity does not match selected EVT-20")
    require(
        "pilot_fallback_quantity_if_activated: 20" in baseline,
        "baseline 3D fallback quantity does not match selected EVT-20",
    )
    require("authoritative_position_source: configured_installation_coordinates" in baseline, "configured installation coordinates are not authoritative")
    require("wifi_positioning_required: false" in baseline, "Wi-Fi positioning unexpectedly required")
    require("server_tdoa_station_position_source: configured_installation_coordinates" in baseline, "TDOA position source is not configured installation position")
    require("module_primary: Raytac_MDBT50Q-P1MV2" in baseline, "nRF52840 BLE module not locked in baseline")
    require("esp32_c3_status: SUPERSEDED_NOT_IN_REV_A" in baseline, "ESP32-C3 is not explicitly superseded")

    cellular = (ROOT / "config/cellular/dual_sim_apn_profiles.yaml").read_text(encoding="utf-8")
    require("pilot_apn_policy: public_only" in cellular, "cellular public-only policy missing")
    require("allowed_in_pilot: false" in cellular, "private APN is not explicitly disabled")

    android = (ROOT / "android/app/src/main/java/ru/dioneya/commissioning/core/StationModels.kt").read_text(encoding="utf-8")
    require("private_apn_not_allowed_in_pilot" in android, "Android private APN rejection missing")
    require("missing_installation_position" in android, "Android does not require installation position")
    require("PositionTrustPolicy" in android, "Android position trust policy model missing")

    position_doc = (ROOT / "protocols/POSITION_TIME_TRUST_REV_A.md").read_text(encoding="utf-8")
    require("installation_position" in position_doc, "position trust architecture missing installation position")
    require("GNSS_TIME_SUSPECT" in position_doc, "time trust is not separated from position trust")

    operational_files = [
        ROOT / "README.md",
        ROOT / "protocols/CELLULAR_CONNECTIVITY_BASELINE.md",
        ROOT / "manufacturing/LOT_SERIAL_REGISTER.csv",
        ROOT / "tests/EVT_MATRIX.csv",
    ]
    forbidden = [
        "PUBLIC_PRIMARY_PRIVATE_IF_PROVISIONED",
        "10 printed plus 10 vacuum cast",
        "public/private APN failover",
    ]
    for path in operational_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            require(token not in text, f"superseded token in {path.relative_to(ROOT)}: {token}")


def main() -> None:
    validate_csv_shapes()
    validate_lot()
    validate_procurement()
    validate_decisions_and_tests()
    validate_deliverable_register()
    validate_pinmap()
    validate_hardware_baseline()
    validate_policy_text()
    print("EVT-PRE-20 configuration + exact-package hardware baseline: PASS")


if __name__ == "__main__":
    main()
