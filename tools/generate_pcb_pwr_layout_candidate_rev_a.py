#!/usr/bin/env python3
"""Generate the unrouted PCB-PWR Rev.A electrical placement candidate.

The output is a provisional canvas while DIM-003 is open. It intentionally has no
mounting holes, tracks, vias or zones and must never be used for CAM export.
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
PLACEMENT = ROOT / "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv"
PIN_AUTHORITY = ROOT / "hardware/PCB_PWR_PIN_AUTHORITY_REV_A.csv"
PASSIVE_AUTHORITY = ROOT / "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv"
PWR_FP = ROOT / "hardware/kicad/native/PCB-PWR/libs/DioneyaPWR.pretty"
MAIN_FP = ROOT / "hardware/kicad/native/PCB-MAIN/libs/DioneyaMain.pretty"
KICAD_FP = Path(os.environ.get("DIONEYA_KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints"))

MAJOR_FOOTPRINTS = {
    "U1": "DioneyaPWR:TI_DBV0006A_SOT23-6",
    "U2": "DioneyaPWR:TI_DGS0010A_VSSOP10",
    "U3": "DioneyaPWR:LMR60440_RAK0009A",
    "U4": "DioneyaPWR:LMR60440_RAK0009A",
    "U5": "DioneyaMain:TI_DBV0005A_SOT23-5",
    "Q1": "DioneyaPWR:CSD18540Q5B_DNK",
}

OTHER = {
    "J1": ("43045-0213", "DioneyaPWR:Molex_43045-0213_MicroFit-2_Vertical", "1=VBAT_RAW;2=GND_PWR"),
    "J2": ("43045-1202", "DioneyaMain:Molex_43045-1202_MicroFit-12_RA", "1=3V8_MODEM;2=GND_MODEM;3=3V3_DIGITAL;4=GND_DIGITAL;5=1V8_MIC;6=GND_MIC;7=PWR_GOOD;8=FAULT;9=EN_MODEM;10=EN_AUX;11=I2C2_SCL;12=I2C2_SDA"),
    "F1": ("0451005.MRL CANDIDATE", "Fuse:Fuse_1206_3216Metric", "1=VBAT_RAW;2=VBAT_FUSED"),
    "D1": ("SMBJ18A CANDIDATE", "Diode_SMD:D_SMB", "1=VBAT_FUSED;2=GND_PWR"),
    "RSH1": ("WSK2512R0100FEA", "DioneyaPWR:Vishay_WSK2512_4T_T1.19mm", "1=VBAT_PROTECTED;2=VBAT_SYS;3=SHUNT_SOURCE_SENSE;4=SHUNT_LOAD_SENSE"),
    "L1": ("XAL7030-472MEC", "DioneyaPWR:Coilcraft_XAL7030_472", "1=SW_3V8;2=3V8_MODEM"),
    "L2": ("XAL7030-472MEC", "DioneyaPWR:Coilcraft_XAL7030_472", "1=SW_3V3;2=3V3_DIGITAL"),
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def pin_map(value: str) -> dict[str, str]:
    result = {}
    for assignment in value.split(";"):
        number, net = assignment.split("=", 1)
        result[number] = net
    return result


def catalog() -> dict[str, dict[str, object]]:
    components: dict[str, dict[str, object]] = {}
    major_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(PIN_AUTHORITY):
        major_rows[row["RefDes"]].append(row)
    require(set(major_rows) == set(MAJOR_FOOTPRINTS), "major PCB-PWR placement component set drift")
    for ref, rows in major_rows.items():
        mpns = {row["MPN"] for row in rows}
        require(len(mpns) == 1, f"{ref}: MPN authority drift")
        components[ref] = {
            "value": next(iter(mpns)), "footprint": MAJOR_FOOTPRINTS[ref],
            "population": "FITTED", "pins": {row["Pin"]: row["RevA_Net"] for row in rows},
        }

    for row in read_csv(PASSIVE_AUTHORITY):
        ref = row["RefDes"]
        require(ref not in components, f"duplicate component authority: {ref}")
        components[ref] = {
            "value": f"{row['Value']} {row['MPN']}", "footprint": row["Footprint"],
            "population": row["Population"], "pins": pin_map(row["Pin_Map"]),
        }

    for ref, (value, footprint, pins) in OTHER.items():
        require(ref not in components, f"duplicate component authority: {ref}")
        components[ref] = {
            "value": value, "footprint": footprint, "population": "FITTED",
            "pins": pin_map(pins),
        }
    require(len(components) == 60, f"expected 60 PCB-PWR physical components; got {len(components)}")
    return components


def mm(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I_MM(float(x), float(y))


def add_outline(board: pcbnew.BOARD) -> None:
    for start, end in (((0, 0), (90, 0)), ((90, 0), (90, 60)),
                       ((90, 60), (0, 60)), ((0, 60), (0, 0))):
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(mm(*start)); edge.SetEnd(mm(*end))
        edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(pcbnew.FromMM(0.1))
        board.Add(edge)


def load_footprint(binding: str) -> pcbnew.FOOTPRINT:
    nickname, name = binding.split(":", 1)
    if nickname == "DioneyaPWR":
        directory = PWR_FP
    elif nickname == "DioneyaMain":
        directory = MAIN_FP
    else:
        directory = KICAD_FP / f"{nickname}.pretty"
    footprint = pcbnew.FootprintLoad(str(directory), name)
    if footprint is None:
        raise RuntimeError(f"cannot load controlled footprint {binding} from {directory}")
    return footprint


def normalize_text(footprint: pcbnew.FOOTPRINT) -> None:
    footprint.Value().SetVisible(False)
    footprint.Reference().SetVisible(True)
    footprint.Reference().SetTextSize(mm(0.8, 0.8))
    footprint.Reference().SetTextThickness(pcbnew.FromMM(0.12))
    footprint.Reference().SetPosition(footprint.GetPosition() + mm(0, -1.4))


def main() -> int:
    components = catalog()
    placements = read_csv(PLACEMENT)
    by_ref = {row["RefDes"]: row for row in placements}
    require(len(placements) == 60 and len(by_ref) == 60, "placement table must contain 60 unique rows")
    require(set(by_ref) == set(components), "placement table/component authority mismatch")
    require(all(row["Side"] == "TOP" and row["Placement_Status"].startswith("PROVISIONAL_")
                for row in placements), "placement rows must remain provisional top-side candidates")

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    board.GetDesignSettings().SetCopperLayerCount(4)
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
    add_outline(board)

    net_names = sorted({net for component in components.values()
                        for net in component["pins"].values() if net != "NC"})
    nets: dict[str, pcbnew.NETINFO_ITEM] = {}
    for name in net_names:
        item = pcbnew.NETINFO_ITEM(board, name)
        board.Add(item); nets[name] = item

    for row in placements:
        ref = row["RefDes"]
        component = components[ref]
        footprint = load_footprint(str(component["footprint"]))
        footprint.SetReference(ref); footprint.SetValue(str(component["value"]))
        footprint.SetProperty("DIONEA_FOOTPRINT_BINDING", str(component["footprint"]))
        footprint.SetProperty("DIONEA_POPULATION", str(component["population"]))
        footprint.SetProperty("DIONEA_FUNCTIONAL_ZONE", row["Functional_Zone"])
        footprint.SetProperty("DIONEA_PLACEMENT_STATUS", row["Placement_Status"])
        footprint.SetProperty("DIONEA_SOURCE_AUTHORITY", row["Source_Authority"])
        if component["population"] in {"DNP", "PCB_FEATURE"}:
            footprint.SetExcludedFromPosFiles(True)

        pads: dict[str, list[pcbnew.PAD]] = defaultdict(list)
        for pad in footprint.Pads():
            if pad.GetNumber():
                pads[pad.GetNumber()].append(pad)
        require(set(pads) == set(component["pins"]),
                f"{ref}: footprint pins {sorted(pads)} != authority {sorted(component['pins'])}")
        for number, net in component["pins"].items():
            if net != "NC":
                for pad in pads[number]:
                    pad.SetNet(nets[net])

        footprint.SetPosition(mm(float(row["X_mm"]), float(row["Y_mm"])))
        footprint.SetOrientationDegrees(float(row["Rotation_deg"]))
        normalize_text(footprint)
        board.Add(footprint)

    board.BuildListOfNets()
    require(len(list(board.GetTracks())) == 0 and len(list(board.Zones())) == 0,
            "placement generator must not create routing or zones")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.SaveBoard(str(OUT), board)
    print(f"PCB-PWR provisional placement candidate: {OUT.relative_to(ROOT)}")
    print(f"components=60 nets={len(net_names)} layers=4 outline=90x60 mounting_holes=0")
    print("routing=ABSENT zones=ABSENT CAM=PROHIBITED DIM-003=OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
