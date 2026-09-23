#!/usr/bin/env python3
"""Load an nRF52840 bridge image into the station's NOR slot over the B1 console and, optionally, flash the module.

    python tools/nrf_image_push.py COM7 build/nrf/zephyr/zephyr.signed.bin --version 3 [--update]

Speaks the console protocol of firmware/targets/evt_pre_20/app/app_nrf_update.c: `nrfimg begin <size> <version> <sha256>`,
`nrfimg put <offset> <base64>` (96 bytes per line, each acknowledged with `ok <next offset>`), `nrfimg end`
(the station verifies the SHA-256 it computed while writing and the one it reads back from NOR). With --update the
script then sends `nrfupd` and prints the station's progress while it restarts the module into MCUboot serial
recovery and uploads the slot image over the IPC UART (addendum C.6).  Requires pyserial.
"""
from __future__ import annotations
import argparse, base64, hashlib, sys, time
from pathlib import Path

CHUNK = 96


def read_line(ser, timeout: float) -> str:
    ser.timeout = timeout
    raw = ser.readline()
    return raw.decode("ascii", errors="replace").strip()


def expect_ok(ser, what: str, timeout: float = 3.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = read_line(ser, deadline - time.time())
        if not line or line == ">":
            continue
        if line.startswith("ok"):
            return line
        if line.startswith("fail") or line.startswith("nrfimg:"):
            raise SystemExit(f"{what}: station said: {line}")
    raise SystemExit(f"{what}: no acknowledgement from the station")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("image", type=Path)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--version", type=int, default=0)
    ap.add_argument("--update", action="store_true", help="send nrfupd after the image is stored")
    a = ap.parse_args()
    try:
        import serial
    except ImportError:
        raise SystemExit("pip install pyserial")
    data = a.image.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    ser = serial.Serial(a.port, a.baud, timeout=1)
    ser.reset_input_buffer()
    ser.write(b"\r\n")
    time.sleep(0.2)
    ser.reset_input_buffer()
    ser.write(f"nrfimg begin {len(data)} {a.version} {sha}\r\n".encode())
    expect_ok(ser, "begin", timeout=10.0)          # the slot erase takes a few seconds
    off, t0 = 0, time.time()
    while off < len(data):
        chunk = data[off:off + CHUNK]
        ser.write(f"nrfimg put {off} {base64.b64encode(chunk).decode()}\r\n".encode())
        reply = expect_ok(ser, f"put {off}")
        try:
            nxt = int(reply.split()[1])
        except (IndexError, ValueError):
            raise SystemExit(f"put {off}: unexpected reply {reply!r}")
        off = nxt
        if off % (CHUNK * 200) == 0 or off == len(data):
            rate = off / max(1e-3, time.time() - t0)
            print(f"\r{off}/{len(data)} bytes ({100 * off // len(data)} %, {rate / 1024:.1f} KiB/s)", end="", flush=True)
    print()
    ser.write(b"nrfimg end\r\n")
    print(expect_ok(ser, "end", timeout=30.0))     # read-back SHA-256 of the whole image
    if a.update:
        ser.write(b"nrfupd\r\n")
        deadline = time.time() + 600
        while time.time() < deadline:
            line = read_line(ser, 5.0)
            if line and line != ">":
                print(line)
                if line.startswith("nrfupd: done") or "FAILED" in line or "no valid image" in line or "no reply" in line:
                    break
    return 0


if __name__ == "__main__":
    sys.exit(main())
