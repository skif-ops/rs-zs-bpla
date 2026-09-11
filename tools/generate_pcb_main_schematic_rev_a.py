#!/usr/bin/env python3
"""Generate the controlled native KiCad PCB-MAIN Rev.A schematic.

The eleven closed PCB-MAIN capture authorities are the source of truth.  This
generator deliberately uses embedded, controlled pin bodies plus a reproducible
project-local symbol library rather than silently depending on workstation-specific
symbols.  Every authority pin is either bound to its frozen Rev.A net or marked
explicit NC.  Every MAIN-AUTH-010 support component and every PCB-MAIN harness
connector is materialized with exact RefDes, MPN, package, population and pin-to-net
data.  Unreviewed custom land patterns remain blank instead of using placeholders.

The output is a schematic-review input.  It is NOT FOR MANUFACTURE: PCB layout,
Review-B, factory DFM and physical EVT remain separate gates.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from kiutils.items.common import Effects, Fill, Font, PageSettings, Position, Property, Stroke, TitleBlock
from kiutils.items.schitems import LocalLabel, NoConnect, SchematicSymbol, SymbolProjectInstance, SymbolProjectPath
from kiutils.items.syitems import SyRect
from kiutils.schematic import Schematic
from kiutils.symbol import Symbol, SymbolLib, SymbolPin


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "PCB-MAIN.kicad_sch"
CONTROLLED_FOOTPRINTS = (
    ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "libs" /
    "DioneyaMain.pretty" / "PESD5V0C1BSF_SOD962-2.kicad_mod",
    ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "libs" /
    "DioneyaMain.pretty" / "STTS22H_UDFN-6L.kicad_mod",
    ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "libs" /
    "DioneyaMain.pretty" / "LT6000_DCB-7.kicad_mod",
    ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "libs" /
    "DioneyaMain.pretty" / "SiT1552_JE_CSP-4.kicad_mod",
    ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "libs" /
    "DioneyaMain.pretty" / "u-blox_MAX-M10S_LCC-18.kicad_mod",
    ROOT / "hardware" / "kicad" / "native" / "PCB-MAIN" / "libs" /
    "DioneyaMain.pretty" / "Ebyte_E22-M22S_Castellated-22.kicad_mod",
)
UUID_NAMESPACE = uuid.UUID("224f8048-0668-5a9f-98cb-43f39e0d8d3e")

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
SUPPORT_AUTHORITY = ROOT / "hardware" / "PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv"
HARNESS_AUTHORITY = ROOT / "hardware" / "HARNESS_LOGICAL_PINOUT_REV_A.csv"
MAIN_FREEZE = ROOT / "hardware" / "MAIN_COMPONENT_FREEZE_REV_A.csv"
CONNECTOR_FREEZE = ROOT / "hardware" / "CONNECTOR_FREEZE_REV_A.csv"
CAPTURE_STATUS = ROOT / "hardware" / "PCB_MAIN_CAPTURE_STATUS_REV_A.json"
MECHANICAL_AUTHORITY = ROOT / "hardware" / "PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv"
NET_OVERLAY = ROOT / "hardware" / "PCB_MAIN_NATIVE_NET_OVERLAY_REV_A.csv"
GROUND_AUTHORITY = ROOT / "hardware" / "PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.csv"

INPUTS = (*PIN_AUTHORITIES, SUPPORT_AUTHORITY, HARNESS_AUTHORITY, MAIN_FREEZE,
          CONNECTOR_FREEZE, CAPTURE_STATUS, MECHANICAL_AUTHORITY, NET_OVERLAY,
          GROUND_AUTHORITY)

EXPECTED_GENERIC_GROUND_ENDPOINTS = 157
EXPECTED_MIC_GROUND_ENDPOINTS = 21
CONNECTION_GRID_MM = 1.27


@dataclass(frozen=True)
class PinSpec:
    number: str
    name: str
    net: str
    direction: str


@dataclass(frozen=True)
class ComponentSpec:
    ref: str
    manufacturer: str
    mpn: str
    package: str
    value: str
    population: str
    authority: str
    pins: tuple[PinSpec, ...]
    on_board: bool = True


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def natural(value: str) -> tuple[object, ...]:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value))


def stable_uuid(key: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, key))


def connection_grid(value: float) -> float:
    """Snap schematic connection points to KiCad's 50 mil electrical grid."""
    return round(round(value / CONNECTION_GRID_MM) * CONNECTION_GRID_MM, 4)


def sanitize(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return cleaned or "UNSPECIFIED"


def parse_pin_map(value: str) -> tuple[PinSpec, ...]:
    pins: list[PinSpec] = []
    for token in value.split(";"):
        number, sep, net = token.partition("=")
        if not sep or not number.strip() or not net.strip():
            raise RuntimeError(f"invalid Pin_Map token {token!r} in {value!r}")
        net = net.strip()
        pins.append(PinSpec(number.strip(), number.strip(), net, "PASSIVE" if net != "NC" else "NC"))
    return tuple(sorted(pins, key=lambda pin: natural(pin.number)))


def load_component_specs() -> list[ComponentSpec]:
    freeze = {row["RefDes"]: row for row in read_csv(MAIN_FREEZE) if row["Assembly"] == "PCB-MAIN"}
    grouped: dict[str, dict[str, object]] = {}

    for path in PIN_AUTHORITIES:
        for row in read_csv(path):
            if path.name == "PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.csv":
                ref = "U1"
                pin_number = row["LQFP100_Pin"]
                pin_name = row["Pin_Name"]
                direction = row["Pin_Type"]
                frozen = freeze[ref]
                mpn = frozen["MPN"]
                package = frozen["Package_or_Module"]
                manufacturer = frozen["Manufacturer"]
            else:
                ref = row["RefDes"]
                pin_number = row["Pin"]
                pin_name = row["Pin_Name"]
                direction = row["Direction"]
                mpn = row["MPN"]
                package = row["Package"]
                frozen = freeze.get(ref, {})
                manufacturer = str(frozen.get("Manufacturer", "CONTROLLED_AUTHORITY"))
            item = grouped.setdefault(ref, {
                "manufacturer": manufacturer, "mpn": mpn, "package": package,
                "authority": path.name, "pins": {},
            })
            if (item["mpn"], item["package"]) != (mpn, package):
                raise RuntimeError(f"{ref}: conflicting MPN/package authority")
            pin = PinSpec(pin_number, pin_name, row["RevA_Net"], direction)
            old = item["pins"].get(pin_number)
            if old is not None and old != pin:
                raise RuntimeError(f"{ref}.{pin_number}: conflicting pin authorities: {old} != {pin}")
            item["pins"][pin_number] = pin
            if path.name not in str(item["authority"]):
                item["authority"] = f"{item['authority']};{path.name}"

    specs: list[ComponentSpec] = []
    for ref, item in grouped.items():
        specs.append(ComponentSpec(
            ref=ref,
            manufacturer=str(item["manufacturer"]),
            mpn=str(item["mpn"]),
            package=str(item["package"]),
            value=str(item["mpn"]),
            population="FITTED",
            authority=str(item["authority"]),
            pins=tuple(sorted(item["pins"].values(), key=lambda pin: natural(pin.number))),
            on_board=ref != "U12",
        ))

    active_refs = set(grouped)
    for row in read_csv(SUPPORT_AUTHORITY):
        ref = row["RefDes"]
        if ref in active_refs:
            raise RuntimeError(f"{ref}: duplicated between pin and support authorities")
        specs.append(ComponentSpec(
            ref=ref,
            manufacturer=row["Manufacturer"],
            mpn=row["MPN"],
            package=row["Package"],
            value=row["Value"],
            population=row["Population"],
            authority=row["Authority"],
            pins=parse_pin_map(row["Pin_Map"]),
        ))

    harness_groups: dict[str, list[dict[str, str]]] = {}
    for row in read_csv(HARNESS_AUTHORITY):
        ref = row["Connector_Ref"]
        if ref == "J_PWR" or ref.startswith("J_MIC"):
            harness_groups.setdefault(ref, []).append(row)
    for ref, rows in harness_groups.items():
        if ref in active_refs:
            raise RuntimeError(f"{ref}: harness connector duplicates pin authority")
        if ref == "J_PWR":
            mpn, package = "43045-1202", "Micro-Fit_3.0_2x06_Right_Angle"
        else:
            mpn, package = "504050-0691", "Pico-Lock_1.5_1x06_Right_Angle"
        pins = tuple(PinSpec(row["Pin"], row["Net"], row["Net"], row["Direction_at_MAIN"])
                     for row in sorted(rows, key=lambda row: natural(row["Pin"])))
        specs.append(ComponentSpec(ref, "Molex", mpn, package, mpn, "FITTED",
                                   HARNESS_AUTHORITY.name, pins))

    overlay_rows = read_csv(NET_OVERLAY)
    overlay: dict[tuple[str, str], dict[str, str]] = {}
    for row in overlay_rows:
        key = (row["RefDes"], row["Pin"])
        if key in overlay:
            raise RuntimeError(f"duplicate native-net overlay for {key}")
        overlay[key] = row
    used_overlay: set[tuple[str, str]] = set()
    mapped_specs: list[ComponentSpec] = []
    for spec in specs:
        mapped_pins: list[PinSpec] = []
        for pin in spec.pins:
            key = (spec.ref, pin.number)
            row = overlay.get(key)
            if row is None:
                mapped_pins.append(pin)
                continue
            if row["Logical_Net"] != pin.net:
                raise RuntimeError(
                    f"{spec.ref}.{pin.number}: overlay logical net {row['Logical_Net']} != authority {pin.net}"
                )
            mapped_pins.append(PinSpec(pin.number, pin.name, row["Native_Net"], pin.direction))
            used_overlay.add(key)
        mapped_specs.append(ComponentSpec(
            spec.ref, spec.manufacturer, spec.mpn, spec.package, spec.value,
            spec.population, spec.authority, tuple(mapped_pins), spec.on_board,
        ))
    unused = sorted(set(overlay) - used_overlay)
    if unused:
        raise RuntimeError(f"native-net overlay contains unknown endpoints: {unused}")
    specs = mapped_specs

    ground_rows = read_csv(GROUND_AUTHORITY)
    defaults = [row for row in ground_rows if row["Rule_Type"] == "DEFAULT"]
    if len(defaults) != 1:
        raise RuntimeError("ground-domain authority must contain exactly one DEFAULT rule")
    default = defaults[0]
    if (default["Logical_Net"], default["Native_Net"], default["RefDes"], default["Pin"]) != (
            "GND", "GND_DIGITAL", "*", "*"):
        raise RuntimeError("ground-domain DEFAULT must map remaining GND endpoints to GND_DIGITAL")

    ground_endpoints: dict[tuple[str, str], dict[str, str]] = {}
    for row in ground_rows:
        if row["Rule_Type"] == "DEFAULT":
            continue
        if row["Rule_Type"] != "ENDPOINT":
            raise RuntimeError(f"unsupported ground-domain rule type: {row['Rule_Type']}")
        key = (row["RefDes"], row["Pin"])
        if key in ground_endpoints:
            raise RuntimeError(f"duplicate ground-domain endpoint: {key}")
        if row["Logical_Net"] != "GND" or row["Native_Net"] != "GND_MIC":
            raise RuntimeError(f"explicit ground-domain endpoint must map GND to GND_MIC: {key}")
        ground_endpoints[key] = row

    used_ground_endpoints: set[tuple[str, str]] = set()
    generic_ground_count = 0
    mic_ground_count = 0
    ground_mapped_specs: list[ComponentSpec] = []
    for spec in specs:
        mapped_pins = []
        for pin in spec.pins:
            if pin.net != "GND":
                mapped_pins.append(pin)
                continue
            generic_ground_count += 1
            key = (spec.ref, pin.number)
            if key in ground_endpoints:
                target = ground_endpoints[key]["Native_Net"]
                used_ground_endpoints.add(key)
                mic_ground_count += 1
            else:
                target = default["Native_Net"]
            mapped_pins.append(PinSpec(pin.number, pin.name, target, pin.direction))
        ground_mapped_specs.append(ComponentSpec(
            spec.ref, spec.manufacturer, spec.mpn, spec.package, spec.value,
            spec.population, spec.authority, tuple(mapped_pins), spec.on_board,
        ))
    unused_ground = sorted(set(ground_endpoints) - used_ground_endpoints)
    if unused_ground:
        raise RuntimeError(f"ground-domain authority contains unknown endpoints: {unused_ground}")
    if generic_ground_count != EXPECTED_GENERIC_GROUND_ENDPOINTS:
        raise RuntimeError(
            f"generic GND endpoint set changed: {generic_ground_count} != "
            f"{EXPECTED_GENERIC_GROUND_ENDPOINTS}"
        )
    if mic_ground_count != EXPECTED_MIC_GROUND_ENDPOINTS:
        raise RuntimeError(
            f"GND_MIC endpoint set changed: {mic_ground_count} != "
            f"{EXPECTED_MIC_GROUND_ENDPOINTS}"
        )
    specs = ground_mapped_specs

    refs = [spec.ref for spec in specs]
    if len(refs) != len(set(refs)):
        raise RuntimeError("duplicate component references in generated capture")
    if len([spec for spec in specs if spec.ref in active_refs]) != len(active_refs):
        raise RuntimeError("active authority component count changed unexpectedly")
    return sorted(specs, key=lambda spec: natural(spec.ref))


def footprint_for(spec: ComponentSpec) -> str:
    package = spec.package
    metric = {
        "0402": "0402_1005Metric", "0603": "0603_1608Metric",
        "0805": "0805_2012Metric", "1206": "1206_3216Metric",
        "1210": "1210_3225Metric",
    }
    if package in metric:
        prefix = "Capacitor_SMD:C_" if spec.ref.startswith("C") else "Resistor_SMD:R_"
        if spec.ref.startswith("L") or spec.ref.startswith("FB"):
            prefix = "Inductor_SMD:L_"
        return prefix + metric[package]
    if spec.ref == "U12":
        return ""
    # Exact manufacturer land patterns remain a Review-A/Review-B deliverable.
    # Do not put synthetic package-shaped placeholders into the native source.
    return ""


def electrical_type(direction: str, net: str) -> str:
    if net == "NC":
        return "passive"
    direction = direction.upper()
    if direction in {"OUTPUT", "POWER_OUT", "POWER_OUTPUT"}:
        return "output"
    if direction in {"OPEN_DRAIN", "OUTPUT_OD", "OPEN_COLLECTOR"}:
        return "open_collector"
    if direction in {"BIDIR", "BIDIR_OD", "DIGITAL_IO", "DIGITAL_IO_ANALOG",
                     "DIGITAL_IO_TRACE", "DIGITAL_IO_NFC", "RF_BIDIR", "USB_BIDIR",
                     "DEBUG_BIDIR", "CONTACT"}:
        return "bidirectional"
    if direction in {"INPUT", "DEBUG_INPUT", "SENSE", "POWER_SENSE"}:
        return "input"
    # Power and mechanical contacts are deliberately passive at this capture layer.
    # Rail-source validity is controlled by PCB-PWR and verified separately.
    return "passive"


def native_electrical_type(spec: ComponentSpec, pin: PinSpec) -> str:
    """Translate authority directions into an ERC-honest KiCad pin model."""
    if spec.ref.startswith("TP_"):
        # Fixture contacts are passive copper even when the station sees a signal
        # as an input, output or sense line.
        return "passive"
    if (spec.ref, pin.number) == ("U8", "17"):
        # BG95 RESET_N is internally biased and intentionally pulled low only by
        # the open-collector Q2 stage; modelling it as a passive control node
        # avoids inventing a push-pull source on the modem domain.
        return "passive"
    if (spec.ref, pin.number) == ("U1", "98"):
        # The two VDD11 balls are one internal regulator output. Keep pin 49 as
        # the ERC source and the second bonded output contact passive.
        return "passive"
    return electrical_type(pin.direction, pin.net)


def make_symbol(spec: ComponentSpec) -> tuple[Symbol, dict[str, SymbolPin], float]:
    entry = sanitize(f"{spec.ref}_{spec.mpn}")
    root = Symbol.create_new(
        f"DioneyaMain:{entry}", spec.ref.rstrip("0123456789_") or spec.ref,
        spec.value, footprint_for(spec), spec.authority,
    )
    root.pinNames = True
    root.pinNamesOffset = 0.8
    unit = Symbol(entryName=entry, unitId=1, styleId=1)
    count = len(spec.pins)
    left_count = (count + 1) // 2
    right_count = count - left_count
    rows = max(left_count, right_count, 1)
    pitch = 2.54
    half_height = max(5.08, (rows + 1) * pitch / 2)
    half_width = 13.97 if count > 16 else 10.16
    unit.graphicItems.append(SyRect(
        start=Position(X=-half_width, Y=half_height),
        end=Position(X=half_width, Y=-half_height),
        stroke=Stroke(width=0.254), fill=Fill(type="background"),
    ))
    pin_effect = Effects(font=Font(width=0.9, height=0.9))
    pins_by_number: dict[str, SymbolPin] = {}
    for index, spec_pin in enumerate(spec.pins):
        if index < left_count:
            row = index
            position = Position(X=-half_width - 2.54,
                                Y=(left_count - 1) * pitch / 2 - row * pitch, angle=0)
        else:
            row = index - left_count
            position = Position(X=half_width + 2.54,
                                Y=(right_count - 1) * pitch / 2 - row * pitch, angle=180)
        pin = SymbolPin(
            electricalType=native_electrical_type(spec, spec_pin),
            graphicalStyle="line", position=position, length=2.54,
            name=spec_pin.name, number=spec_pin.number,
            nameEffects=pin_effect, numberEffects=pin_effect,
        )
        unit.pins.append(pin)
        pins_by_number[spec_pin.number] = pin
    root.units.append(unit)
    return root, pins_by_number, half_height


def instance_property(key: str, value: str, ident: int, x: float, y: float, hide: bool = False) -> Property:
    return Property(key=key, value=value, id=ident, position=Position(X=x, Y=y, angle=0),
                    effects=Effects(font=Font(width=1.0, height=1.0), hide=hide))


def make_instance(schematic: Schematic, spec: ComponentSpec, symbol: Symbol,
                  pins: dict[str, SymbolPin], x: float, y: float, half_height: float) -> SchematicSymbol:
    inst = SchematicSymbol()
    inst.libId = symbol.libId
    inst.position = Position(X=x, Y=y, angle=0)
    inst.unit = 1
    inst.inBom = True
    inst.onBoard = spec.on_board
    inst.dnp = spec.population == "DNP"
    inst.uuid = stable_uuid(f"instance:{spec.ref}")
    inst.properties = [
        instance_property("Reference", spec.ref, 0, x, y - half_height - 3.0),
        instance_property("Value", spec.value, 1, x, y + half_height + 3.0),
        instance_property("Footprint", footprint_for(spec), 2, x, y + half_height + 5.0, True),
        instance_property("Datasheet", spec.authority, 3, x, y + half_height + 7.0, True),
        instance_property("Manufacturer", spec.manufacturer, 4, x, y + half_height + 9.0, True),
        instance_property("MPN", spec.mpn, 5, x, y + half_height + 11.0, True),
        instance_property("Package", spec.package, 6, x, y + half_height + 13.0, True),
        instance_property("Population", spec.population, 7, x, y + half_height + 15.0, True),
        instance_property("Authority", spec.authority, 8, x, y + half_height + 17.0, True),
    ]
    inst.pins = {number: stable_uuid(f"instance-pin:{spec.ref}:{number}") for number in pins}
    inst.instances = [SymbolProjectInstance(name="PCB-MAIN", paths=[SymbolProjectPath(
        sheetInstancePath=f"/{schematic.uuid}", reference=spec.ref, unit=1,
    )])]
    return inst


def endpoint(inst: SchematicSymbol, pin: SymbolPin) -> Position:
    return Position(X=round(inst.position.X + pin.position.X, 4),
                    Y=round(inst.position.Y - pin.position.Y, 4), angle=0)


def add_pin_binding(schematic: Schematic, spec: ComponentSpec, inst: SchematicSymbol,
                    pins: dict[str, SymbolPin]) -> None:
    for spec_pin in spec.pins:
        at = endpoint(inst, pins[spec_pin.number])
        if spec_pin.net == "NC":
            schematic.noConnects.append(NoConnect(
                position=at, uuid=stable_uuid(f"nc:{spec.ref}:{spec_pin.number}")))
        else:
            schematic.labels.append(LocalLabel(
                text=spec_pin.net, position=at,
                effects=Effects(font=Font(width=0.9, height=0.9)),
                uuid=stable_uuid(f"label:{spec.ref}:{spec_pin.number}"),
            ))


def place_components(specs: list[ComponentSpec], symbol_data: dict[str, tuple[Symbol, dict[str, SymbolPin], float]]) -> dict[str, tuple[float, float]]:
    active = [spec for spec in specs if len(spec.pins) > 2 or spec.ref.startswith(("J_", "TP_"))]
    simple = [spec for spec in specs if spec not in active]
    positions: dict[str, tuple[float, float]] = {}

    # Balance large authority devices across five columns in the upper portion of A0.
    column_x = [75.0, 305.0, 535.0, 765.0, 995.0]
    column_y = [55.0] * len(column_x)
    for spec in sorted(active, key=lambda item: (-len(item.pins), natural(item.ref))):
        column = min(range(len(column_x)), key=lambda idx: column_y[idx])
        half_height = symbol_data[spec.ref][2]
        y = column_y[column] + half_height
        positions[spec.ref] = (connection_grid(column_x[column]), connection_grid(y))
        column_y[column] = y + half_height + 18.0

    # MAIN-AUTH-010 two-pin support network is dense but still readable on one A0 sheet.
    cols = 17
    x0, y0 = 48.0, 585.0
    x_pitch, y_pitch = 68.0, 18.0
    for index, spec in enumerate(sorted(simple, key=lambda item: natural(item.ref))):
        positions[spec.ref] = (
            connection_grid(x0 + (index % cols) * x_pitch),
            connection_grid(y0 + (index // cols) * y_pitch),
        )
    return positions


def write_project_libraries(schematic: Schematic, project_dir: Path) -> tuple[Path, Path, Path]:
    libs = project_dir / "libs"
    libs.mkdir(parents=True, exist_ok=True)
    symbol_library = libs / "DioneyaMain.kicad_sym"

    exported = []
    for symbol in schematic.libSymbols:
        item = copy.deepcopy(symbol)
        item.libraryNickname = None
        exported.append(item)
    SymbolLib(version="20231120", generator="kiutils", symbols=exported).to_file(
        str(symbol_library), encoding="utf-8"
    )

    sym_table = project_dir / "sym-lib-table"
    sym_table.write_text('''(sym_lib_table
  (version 7)
  (lib (name "DioneyaMain")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaMain.kicad_sym")(options "")(descr "Dioneya PCB-MAIN controlled Review-A symbols"))
)
''', encoding="utf-8")

    fp_table = project_dir / "fp-lib-table"
    fp_table.write_text('''(fp_lib_table
  (version 7)
  (lib (name "DioneyaMain")(type "KiCad")(uri "${KIPRJMOD}/libs/DioneyaMain.pretty")(options "")(descr "Controlled PCB-MAIN manufacturer land patterns"))
  (lib (name "Capacitor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Capacitor_SMD.pretty")(options "")(descr "KiCad capacitor SMD footprints"))
  (lib (name "Inductor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Inductor_SMD.pretty")(options "")(descr "KiCad inductor SMD footprints"))
  (lib (name "Resistor_SMD")(type "KiCad")(uri "${KICAD9_FOOTPRINT_DIR}/Resistor_SMD.pretty")(options "")(descr "KiCad resistor SMD footprints"))
)
''', encoding="utf-8")
    return symbol_library, sym_table, fp_table


def project_payload() -> dict[str, object]:
    return {
        "board": {}, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": "PCB-MAIN.kicad_pro", "version": 1},
        "net_settings": {"classes": [], "meta": {"version": 3}},
        "pcbnew": {}, "schematic": {},
        "text_variables": {
            "PROJECT": "Dioneya EVT-PRE-20", "REV": "A", "BOARD": "PCB-MAIN",
            "STATUS": "LAYOUT_ENGINEERING_CANDIDATE_NOT_FOR_MANUFACTURE",
        },
    }


def build(output: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    specs = load_component_specs()
    schematic = Schematic.create_new()
    schematic.version = "20231120"
    schematic.generator = "kiutils"
    schematic.uuid = stable_uuid("schematic:PCB-MAIN:RevA")
    schematic.paper = PageSettings(paperSize="A0")
    schematic.titleBlock = TitleBlock(
        title="Dioneya EVT-PRE-20 PCB-MAIN Rev.A",
        date="2026-09-10", revision="A", company="Dioneya / ZS-BPLA",
        comments={
            1: "MAIN-AUTH-001..011 controlled native capture",
            2: "SCHEMATIC REVIEW / NOT FOR MANUFACTURE",
            3: "Layout, Review B, DFM and physical EVT pending",
        },
    )

    symbol_data = {spec.ref: make_symbol(spec) for spec in specs}
    positions = place_components(specs, symbol_data)
    for spec in specs:
        symbol, pins, half_height = symbol_data[spec.ref]
        schematic.libSymbols.append(symbol)
        x, y = positions[spec.ref]
        inst = make_instance(schematic, spec, symbol, pins, x, y, half_height)
        schematic.schematicSymbols.append(inst)
        add_pin_binding(schematic, spec, inst, pins)

    output.parent.mkdir(parents=True, exist_ok=True)
    schematic.to_file(str(output))
    project = output.with_suffix(".kicad_pro")
    project.write_text(json.dumps(project_payload(), indent=2) + "\n", encoding="utf-8")
    symbol_library, sym_table, fp_table = write_project_libraries(schematic, output.parent)
    manifest = output.parent / "PCB-MAIN_capture_manifest.json"
    manifest_payload = {
        "configuration": "EVT-PRE-20 Rev.A",
        "board": "PCB-MAIN",
        "state": "LAYOUT_ENGINEERING_CANDIDATE_NOT_FOR_MANUFACTURE",
        "generator": str(Path(__file__).relative_to(ROOT)),
        "generator_sha256": sha256(Path(__file__)),
        "inputs": [{"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for path in INPUTS],
        "component_count": len(specs),
        "fitted_count": sum(spec.population == "FITTED" for spec in specs),
        "dnp_count": sum(spec.population == "DNP" for spec in specs),
        "pin_count": sum(len(spec.pins) for spec in specs),
        "schematic_sha256": sha256(output),
        "project_sha256": sha256(project),
        "symbol_library_sha256": sha256(symbol_library),
        "symbol_library_table_sha256": sha256(sym_table),
        "footprint_library_table_sha256": sha256(fp_table),
        "controlled_footprints": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}
            for path in CONTROLLED_FOOTPRINTS
        ],
        "review_a": "AUTOMATED_SOURCE_NET_AUDIT_AND_KICAD_ERC_PASS_HUMAN_SIGNOFF_PENDING",
        "review_b": "OPEN_PLACEMENT_CANDIDATE_ROUTING_AND_EVIDENCE_PENDING",
    }
    manifest.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
    return output, project, symbol_library, sym_table, fp_table, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()

    if args.check:
        expected = (
            output,
            output.with_suffix(".kicad_pro"),
            output.parent / "libs" / "DioneyaMain.kicad_sym",
            output.parent / "sym-lib-table",
            output.parent / "fp-lib-table",
            output.parent / "PCB-MAIN_capture_manifest.json",
        )
        with tempfile.TemporaryDirectory(prefix="pcb-main-capture-check-") as tmp:
            actual = build(Path(tmp) / "PCB-MAIN.kicad_sch")
            for generated, committed in zip(actual, expected):
                if not committed.is_file():
                    raise SystemExit(f"missing generated source: {committed}")
                if generated.read_bytes() != committed.read_bytes():
                    raise SystemExit(f"generated source drift: {committed}")
        print("PCB-MAIN deterministic native capture check: PASS")
        return 0

    generated = build(output)
    for path in generated:
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
