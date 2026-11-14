#!/usr/bin/env python3
"""Fails when any function of the STM32 target build has a stack frame above the limit.

The target task stacks are 2..8 KB (app_config.h); a single frame above ~2.5 KB is almost always a local
buffer that belongs in static scratch (three of those overflowed the DSP, BLE and nRF stacks before this
check existed: YIN arrays, a 4 KB IPC frame copy, a 4 KB BLE write copy).  Reads the GCC -fstack-usage
files (.su) of the application and zs_core objects; vendor code (_deps) is ignored.

    python3 firmware/tools/check_stack_usage.py build-target [--limit 2560] [--top 15]
"""
import argparse
import pathlib
import sys

EXCEPTIONS = {
    # function name: allowed bytes (documented in COMMAND_TRUST_ED25519 note: TweetNaCl-style verify, comms stack 8 KB)
    "zs_ed25519_verify": 2600,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("build_dir")
    ap.add_argument("--limit", type=int, default=2560)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    rows = []
    for su in pathlib.Path(a.build_dir).rglob("*.su"):
        if "_deps" in su.parts:
            continue
        for line in su.read_text(errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            where, size = parts[0], parts[1]
            try:
                size = int(size)
            except ValueError:
                continue
            name = where.split(":")[-1]
            rows.append((size, name, where, parts[2]))
    if not rows:
        print("no .su files found: build the target with -fstack-usage", file=sys.stderr)
        return 2
    rows.sort(reverse=True)
    print(f"{'bytes':>6}  {'kind':8} function")
    for size, name, where, kind in rows[: a.top]:
        print(f"{size:>6}  {kind:8} {name}  ({where.rsplit(':', 3)[0]})")
    bad = [(s, n, w) for s, n, w, _ in rows if s > EXCEPTIONS.get(n, a.limit)]
    if bad:
        print("\nstack frames over the limit:", file=sys.stderr)
        for s, n, w in bad:
            print(f"  {s} B  {n}  ({w})", file=sys.stderr)
        return 1
    print(f"\nall frames <= {a.limit} B (exceptions: {', '.join(f'{k}<={v}' for k, v in EXCEPTIONS.items())})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
