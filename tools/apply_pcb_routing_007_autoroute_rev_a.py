#!/usr/bin/env python3
"""PCB routing 007 (ci-apply): fifth Freerouting session - 3V3_DIGITAL as traces (owner decision, option A).

Router input = the session-D input (tools/apply_pcb_routing_006_autoroute_rev_a.route_input_d) plus the new copper
candidate 006 accepted from session D (without its DRC-rejected nets) fixed, and 3V3_DIGITAL moved from the locked
class to the power class (F.Cu/In3.Cu/B.Cu, 0.30 mm). An In3 pour of 3V3 was not made: In2 carries the GND_MIC
plane under almost the whole board (5677 mm2), 0.11 mm from In3.
Output: PCB-MAIN_ROUTE_INPUT_E.dsn, PCB-MAIN_ROUTED_E.ses, AUTOROUTE_E.json under PCB-ROUTING-007.
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
import apply_pcb_main_routing_004_candidate_rev_a as c4  # noqa: E402
import apply_pcb_main_routing_006_candidate_rev_a as c6  # noqa: E402
import apply_pcb_routing_004_autoroute_rev_a as step2  # noqa: E402
import apply_pcb_routing_004b_autoroute_rev_a as step4b  # noqa: E402
import apply_pcb_routing_006_autoroute_rev_a as ar6  # noqa: E402

OUT = ROOT / "hardware/kicad/candidates/PCB-ROUTING-007"
INPUT = OUT / "PCB-MAIN_ROUTE_INPUT_E.dsn"
SES = OUT / "PCB-MAIN_ROUTED_E.ses"
LOG = OUT / "AUTOROUTE_E.json"
PASSES = 8
TIME_LIMIT_S = 110 * 60
UNLOCK = "3V3_DIGITAL"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_d() -> dict:
    info = json.loads(ar6.LOG.read_text(encoding="utf-8"))
    rejected = set(json.loads(c6.REJECTED_D.read_text(encoding="utf-8"))["nets"]) if c6.REJECTED_D.is_file() else set()
    return c4.session_copy(ar6.SES.read_text(encoding="utf-8"), set(info["prep"]["not_autorouted"]) | rejected)


def move_class(text: str, net: str, src: str, dst: str) -> str:
    def span(name):
        start = text.index(f"    (class {name}")
        return start, text.index("(circuit", start)
    s0, s1 = span(src)
    head = text[s0:s1]
    new_head = re.sub(r"(?<=\s)" + re.escape(net) + r"(?=\s)", "", head, count=1)
    assert new_head != head, f"{net} not in class {src}"
    text = text[:s0] + new_head + text[s1:]
    d0 = text.index(f"    (class {dst}") + len(f"    (class {dst}")
    return text[:d0] + f" {net}" + text[d0:]


def route_input_e() -> tuple[str, dict]:
    text, prep = ar6.route_input_d()
    copper = accepted_d()
    text, fixed = step4b.add_fixed(text, copper)
    text = move_class(text, UNLOCK, "locked", "power")
    not_routed = sorted(set(prep["not_autorouted"]) - {UNLOCK})
    return text, {"base": "session-D input", "fixed_d_items": fixed, "fixed_d_nets": sorted(copper),
                  "unlocked": UNLOCK, "not_autorouted": not_routed}


def main() -> int:
    if "--check" in sys.argv[1:]:
        info = json.loads(LOG.read_text(encoding="utf-8"))
        assert info["input_dsn_sha256"] == sha256(INPUT)
        print(f"PCB routing 007 autoroute: recorded (session {'present' if SES.is_file() else 'missing'})")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    text, prep = route_input_e()
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
    info = {"schema": "dioneya-pcb-routing-007-autoroute-v1", "freerouting": "2.4.1", "passes": PASSES, "rc": rc,
            "seconds": round(time.time() - started), "input_dsn_sha256": sha256(INPUT), "prep": prep,
            "session_d_sha256": sha256(ar6.SES), "session_sha256": sha256(SES) if SES.is_file() else None,
            "log_tail": [line[:220] for line in lines if re.search(r"pass|unrouted|stage|completed|error|exception|warn",
                                                                    line, re.I)][-40:]}
    LOG.write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in ("rc", "seconds", "session_sha256")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
