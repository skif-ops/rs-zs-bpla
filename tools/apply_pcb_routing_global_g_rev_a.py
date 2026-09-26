#!/usr/bin/env python3
"""PCB routing G (ci-apply): one global Freerouting session from the authoritative (003) board with every fix found
in sessions A-E, instead of stacking sessions on fixed earlier copper.

Router input (deterministic, from the step-1 DSN): ground planes as power layers; the 003 copper fixed; back-side
test connectors as pre-mirrored front parts; polygon pads as bounding rectangles; L1 at the SMPS pins
(53.75, 40.75, 180); classes signal (F/B 0.15), slow (F/In3/B 0.15: LOW_SPEED_CONTROL, FIXTURE_DEBUG,
ANALOG_SENSE_BIAS, MIC_WAKE_SIGNAL, I2C_OPEN_DRAIN, UART_SIGNAL), power (POWER_RAIL incl. 3V3_DIGITAL as traces,
SWITCH_NODE: F/In3/B 0.30), burst (MODEM_BURST_POWER 0.80), locked (RF_50OHM, USB_90OHM_DIFF); grounds without pins.
Output: PCB-MAIN_ROUTE_INPUT_G.dsn, PCB-MAIN_ROUTED_G.ses, AUTOROUTE_G.json under PCB-ROUTING-G.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# the routing modules and the step-1 DSN live on feature/pcb-routing-004; they are taken from a pinned commit into a
# scratch tree (nothing of it is committed here)
SOURCE_COMMIT = "8c2ce64f098b4730d87d2995e07f29d9893b4654"
SCRATCH = Path("/tmp/pcb_routing_g_src")
if not (SCRATCH / "tools").is_dir():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "archive", SOURCE_COMMIT, "tools", "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv",
                              "hardware/kicad/candidates/PCB-ROUTING-004/PCB-MAIN_BASE.dsn"],
                             cwd=ROOT, capture_output=True, check=True)
    subprocess.run(["tar", "-x", "-C", str(SCRATCH)], input=archive.stdout, check=True)
sys.path.insert(0, str(SCRATCH / "tools"))
import apply_pcb_routing_004_autoroute_rev_a as step2  # noqa: E402
import apply_pcb_routing_005_autoroute_rev_a as ar5  # noqa: E402
import apply_pcb_routing_006_autoroute_rev_a as ar6  # noqa: E402

OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-G"
INPUT = OUT / "PCB-MAIN_ROUTE_INPUT_G.dsn"
SES = OUT / "PCB-MAIN_ROUTED_G.ses"
LOG = OUT / "AUTOROUTE_G.json"
PASSES = 10
TIME_LIMIT_S = 170 * 60


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def route_input_g() -> tuple[str, dict]:
    saved_fixed = ar5.accepted_004
    ar5.accepted_004 = lambda: {}
    try:
        text, prep = ar5.route_input_c()
    finally:
        ar5.accepted_004 = saved_fixed
    text, rects = ar6.rect_pads(text)
    saved_locked = set(ar6.LOCKED_NETS)
    ar6.LOCKED_NETS.clear()
    try:
        text, classes = ar6.reclass(text)
    finally:
        ar6.LOCKED_NETS |= saved_locked
    return text, {"base": "003 board (step-1 DSN), no autorouted copper fixed", "polygon_pads_as_rect": rects,
                  "classes": classes, "back_parts_as_front": prep["back_parts_as_front"], "l1": prep["l1"],
                  "not_autorouted": prep["not_autorouted"]}


def main() -> int:
    if "--check" in sys.argv[1:]:
        info = json.loads(LOG.read_text(encoding="utf-8"))
        assert info["input_dsn_sha256"] == sha256(INPUT)
        print(f"PCB routing G autoroute: recorded (session {'present' if SES.is_file() else 'missing'})")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    text, prep = route_input_g()
    INPUT.write_text(text, encoding="utf-8")
    jar = Path("/tmp/freerouting-2.4.1.jar")
    if not jar.is_file():
        urllib.request.urlretrieve(step2.JAR_URL, jar)
    assert sha256(jar) == step2.JAR_SHA256, "Freerouting jar hash differs"
    java = step2.java25()
    started = time.time()
    try:
        done = subprocess.run([java, "-Xmx6g", "-jar", str(jar), "-de", str(INPUT), "-do", str(SES), "-mp", str(PASSES),
                               "--gui.enabled=false", "--router.fanout.enabled=false", "--router.optimizer.enabled=false"],
                              capture_output=True, text=True, timeout=TIME_LIMIT_S)
        rc, log = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as exc:
        rc, log = "timeout", (exc.stdout or b"").decode(errors="replace") + (exc.stderr or b"").decode(errors="replace")
    lines = [line for line in log.splitlines() if "Analytics" not in line and "power layer" not in line]
    info = {"schema": "dioneya-pcb-routing-g-autoroute-v1", "freerouting": "2.4.1", "passes": PASSES, "rc": rc,
            "seconds": round(time.time() - started), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "source_commit": SOURCE_COMMIT,
            "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in lines if re.search(r"pass|unrouted|stage|completed|error|exception|warn",
                                                                    line, re.I)][-40:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("rc", "seconds", "session_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
