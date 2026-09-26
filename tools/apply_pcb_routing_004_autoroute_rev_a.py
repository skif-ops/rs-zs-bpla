#!/usr/bin/env python3
"""PCB routing 004, step 2 (ci-apply): autoroute the open PCB-MAIN connections with Freerouting.

Input: hardware/kicad/candidates/PCB-ROUTING-004/PCB-MAIN_BASE.dsn (KiCad 9 export of the authoritative board,
step 1). The router input is derived from it deterministically:
- In1.Cu, In2.Cu, In4.Cu (ground planes) are power layers: no trace is routed on them;
- every existing track and via is fixed (type fix): RF, USB, OctoSPI 003 and the rest stay as they are;
- net classes from hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv:
    signal  - every other net: F.Cu/B.Cu, 0.15 mm, clearance 0.20 mm
    power   - POWER_RAIL: F.Cu/In3.Cu/B.Cu, 0.30 mm
    burst   - MODEM_BURST_POWER: F.Cu/In3.Cu/B.Cu, 0.80 mm
  vias 0.5/0.3 mm;
- RETURN_PLANE (grounds, joined by the zones), RF_50OHM, USB_90OHM_DIFF and SWITCH_NODE nets keep their copper as
  obstacles but get no pins: they are not autorouted (controlled geometry, routed separately).
Freerouting 2.4.1 (SHA-256 pinned) runs headless without fan-out and optimizer. Output:
PCB-MAIN_ROUTE_INPUT.dsn, PCB-MAIN_ROUTED.ses and AUTOROUTE.json (log tail, timing). The session is only an input
for the candidate generator; nothing under hardware/kicad/native changes.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-004"
BASE = OUT / "PCB-MAIN_BASE.dsn"
INPUT = OUT / "PCB-MAIN_ROUTE_INPUT.dsn"
SES = OUT / "PCB-MAIN_ROUTED.ses"
LOG = OUT / "AUTOROUTE.json"
AUTHORITY = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
JAR_URL = "https://github.com/freerouting/freerouting/releases/download/v2.4.1/freerouting-2.4.1.jar"
JAR_SHA256 = "251101c3eeac22d7e7dfcf6796603279e5d1000283eb82d8f093780f7afc6aa9"
PASSES = 8  # run 1: 423 -> 127 unrouted after 7 passes, 123 after 11 (5-6 min per pass); the session is written at the end
TIME_LIMIT_S = 110 * 60
CLASSES = [("signal", None, ["F.Cu", "B.Cu"], 150), ("power", "POWER_RAIL", ["F.Cu", "In3.Cu", "B.Cu"], 300),
           ("burst", "MODEM_BURST_POWER", ["F.Cu", "In3.Cu", "B.Cu"], 800)]
NOT_AUTOROUTED = ("RETURN_PLANE", "RF_50OHM", "USB_90OHM_DIFF", "SWITCH_NODE")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quote(name: str) -> str:
    return f'"{name}"' if re.search(r'[\s()"]', name) else name


def route_input(text: str) -> tuple[str, dict]:
    for layer in ("In1.Cu", "In2.Cu", "In4.Cu"):
        old = f"    (layer {layer}\n      (type signal)"
        assert text.count(old) == 1, layer
        text = text.replace(old, f"    (layer {layer}\n      (type power)")
    fixed = text.count("(type route)")
    text = text.replace("(type route)", "(type fix)")
    rows = {r["Net_Name"]: r for r in csv.DictReader(AUTHORITY.open(encoding="utf-8"))}
    start = text.index("    (class kicad_default")
    end = text.index("\n    )\n", start) + 7
    block = text[start:end]
    names = re.findall(r'[^\s()]+', block[len("    (class kicad_default"):block.index("(circuit")])
    members = {name: [] for name, *_ in CLASSES}
    for net in names:
        route_class = rows[net]["Route_Class"]
        target = next((c[0] for c in CLASSES[1:] if c[1] == route_class), "signal")
        members[target].append(net)
    classes = ""
    for name, _, layers, width in CLASSES:
        lines, current = [], f"    (class {name}"
        for net in members[name]:
            if len(current) + len(quote(net)) + 1 > 110:
                lines.append(current)
                current = "      " + quote(net)
            else:
                current += " " + quote(net)
        lines.append(current)
        classes += ("\n".join(lines) + '\n      (circuit\n        (use_via "Via[0-5]_500:300_um")\n'
                    f'        (use_layer {" ".join(layers)})\n      )\n      (rule\n        (width {width})\n'
                    "        (clearance 200)\n      )\n    )\n")
    text = text[:start] + classes + text[end:]
    skipped = sorted(n for n in names if rows[n]["Route_Class"] in NOT_AUTOROUTED)
    network = text.index("  (network")
    for net in skipped:
        m = re.search(r"\n    \(net " + re.escape(quote(net)) + r"\n      \(pins[^)]*\)\n    \)", text[network:])
        assert m, net
        a, b = network + m.start(), network + m.end()
        text = text[:a] + f"\n    (net {quote(net)}\n      (pins)\n    )" + text[b:]
    return text, {"fixed_wiring_items": fixed, "classes": {k: len(v) for k, v in members.items()},
                  "not_autorouted": skipped}


def java25() -> str:
    for candidate in ("/usr/lib/jvm/java-25-openjdk-amd64/bin/java", "java"):
        try:
            done = subprocess.run([candidate, "-version"], capture_output=True, text=True)
            if re.search(r'version "25', done.stderr):
                return candidate
        except FileNotFoundError:
            pass
    subprocess.run(["sudo", "apt-get", "update", "-q"], check=True, capture_output=True)
    subprocess.run(["sudo", "apt-get", "install", "-y", "-q", "openjdk-25-jre-headless"], check=True,
                   capture_output=True)
    return "/usr/lib/jvm/java-25-openjdk-amd64/bin/java"


def main() -> int:
    if "--check" in sys.argv[1:]:
        info = json.loads(LOG.read_text(encoding="utf-8"))
        assert info["base_dsn_sha256"] == sha256(BASE) and info["input_dsn_sha256"] == sha256(INPUT)
        print(f"PCB routing 004 autoroute: recorded (session {'present' if SES.is_file() else 'missing'})")
        return 0
    text, prep = route_input(BASE.read_text(encoding="utf-8"))
    INPUT.write_text(text, encoding="utf-8")
    jar = Path("/tmp/freerouting-2.4.1.jar")
    if not jar.is_file():
        urllib.request.urlretrieve(JAR_URL, jar)
    assert sha256(jar) == JAR_SHA256, "Freerouting jar hash differs"
    java = java25()
    started = time.time()
    try:
        done = subprocess.run([java, "-Xmx6g", "-jar", str(jar), "-de", str(INPUT), "-do", str(SES),
                               "-mp", str(PASSES), "--gui.enabled=false", "--router.fanout.enabled=false",
                               "--router.optimizer.enabled=false"], capture_output=True, text=True,
                              timeout=TIME_LIMIT_S)
        rc, log = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as exc:
        rc, log = "timeout", (exc.stdout or b"").decode(errors="replace") + (exc.stderr or b"").decode(errors="replace")
    lines = [line for line in log.splitlines() if "Analytics" not in line and "power layer" not in line]
    info = {"schema": "dioneya-pcb-routing-004-autoroute-v1", "freerouting": "2.4.1", "jar_sha256": JAR_SHA256,
            "passes": PASSES, "rc": rc, "seconds": round(time.time() - started),
            "base_dsn_sha256": sha256(BASE), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in lines if re.search(r"pass|unrouted|stage|completed|error|exception",
                                                                    line, re.I)][-60:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("rc", "seconds", "session_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
