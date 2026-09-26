#!/usr/bin/env python3
"""PCB routing 005 (ci-apply): third Freerouting session, on top of candidate 004, with L1 at the SMPS pins.

Router input, derived deterministically from the step-1 DSN of the authoritative (003) board:
- ground planes In1/In2/In4 are power layers; every existing track and via is fixed;
- the copper candidate 004 accepted from both sessions is added as fixed, except the two nets ripped for L1
  (RIPPED: their new copper crossed the new L1 site and is routed again here);
- the five back-side test connectors as front parts with pre-mirrored images and B.Cu pads (as in 004b);
- L1 (LQH32PN2R2NN0L, 2.2 uH, SMPS of U1) moves from (52.0, 19.75) to (53.75, 40.75), rotation 180 kept: pad 1
  SMPS_SW next to VLXSMPS (U1.46), pad 2 VCORE_1V1 towards VDD11 (U1.49) - STM32U5 AN5373 layout guidance;
- classes: signal (F.Cu/B.Cu 0.15 mm), power (POWER_RAIL + SWITCH_NODE: F.Cu/In3.Cu/B.Cu 0.30 mm), burst
  (MODEM_BURST_POWER, 0.80 mm) and locked (RF_50OHM, USB_90OHM_DIFF: only the In2 plane layer, nothing to route;
  they keep their pins, so their pads stay obstacles). The grounds (RETURN_PLANE) get no pins, as in 004: their
  hundreds of pins would each stay "unrouted" in the router; the zones join them.
Freerouting 2.4.1 (pinned), headless, no fan-out/optimizer. Output: PCB-MAIN_ROUTE_INPUT_C.dsn,
PCB-MAIN_ROUTED_C.ses, AUTOROUTE_C.json. Nothing under hardware/kicad/native changes.
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
import apply_pcb_routing_004_autoroute_rev_a as step2  # noqa: E402
import apply_pcb_routing_004b_autoroute_rev_a as step4b  # noqa: E402

OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-005"
INPUT = OUT / "PCB-MAIN_ROUTE_INPUT_C.dsn"
SES = OUT / "PCB-MAIN_ROUTED_C.ses"
LOG = OUT / "AUTOROUTE_C.json"
PASSES = 8
TIME_LIMIT_S = 110 * 60
RIPPED = {"LORA_MOSI_U10", "PDM_DATA1_1V8"}
L1_OLD, L1_NEW = "(place L1 52000.000000 -19750.000000 front 180.000000", "(place L1 53750.000000 -40750.000000 front 180.000000"
CLASSES = [("signal", None, ["F.Cu", "B.Cu"], 150),
           ("power", ("POWER_RAIL", "SWITCH_NODE"), ["F.Cu", "In3.Cu", "B.Cu"], 300),
           ("burst", ("MODEM_BURST_POWER",), ["F.Cu", "In3.Cu", "B.Cu"], 800),
           ("locked", ("RF_50OHM", "USB_90OHM_DIFF"), ["In2.Cu"], 150)]
EMPTIED = ("RETURN_PLANE",)  # grounds: joined by the zones; hundreds of pins would each stay "unrouted" in the router


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_004() -> dict:
    """The new copper of candidate 004 (both sessions, after its DRC rejections), minus RIPPED."""
    info = json.loads(c4.AUTOROUTE.read_text(encoding="utf-8"))
    rejected = set(json.loads(c4.REJECTED.read_text(encoding="utf-8"))["nets"])
    copper = c4.session_copy(c4.SES.read_text(encoding="utf-8"),
                             set(info["prep"]["not_autorouted"]) | c4.DEFERRED | rejected | RIPPED)
    info_b = json.loads(c4.AUTOROUTE_B.read_text(encoding="utf-8"))
    rejected_b = set(json.loads(c4.REJECTED_B.read_text(encoding="utf-8"))["nets"])
    second = c4.session_copy(c4.SES_B.read_text(encoding="utf-8"),
                             set(info_b["prep"]["not_autorouted"]) | c4.DEFERRED | rejected_b | RIPPED)
    for net, entry in second.items():
        merged = copper.setdefault(net, {"wires": [], "vias": []})
        merged["wires"] += entry["wires"]
        merged["vias"] += entry["vias"]
    return copper


def route_input_c() -> tuple[str, dict]:
    text = step2.BASE.read_text(encoding="utf-8")
    for layer in ("In1.Cu", "In2.Cu", "In4.Cu"):
        old = f"    (layer {layer}\n      (type signal)"
        assert text.count(old) == 1, layer
        text = text.replace(old, f"    (layer {layer}\n      (type power)")
    text = text.replace("(type route)", "(type fix)")
    rows = {r["Net_Name"]: r for r in csv.DictReader(step2.AUTHORITY.open(encoding="utf-8"))}
    start = text.index("    (class kicad_default")
    end = text.index("\n    )\n", start) + 7
    block = text[start:end]
    names = re.findall(r'[^\s()]+', block[len("    (class kicad_default"):block.index("(circuit")])
    members = {c[0]: [] for c in CLASSES}
    for net in names:
        target = next((c[0] for c in CLASSES[1:] if rows[net]["Route_Class"] in c[1]), "signal")
        members[target].append(net)
    classes = ""
    for name, _, layers, width in CLASSES:
        lines, current = [], f"    (class {name}"
        for net in members[name]:
            if len(current) + len(step2.quote(net)) + 1 > 110:
                lines.append(current)
                current = "      " + step2.quote(net)
            else:
                current += " " + step2.quote(net)
        lines.append(current)
        classes += ("\n".join(lines) + '\n      (circuit\n        (use_via "Via[0-5]_500:300_um")\n'
                    f'        (use_layer {" ".join(layers)})\n      )\n      (rule\n        (width {width})\n'
                    "        (clearance 200)\n      )\n    )\n")
    text = text[:start] + classes + text[end:]
    network = text.index("  (network")
    emptied = sorted(n for n in names if rows[n]["Route_Class"] in EMPTIED)
    for net in emptied:
        m = re.search(r"\n    \(net " + re.escape(step2.quote(net)) + r"\n      \(pins[^)]*\)\n    \)", text[network:])
        assert m, net
        a, b = network + m.start(), network + m.end()
        text = text[:a] + f"\n    (net {step2.quote(net)}\n      (pins)\n    )" + text[b:]
    text, moved = step4b.mirror_back_parts(text)
    copper = accepted_004()
    text, fixed = step4b.add_fixed(text, copper)
    assert text.count(L1_OLD) == 1, "L1 placement"
    text = text.replace(L1_OLD, L1_NEW)
    return text, {"classes": {k: len(v) for k, v in members.items()}, "locked": sorted(members["locked"]),
                  "emptied": emptied, "not_autorouted": sorted(set(members["locked"]) | set(emptied)),
                  "back_parts_as_front": moved, "fixed_004_items": fixed, "fixed_004_nets": sorted(copper),
                  "ripped": sorted(RIPPED), "l1": [L1_OLD, L1_NEW]}


def main() -> int:
    if "--check" in sys.argv[1:]:
        info = json.loads(LOG.read_text(encoding="utf-8"))
        assert info["input_dsn_sha256"] == sha256(INPUT)
        print(f"PCB routing 005 autoroute: recorded (session {'present' if SES.is_file() else 'missing'})")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    text, prep = route_input_c()
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
    info = {"schema": "dioneya-pcb-routing-005-autoroute-v1", "freerouting": "2.4.1", "passes": PASSES, "rc": rc,
            "seconds": round(time.time() - started), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "session_004a_sha256": sha256(c4.SES), "session_004b_sha256": sha256(c4.SES_B),
            "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in lines if re.search(r"pass|unrouted|stage|completed|error|exception|warn",
                                                                    line, re.I)][-40:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("rc", "seconds", "session_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
