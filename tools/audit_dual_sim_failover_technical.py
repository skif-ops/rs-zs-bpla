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
    bridge_source = (ROOT / "firmware/src/zs_dual_sim_bg95.c").read_text(
        encoding="utf-8"
    )
    bridge_test = (ROOT / "firmware/tests/test_dual_sim_bg95.c").read_text(
        encoding="utf-8"
    )
    gpio_source = (
        ROOT / "firmware/targets/evt_pre_20/src/evt_pre_20_dual_sim_gpio.c"
    ).read_text(encoding="utf-8")
    board = (
        ROOT / "firmware/targets/evt_pre_20/include/evt_pre_20_board_pins.h"
    ).read_text(encoding="utf-8")
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
    for pin_id in (
        "CELL_PWRKEY_CMD", "CELL_STATUS", "SIM_MUX_SEL", "SIM_MUX_EN",
        "SIM1_DET", "SIM2_DET", "PWR_GOOD", "EN_MODEM",
    ):
        require(f"EVT_PRE_20_PIN_{pin_id}" in board,
                f"generated named target pin missing: {pin_id}")
    require(gpio_source.index("EVT_PRE_20_PIN_CELL_STATUS, false") <
            gpio_source.index("EVT_PRE_20_PIN_SIM_MUX_EN, false") <
            gpio_source.index("EVT_PRE_20_PIN_EN_MODEM, false"),
            "target adapter could remove rail before modem-off/mux-off checks")
    require("graceful_shutdown_unavailable" in gpio_source and
            "EVT_PRE_20_PWRKEY_FALLBACK_PULSE_MS" in gpio_source,
            "target fallback is not gated after graceful shutdown")
    require("EVT_PRE_20_DUAL_SIM_IO_COMPLETE_LOGICAL" in gpio_source and
            "EVT_PRE_20_DUAL_SIM_IO_COMPLETE_PHYSICAL" in gpio_source,
            "logical versus physical U13 evidence boundary is missing")
    require("zs_dual_sim_pending_profile" in bridge_source and
            "zs_bg95_selected_apn_profile" in bridge_source and
            "selected_profile != pending_profile" in bridge_source,
            "BG95 selected profile is not bound to pending dual-SIM profile")
    mismatch_check = bridge_test.index(
        "!zs_dual_sim_bg95_confirm_link(&controller, &modem, 763u)"
    )
    corrected_profile = bridge_test.index("modem.selected_apn_profile = 0u")
    accepted_link = bridge_test.index(
        "zs_dual_sim_bg95_confirm_link(&controller, &modem, 763u)",
        corrected_profile,
    )
    require(mismatch_check < corrected_profile < accepted_link,
            "profile mismatch fail-closed runtime scenario is missing")

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
        (
            "evt_pre_20_dual_sim_gpio_qg2",
            (
                "firmware/src/zs_dual_sim.c",
                "firmware/targets/evt_pre_20/src/evt_pre_20_dual_sim_gpio.c",
                "firmware/tests/test_evt_pre_20_dual_sim_gpio.c",
            ),
            "EVT-PRE-20 dual-SIM GPIO binding tests passed",
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
                    f"-I{ROOT / 'firmware/targets/evt_pre_20/include'}",
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
