#!/usr/bin/env python3
"""Independent structural Review-A audit of the native PCB-MIC Rev.A schematic.

This control deliberately does not import the schematic generator. It checks the
committed KiCad source against the frozen harness, production BOM and project-local
footprint authority. A PASS is evidence for Review A; it is not a Review-A signature
and does not authorize manufacturing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from kiutils.schematic import Schematic
from kiutils.symbol import SymbolLib


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMATIC = ROOT / "hardware/kicad/native/PCB-MIC/PCB-MIC.kicad_sch"
DEFAULT_OUTPUT = ROOT / "artifacts/pcb_mic_native_schematic_rev_a.json"
SYMBOL_LIBRARY = ROOT / "hardware/kicad/native/PCB-MIC/libs/Dioneya.kicad_sym"
HARNESS = ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv"
BOM = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
STATUS = ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json"
GENERATOR = ROOT / "tools/generate_pcb_mic_schematic.py"

CUSTOM_FOOTPRINTS = {
    "J1": (
        "Dioneya:Molex_5040500691",
        ROOT / "hardware/kicad/native/PCB-MIC/libs/Dioneya.pretty/Molex_5040500691.kicad_mod",
    ),
    "MK1": (
        "Dioneya:T5838_RevA",
        ROOT / "hardware/kicad/native/PCB-MIC/libs/Dioneya.pretty/T5838_RevA.kicad_mod",
    ),
}

EXPECTED_COMPONENTS = {
    "J1": {
        "value": "5040500691",
        "footprint": CUSTOM_FOOTPRINTS["J1"][0],
        "pins": {
            "1": "1V8_MIC",
            "2": "GND",
            "3": "PDM_CLK",
            "4": "PDM_DATA",
            "5": "MIC_WAKE",
            "6": "AAD_CFG",
            "7": "NC",
            "8": "NC",
        },
    },
    "MK1": {
        "value": "MMICT5838-00-012",
        "footprint": CUSTOM_FOOTPRINTS["MK1"][0],
        "pins": {
            "1": "PDM_DATA_MIC",
            "2": "GND",
            "3": "GND",
            "4": "MIC_WAKE",
            "5": "AAD_CFG",
            "6": "PDM_CLK",
            "7": "1V8_MIC",
        },
    },
    "R1": {
        "value": "0R EVT_SI_TUNE",
        "footprint": "Resistor_SMD:R_0402_1005Metric",
        "pins": {"1": "PDM_DATA", "2": "PDM_DATA_MIC"},
    },
    "C1": {
        "value": "100nF X7R",
        "footprint": "Capacitor_SMD:C_0402_1005Metric",
        "pins": {"1": "1V8_MIC", "2": "GND"},
    },
}

EXPECTED_MIC_PIN_NAMES = {
    "1": "DATA",
    "2": "SELECT",
    "3": "GND",
    "4": "WAKE",
    "5": "THSEL",
    "6": "CLK",
    "7": "VDD",
}

EXPECTED_BOM = {
    "MK1": {
        "Manufacturer": "TDK InvenSense",
        "MPN": "MMICT5838-00-012",
        "Qty_per_station": "4",
        "Value": "",
        "Temperature_C": "-40..85",
    },
    "J-MIC": {
        "Manufacturer": "Molex",
        "MPN": "5040500691",
        "Qty_per_station": "4",
        "Value": "",
        "Temperature_C": "-40..105",
    },
    "C-MIC": {
        "Manufacturer": "TDK",
        "MPN": "CGA2B3X7R1E104K050BB",
        "Qty_per_station": "4",
        "Value": "100 nF 25 V X7R",
        "Temperature_C": "-55..125",
    },
    "R-MIC": {
        "Manufacturer": "Panasonic Industry",
        "MPN": "ERJ-2GE0R00X",
        "Qty_per_station": "4",
        "Value": "0 ohm",
        "Temperature_C": "-55..155",
    },
}

FORBIDDEN_SOURCE_TOKENS = (
    "MMICT5837",
    "t5838_ref:",
    "molex_5040500691_ref:",
    "CONN-SMD_6P-P1.50_A1501WRB-S-6P",
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def selected_pins(symbol, unit: int = 1) -> dict[str, object]:
    found: dict[str, object] = {}

    def visit(node, active: bool) -> None:
        node_active = active
        if node is not symbol:
            node_active = (node.unitId in (None, 0, unit)) and (node.styleId in (None, 1))
        if node_active:
            for pin in node.pins:
                found[str(pin.number)] = pin
        for child in node.units:
            visit(child, node_active)

    visit(symbol, True)
    return found


def properties(item) -> dict[str, str]:
    return {str(prop.key): str(prop.value) for prop in item.properties}


def ref_of(instance) -> str:
    return properties(instance).get("Reference", "")


def endpoint(instance, symbol, pin_number: str) -> tuple[float, float]:
    pin = selected_pins(symbol, instance.unit or 1)[pin_number]
    require(instance.position.angle in (None, 0), f"{ref_of(instance)}: unsupported symbol rotation")
    return (
        round(instance.position.X + pin.position.X, 4),
        round(instance.position.Y - pin.position.Y, 4),
    )


def normalized_harness_net(net: str) -> str:
    if re.fullmatch(r"PDM_DATA[1-4]", net):
        return "PDM_DATA"
    if re.fullmatch(r"MIC_WAKE[1-4]", net):
        return "MIC_WAKE"
    return net


def audit_harness() -> dict[str, list[str]]:
    expected = ["1V8_MIC", "GND", "PDM_CLK", "PDM_DATA", "MIC_WAKE", "AAD_CFG"]
    normalized: dict[str, list[str]] = {}
    harness_rows = rows(HARNESS)
    for index in range(1, 5):
        ref = f"J_MIC{index}"
        selected = [row for row in harness_rows if row["Connector_Ref"] == ref]
        require([row["Pin"] for row in selected] == [str(pin) for pin in range(1, 7)],
                f"{ref}: frozen harness pin order mismatch")
        require(all(row["Release_status"] == "LOGICAL_FROZEN" for row in selected),
                f"{ref}: harness contains a non-frozen row")
        actual = [normalized_harness_net(row["Net"]) for row in selected]
        require(actual == expected, f"{ref}: normalized PCB-MIC mapping mismatch: {actual}")
        normalized[ref] = actual
    return normalized


def audit_bom() -> dict[str, dict[str, str]]:
    bom_rows = rows(BOM)
    by_item: dict[str, dict[str, str]] = {}
    for item_id in EXPECTED_BOM:
        matches = [row for row in bom_rows if row["Item_ID"] == item_id]
        require(len(matches) == 1, f"production BOM must contain exactly one {item_id} row")
        row = matches[0]
        require(row["Assembly"] == "PCB-MIC", f"{item_id}: wrong BOM assembly")
        require(row["Population"] == "FITTED", f"{item_id}: not FITTED in production BOM")
        for field, expected in EXPECTED_BOM[item_id].items():
            require(row[field] == expected,
                    f"{item_id}.{field}: {row[field]!r} != controlled {expected!r}")
        by_item[item_id] = {field: row[field] for field in EXPECTED_BOM[item_id]}
    return by_item


def audit_source_tokens(paths: tuple[Path, ...]) -> None:
    for path in paths:
        require(path.is_file() and path.stat().st_size > 0, f"controlled source missing: {path}")
        serialized = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_SOURCE_TOKENS:
            require(token not in serialized, f"{display_path(path)} retains stale token {token!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, default=DEFAULT_SCHEMATIC)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    schematic_path = args.schematic.resolve()

    audit_source_tokens((schematic_path, SYMBOL_LIBRARY, GENERATOR))
    generator_source = GENERATOR.read_text(encoding="utf-8")
    for footprint, _path in CUSTOM_FOOTPRINTS.values():
        require(generator_source.count(footprint) >= 2,
                f"schematic generator does not bind embedded and instance defaults to {footprint}")
    schematic = Schematic.from_file(str(schematic_path), encoding="utf-8")
    instances = {ref_of(instance): instance for instance in schematic.schematicSymbols}
    require("" not in instances, "native PCB-MIC schematic contains an empty reference")
    require(len(instances) == len(schematic.schematicSymbols), "duplicate PCB-MIC reference")
    require(set(instances) == set(EXPECTED_COMPONENTS),
            f"PCB-MIC component set mismatch: {sorted(instances)}")

    embedded = {str(symbol.libId): symbol for symbol in schematic.libSymbols}
    require(len(embedded) == len(schematic.libSymbols), "duplicate embedded library symbol ID")
    labels: dict[tuple[float, float], set[str]] = {}
    for label in schematic.labels:
        position = (round(label.position.X, 4), round(label.position.Y, 4))
        labels.setdefault(position, set()).add(str(label.text))
    no_connects = {
        (round(item.position.X, 4), round(item.position.Y, 4))
        for item in schematic.noConnects
    }

    expected_nc_positions: set[tuple[float, float]] = set()
    pin_count = 0
    for ref, contract in EXPECTED_COMPONENTS.items():
        instance = instances[ref]
        props = properties(instance)
        require(props.get("Value") == contract["value"], f"{ref}: exact value/MPN mismatch")
        require(props.get("Footprint") == contract["footprint"], f"{ref}: footprint link mismatch")
        require(bool(instance.inBom) and bool(instance.onBoard) and not bool(instance.dnp),
                f"{ref}: native population flags are not FITTED/in-BOM/on-board")
        require(instance.libId in embedded, f"{ref}: embedded symbol missing for {instance.libId}")
        symbol = embedded[instance.libId]
        pins = selected_pins(symbol, instance.unit or 1)
        require(set(pins) == set(contract["pins"]), f"{ref}: pin set mismatch")
        pin_count += len(pins)
        if ref == "MK1":
            require({number: str(pin.name) for number, pin in pins.items()} == EXPECTED_MIC_PIN_NAMES,
                    "MK1: controlled T5838 pin-name mapping mismatch")
        if ref == "J1":
            require({number: str(pin.name) for number, pin in pins.items()} ==
                    {str(number): str(number) for number in range(1, 9)},
                    "J1: imported Molex circuit-number mapping mismatch")
        for pin_number, expected_net in contract["pins"].items():
            position = endpoint(instance, symbol, pin_number)
            if expected_net == "NC":
                expected_nc_positions.add(position)
                require(position in no_connects, f"{ref}.{pin_number}: explicit NC marker missing")
                require(not labels.get(position), f"{ref}.{pin_number}: NC pin also has a label")
            else:
                require(labels.get(position, set()) == {expected_net},
                        f"{ref}.{pin_number}: expected {expected_net}, got {sorted(labels.get(position, set()))}")
                require(position not in no_connects, f"{ref}.{pin_number}: connected pin also marked NC")

    require(len(schematic.labels) == 17, f"PCB-MIC label count drift: {len(schematic.labels)}")
    require(len(no_connects) == 2 and no_connects == expected_nc_positions,
            "PCB-MIC explicit no-connect set must be exactly J1.7/J1.8")
    require(pin_count == 19, f"PCB-MIC pin count drift: {pin_count}")

    local_library = SymbolLib.from_file(str(SYMBOL_LIBRARY), encoding="utf-8")
    local_symbols = {str(symbol.entryName): symbol for symbol in local_library.symbols}
    require(set(local_symbols) == {"5040500691", "MMICT5838-00-012"},
            f"project-local PCB-MIC symbol set mismatch: {sorted(local_symbols)}")
    for ref, entry in (("J1", "5040500691"), ("MK1", "MMICT5838-00-012")):
        footprint, path = CUSTOM_FOOTPRINTS[ref]
        require(path.is_file() and path.stat().st_size > 0,
                f"{ref}: controlled footprint file missing: {display_path(path)}")
        embedded_default = properties(embedded[instances[ref].libId]).get("Footprint")
        local_default = properties(local_symbols[entry]).get("Footprint")
        require(embedded_default == footprint,
                f"{ref}: embedded symbol footprint default is not {footprint}")
        require(local_default == footprint,
                f"{ref}: project-local symbol footprint default is not {footprint}")

    normalized_harness = audit_harness()
    bom_evidence = audit_bom()
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    require(status["assembly"] == "PCB-MIC", "PCB-MIC status identity mismatch")
    require(status["review_a"]["complete"] is False,
            "structural audit must not silently promote Review A to complete")
    require(status["manufacturing_release"] is False,
            "PCB-MIC manufacturing release is asserted before Review A/B")

    report = {
        "status": "PASS_STRUCTURAL_EVIDENCE_REVIEW_A_REMAINS_OPEN",
        "configuration": "EVT-PRE-20 Rev.A",
        "board": "PCB-MIC",
        "schematic": display_path(schematic_path),
        "schematic_sha256": sha256(schematic_path),
        "components": len(instances),
        "pins": pin_count,
        "labels": len(schematic.labels),
        "explicit_nc": len(no_connects),
        "custom_footprints": {
            ref: {"id": footprint, "file": display_path(path)}
            for ref, (footprint, path) in CUSTOM_FOOTPRINTS.items()
        },
        "normalized_station_harnesses": normalized_harness,
        "production_bom_items": bom_evidence,
        "review_a_complete": False,
        "manufacturing_release": False,
        "remaining_review_a_evidence": [
            "commit-matched KiCad 9 ERC with zero unexplained violations",
            "commit-matched archived manufacturer geometry audit artifacts",
            "reviewer/date/commit signature",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("PCB-MIC native schematic independent structural Review-A audit PASS")
    print("components=4 pins=19 labels=17 explicit_nc=2; four frozen harness leaves normalized")
    print("exact MK1/J1/C1/R1 production BOM bindings and project-local footprints PASS")
    print("Review A remains OPEN pending KiCad 9 ERC, archived commit-matched geometry evidence and signed traceability")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
