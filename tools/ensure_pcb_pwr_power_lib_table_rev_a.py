#!/usr/bin/env python3
"""Ensure the PCB-PWR project symbol table includes KiCad's standard power library."""
from __future__ import annotations

import argparse
from pathlib import Path

POWER_LINE = '  (lib (name "power")(type "KiCad")(uri "${KICAD9_SYMBOL_DIR}/power.kicad_sym")(options "")(descr "KiCad power symbols"))'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", type=Path, required=True)
    args = ap.parse_args()

    text = args.table.read_text(encoding="utf-8")
    if '(name "power")' not in text:
        stripped = text.rstrip()
        if not stripped.endswith(')'):
            raise RuntimeError("invalid sym-lib-table: closing parenthesis missing")
        stripped = stripped[:-1].rstrip()
        text = stripped + "\n" + POWER_LINE + "\n)\n"
        args.table.write_text(text, encoding="utf-8")

    verify = args.table.read_text(encoding="utf-8")
    if verify.count('(name "power")') != 1:
        raise RuntimeError("power library registration is missing or duplicated")
    print("PCB-PWR power symbol library registration PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
