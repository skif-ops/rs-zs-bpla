#!/usr/bin/env python3
"""Check immutable historical routing generators against their archived board.

The accepted 006 application changes the authoritative board. Older generators
remain hash-bound review evidence, so redirect only their in-memory source
when replaying --check; do not edit the reviewed generator or archived files.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

from pcb_pwr_hot_loop_006_board import PREDECESSOR, ROOT, is_exact_application


ALLOWED = {
    "generate_pcb_pwr_buck_placement_eco_001_candidate_rev_a",
    "generate_pcb_pwr_buck_bootstrap_routing_001_candidate_rev_a",
    "generate_pcb_pwr_buck_bootstrap_routing_001_application_rev_a",
    "generate_pcb_pwr_lm74700_vcap_routing_002_candidate_rev_a",
    "generate_pcb_pwr_lm74700_vcap_routing_002_application_rev_a",
    "generate_pcb_pwr_vbat_raw_routing_003_candidate_rev_a",
    "generate_pcb_pwr_vbat_raw_routing_003_application_rev_a",
    "generate_pcb_pwr_rev_gate_routing_004_candidate_rev_a",
    "generate_pcb_pwr_rev_gate_routing_004_application_rev_a",
    "generate_pcb_pwr_buck_switch_node_routing_005_candidate_rev_a",
    "generate_pcb_pwr_buck_input_hot_loop_routing_006_candidate_rev_a",
    "generate_pcb_pwr_buck_power_stage_eco_002_candidate_rev_a",
    "generate_pcb_pwr_buck_power_stage_eco_002_application_rev_a",
}
ACTIVE = ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb"
PREDECESSOR_SHA = "44bbcd77bc3245f5f403361559167ed1fcf5cb5c130806bcc5db97613bb0e77c"


def main() -> int:
    assert len(sys.argv) >= 3 and sys.argv[1].endswith(".py")
    module_name = Path(sys.argv[1]).stem
    assert module_name in ALLOWED, "unreviewed historical generator"
    args = sys.argv[2:]
    if "--check" not in args:
        assert module_name == "generate_pcb_pwr_buck_placement_eco_001_candidate_rev_a"
        assert "--base-output" in args and "--output" in args
        for flag in ("--base-output", "--output"):
            dest = Path(args[args.index(flag) + 1]).resolve()
            assert not dest.is_relative_to(ROOT), "historical regeneration must use temporary outputs"
    assert is_exact_application(ACTIVE), "authoritative 006 board identity drift"
    assert hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest() == PREDECESSOR_SHA
    module = importlib.import_module(module_name)
    if getattr(module, "SOURCE", None) == ACTIVE:
        module.SOURCE = PREDECESSOR
    if getattr(module, "BOARD", None) == ACTIVE:
        module.BOARD = PREDECESSOR
    sys.argv = [str(ROOT / "tools" / (module_name + ".py")), *args]
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
