#!/usr/bin/env python3
"""PCB routing 004b (ci-apply): second Freerouting run on the connections left open by candidate 004.

Router input, derived deterministically:
- the step-1 DSN of the authoritative (003) board with the step-2 preparation (tools/apply_pcb_routing_004_autoroute
  _rev_a.route_input: ground planes as power layers, existing copper fixed, signal/power/burst classes);
- the copper candidate 004 accepted from the first session (every autorouted net except the DRC-rejected and the
  deferred ones) added to the wiring as fixed;
- the five back-side test connectors (TP_EOL, TP_BLE_SWD, TP_MCU_SWD, TP_CELL_USB, TP_CELL_DBG) described as front
  parts with pre-mirrored images and B.Cu padstacks: Freerouting misplaced their mirrored pads in the first run, which
  caused the DRC-rejected shorts. Board positions are unchanged: pos + R(rot) * (-x, y) == pos + R(rot) * M * (x, y);
- VCORE_1V1 (deferred to 005) gets no pins, as the grounds, RF, USB and SMPS_SW already do.
Freerouting 2.4.1 (pinned), headless, no fan-out/optimizer. Output: PCB-MAIN_ROUTE_INPUT_B.dsn,
PCB-MAIN_ROUTED_B.ses, AUTOROUTE_B.json. Nothing under hardware/kicad/native changes.
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
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_main_routing_004_candidate_rev_a as cand  # noqa: E402
import apply_pcb_routing_004_autoroute_rev_a as step2  # noqa: E402

OUT = step2.OUT
INPUT = OUT / "PCB-MAIN_ROUTE_INPUT_B.dsn"
SES = OUT / "PCB-MAIN_ROUTED_B.ses"
LOG = OUT / "AUTOROUTE_B.json"
PASSES = 8
TIME_LIMIT_S = 110 * 60
BACK_IMAGES = ("::8", "::9", "::10")
BACK_PADSTACK = "Round[T]Pad_1700.000000_um"
BOTTOM_PADSTACK = "Round[B]Pad_1700.000000_um"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_copper() -> dict:
    info = json.loads(cand.AUTOROUTE.read_text(encoding="utf-8"))
    rejected = set(json.loads(cand.REJECTED.read_text(encoding="utf-8"))["nets"])
    skip = set(info["prep"]["not_autorouted"]) | cand.DEFERRED | rejected
    return cand.session_copy(cand.SES.read_text(encoding="utf-8"), skip)


def quote(name: str) -> str:
    return step2.quote(name)


def mirror_back_parts(text: str) -> tuple[str, list]:
    old = f"    (padstack {BACK_PADSTACK}\n      (shape (circle F.Cu 1700))\n      (attach off)\n    )\n"
    assert text.count(old) == 1, "back padstack"
    text = text.replace(old, old + f"    (padstack {BOTTOM_PADSTACK}\n      (shape (circle B.Cu 1700))\n      (attach off)\n    )\n")
    moved = []
    for image in BACK_IMAGES:
        start = text.index(f"    (image {image}\n")
        end = text.index("\n    )\n", start)
        block = text[start:end]
        pins = re.findall(r"\(pin (\S+) (\S+) ([-\d.]+) ([-\d.]+)\)", block)
        assert pins and all(p[0] == BACK_PADSTACK for p in pins), image
        new = f"    (image {image}\n" + "\n".join(
            f"      (pin {BOTTOM_PADSTACK} {num} {-float(x):g} {float(y):g})" for _, num, x, y in pins)
        text = text[:start] + new + text[end:]
        comp = re.search(r"\(component " + re.escape(image) + r"\n((?:\s+\(place [^\n]+\n)+)", text)
        places = comp.group(1)
        assert places.count(" back ") == places.count("(place ")
        moved += re.findall(r"\(place (\S+)", places)
        text = text[:comp.start(1)] + places.replace(" back ", " front ") + text[comp.end(1):]
    return text, moved


def add_fixed(text: str, copper: dict) -> tuple[str, int]:
    lines = []
    for net in sorted(copper):
        for layer, width, pts in copper[net]["wires"]:
            if len(set(pts)) < 2:  # degenerate one-point path: no shape
                continue
            coords = "  ".join(f"{x * 1000:.1f} {-y * 1000:.1f}" for x, y in pts)
            lines.append(f"    (wire (path {layer} {width * 1000:.1f}  {coords})(net {quote(net)})(type fix))")
        for x, y in copper[net]["vias"]:
            lines.append(f'    (via "Via[0-5]_500:300_um"  {x * 1000:.1f} {-y * 1000:.1f} (net {quote(net)})(type fix))')
    start = text.index("  (wiring\n")
    end = text.index("\n  )", start)
    return text[:end] + "\n" + "\n".join(lines) + text[end:], len(lines)


def route_input_b() -> tuple[str, dict]:
    text, prep = step2.route_input(step2.BASE.read_text(encoding="utf-8"))
    text, moved = mirror_back_parts(text)
    copper = accepted_copper()
    text, fixed = add_fixed(text, copper)
    network = text.index("  (network")
    for net in sorted(cand.DEFERRED):
        m = re.search(r"\n    \(net " + re.escape(quote(net)) + r"\n      \(pins[^)]*\)\n    \)", text[network:])
        assert m, net
        a, b = network + m.start(), network + m.end()
        text = text[:a] + f"\n    (net {quote(net)}\n      (pins)\n    )" + text[b:]
    prep.update({"back_parts_as_front": moved, "fixed_004_items": fixed, "fixed_004_nets": sorted(copper),
                 "not_autorouted": sorted(set(prep["not_autorouted"]) | cand.DEFERRED)})
    return text, prep


def main() -> int:
    if "--check" in sys.argv[1:]:
        info = json.loads(LOG.read_text(encoding="utf-8"))
        assert info["input_dsn_sha256"] == sha256(INPUT)
        print(f"PCB routing 004b autoroute: recorded (session {'present' if SES.is_file() else 'missing'})")
        return 0
    text, prep = route_input_b()
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
    info = {"schema": "dioneya-pcb-routing-004b-autoroute-v1", "freerouting": "2.4.1", "passes": PASSES, "rc": rc,
            "seconds": round(time.time() - started), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "first_session_sha256": sha256(cand.SES),
            "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in lines if re.search(r"pass|unrouted|stage|completed|error|exception",
                                                                    line, re.I)][-40:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("rc", "seconds", "session_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
