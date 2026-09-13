#!/usr/bin/env python3
"""QG-2 independent technical audit of portable dual-SIM failover."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def macro(header: str, name: str) -> int:
    match = re.search(rf"^#define {re.escape(name)} (\d+)u$", header, re.MULTILINE)
    require(match is not None, f"missing numeric policy macro {name}")
    return int(match.group(1))


def main() -> int:
    header = (ROOT / "firmware/include/zs_dual_sim.h").read_text(encoding="utf-8")
    source = (ROOT / "firmware/src/zs_dual_sim.c").read_text(encoding="utf-8")
    test = (ROOT / "firmware/tests/test_dual_sim.c").read_text(encoding="utf-8")
    target = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(
        encoding="utf-8"
    )

    require(macro(header, "ZS_DUAL_SIM_SLOT_COUNT") == 2, "slot count drift")
    require(macro(header, "ZS_DUAL_SIM_DEBOUNCE_MS") == 20, "DET debounce drift")
    require(macro(header, "ZS_DUAL_SIM_MIN_HOLD_MS") == 900_000,
            "minimum hold drift")
    require(macro(header, "ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE") == 3,
            "attempt bound drift")
    require(macro(header, "ZS_DUAL_SIM_POWER_GOOD_STABLE_MS") == 30,
            "power-good stability drift")

    switch_prefix = test[test.index("static void drive_safe_switch_prefix"):]
    ordered_actions = (
        "ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT",
        "ZS_DUAL_SIM_ACTION_STOP_NEW_TRAFFIC",
        "ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION",
        "ZS_DUAL_SIM_ACTION_CLOSE_TRANSPORT_AND_DETACH",
        "ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF",
        "ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF",
        "ZS_DUAL_SIM_ACTION_DISABLE_MUX",
        "ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z",
        "ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL",
    )
    offsets = [switch_prefix.index(action) for action in ordered_actions]
    require(offsets == sorted(offsets), "safe shutdown action order drift")
    recovery = test[test.index("static uint32_t drive_safe_recovery"):]
    recovery_actions = (
        "ZS_DUAL_SIM_ACTION_REQUEST_MODEM_OFF_GRACEFUL_OR_FALLBACK_1000_MS",
        "ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF",
        "ZS_DUAL_SIM_ACTION_DISABLE_MUX",
        "ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z",
        "ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL",
    )
    recovery_offsets = [recovery.index(action) for action in recovery_actions]
    require(recovery_offsets == sorted(recovery_offsets),
            "failure recovery could remove rail before modem-off and mux High-Z")
    require(source.index("ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z") <
            source.index("ZS_DUAL_SIM_ACTION_DISABLE_MODEM_RAIL") <
            source.index("ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT"),
            "source no longer represents High-Z/rail-off before slot select")
    require("physical_sim_operator_and_24h_evidence: DEFERRED_UNTIL_STATIONS_ASSEMBLED" in target,
            "assembled-station evidence boundary drift")
    require("dual_sim_gpio_power_binding:" in target and
            "BLOCKER" in next(line for line in target.splitlines()
                              if "dual_sim_gpio_power_binding:" in line),
            "target GPIO/power binding is not retained as blocker")

    compiler = shutil.which("cc") or shutil.which("gcc")
    require(compiler is not None, "host C compiler is unavailable")
    test_sets = (
        (
            "dual_sim_qg2",
            ("firmware/src/zs_dual_sim.c", "firmware/tests/test_dual_sim.c"),
            "dual-SIM safe failover tests passed",
        ),
        (
            "dual_sim_bg95_qg2",
            (
                "firmware/src/zs_dual_sim.c",
                "firmware/src/zs_bg95.c",
                "firmware/src/zs_dual_sim_bg95.c",
                "firmware/tests/test_dual_sim_bg95.c",
            ),
            "dual-SIM BG95 bridge tests passed",
        ),
    )
    with tempfile.TemporaryDirectory(prefix="zs-dual-sim-qg2-") as directory:
        for test_name, sources, success_text in test_sets:
            binary = Path(directory) / test_name
            compile_result = subprocess.run(
                [
                    compiler,
                    "-std=c11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                    "-O2", "-UNDEBUG", f"-I{ROOT / 'firmware/include'}",
                    *(str(ROOT / source_name) for source_name in sources),
                    "-o", str(binary),
                ],
                check=False, capture_output=True, text=True, cwd=ROOT,
            )
            require(compile_result.returncode == 0,
                    f"strict {test_name} compile failed: {compile_result.stderr}")
            run_result = subprocess.run(
                [str(binary)], check=False, capture_output=True, text=True, cwd=ROOT
            )
            require(run_result.returncode == 0,
                    f"{test_name} runtime failed: {run_result.stderr}")
            require(success_text in run_result.stdout,
                    f"{test_name} runtime did not report PASS")

    print("Dual-SIM safe failover QG-2 independent technical audit: PASS")
    print("fixed bounds, non-skippable fault recovery, safe action order, BG95 bridge and strict C runtimes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
