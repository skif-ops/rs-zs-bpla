#!/usr/bin/env python3
"""Generate native KiCad schematic for Dioneya EVT-PRE-20 PCB-PWR Rev.A.

The reviewed CSV pin/net authorities are the design authority. This generator only
materializes them into a native KiCad schematic. Manufacturer IC symbols are represented
with controlled generic multi-pin symbols whose pin numbers/names are rewritten from the
Review-A authority; controlled footprints remain subject to layout/DFM review.

Output remains NOT FOR MANUFACTURE. Full schematic Review A, exact passive MPN freeze,
layout Review B and EVT evidence remain mandatory.
"""
from __future__ import annotations

import argparse
import copy
import json
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


def customize_pins(symbol: Symbol, names: dict[str, str], electrical: dict[str, str] | None = None) -> None:
    pins = selected_pins(symbol)
    if set(pins) != set(names):
        raise RuntimeError(f"{symbol.entryName}: pin-set mismatch expected={sorted(names)} actual={sorted(pins)}")
    for number, name in names.items():
        pins[number].name = name
        if electrical and number in electrical:
            pins[number].electricalType = electrical[number]


def prop(key: str, value: str, ident: int, x: float, y: float, *, hide: bool = False) -> Property:
    return Property(key=key, value=value, id=ident, position=Position(X=x, Y=y, angle=0), effects=Effects(hide=hide))


def make_instance(sch: Schematic, symbol: Symbol, *, reference: str, value: str, footprint: str,
                  datasheet: str, x: float, y: float, dnp: bool = False) -> SchematicSymbol:
    inst = SchematicSymbol()
    inst.libId = symbol.libId
    inst.position = Position(X=x, Y=y, angle=0)
    inst.unit = 1
    inst.inBom = True
    inst.onBoard = True
    inst.dnp = dnp
    inst.uuid = uid()
    inst.properties = [
        prop("Reference", reference, 0, x, y - 9.0),
        prop("Value", value, 1, x, y + 9.0),
        prop("Footprint", footprint, 2, x, y + 11.0, hide=True),
        prop("Datasheet", datasheet, 3, x, y + 13.0, hide=True),
    ]
    for number in sorted(selected_pins(symbol), key=lambda s: (len(s), s)):
        inst.pins[number] = uid()
    inst.instances = [SymbolProjectInstance(name="PCB-PWR", paths=[SymbolProjectPath(
        sheetInstancePath=f"/{sch.uuid}", reference=reference, unit=1)])]
    return inst


def endpoint(inst: SchematicSymbol, symbol: Symbol, pin_number: str) -> Position:
    pin = selected_pins(symbol)[str(pin_number)]
    return Position(X=round(inst.position.X + pin.position.X, 4),
                    Y=round(inst.position.Y - pin.position.Y, 4), angle=0)


def add_label(sch: Schematic, text: str, at: Position) -> None:
    sch.labels.append(LocalLabel(text=text, position=at, effects=Effects(), uuid=uid()))


def label_pins(sch: Schematic, inst: SchematicSymbol, symbol: Symbol, mapping: dict[str, str]) -> None:
    for pin, net in mapping.items():
        add_label(sch, net, endpoint(inst, symbol, pin))


def project_payload() -> dict[str, object]:
    return {
        "board": {}, "boards": [], "cvpcb": {}, "erc": {}, "libraries": {},
        "meta": {"filename": "PCB-PWR.kicad_pro", "version": 1},
        "net_settings": {"classes": [], "meta": {"version": 3}},
        "pcbnew": {}, "schematic": {},
        "text_variables": {"PROJECT": "Dioneya EVT-PRE-20", "REV": "A", "BOARD": "PCB-PWR"},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connector-symbols", type=Path, default=Path("/usr/share/kicad/symbols/Connector_Generic.kicad_sym"))
    ap.add_argument("--device-symbols", type=Path, default=Path("/usr/share/kicad/symbols/Device.kicad_sym"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    # Controlled generic bodies. Pin numbers and names are rewritten exactly from Review A.
    j2sym = load_symbol(args.connector_symbols, "Conn_01x12", "DioneyaPWR")
    j1sym = load_symbol(args.connector_symbols, "Conn_01x02", "DioneyaPWR")
    u1sym = load_symbol(args.connector_symbols, "Conn_01x06", "DioneyaPWR")
    q1sym = load_symbol(args.connector_symbols, "Conn_01x08", "DioneyaPWR")
    u2sym = load_symbol(args.connector_symbols, "Conn_01x10", "DioneyaPWR")
    u34sym = load_symbol(args.connector_symbols, "Conn_01x09", "DioneyaPWR")
    u5sym = load_symbol(args.connector_symbols, "Conn_01x05", "DioneyaPWR")
    rshsym = load_symbol(args.connector_symbols, "Conn_01x04", "DioneyaPWR")
    resistor = load_symbol(args.device_symbols, "R", "Device")
    capacitor = load_symbol(args.device_symbols, "C", "Device")
    inductor = load_symbol(args.device_symbols, "L", "Device")
    fuse = load_symbol(args.device_symbols, "Fuse", "Device")
    tvs = load_symbol(args.device_symbols, "D_TVS", "Device")

    customize_pins(j1sym, {"1": "VBAT_PLUS", "2": "VBAT_MINUS"})
    customize_pins(j2sym, {
        "1": "3V8_MODEM", "2": "GND_MODEM", "3": "3V3_DIGITAL", "4": "GND_DIGITAL",
        "5": "1V8_MIC", "6": "GND_MIC", "7": "PWR_GOOD", "8": "FAULT",
        "9": "EN_MODEM", "10": "EN_AUX", "11": "I2C2_SCL", "12": "I2C2_SDA",
    })
    customize_pins(u1sym, {"1": "VCAP", "2": "GND", "3": "EN", "4": "CATHODE", "5": "GATE", "6": "ANODE"})
    customize_pins(q1sym, {"1": "SOURCE", "2": "SOURCE", "3": "SOURCE", "4": "GATE",
                             "5": "DRAIN", "6": "DRAIN", "7": "DRAIN", "8": "DRAIN"})
    customize_pins(u2sym, {"1": "A1", "2": "A0", "3": "ALERT", "4": "SDA", "5": "SCL",
                             "6": "VS", "7": "GND", "8": "VBUS", "9": "IN-", "10": "IN+"})
    customize_pins(u34sym, {"1": "VIN", "2": "PGND", "3": "SW", "4": "BOOT", "5": "PG",
                              "6": "FB", "7": "MODE/SYNC", "8": "RT", "9": "EN"})
    customize_pins(u5sym, {"1": "IN", "2": "GND", "3": "EN", "4": "NC", "5": "OUT"})
    customize_pins(rshsym, {"1": "CURRENT_SOURCE", "2": "CURRENT_LOAD", "3": "SENSE_SOURCE", "4": "SENSE_LOAD"})

    sch = Schematic.create_new()
    sch.version = "20231120"
    sch.generator = "kiutils"
    sch.uuid = uid()
    sch.titleBlock = TitleBlock(
        title="Dioneya EVT-PRE-20 PCB-PWR Rev.A",
        date="2026-09-09", revision="A", company="Dioneya / ZS-BPLA",
        comments={1: "Review A pin/net authority PASS", 2: "NOT FOR MANUFACTURE - schematic Review A/Review B/EVT pending"},
    )
    sch.libSymbols.extend([j1sym, j2sym, u1sym, q1sym, u2sym, u34sym, u5sym, rshsym,
                           resistor, capacitor, inductor, fuse, tvs])

    # Main functional blocks. Coordinates are schematic-only and intentionally grid aligned.
    J1 = make_instance(sch, j1sym, reference="J1", value="PWR_INPUT_43045-0213",
                       footprint="DioneyaPWR:Molex_43045-0213_MicroFit-2_Vertical",
                       datasheet="Molex SD-43045-005 Rev.G1", x=25.40, y=38.10)
    F1 = make_instance(sch, fuse, reference="F1", value="0451005.MRL CANDIDATE",
                       footprint="Fuse:Fuse_1206_3216Metric", datasheet="Littelfuse 0451", x=48.26, y=35.56)
    D1 = make_instance(sch, tvs, reference="D1", value="SMBJ18A CANDIDATE",
                       footprint="Diode_SMD:D_SMB", datasheet="Littelfuse SMBJ", x=60.96, y=50.80)
    U1 = make_instance(sch, u1sym, reference="U1", value="LM74700QDBVRQ1",
                       footprint="DioneyaPWR:TI_DBV0006A_SOT23-6", datasheet="TI LM74700-Q1 Rev.G", x=83.82, y=38.10)
    Q1 = make_instance(sch, q1sym, reference="Q1", value="CSD18540Q5B",
                       footprint="DioneyaPWR:CSD18540Q5B_DNK", datasheet="TI CSD18540Q5B Rev.B", x=109.22, y=38.10)
    C1 = make_instance(sch, capacitor, reference="C1", value="100nF VCAP",
                       footprint="Capacitor_SMD:C_0402_1005Metric", datasheet="~", x=83.82, y=58.42)
    RSH1 = make_instance(sch, rshsym, reference="RSH1", value="WSK2512R0100FEA 10mOhm 1% 1W 4T",
                         footprint="DioneyaPWR:Vishay_WSK2512_4T_T1.19mm",
                         datasheet="Vishay WSK2512 document 30108", x=137.16, y=38.10)
    U2 = make_instance(sch, u2sym, reference="U2", value="INA226AIDGSR",
                       footprint="DioneyaPWR:TI_DGS0010A_VSSOP10", datasheet="TI INA226 Rev.C", x=137.16, y=68.58)
    C2 = make_instance(sch, capacitor, reference="C2", value="100nF INA226",
                       footprint="Capacitor_SMD:C_0402_1005Metric", datasheet="~", x=157.48, y=76.20)

    U3 = make_instance(sch, u34sym, reference="U3", value="LMR604403SRAKR 3V8",
                       footprint="DioneyaPWR:LMR60440_RAK0009A", datasheet="TI LMR60440 SNAS877", x=55.88, y=101.60)
    L1 = make_instance(sch, inductor, reference="L1", value="XAL7030-472MEC 4.7uH",
                       footprint="DioneyaPWR:Coilcraft_XAL7030_472",
                       datasheet="Coilcraft XAL7030 document 863", x=81.28, y=96.52)
    C3 = make_instance(sch, capacitor, reference="C3", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                       footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=91.44, y=111.76)
    C14 = make_instance(sch, capacitor, reference="C14", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                        footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=96.52, y=111.76)
    C15 = make_instance(sch, capacitor, reference="C15", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                        footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=101.60, y=111.76)
    C16 = make_instance(sch, capacitor, reference="C16", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                        footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=106.68, y=111.76)
    C4 = make_instance(sch, capacitor, reference="C4", value="100nF BOOT_3V8",
                       footprint="Capacitor_SMD:C_0402_1005Metric", datasheet="~", x=68.58, y=83.82)
    R1 = make_instance(sch, resistor, reference="R1", value="100k 0.1% RFBT",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=91.44, y=88.90)
    R2 = make_instance(sch, resistor, reference="R2", value="35.7k 0.1% RFBB",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=91.44, y=101.60)
    R3 = make_instance(sch, resistor, reference="R3", value="86.6k RT",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=45.72, y=121.92)
    R4 = make_instance(sch, resistor, reference="R4", value="0R MODE PFM",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=55.88, y=121.92)
    R5 = make_instance(sch, resistor, reference="R5", value="0R MODE-FPWM DNP",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=66.04, y=121.92, dnp=True)
    R6 = make_instance(sch, resistor, reference="R6", value="100k EN_MODEM PD",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=35.56, y=111.76)

    U4 = make_instance(sch, u34sym, reference="U4", value="LMR604403SRAKR 3V3 AON",
                       footprint="DioneyaPWR:LMR60440_RAK0009A", datasheet="TI LMR60440 SNAS877", x=121.92, y=101.60)
    L2 = make_instance(sch, inductor, reference="L2", value="XAL7030-472MEC 4.7uH",
                       footprint="DioneyaPWR:Coilcraft_XAL7030_472",
                       datasheet="Coilcraft XAL7030 document 863", x=147.32, y=96.52)
    C5 = make_instance(sch, capacitor, reference="C5", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                       footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=152.40, y=111.76)
    C17 = make_instance(sch, capacitor, reference="C17", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                        footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=157.48, y=111.76)
    C18 = make_instance(sch, capacitor, reference="C18", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                        footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=162.56, y=111.76)
    C19 = make_instance(sch, capacitor, reference="C19", value="22uF 25V X7R CGA6P3X7R1E226M250AB",
                        footprint="Capacitor_SMD:C_1210_3225Metric", datasheet="TDK CGA6P3X7R1E226M250AB", x=167.64, y=111.76)
    C6 = make_instance(sch, capacitor, reference="C6", value="100nF BOOT_3V3",
                       footprint="Capacitor_SMD:C_0402_1005Metric", datasheet="~", x=134.62, y=83.82)
    R7 = make_instance(sch, resistor, reference="R7", value="86.6k RT",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=111.76, y=121.92)
    R8 = make_instance(sch, resistor, reference="R8", value="0R MODE PFM",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=121.92, y=121.92)
    R9 = make_instance(sch, resistor, reference="R9", value="0R MODE-FPWM DNP",
                       footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=132.08, y=121.92, dnp=True)
    R10 = make_instance(sch, resistor, reference="R10", value="10k PWR_GOOD PU",
                        footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=157.48, y=88.90)

    U5 = make_instance(sch, u5sym, reference="U5", value="TPS7A2018PDBVR 1V8_MIC",
                       footprint="DioneyaMain:TI_DBV0005A_SOT23-5", datasheet="TI TPS7A20 Rev.H", x=68.58, y=157.48)
    C7 = make_instance(sch, capacitor, reference="C7", value="2.2uF IN",
                       footprint="Capacitor_SMD:C_0603_1608Metric", datasheet="~", x=50.80, y=172.72)
    C8 = make_instance(sch, capacitor, reference="C8", value="2.2uF OUT",
                       footprint="Capacitor_SMD:C_0603_1608Metric", datasheet="~", x=86.36, y=172.72)
    R11 = make_instance(sch, resistor, reference="R11", value="100k EN_AUX PD",
                        footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=58.42, y=180.34)

    R12 = make_instance(sch, resistor, reference="R12", value="10k FAULT PU",
                        footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=157.48, y=63.50)
    R13 = make_instance(sch, resistor, reference="R13", value="4.7k SCL PU DNP",
                        footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=172.72, y=63.50, dnp=True)
    R14 = make_instance(sch, resistor, reference="R14", value="4.7k SDA PU DNP",
                        footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=182.88, y=63.50, dnp=True)
    R15 = make_instance(sch, resistor, reference="R15", value="10k PG_3V8 PU DNP",
                        footprint="Resistor_SMD:R_0402_1005Metric", datasheet="~", x=96.52, y=121.92, dnp=True)

    NT1 = make_instance(sch, resistor, reference="NT1", value="NET_TIE GND_MODEM-GND_PWR",
                        footprint="NetTie:NetTie-2_SMD_Pad0.5mm", datasheet="~", x=132.08, y=157.48)
    NT2 = make_instance(sch, resistor, reference="NT2", value="NET_TIE GND_DIGITAL-GND_PWR",
                        footprint="NetTie:NetTie-2_SMD_Pad0.5mm", datasheet="~", x=147.32, y=157.48)
    NT3 = make_instance(sch, resistor, reference="NT3", value="NET_TIE GND_MIC-GND_PWR",
                        footprint="NetTie:NetTie-2_SMD_Pad0.5mm", datasheet="~", x=162.56, y=157.48)

    J2 = make_instance(sch, j2sym, reference="J2", value="MAIN_PWR_43045-1202_12PIN",
                       footprint="DioneyaMain:Molex_43045-1202_MicroFit-12_RA",
                       datasheet="Molex 43045-1202", x=198.12, y=109.22)

    sch.schematicSymbols.extend([J1,F1,D1,U1,Q1,C1,RSH1,U2,C2,U3,L1,C3,C14,C15,C16,C4,R1,R2,R3,R4,R5,R6,
                                 U4,L2,C5,C17,C18,C19,C6,R7,R8,R9,R10,U5,C7,C8,R11,R12,R13,R14,R15,NT1,NT2,NT3,J2])

    # Functional net labels - no hidden generator-inferred wiring.
    label_pins(sch, J1, j1sym, {"1":"VBAT_RAW","2":"GND_PWR"})
    label_pins(sch, F1, fuse, {"1":"VBAT_RAW","2":"VBAT_FUSED"})
    label_pins(sch, D1, tvs, {"1":"GND_PWR","2":"VBAT_FUSED"})
    label_pins(sch, U1, u1sym, {"1":"LM74700_VCAP","2":"GND_PWR","3":"VBAT_FUSED","4":"VBAT_PROTECTED","5":"REV_GATE","6":"VBAT_FUSED"})
    label_pins(sch, Q1, q1sym, {"1":"VBAT_FUSED","2":"VBAT_FUSED","3":"VBAT_FUSED","4":"REV_GATE",
                                  "5":"VBAT_PROTECTED","6":"VBAT_PROTECTED","7":"VBAT_PROTECTED","8":"VBAT_PROTECTED"})
    label_pins(sch, C1, capacitor, {"1":"LM74700_VCAP","2":"VBAT_FUSED"})
    label_pins(sch, RSH1, rshsym, {"1":"VBAT_PROTECTED","2":"VBAT_SYS","3":"SHUNT_SOURCE_SENSE","4":"SHUNT_LOAD_SENSE"})
    label_pins(sch, U2, u2sym, {"1":"GND_PWR","2":"GND_PWR","3":"FAULT","4":"I2C2_SDA","5":"I2C2_SCL",
                                  "6":"3V3_DIGITAL","7":"GND_PWR","8":"VBAT_SYS","9":"SHUNT_LOAD_SENSE","10":"SHUNT_SOURCE_SENSE"})
    label_pins(sch, C2, capacitor, {"1":"3V3_DIGITAL","2":"GND_PWR"})

    label_pins(sch, U3, u34sym, {"1":"VBAT_SYS","2":"GND_PWR","3":"SW_3V8","4":"BOOT_3V8","5":"PG_3V8",
                                   "6":"FB_3V8","7":"MODE_3V8","8":"RT_3V8","9":"EN_MODEM"})
    label_pins(sch, L1, inductor, {"1":"SW_3V8","2":"3V8_MODEM"})
    for cap in (C3, C14, C15, C16):
        label_pins(sch, cap, capacitor, {"1":"3V8_MODEM","2":"GND_PWR"})
    label_pins(sch, C4, capacitor, {"1":"BOOT_3V8","2":"SW_3V8"})
    label_pins(sch, R1, resistor, {"1":"3V8_MODEM","2":"FB_3V8"})
    label_pins(sch, R2, resistor, {"1":"FB_3V8","2":"GND_PWR"})
    label_pins(sch, R3, resistor, {"1":"RT_3V8","2":"GND_PWR"})
    label_pins(sch, R4, resistor, {"1":"MODE_3V8","2":"GND_PWR"})
    label_pins(sch, R5, resistor, {"1":"MODE_3V8","2":"RT_3V8"})
    label_pins(sch, R6, resistor, {"1":"EN_MODEM","2":"GND_PWR"})
    label_pins(sch, R15, resistor, {"1":"PG_3V8","2":"3V3_DIGITAL"})

    label_pins(sch, U4, u34sym, {"1":"VBAT_SYS","2":"GND_PWR","3":"SW_3V3","4":"BOOT_3V3","5":"PWR_GOOD",
                                   "6":"3V3_DIGITAL","7":"MODE_3V3","8":"RT_3V3","9":"VBAT_SYS"})
    label_pins(sch, L2, inductor, {"1":"SW_3V3","2":"3V3_DIGITAL"})
    for cap in (C5, C17, C18, C19):
        label_pins(sch, cap, capacitor, {"1":"3V3_DIGITAL","2":"GND_PWR"})
    label_pins(sch, C6, capacitor, {"1":"BOOT_3V3","2":"SW_3V3"})
    label_pins(sch, R7, resistor, {"1":"RT_3V3","2":"GND_PWR"})
    label_pins(sch, R8, resistor, {"1":"MODE_3V3","2":"GND_PWR"})
    label_pins(sch, R9, resistor, {"1":"MODE_3V3","2":"RT_3V3"})
    label_pins(sch, R10, resistor, {"1":"3V3_DIGITAL","2":"PWR_GOOD"})

    label_pins(sch, U5, u5sym, {"1":"3V3_DIGITAL","2":"GND_PWR","3":"EN_AUX","5":"1V8_MIC"})
    sch.noConnects.append(NoConnect(position=endpoint(U5, u5sym, "4"), uuid=uid()))
    label_pins(sch, C7, capacitor, {"1":"3V3_DIGITAL","2":"GND_PWR"})
    label_pins(sch, C8, capacitor, {"1":"1V8_MIC","2":"GND_PWR"})
    label_pins(sch, R11, resistor, {"1":"EN_AUX","2":"GND_PWR"})

    label_pins(sch, R12, resistor, {"1":"3V3_DIGITAL","2":"FAULT"})
    label_pins(sch, R13, resistor, {"1":"3V3_DIGITAL","2":"I2C2_SCL"})
    label_pins(sch, R14, resistor, {"1":"3V3_DIGITAL","2":"I2C2_SDA"})
    label_pins(sch, NT1, resistor, {"1":"GND_MODEM","2":"GND_PWR"})
    label_pins(sch, NT2, resistor, {"1":"GND_DIGITAL","2":"GND_PWR"})
    label_pins(sch, NT3, resistor, {"1":"GND_MIC","2":"GND_PWR"})
    label_pins(sch, J2, j2sym, {"1":"3V8_MODEM","2":"GND_MODEM","3":"3V3_DIGITAL","4":"GND_DIGITAL",
                                  "5":"1V8_MIC","6":"GND_MIC","7":"PWR_GOOD","8":"FAULT","9":"EN_MODEM",
                                  "10":"EN_AUX","11":"I2C2_SCL","12":"I2C2_SDA"})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sch.to_file(str(args.output), encoding="utf-8")
    pro = args.output.with_suffix(".kicad_pro")
    pro.write_text(json.dumps(project_payload(), indent=2) + "\n", encoding="utf-8")

    reread = Schematic.from_file(str(args.output), encoding="utf-8")
    refs = sorted(next((p.value for p in s.properties if p.key == "Reference"), "") for s in reread.schematicSymbols)
    required = {"J1","J2","F1","D1","U1","Q1","RSH1","U2","U3","U4","U5",
                "C3","C5","C14","C15","C16","C17","C18","C19","NT1","NT2","NT3"}
    if not required.issubset(refs):
        raise RuntimeError(f"round-trip required references missing: {sorted(required - set(refs))}")
    if len(reread.noConnects) != 1:
        raise RuntimeError(f"expected exactly U5.4 no-connect, got {len(reread.noConnects)}")
    if len(reread.labels) < 100:
        raise RuntimeError(f"unexpectedly small native net-label set: {len(reread.labels)}")
    print(f"saved native schematic {args.output}")
    print(f"saved native project {pro}")
    print("PCB-PWR round-trip PASS; refs", len(refs), "labels", len(reread.labels), "NC", len(reread.noConnects))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
