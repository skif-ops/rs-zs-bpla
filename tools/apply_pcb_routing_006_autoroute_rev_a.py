#!/usr/bin/env python3
"""PCB routing 006 (ci-apply): fourth Freerouting session on top of candidate 005 (owner decisions 2026-09-26).

Router input = the session-C input (tools/apply_pcb_routing_005_autoroute_rev_a.route_input_c) plus:
- the new copper candidate 005 accepted from session C (without its DRC-rejected nets) fixed;
- every polygon padstack replaced by its bounding rectangle (conservative): the router passed through the
  RoundRect polygon pads of L1, R62 and FB1 in sessions A-C;
- class `slow` (F.Cu/In3.Cu/B.Cu, 0.15 mm) for the slow classes of the routing authority: LOW_SPEED_CONTROL,
  FIXTURE_DEBUG, ANALOG_SENSE_BIAS, MIC_WAKE_SIGNAL, I2C_OPEN_DRAIN, UART_SIGNAL (owner decision 2: In3 allowed
  for slow signals); SD, SPI, PDM, SIM and clocks stay on F.Cu/B.Cu;
- 3V3_DIGITAL locked (owner decision 1: it becomes an In3 pour in the digital area, done separately).
Output: PCB-MAIN_ROUTE_INPUT_D.dsn, PCB-MAIN_ROUTED_D.ses, AUTOROUTE_D.json under PCB-ROUTING-006.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_routing_004_candidate_rev_a as c4  # noqa: E402
import apply_pcb_main_routing_005_candidate_rev_a as c5  # noqa: E402
import apply_pcb_routing_004_autoroute_rev_a as step2  # noqa: E402
import apply_pcb_routing_004b_autoroute_rev_a as step4b  # noqa: E402
import apply_pcb_routing_005_autoroute_rev_a as ar5  # noqa: E402

OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-006"
INPUT = OUT / "PCB-MAIN_ROUTE_INPUT_D.dsn"
SES = OUT / "PCB-MAIN_ROUTED_D.ses"
LOG = OUT / "AUTOROUTE_D.json"
PASSES = 8
TIME_LIMIT_S = 110 * 60
SLOW = ("LOW_SPEED_CONTROL", "FIXTURE_DEBUG", "ANALOG_SENSE_BIAS", "MIC_WAKE_SIGNAL", "I2C_OPEN_DRAIN", "UART_SIGNAL")
LOCKED_NETS = {"3V3_DIGITAL"}
CLASSES = [("signal", ["F.Cu", "B.Cu"], 150), ("slow", ["F.Cu", "In3.Cu", "B.Cu"], 150),
           ("power", ["F.Cu", "In3.Cu", "B.Cu"], 300), ("burst", ["F.Cu", "In3.Cu", "B.Cu"], 800),
           ("locked", ["In2.Cu"], 150)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_c() -> dict:
    info = json.loads(ar5.LOG.read_text(encoding="utf-8"))
    rejected = set(json.loads(c5.REJECTED_C.read_text(encoding="utf-8"))["nets"])
    return c4.session_copy(ar5.SES.read_text(encoding="utf-8"), set(info["prep"]["not_autorouted"]) | rejected)


def rect_pads(text: str) -> tuple[str, int]:
    """Replace each polygon shape of a padstack by its bounding rectangle."""
    lib = text.index("  (library")
    end = text.index("\n  (network", lib)
    count = 0

    def repl(m):
        nonlocal count
        nums = [float(v) for v in m.group(3).split()]
        xs, ys = nums[0::2], nums[1::2]
        count += 1
        return f"(shape (rect {m.group(1)} {min(xs):g} {min(ys):g} {max(xs):g} {max(ys):g}))"

    body = re.sub(r"\(shape \(polygon (\S+) (\S+)\s+([-\d.\s]+)\)\)", repl, text[lib:end])
    return text[:lib] + body + text[end:], count


def reclass(text: str) -> tuple[str, dict]:
    rows = {r["Net_Name"]: r for r in csv.DictReader(step2.AUTHORITY.open(encoding="utf-8"))}
    start = text.index("    (class signal")
    last = text.index("    (class locked")
    end = text.index("\n    )\n", last) + 7
    old = {}
    for m in re.finditer(r"    \(class (\S+)((?:\s+[^\s()]+)+)\s+\(circuit", text[start:end]):
        old[m.group(1)] = m.group(2).split()
    members = {c[0]: [] for c in CLASSES}
    for name, nets in old.items():
        for net in nets:
            bare = net.strip('"')
            if bare in LOCKED_NETS:
                members["locked"].append(net)
            elif name == "signal" and rows[bare]["Route_Class"] in SLOW:
                members["slow"].append(net)
            else:
                members[name].append(net)
    block = ""
    for name, layers, width in CLASSES:
        lines, current = [], f"    (class {name}"
        for net in members[name]:
            if len(current) + len(net) + 1 > 110:
                lines.append(current)
                current = "      " + net
            else:
                current += " " + net
        lines.append(current)
        block += ("\n".join(lines) + '\n      (circuit\n        (use_via "Via[0-5]_500:300_um")\n'
                  f'        (use_layer {" ".join(layers)})\n      )\n      (rule\n        (width {width})\n'
                  "        (clearance 200)\n      )\n    )\n")
    return text[:start] + block + text[end:], {k: len(v) for k, v in members.items()}


def route_input_d() -> tuple[str, dict]:
    text, prep = ar5.route_input_c()
    copper = accepted_c()
    text, fixed = step4b.add_fixed(text, copper)
    text, rects = rect_pads(text)
    text, classes = reclass(text)
    not_routed = sorted(set(prep["not_autorouted"]) | LOCKED_NETS)
    return text, {"base": "session-C input", "fixed_c_items": fixed, "fixed_c_nets": sorted(copper),
                  "polygon_pads_as_rect": rects, "classes": classes, "slow_route_classes": list(SLOW),
                  "not_autorouted": not_routed}


def main() -> int:
    if "--check" in sys.argv[1:]:
        info = json.loads(LOG.read_text(encoding="utf-8"))
        assert info["input_dsn_sha256"] == sha256(INPUT)
        print(f"PCB routing 006 autoroute: recorded (session {'present' if SES.is_file() else 'missing'})")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    text, prep = route_input_d()
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
    info = {"schema": "dioneya-pcb-routing-006-autoroute-v1", "freerouting": "2.4.1", "passes": PASSES, "rc": rc,
            "seconds": round(time.time() - started), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "session_c_sha256": sha256(ar5.SES), "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in lines if re.search(r"pass|unrouted|stage|completed|error|exception|warn",
                                                                    line, re.I)][-40:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("rc", "seconds", "session_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
