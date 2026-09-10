#!/usr/bin/env python3
"""Generate the native EVT-PRE-20 PCB-MIC Rev.A KiCad schematic.

The generator uses kiutils objects and the same reference symbol libraries that are
independently inspected before board generation. It does not hand-write the KiCad
S-expression. The output is re-parsed through kiutils and then must pass KiCad 9 ERC
in the PCB Native Gate.

This is still NOT FOR MANUFACTURE until Review A/B, mechanical envelope freeze, SI
validation and the complete PCB-MIC release gate pass.
"""
from __future__ import annotations

import argparse
import copy
import uuid
from pathlib import Path

from kiutils.items.common import Effects, Position, Property, TitleBlock
from kiutils.items.schitems import LocalLabel, NoConnect, SchematicSymbol, SymbolProjectInstance, SymbolProjectPath
from kiutils.schematic import Schematic
from kiutils.symbol import Symbol, SymbolLib


def uid() -> str:
    return str(uuid.uuid4())


def load_symbol(path: Path, entry: str, nickname: str) -> Symbol:
    lib = SymbolLib().from_file(str(path))
    matches = [s for s in lib.symbols if s.entryName == entry]
    if len(matches) != 1:
        raise RuntimeError(f"{path}: expected one symbol {entry}, found {len(matches)}")
    symbol = copy.deepcopy(matches[0])
    symbol.libraryNickname = nickname
    return symbol


def selected_pins(symbol: Symbol, unit: int = 1) -> dict[str, object]:
    """Collect common pins and the selected unit/style-1 pins by number."""
    found: dict[str, object] = {}

    def visit(node: Symbol, active: bool) -> None:
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


def set_pin_types(symbol: Symbol, mapping: dict[str, str]) -> None:
    pins = selected_pins(symbol)
    for number, electrical_type in mapping.items():
        if number not in pins:
            raise RuntimeError(f"{symbol.libId}: missing pin {number} while assigning {electrical_type}")
        pins[number].electricalType = electrical_type


def prop(key: str, value: str, ident: int, x: float, y: float, *, hide: bool = False) -> Property:
    return Property(
        key=key,
        value=value,
        id=ident,
        position=Position(X=x, Y=y, angle=0),
        effects=Effects(hide=hide),
    )


def make_instance(
    schematic: Schematic,
    symbol: Symbol,
    *,
    reference: str,
    value: str,
    footprint: str,
    datasheet: str,
    x: float,
    y: float,
    unit: int = 1,
) -> SchematicSymbol:
    inst = SchematicSymbol()
    inst.libId = symbol.libId
    inst.position = Position(X=x, Y=y, angle=0)
    inst.unit = unit
    inst.inBom = True
    inst.onBoard = True
    inst.dnp = False
    inst.uuid = uid()
    inst.properties = [
        prop("Reference", reference, 0, x, y - 11.0),
        prop("Value", value, 1, x, y + 11.0),
        prop("Footprint", footprint, 2, x, y + 13.0, hide=True),
        prop("Datasheet", datasheet, 3, x, y + 15.0, hide=True),
    ]
    for number in sorted(selected_pins(symbol, unit), key=lambda s: (len(s), s)):
        inst.pins[number] = uid()
    inst.instances = [
        SymbolProjectInstance(
            name="PCB-MIC",
            paths=[
                SymbolProjectPath(
                    sheetInstancePath=f"/{schematic.uuid}",
                    reference=reference,
                    unit=unit,
                )
            ],
        )
    ]
    return inst


def endpoint(inst: SchematicSymbol, symbol: Symbol, pin_number: str) -> Position:
    """Return KiCad sheet-space pin endpoint for a zero-degree library symbol.

    KiCad symbol-library coordinates use +Y upward while schematic sheet coordinates
    use +Y downward. X is translated directly; Y must therefore be subtracted. This
    transform is independently checked by KiCad ERC in the native gate.
    """
    if inst.position.angle not in (None, 0):
        raise RuntimeError("PCB-MIC schematic generator currently permits only zero-degree symbols")
    pins = selected_pins(symbol, inst.unit or 1)
    pin = pins[str(pin_number)]
    return Position(
        X=round(inst.position.X + pin.position.X, 4),
        Y=round(inst.position.Y - pin.position.Y, 4),
        angle=0,
    )


def add_label(schematic: Schematic, text: str, at: Position) -> None:
    schematic.labels.append(LocalLabel(text=text, position=at, effects=Effects(), uuid=uid()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--t5838-symbol", type=Path, required=True)
    ap.add_argument("--molex-symbol", type=Path, required=True)
    ap.add_argument("--device-symbols", type=Path, default=Path("/usr/share/kicad/symbols/Device.kicad_sym"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    t5838 = load_symbol(args.t5838_symbol, "MMICT5838-00-012", "Dioneya")
    molex = load_symbol(args.molex_symbol, "5040500691", "Dioneya")
    resistor = load_symbol(args.device_symbols, "R", "Device")
    capacitor = load_symbol(args.device_symbols, "C", "Device")

    # Make ERC electrically meaningful for this leaf board. The external harness side
    # is modeled from the PCB-MIC point of view: MAIN sources 1V8/PDM_CLK/AAD_CFG and
    # receives PDM_DATA/MIC_WAKE.
    set_pin_types(t5838, {
        "1": "output",       # DATA
        "2": "input",        # SELECT, strapped low on the leaf
        "3": "power_in",     # GND
        "4": "output",       # WAKE
        "5": "input",        # THSEL/AAD_CFG
        "6": "input",        # CLK
        "7": "power_in",     # VDD
    })
    set_pin_types(molex, {
        "1": "power_out",    # 1V8 from MAIN
        "2": "power_out",    # external return reference for ERC
        "3": "output",       # PDM_CLK from MAIN
        "4": "input",        # PDM_DATA to MAIN
        "5": "input",        # MIC_WAKE to MAIN
        "6": "output",       # AAD_CFG from MAIN
        "7": "no_connect",   # mechanical anchor in imported CAD symbol
        "8": "no_connect",   # mechanical anchor in imported CAD symbol
    })

    sch = Schematic.create_new()
    sch.version = "20231120"
    sch.generator = "kiutils"
    sch.uuid = uid()
    sch.titleBlock = TitleBlock(
        title="Dioneya EVT-PRE-20 PCB-MIC Rev.A",
        date="2026-09-09",
        revision="A",
        company="Dioneya / ZS-BPLA",
        comments={1: "T5838 PDM + AAD WAKE + THSEL", 2: "NOT FOR MANUFACTURE until Review A/B"},
    )

    # Embedded library symbols make the native schematic self-contained.
    sch.libSymbols.extend([t5838, molex, resistor, capacitor])

    # All instances are placed on the 1.27 mm (50 mil) schematic grid. This is a
    # deliberate ERC constraint, not a cosmetic alignment choice.
    j1 = make_instance(
        sch, molex,
        reference="J1", value="5040500691",
        footprint="CONN-SMD_6P-P1.50_A1501WRB-S-6P",
        datasheet="Molex 504050 series",
        x=35.56, y=69.85,
    )
    mk1 = make_instance(
        sch, t5838,
        reference="MK1", value="MMICT5838-00-012",
        footprint="MIC-SMD_7P-L3.5-W2.7_MMICT5837-00-012",
        datasheet="TDK DS-000383 v1.2",
        x=120.65, y=69.85,
    )
    r1 = make_instance(
        sch, resistor,
        reference="R1", value="0R EVT_SI_TUNE",
        footprint="Resistor_SMD:R_0402_1005Metric",
        datasheet="~",
        x=81.28, y=63.50,
    )
    c1 = make_instance(
        sch, capacitor,
        reference="C1", value="100nF X7R",
        footprint="Capacitor_SMD:C_0402_1005Metric",
        datasheet="~",
        x=91.44, y=91.44,
    )
    sch.schematicSymbols.extend([j1, mk1, r1, c1])

    # Local labels at pin endpoints are intentional: named nets stay unambiguous and
    # the generator does not infer visual wire coordinates from unrelated symbol body geometry.
    j_nets = {
        "1": "1V8_MIC",
        "2": "GND",
        "3": "PDM_CLK",
        "4": "PDM_DATA",
        "5": "MIC_WAKE",
        "6": "AAD_CFG",
    }
    for number, net in j_nets.items():
        add_label(sch, net, endpoint(j1, molex, number))
    sch.noConnects.extend([
        NoConnect(position=endpoint(j1, molex, "7"), uuid=uid()),
        NoConnect(position=endpoint(j1, molex, "8"), uuid=uid()),
    ])

    mic_nets = {
        "1": "PDM_DATA_MIC",
        "2": "GND",
        "3": "GND",
        "4": "MIC_WAKE",
        "5": "AAD_CFG",
        "6": "PDM_CLK",
        "7": "1V8_MIC",
    }
    for number, net in mic_nets.items():
        add_label(sch, net, endpoint(mk1, t5838, number))

    # R1 is a source-termination/tuning footprint, 0 ohm baseline pending harness SI EVT.
    add_label(sch, "PDM_DATA", endpoint(r1, resistor, "1"))
    add_label(sch, "PDM_DATA_MIC", endpoint(r1, resistor, "2"))
    add_label(sch, "1V8_MIC", endpoint(c1, capacitor, "1"))
    add_label(sch, "GND", endpoint(c1, capacitor, "2"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sch.to_file(str(args.output), encoding="utf-8")

    # Serializer round-trip is the first independent structural check; KiCad ERC is
    # deliberately a separate second check in the workflow.
    reread = Schematic.from_file(str(args.output), encoding="utf-8")
    refs = sorted(
        next((p.value for p in s.properties if p.key == "Reference"), "")
        for s in reread.schematicSymbols
    )
    if refs != ["C1", "J1", "MK1", "R1"]:
        raise RuntimeError(f"round-trip reference mismatch: {refs}")
    if len(reread.labels) != 17:
        raise RuntimeError(f"round-trip net label count mismatch: {len(reread.labels)}")
    if len(reread.noConnects) != 2:
        raise RuntimeError(f"round-trip no-connect count mismatch: {len(reread.noConnects)}")

    print(f"saved native schematic {args.output}")
    print("round-trip PASS; refs", refs, "labels", len(reread.labels), "NC", len(reread.noConnects))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
