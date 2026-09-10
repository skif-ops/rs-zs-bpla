#!/usr/bin/env python3
"""Independent structural and net Review-A audit of native PCB-MAIN Rev.A."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from kiutils.schematic import Schematic


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMATIC = ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "PCB-MAIN.kicad_sch"
MANIFEST = DEFAULT_SCHEMATIC.parent / "PCB-MAIN_capture_manifest.json"
GENERATOR = ROOT / "tools" / "generate_pcb_main_schematic_rev_a.py"

PIN_AUTHORITIES = (
    ROOT / "hardware" / "PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_STORAGE_SENSOR_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_AUDIO_LOGIC_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_CELLULAR_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_DUAL_SIM_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_GNSS_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_LORA_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_BLE_PIN_AUTHORITY_REV_A.csv",
    ROOT / "hardware" / "PCB_MAIN_CONNECTOR_FIXTURE_PIN_AUTHORITY_REV_A.csv",
)
SUPPORT = ROOT / "hardware" / "PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
HARNESS = ROOT / "hardware" / "HARNESS_LOGICAL_PINOUT_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware" / "MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware" / "CONNECTOR_FREEZE_REV_A.csv"
CAPTURE_STATUS = ROOT / "hardware" / "PCB_MAIN_CAPTURE_STATUS_REV_A.json"
MECHANICAL = ROOT / "hardware" / "PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
NET_OVERLAY = ROOT / "hardware" / "PCB_MAIN_NATIVE_NET_OVERLAY_REV_A.csv"
GROUND_AUTHORITY = ROOT / "hardware" / "PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.csv"
SOURCE_INPUTS = (*PIN_AUTHORITIES, SUPPORT, HARNESS, MAIN_FREEZE, CONNECTOR_FREEZE,
                 CAPTURE_STATUS, MECHANICAL, NET_OVERLAY, GROUND_AUTHORITY)

EXPECTED_COMPONENTS = 248
EXPECTED_FITTED = 233
EXPECTED_DNP = 15
EXPECTED_PINS = 1074
EXPECTED_GENERIC_GROUND_ENDPOINTS = 157
EXPECTED_MIC_GROUND_ENDPOINTS = 21


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def properties(instance) -> dict[str, str]:
    return {str(prop.key): str(prop.value) for prop in instance.properties}


def ref_of(instance) -> str:
    return properties(instance).get("Reference", "")


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


def endpoint(instance, symbol, pin_number: str) -> tuple[float, float]:
    pin = selected_pins(symbol, instance.unit or 1)[pin_number]
    return (
        round(instance.position.X + pin.position.X, 4),
        round(instance.position.Y - pin.position.Y, 4),
    )


def parse_pin_map(value: str) -> dict[str, dict[str, str]]:
    parsed: dict[str, dict[str, str]] = {}
    for token in value.split(";"):
        pin, separator, net = token.partition("=")
        require(bool(separator and pin.strip() and net.strip()), f"invalid Pin_Map token: {token!r}")
        number = pin.strip()
        require(number not in parsed, f"duplicate Pin_Map pin {number}")
        parsed[number] = {"name": number, "logical": net.strip(), "native": net.strip()}
    return parsed


def expected_components() -> dict[str, dict[str, object]]:
    components: dict[str, dict[str, object]] = {}
    freeze = {row["RefDes"]: row for row in rows(MAIN_FREEZE) if row["Assembly"] == "PCB-MAIN"}

    for path in PIN_AUTHORITIES:
        for row in rows(path):
            if path.name == "PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv":
                ref = "U1"
                pin_number = row["LQFP100_Pin"]
                pin_name = row["Pin_Name"]
                mpn = freeze[ref]["MPN"]
                package = freeze[ref]["Package_or_Module"]
            else:
                ref = row["RefDes"]
                pin_number = row["Pin"]
                pin_name = row["Pin_Name"]
                mpn = row["MPN"]
                package = row["Package"]
            component = components.setdefault(ref, {
                "mpn": mpn,
                "package": package,
                "population": "FITTED",
                "on_board": ref != "U12",
                "authorities": [],
                "pins": {},
            })
            require(component["mpn"] == mpn and component["package"] == package,
                    f"{ref}: conflicting active-component MPN/package")
            if path.name not in component["authorities"]:
                component["authorities"].append(path.name)
            pin = {"name": pin_name, "logical": row["RevA_Net"], "native": row["RevA_Net"]}
            old = component["pins"].get(pin_number)
            require(old is None or old == pin, f"{ref}.{pin_number}: conflicting pin authority")
            component["pins"][pin_number] = pin

    active_refs = set(components)
    for row in rows(SUPPORT):
        ref = row["RefDes"]
        require(ref not in active_refs and ref not in components,
                f"{ref}: duplicated support component reference")
        components[ref] = {
            "mpn": row["MPN"],
            "package": row["Package"],
            "population": row["Population"],
            "on_board": True,
            "authorities": [row["Authority"]],
            "pins": parse_pin_map(row["Pin_Map"]),
        }

    harness_groups: dict[str, list[dict[str, str]]] = {}
    for row in rows(HARNESS):
        if row["Connector_Ref"] == "J_PWR" or row["Connector_Ref"].startswith("J_MIC"):
            harness_groups.setdefault(row["Connector_Ref"], []).append(row)
    for ref, connector_rows in harness_groups.items():
        require(ref not in components, f"{ref}: duplicated harness connector")
        if ref == "J_PWR":
            mpn, package = "43045-1202", "Micro-Fit_3.0_2x06_Right_Angle"
        else:
            mpn, package = "504050-0691", "Pico-Lock_1.5_1x06_Right_Angle"
        pins = {
            row["Pin"]: {"name": row["Net"], "logical": row["Net"], "native": row["Net"]}
            for row in connector_rows
        }
        require(len(pins) == len(connector_rows), f"{ref}: duplicate harness pins")
        components[ref] = {
            "mpn": mpn,
            "package": package,
            "population": "FITTED",
            "on_board": True,
            "authorities": [HARNESS.name],
            "pins": pins,
        }

    endpoint_index = {
        (ref, pin_number): pin
        for ref, component in components.items()
        for pin_number, pin in component["pins"].items()
    }
    used_overlay: set[tuple[str, str]] = set()
    for row in rows(NET_OVERLAY):
        key = (row["RefDes"], row["Pin"])
        require(key in endpoint_index, f"unknown native-net overlay endpoint: {key}")
        require(key not in used_overlay, f"duplicate native-net overlay endpoint: {key}")
        pin = endpoint_index[key]
        require(pin["logical"] == row["Logical_Net"],
                f"{key}: overlay logical net mismatch")
        pin["native"] = row["Native_Net"]
        used_overlay.add(key)

    ground_rows = rows(GROUND_AUTHORITY)
    defaults = [row for row in ground_rows if row["Rule_Type"] == "DEFAULT"]
    require(len(defaults) == 1, "ground authority must contain exactly one DEFAULT")
    default = defaults[0]
    require((default["Logical_Net"], default["Native_Net"]) == ("GND", "GND_DIGITAL"),
            "ground DEFAULT must map GND to GND_DIGITAL")
    explicit: dict[tuple[str, str], dict[str, str]] = {}
    for row in ground_rows:
        if row["Rule_Type"] == "DEFAULT":
            continue
        require(row["Rule_Type"] == "ENDPOINT", f"unsupported ground rule {row['Rule_Type']}")
        key = (row["RefDes"], row["Pin"])
        require(key not in explicit, f"duplicate ground endpoint: {key}")
        require(row["Logical_Net"] == "GND" and row["Native_Net"] == "GND_MIC",
                f"{key}: explicit ground endpoint must map GND to GND_MIC")
        explicit[key] = row

    generic = {key for key, pin in endpoint_index.items() if pin["logical"] == "GND"}
    require(len(generic) == EXPECTED_GENERIC_GROUND_ENDPOINTS,
            f"generic GND endpoint count changed: {len(generic)}")
    require(set(explicit) <= generic, f"ground authority contains unknown endpoints: {sorted(set(explicit)-generic)}")
    require(len(explicit) == EXPECTED_MIC_GROUND_ENDPOINTS,
            f"explicit GND_MIC endpoint count changed: {len(explicit)}")
    for key in generic:
        endpoint_index[key]["native"] = "GND_MIC" if key in explicit else default["Native_Net"]

    return components


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schematic", type=Path, default=DEFAULT_SCHEMATIC)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bom-output", type=Path)
    args = parser.parse_args()
    schematic_path = args.schematic.resolve()

    expected = expected_components()
    schematic = Schematic.from_file(str(schematic_path), encoding="utf-8")
    instances = {ref_of(instance): instance for instance in schematic.schematicSymbols}
    require("" not in instances, "native schematic contains an empty component reference")
    require(len(instances) == len(schematic.schematicSymbols), "duplicate native component reference")
    require(set(instances) == set(expected),
            f"native component set mismatch: missing={sorted(set(expected)-set(instances))} "
            f"extra={sorted(set(instances)-set(expected))}")
    lib_by_id = {symbol.libId: symbol for symbol in schematic.libSymbols}
    require(len(lib_by_id) == len(schematic.libSymbols), "duplicate embedded library symbol ID")

    labels: dict[tuple[float, float], set[str]] = {}
    for label in schematic.labels:
        position = (round(label.position.X, 4), round(label.position.Y, 4))
        labels.setdefault(position, set()).add(str(label.text))
    no_connects = {(round(item.position.X, 4), round(item.position.Y, 4)) for item in schematic.noConnects}

    endpoint_counts: Counter[str] = Counter()
    fitted_count = 0
    dnp_count = 0
    pin_count = 0
    nc_count = 0
    for ref, component in expected.items():
        instance = instances[ref]
        require(instance.position.angle is not None,
                f"{ref}: symbol position is missing the KiCad rotation field")
        for prop in instance.properties:
            require(prop.position.angle is not None,
                    f"{ref}.{prop.key}: property position is missing the KiCad rotation field")
        require(instance.libId in lib_by_id, f"{ref}: missing embedded library symbol")
        symbol = lib_by_id[instance.libId]
        native_pins = selected_pins(symbol, instance.unit or 1)
        expected_pins = component["pins"]
        require(set(native_pins) == set(expected_pins),
                f"{ref}: pin set mismatch native={sorted(native_pins)} expected={sorted(expected_pins)}")
        props = properties(instance)
        require(props.get("MPN") == component["mpn"], f"{ref}: MPN mismatch")
        require(props.get("Package") == component["package"], f"{ref}: package mismatch")
        require(props.get("Population") == component["population"], f"{ref}: population property mismatch")
        require(props.get("Authority") == ";".join(component["authorities"]), f"{ref}: authority property mismatch")
        expected_dnp = component["population"] == "DNP"
        require(bool(instance.dnp) == expected_dnp, f"{ref}: native DNP flag mismatch")
        require(bool(instance.inBom), f"{ref}: unexpectedly excluded from BOM")
        require(bool(instance.onBoard) == component["on_board"], f"{ref}: on-board flag mismatch")
        fitted_count += int(not expected_dnp)
        dnp_count += int(expected_dnp)

        ground_domains: set[str] = set()
        for pin_number, expected_pin in expected_pins.items():
            pin_count += 1
            native_pin = native_pins[pin_number]
            require(str(native_pin.name) == expected_pin["name"],
                    f"{ref}.{pin_number}: pin name mismatch")
            position = endpoint(instance, symbol, pin_number)
            native_net = expected_pin["native"]
            if native_net == "NC":
                nc_count += 1
                require(position in no_connects, f"{ref}.{pin_number}: NC marker missing")
                require(not labels.get(position), f"{ref}.{pin_number}: NC pin also has net label")
            else:
                require(labels.get(position, set()) == {native_net},
                        f"{ref}.{pin_number}: expected {native_net}, got {sorted(labels.get(position, set()))}")
                require(position not in no_connects, f"{ref}.{pin_number}: connected pin also marked NC")
                endpoint_counts[native_net] += 1
                if native_net in {"GND_MODEM", "GND_DIGITAL", "GND_MIC"}:
                    ground_domains.add(native_net)
        if ref != "J_PWR":
            require(len(ground_domains) <= 1,
                    f"{ref}: bridges return domains on PCB-MAIN: {sorted(ground_domains)}")

    require(len(schematic.labels) == pin_count - nc_count,
            "native schematic contains missing or extra endpoint labels")
    require(len(schematic.noConnects) == nc_count,
            "native schematic contains missing or extra NC markers")
    require("GND" not in endpoint_counts, "unresolved generic GND remains in native schematic")
    singletons = sorted(net for net, count in endpoint_counts.items() if count < 2)
    require(not singletons, f"native schematic has singleton nets: {singletons}")

    require(len(expected) == EXPECTED_COMPONENTS, f"component count changed: {len(expected)}")
    require(fitted_count == EXPECTED_FITTED, f"fitted count changed: {fitted_count}")
    require(dnp_count == EXPECTED_DNP, f"DNP count changed: {dnp_count}")
    require(pin_count == EXPECTED_PINS, f"pin count changed: {pin_count}")
    require(endpoint_counts["GND_MIC"] == EXPECTED_MIC_GROUND_ENDPOINTS + 1,
            f"GND_MIC count changed: {endpoint_counts['GND_MIC']}")
    require(endpoint_counts["GND_DIGITAL"] ==
            EXPECTED_GENERIC_GROUND_ENDPOINTS - EXPECTED_MIC_GROUND_ENDPOINTS + 1,
            f"GND_DIGITAL count changed: {endpoint_counts['GND_DIGITAL']}")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_inputs = {record["path"]: record["sha256"] for record in manifest["inputs"]}
    expected_inputs = {str(path.relative_to(ROOT)): sha256(path) for path in SOURCE_INPUTS}
    require(manifest_inputs == expected_inputs, "capture manifest input set or hashes are stale")
    require(manifest["generator"] == str(GENERATOR.relative_to(ROOT)), "manifest generator path mismatch")
    require(manifest["generator_sha256"] == sha256(GENERATOR), "manifest generator hash mismatch")
    require(manifest["schematic_sha256"] == sha256(schematic_path), "manifest schematic hash mismatch")
    project = schematic_path.with_suffix(".kicad_pro")
    require(manifest["project_sha256"] == sha256(project), "manifest project hash mismatch")
    require((manifest["component_count"], manifest["fitted_count"], manifest["dnp_count"],
             manifest["pin_count"]) ==
            (EXPECTED_COMPONENTS, EXPECTED_FITTED, EXPECTED_DNP, EXPECTED_PINS),
            "capture manifest structural counts mismatch")

    bom_sha256 = None
    if args.bom_output:
        args.bom_output.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "RefDes", "Manufacturer", "MPN", "Package", "Value", "Footprint",
            "Population", "DNP", "In_BOM", "On_Board", "Authority",
        ]
        with args.bom_output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for ref in sorted(instances):
                instance = instances[ref]
                props = properties(instance)
                writer.writerow({
                    "RefDes": ref,
                    "Manufacturer": props.get("Manufacturer", ""),
                    "MPN": props.get("MPN", ""),
                    "Package": props.get("Package", ""),
                    "Value": props.get("Value", ""),
                    "Footprint": props.get("Footprint", ""),
                    "Population": props.get("Population", ""),
                    "DNP": "YES" if bool(instance.dnp) else "NO",
                    "In_BOM": "YES" if bool(instance.inBom) else "NO",
                    "On_Board": "YES" if bool(instance.onBoard) else "NO",
                    "Authority": props.get("Authority", ""),
                })
        bom_sha256 = sha256(args.bom_output)

    report = {
        "status": "PASS_NATIVE_SOURCE_AND_NET_AUDIT_REVIEW_A_HUMAN_SIGNOFF_PENDING",
        "configuration": "EVT-PRE-20 Rev.A",
        "board": "PCB-MAIN",
        "schematic": str(schematic_path.relative_to(ROOT)),
        "schematic_sha256": sha256(schematic_path),
        "components": len(expected),
        "fitted": fitted_count,
        "dnp": dnp_count,
        "pins": pin_count,
        "explicit_nc": nc_count,
        "native_nets": len(endpoint_counts),
        "ground_endpoint_counts": {
            name: endpoint_counts[name] for name in ("GND_MODEM", "GND_DIGITAL", "GND_MIC")
        },
        "singleton_nets": singletons,
        "pcb_main_ground_net_ties": 0,
        "schematic_derived_bom": (
            {
                "path": str(args.bom_output),
                "sha256": bom_sha256,
                "rows": len(instances),
            }
            if args.bom_output else None
        ),
        "review_a_complete": False,
        "manufacturing_release": False,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("PCB-MAIN native schematic independent Review-A structural/net audit PASS")
    print(
        f"components={len(expected)} fitted={fitted_count} dnp={dnp_count} "
        f"pins={pin_count} explicit_nc={nc_count} native_nets={len(endpoint_counts)}"
    )
    print(
        "ground domains: "
        f"GND_MODEM={endpoint_counts['GND_MODEM']} "
        f"GND_DIGITAL={endpoint_counts['GND_DIGITAL']} "
        f"GND_MIC={endpoint_counts['GND_MIC']}; PCB-MAIN net-ties=0"
    )
    if args.bom_output:
        print(f"schematic-derived BOM: {args.bom_output} rows={len(instances)} sha256={bom_sha256}")
    print("Review A human sign-off, layout, Review B, DFM and physical EVT remain pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
