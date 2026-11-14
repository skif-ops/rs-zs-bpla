"""Compare physical ref/pin connectivity in KiCad XML and Altium Protel2 netlists.

Virtual symbols (designators starting with #) are reported separately. A KiCad
unconnected-(...) singleton is allowed to be absent from Altium's netlist, but
all other physical pin memberships and net names must match for a pass.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

PIN_RE = re.compile(r"^([#A-Za-z_][#A-Za-z0-9_]*)-([A-Za-z0-9]+)(?:\s|$)")


def kicad_nets(path: Path) -> dict[str, set[tuple[str, str]]]:
    nets: dict[str, set[tuple[str, str]]] = {}
    for net in ET.parse(path).findall(".//nets/net"):
        name = net.get("name")
        if not name or name in nets:
            raise ValueError(f"Missing or duplicate KiCad net name: {name}")
        nets[name] = {(node.get("ref"), node.get("pin")) for node in net.findall("node")}
    return nets


def protel2_nets(path: Path) -> dict[str, set[tuple[str, str]]]:
    lines = path.read_text(encoding="latin1").splitlines()
    if not lines or lines[0].strip() != "PROTEL NETLIST 2.0":
        raise ValueError("Expected Protel2 netlist")
    nets: dict[str, set[tuple[str, str]]] = {}
    i = 1
    while i < len(lines):
        if lines[i].strip() != "(":
            i += 1
            continue
        i += 1
        if i == len(lines):
            raise ValueError("Unterminated net section")
        name = lines[i].strip()
        i += 1
        if not name or name in nets:
            raise ValueError(f"Missing or duplicate Altium net name: {name}")
        pins: set[tuple[str, str]] = set()
        while i < len(lines) and lines[i].strip() != ")":
            if lines[i].strip():
                match = PIN_RE.match(lines[i])
                if not match:
                    raise ValueError(f"Cannot parse pin on net {name}: {lines[i]}")
                pin = match.groups()
                if pin in pins:
                    raise ValueError(f"Duplicate pin {pin} on net {name}")
                pins.add(pin)
            i += 1
        if i == len(lines):
            raise ValueError(f"Unterminated net {name}")
        nets[name] = pins
        i += 1
    return nets


def as_json_pins(pins: set[tuple[str, str]]) -> list[str]:
    return [f"{ref}-{pin}" for ref, pin in sorted(pins)]


def physical_partition(nets: dict[str, set[tuple[str, str]]], source: bool):
    groups: dict[frozenset[tuple[str, str]], list[str]] = defaultdict(list)
    pin_to_names: dict[tuple[str, str], list[str]] = defaultdict(list)
    virtual = []
    omitted_singletons = []
    for name, members in nets.items():
        physical = {pin for pin in members if not pin[0].startswith("#")}
        virtual.extend((name, ref, number) for ref, number in members if ref.startswith("#"))
        if source and name.startswith("unconnected-") and len(physical) == 1:
            omitted_singletons.extend(physical)
            continue
        if not physical:
            continue
        group = frozenset(physical)
        groups[group].append(name)
        for pin in physical:
            pin_to_names[pin].append(name)
    duplicates = {f"{ref}-{number}": names for (ref, number), names in pin_to_names.items() if len(names) != 1}
    if duplicates:
        raise ValueError(f"Physical pin appears on multiple nets: {duplicates}")
    return groups, sorted(virtual), sorted(omitted_singletons)


def compare(source_path: Path, altium_path: Path) -> dict:
    source = kicad_nets(source_path)
    altium = protel2_nets(altium_path)
    sg, sv, omitted = physical_partition(source, source=True)
    ag, av, _ = physical_partition(altium, source=False)
    source_pins = set().union(*sg) if sg else set()
    altium_pins = set().union(*ag) if ag else set()
    missing_groups = sg.keys() - ag.keys()
    extra_groups = ag.keys() - sg.keys()
    name_mismatches = []
    for group in sg.keys() & ag.keys():
        source_names = sorted(name.rsplit("/", 1)[-1] for name in sg[group])
        altium_names = sorted(ag[group])
        if source_names != altium_names:
            name_mismatches.append({"pins": as_json_pins(set(group)), "kicad": source_names, "altium": altium_names})
    return {
        "source": str(source_path), "altium": str(altium_path),
        "source_net_count": len(source), "altium_net_count": len(altium),
        "source_physical_net_count": len(sg), "altium_physical_net_count": len(ag),
        "source_physical_pin_count": len(source_pins), "altium_physical_pin_count": len(altium_pins),
        "omitted_kicad_unconnected_singletons": as_json_pins(set(omitted)),
        "source_virtual_nodes": [f"{name}: {ref}-{pin}" for name, ref, pin in sv],
        "altium_virtual_nodes": [f"{name}: {ref}-{pin}" for name, ref, pin in av],
        "physical_pin_universe_equal": source_pins == altium_pins,
        "physical_net_partitions_equal": not missing_groups and not extra_groups,
        "physical_net_names_equal": not name_mismatches,
        "missing_physical_pins": as_json_pins(source_pins - altium_pins),
        "extra_physical_pins": as_json_pins(altium_pins - source_pins),
        "missing_groups": [{"kicad": sg[group], "pins": as_json_pins(set(group))} for group in sorted(missing_groups, key=lambda g: sorted(g))],
        "extra_groups": [{"altium": ag[group], "pins": as_json_pins(set(group))} for group in sorted(extra_groups, key=lambda g: sorted(g))],
        "name_mismatches": sorted(name_mismatches, key=lambda x: x["pins"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-xml", type=Path, required=True)
    parser.add_argument("--altium-net", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.kicad_xml, args.altium_net)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    if not all(result[k] for k in ("physical_pin_universe_equal", "physical_net_partitions_equal", "physical_net_names_equal")):
        sys.exit(1)


if __name__ == "__main__":
    main()
