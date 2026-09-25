#!/usr/bin/env python3
"""Station twin end-to-end scenarios against the Muhoed twin server (CI: protocol-e2e job).

Runs firmware/build/zs_station_twin with the Python server twin on the pipe and checks the server-side report:
  1. a drone fly-by is detected, published over GSM, acknowledged, no duplicates;
  2. a burst of events during a GSM outage goes out over LoRa (30 % loss both ways) once the link is marked
     degraded, every event is delivered exactly once, and a GSM probe restores the link when the network returns.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent
TWIN = REPO_ROOT / "firmware" / "build" / "zs_station_twin"
SERVER_CMD = f"{sys.executable} -m twin.twin_server"


def run(args: list[str]) -> tuple[str, dict]:
    out = subprocess.run([str(TWIN), *args, "--server", SERVER_CMD], cwd=SERVER_ROOT, capture_output=True, text=True, timeout=900)
    if out.returncode != 0:
        sys.stderr.write(out.stdout[-4000:] + out.stderr[-2000:])
        raise SystemExit(f"twin exited with {out.returncode}: {args}")
    report_line = [l for l in out.stdout.splitlines() if l.startswith("SERVER ")]
    assert report_line, "no server report"
    return out.stdout, json.loads(report_line[-1][7:])


def main() -> int:
    log, r = run(["--scene", "drone", "--seconds", "140", "--seed", "3", "--receipt-latency", "2000", "--expect-events", "1", "--expect-delivered", "1"])
    assert r["detections"] >= 1 and r["duplicates"] == 0 and r["decode_errors"] == 0, r
    assert "session done -> COMMS_DONE" in log
    print(f"scenario 1 (drone over GSM): detections {r['detections']}, heartbeats {r['heartbeats']}, duplicates {r['duplicates']}")

    log, r = run(["--scene", "quiet", "--seconds", "1400", "--seed", "3", "--gsm-outage", "5", "1200", "--lora", "--lora-loss", "0.3",
                  "--degraded-after", "2", "--gsm-probe-s", "300", "--inject-events", "12", "30", "--expect-delivered", "12"])
    assert r["lora_detections"] == 12 and r["unique_event_ids"] == 12 and r["decode_errors"] == 0, r
    assert r["duplicates"] == r["lora_frames"] - 12 or r["duplicates"] == 0, r   # a late duplicate frame is deduped, never double-counted
    assert "DEGRADED" in log and "link healthy again" in log, "degraded -> LoRa -> probe -> healthy cycle missing"
    print(f"scenario 2 (LoRa during a GSM outage): lora frames {r['lora_frames']}, delivered {r['lora_detections']}, duplicates {r['duplicates']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
