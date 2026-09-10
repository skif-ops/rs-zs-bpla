#!/usr/bin/env python3
"""Independent structural Review-A regression audit of native PCB-PWR Rev.A schematic."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from kiutils.schematic import Schematic

ROOT = Path(__file__).resolve().parents[1]
PIN_AUTH = ROOT / "hardware" / "PCB_PWR_PIN_AUTHORITY_REV_A.csv"
HARNESS = ROOT / "hardware" / "HARNESS_LOGICAL_PINOUT_REV_A.csv"


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)


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


def ref_of(inst) -> str:
    return next((p.value for p in inst.properties if p.key == "Reference"), "")


def endpoint(inst, symbol, pin_number: str) -> tuple[float, float]:
    pin = selected_pins(symbol, inst.unit or 1)[str(pin_number)]
    return (round(inst.position.X + pin.position.X, 4), round(inst.position.Y - pin.position.Y, 4))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schematic", type=Path, required=True)
    args = ap.parse_args()

    sch = Schematic.from_file(str(args.schematic), encoding="utf-8")
    instances = {ref_of(s): s for s in sch.schematicSymbols}
    require(len(instances) == len(sch.schematicSymbols), "duplicate or empty schematic references")
    lib_by_id = {s.libId: s for s in sch.libSymbols}
    labels: dict[tuple[float, float], set[str]] = {}
    for lab in sch.labels:
        key = (round(lab.position.X, 4), round(lab.position.Y, 4))
        labels.setdefault(key, set()).add(str(lab.text))
    nc_positions = {(round(n.position.X, 4), round(n.position.Y, 4)) for n in sch.noConnects}

    # Pin names and pin-to-net mapping must match the reviewed authority exactly.
    for row in rows(PIN_AUTH):
        ref = row["RefDes"]
        pin_no = row["Pin"]
        require(ref in instances, f"native PCB-PWR missing authority component {ref}")
        inst = instances[ref]
        require(inst.libId in lib_by_id, f"{ref}: embedded library symbol missing for {inst.libId}")
        sym = lib_by_id[inst.libId]
        pins = selected_pins(sym, inst.unit or 1)
        require(pin_no in pins, f"{ref}: native symbol missing pin {pin_no}")
        require(str(pins[pin_no].name) == row["Pin_Name"],
                f"{ref}.{pin_no} name mismatch native={pins[pin_no].name!r} authority={row['Pin_Name']!r}")
        pos = endpoint(inst, sym, pin_no)
        expected_net = row["RevA_Net"]
        if expected_net == "NC":
            require(pos in nc_positions, f"{ref}.{pin_no} must be explicit no-connect")
            require(not labels.get(pos), f"{ref}.{pin_no} NC unexpectedly has net label {labels.get(pos)}")
        else:
            require(expected_net in labels.get(pos, set()),
                    f"{ref}.{pin_no} expected net {expected_net}, found labels {sorted(labels.get(pos, set()))}")

    # Frozen 12-pin external contract.
    main_pwr = [r for r in rows(HARNESS) if r["Interface"] == "MAIN_PWR"]
    require([r["Pin"] for r in main_pwr] == [str(i) for i in range(1, 13)], "authority harness is no longer 12-pin")
    require("J2" in instances, "native MAIN/PWR connector J2 missing")
    j2 = instances["J2"]
    j2sym = lib_by_id[j2.libId]
    for row in main_pwr:
        pos = endpoint(j2, j2sym, row["Pin"])
        require(row["Net"] in labels.get(pos, set()),
                f"J2 pin {row['Pin']} must be {row['Net']}, got {sorted(labels.get(pos, set()))}")
    require(set(selected_pins(j2sym)) == {str(i) for i in range(1, 13)}, "J2 is not exactly 12 positions")

    # Input connector and true 4-terminal shunt topology.
    require("J1" in instances and "RSH1" in instances, "J1/RSH1 missing")
    j1 = instances["J1"]; j1sym = lib_by_id[j1.libId]
    for pin, net in {"1":"VBAT_RAW", "2":"GND_PWR"}.items():
        require(net in labels.get(endpoint(j1,j1sym,pin), set()), f"J1.{pin} input mapping mismatch")
    rsh = instances["RSH1"]; rshsym = lib_by_id[rsh.libId]
    rsh_expected = {"1":"VBAT_PROTECTED","2":"VBAT_SYS","3":"SHUNT_SOURCE_SENSE","4":"SHUNT_LOAD_SENSE"}
    require(set(selected_pins(rshsym)) == set(rsh_expected), "RSH1 must remain true 4-terminal symbol")
    for pin, net in rsh_expected.items():
        require(net in labels.get(endpoint(rsh,rshsym,pin), set()), f"RSH1.{pin} Kelvin/current mapping mismatch")

    # Startup deadlock regression: U4 must self-bootstrap from VBAT_SYS; EN_AUX gates U5 only.
    u4 = instances["U4"]; u4sym = lib_by_id[u4.libId]
    require("VBAT_SYS" in labels.get(endpoint(u4,u4sym,"9"), set()), "U4 EN no longer tied to VBAT_SYS - startup deadlock risk")
    require("EN_AUX" not in labels.get(endpoint(u4,u4sym,"9"), set()), "U4 EN illegally returned to EN_AUX")
    u5 = instances["U5"]; u5sym = lib_by_id[u5.libId]
    require("EN_AUX" in labels.get(endpoint(u5,u5sym,"3"), set()), "U5 EN must be controlled by EN_AUX")

    # Output capacitance is eight physical, individually referenced 1210 MLCCs.
    cap_banks = {
        "3V8_MODEM": ("C3", "C14", "C15", "C16"),
        "3V3_DIGITAL": ("C5", "C17", "C18", "C19"),
    }
    for rail, cap_refs in cap_banks.items():
        for ref in cap_refs:
            require(ref in instances, f"native PCB-PWR missing physical output capacitor {ref}")
            inst = instances[ref]
            sym = lib_by_id[inst.libId]
            value = next((p.value for p in inst.properties if p.key == "Value"), "")
            footprint = next((p.value for p in inst.properties if p.key == "Footprint"), "")
            require("CGA6P3X7R1E226M250AB" in value, f"{ref}: output capacitor MPN is not bound")
            require(footprint == "Capacitor_SMD:C_1210_3225Metric", f"{ref}: 1210 footprint is not bound")
            require(rail in labels.get(endpoint(inst, sym, "1"), set()), f"{ref}.1 is not on {rail}")
            require("GND_PWR" in labels.get(endpoint(inst, sym, "2"), set()), f"{ref}.2 is not on GND_PWR")

    # Explicit ground-return net ties, never implicit plane aliases.
    ties = {
        "NT1": ("GND_MODEM", "GND_PWR"),
        "NT2": ("GND_DIGITAL", "GND_PWR"),
        "NT3": ("GND_MIC", "GND_PWR"),
    }
    for ref, (a,b) in ties.items():
        require(ref in instances, f"missing explicit ground net tie {ref}")
        inst = instances[ref]; sym = lib_by_id[inst.libId]
        require(a in labels.get(endpoint(inst,sym,"1"), set()), f"{ref}.1 must be {a}")
        require(b in labels.get(endpoint(inst,sym,"2"), set()), f"{ref}.2 must be {b}")

    # Population policy that affects behaviour.
    expected_dnp = {"R5","R9","R13","R14","R15"}
    actual_dnp = {ref for ref, inst in instances.items() if bool(inst.dnp)}
    require(expected_dnp.issubset(actual_dnp), f"required DNP options lost: {sorted(expected_dnp-actual_dnp)}")
    require(not ({"R6","R10","R11","R12"} & actual_dnp), "required pull-down/pull-up unexpectedly marked DNP")

    # No stale legacy contract may be embedded in title/value/net labels.
    serialized_tokens = "\n".join([str(l.text) for l in sch.labels] + [
        next((p.value for p in s.properties if p.key == "Value"), "") for s in sch.schematicSymbols
    ])
    require("10-contact" not in serialized_tokens and "10-pin MAIN/PWR" not in serialized_tokens,
            "legacy 10-pin token present in native schematic")

    print("PCB-PWR native schematic Review-A regression audit PASS")
    print("pin/net authority exact; 12-pin MAIN/PWR; INA226 Kelvin; startup-safe 3V3; explicit ground net-ties")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
