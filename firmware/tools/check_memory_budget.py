#!/usr/bin/env python3
"""Fails when the STM32 target build leaves less free memory in a linker region than its budget keeps in reserve.

The link itself fails only on an overflow; RAM grew from 83 % to 91 % of RAM123 in a week of DSP work
(docs/STATION_PIPELINE_2026-09-23.md, docs/STATION_DIRECTION_SEPARATION_2026-10-01.md) without anything noticing.
The budget (firmware/targets/evt_pre_20/memory_budget.json) keeps a reserve per region for what the host build cannot
show: the heap and stack high-water marks measured on the bench and the bring-up fixes that follow.  A change that
needs the reserve updates the budget file in the same change, with the reason.

Regions and their sizes come from the map file's "Memory Configuration"; the use of a region is its extent: from its
origin to the end of the last allocated section whose run address (VMA) is in it, or of the load image (LMA) of
initialised data in flash (alignment gaps count, as they do for the linker).  The
largest symbols of every RAM region are listed, so a failure says where the memory went.

    python3 firmware/tools/check_memory_budget.py build-target/dioneya_evt_pre_20.elf \
        firmware/targets/evt_pre_20/memory_budget.json [--top 12]
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys


def tool(name: str) -> str:
    return f"arm-none-eabi-{name}"


def regions_from_map(map_path: pathlib.Path) -> dict:
    text = map_path.read_text(errors="replace")
    block = text.split("Memory Configuration", 1)[1].split("Linker script and memory map", 1)[0]
    out = {}
    for line in block.splitlines():
        m = re.match(r"^(\S+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)", line.strip())
        if m and m.group(1) != "*default*":
            out[m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16))
    return out


def sections(elf: pathlib.Path) -> list:
    """(name, size, vma, lma, flags) of the allocated sections."""
    lines = subprocess.run([tool("objdump"), "-h", str(elf)], check=True, capture_output=True, text=True).stdout.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s", line)
        if not m or i + 1 >= len(lines):
            continue
        flags = {f.strip() for f in lines[i + 1].split(",")}
        if "ALLOC" in flags:
            out.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16), int(m.group(4), 16), flags))
    return out


def largest_symbols(elf: pathlib.Path, lo: int, hi: int, top: int) -> list:
    lines = subprocess.run([tool("nm"), "-S", "--size-sort", "-r", str(elf)], check=True, capture_output=True,
                           text=True).stdout.splitlines()
    out = []
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        addr, size = int(parts[0], 16), int(parts[1], 16)
        if lo <= addr < hi:
            out.append((size, parts[3]))
        if len(out) >= top:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("elf")
    ap.add_argument("budget")
    ap.add_argument("--map", help="map file (default: the ELF's name with .map)")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    elf = pathlib.Path(a.elf)
    regions = regions_from_map(pathlib.Path(a.map) if a.map else elf.with_suffix(".map"))
    budget = json.loads(pathlib.Path(a.budget).read_text())["regions"]
    used = {name: 0 for name in regions}

    def region_of(addr: int):
        return next((n for n, (o, l) in regions.items() if o <= addr < o + l), None)

    def extend(addr: int, size: int):
        r = region_of(addr)
        if r and size:
            used[r] = max(used[r], addr + size - regions[r][0])

    for name, size, vma, lma, flags in sections(elf):
        extend(vma, size)
        if "LOAD" in flags and lma != vma:                     # initialised data: its image in flash too
            extend(lma, size)
    failed = False
    for name, (origin, length) in regions.items():
        free = length - used[name]
        need = budget.get(name, {}).get("min_free_bytes")
        verdict = "" if need is None else (" ok" if free >= need else f" BELOW the {need} B reserve")
        failed |= need is not None and free < need
        print(f"{name:8s} used {used[name]:8d} of {length:8d} B ({100.0 * used[name] / length:5.1f} %), free {free:8d} B"
              + ("" if need is None else f", reserve {need} B") + verdict)
    for name in budget:
        if name not in regions:
            print(f"{name}: in the budget but not in the map file's memory configuration")
            failed = True
    for name, (origin, length) in regions.items():
        if name.upper().startswith("FLASH") or not used[name]:
            continue
        print(f"largest symbols in {name}:")
        for size, sym in largest_symbols(elf, origin, origin + length, a.top):
            print(f"  {size:8d}  {sym}")
    if failed:
        print("memory budget exceeded: free memory in the region, or update the budget file with the reason", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
