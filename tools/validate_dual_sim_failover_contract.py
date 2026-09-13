#!/usr/bin/env python3
"""QG-1 completeness and traceability for portable dual-SIM failover."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    header = read("firmware/include/zs_dual_sim.h")
    source = read("firmware/src/zs_dual_sim.c")
    test = read("firmware/tests/test_dual_sim.c")
    bridge_header = read("firmware/include/zs_dual_sim_bg95.h")
    bridge_source = read("firmware/src/zs_dual_sim_bg95.c")
    bridge_test = read("firmware/tests/test_dual_sim_bg95.c")
    cmake = read("firmware/CMakeLists.txt")
    policy = read("config/cellular/dual_sim_apn_profiles.yaml")
    baseline = read("config/EVT_PRE_20_BASELINE.yaml")
    hardware = read("hardware/DUAL_SIM_SINGLE_STANDBY.md")
    contract = read("firmware/DUAL_SIM_FAILOVER_CONTRACT_REV_A.md")
    target = read("firmware/targets/evt_pre_20/target_status.yaml")
    decisions = read("docs/DECISION_LOG.csv")
    ci = read(".github/workflows/ci.yml")

    for token in (
        "ZS_DUAL_SIM_DEBOUNCE_MS 20u",
        "ZS_DUAL_SIM_MIN_HOLD_MS 900000u",
        "ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE 3u",
        "ZS_DUAL_SIM_POWER_GOOD_STABLE_MS 30u",
        "ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF",
        "ZS_DUAL_SIM_ACTION_RECORD_SWITCH_INTENT",
        "ZS_DUAL_SIM_ACTION_PERSIST_QUEUE_AND_SESSION",
        "ZS_DUAL_SIM_ACTION_VERIFY_MODEM_OFF",
        "ZS_DUAL_SIM_ACTION_VERIFY_MUX_HIGH_Z",
        "ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT",
        "ZS_DUAL_SIM_ACTION_VERIFY_POWER_GOOD_30_MS",
        "ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS",
        "ZS_DUAL_SIM_ACTION_READ_AND_VERIFY_ICCID",
        "ZS_DUAL_SIM_ACTION_ATTACH_VALIDATE_DNS_TLS",
        "ZS_DUAL_SIM_ACTION_RECORD_SWITCH_COMMIT",
        "ZS_DUAL_SIM_ACTION_RESUME_PRESERVED_QUEUE",
        "zs_dual_sim_request_manual_switch",
        "zs_dual_sim_report_failure",
        "zs_dual_sim_complete_action",
        "zs_dual_sim_on_iccid",
        "zs_dual_sim_report_brownout",
    ):
        require(token in header, f"dual-SIM interface missing {token}")

    for guard in (
        "valid_iccid",
        "stable_present",
        "ZS_DUAL_SIM_REQUEST_REJECTED_AUTH",
        "ZS_DUAL_SIM_REQUEST_REJECTED_HOLD",
        "ZS_DUAL_SIM_MAX_ATTEMPTS_PER_PROFILE",
        "action != zs_dual_sim_next_action(controller)",
        "strcmp(full_iccid",
        "need_safe_off(controller)",
        "now_ms - controller->last_activation_ms",
        "now_ms - controller->modem_rail_enabled_ms",
    ):
        require(guard in source, f"dual-SIM fail-closed guard missing {guard}")
    require("printf" not in source and "puts" not in source,
            "portable controller must not log provisioned or observed identity")

    for bridge_token in (
        "zs_dual_sim_bg95_begin_graceful_shutdown",
        "zs_dual_sim_bg95_confirm_shutdown",
        "zs_dual_sim_bg95_begin_power_on",
        "zs_dual_sim_bg95_confirm_modem_on",
        "zs_dual_sim_bg95_verify_iccid",
        "zs_dual_sim_bg95_confirm_link",
    ):
        require(bridge_token in bridge_header and bridge_token in bridge_source,
                f"dual-SIM/BG95 bridge missing {bridge_token}")
    for bridge_guard in (
        "ZS_DUAL_SIM_ACTION_GRACEFUL_MODEM_OFF",
        "ZS_BG95_SHUTDOWN_STARTED",
        "cell_status_low",
        "ZS_DUAL_SIM_ACTION_PULSE_PWRKEY_700_MS",
        "full_iccid_available",
        "zs_bg95_online",
        "settings->primary_dns[0]",
    ):
        require(bridge_guard in bridge_source,
                f"dual-SIM/BG95 bridge guard missing {bridge_guard}")
    require("printf" not in bridge_source and "puts" not in bridge_source,
            "dual-SIM/BG95 bridge must not log SIM identity")

    for evidence in (
        "test_boot_and_bounded_automatic_failover",
        "test_auth_presence_and_configuration_guards",
        "test_iccid_mismatch_and_action_failure_fail_closed",
        "test_brownout_and_debounced_active_slot_removal",
        "ZS_DUAL_SIM_REQUEST_RETRY_CURRENT",
        "ZS_DUAL_SIM_REQUEST_REJECTED_AUTH",
        "ZS_DUAL_SIM_REQUEST_REJECTED_HOLD",
        "ZS_DUAL_SIM_REQUEST_REJECTED_PRESENCE",
        "ZS_DUAL_SIM_REQUEST_REJECTED_TRIGGER",
        "ZS_DUAL_SIM_ACTION_SELECT_PENDING_SLOT",
        "ZS_DUAL_SIM_ACTION_APPLY_SAFE_OFF",
        "SLOT1_ICCID",
        "SLOT2_ICCID",
    ):
        require(evidence in test, f"dual-SIM runtime scenario missing {evidence}")
    require("src/zs_dual_sim.c" in cmake and
            "src/zs_dual_sim_bg95.c" in cmake and
            "zs_dual_sim_tests" in cmake and
            "zs_dual_sim_bg95_tests" in cmake and
            "add_test(NAME dual_sim" in cmake and
            "add_test(NAME dual_sim_bg95" in cmake and
            "-UNDEBUG" in cmake,
            "dual-SIM test is not bound to strict CMake/CTest")
    for evidence in (
        "test_power_identity_link_and_shutdown_bridge",
        "AT+QPOWD\\r\\n",
        "zs_dual_sim_bg95_verify_iccid",
        "zs_dual_sim_bg95_confirm_link",
        "zs_dual_sim_bg95_confirm_shutdown",
    ):
        require(evidence in bridge_test,
                f"dual-SIM/BG95 integration scenario missing {evidence}")

    for policy_token in (
        "mode: dual_sim_single_standby",
        "simultaneously_active_slots: 1",
        "hot_switch_allowed: false",
        "automatic_failover_enabled: true",
        "minimum_hold_time_s: 900",
        "maximum_attempts_per_profile: 3",
        "preserve_store_and_forward_queue: true",
        "authenticated_BLE_or_mTLS_server_command",
        "expected_iccid_per_slot: PROVISIONED_FULL_VALUE_REQUIRED",
        "FULL_IMSI_AND_ICCID_REQUIRED_IN_MTLS_HEARTBEAT",
        "DEFERRED_UNTIL_STATIONS_ASSEMBLED",
    ):
        require(policy_token in policy, f"dual-SIM policy drift: {policy_token}")
    require("firmware_status: PORTABLE_SAFE_SEQUENCE_BG95_BRIDGE_QG1_QG2_PASS_TARGET_PENDING" in policy,
            "portable failover status missing from controlled policy")
    require("dual_sim_failover_firmware: PORTABLE_SAFE_SEQUENCE_BG95_POWER_IDENTITY_LINK_BRIDGE_QG1_QG2_PASS_TARGET_GPIO_POWER_PROFILE_BINDING_PENDING" in baseline,
            "portable failover status missing from EVT baseline")
    require("firmware debounce не менее 20 ms" in hardware and
            "Переключение без полного штатного выключения модема является ошибкой" in hardware,
            "hardware safe-switch authority drift")
    require("PORTABLE POLICY AND SAFE-SEQUENCE QG-1/QG-2 PASS" in contract and
            "TARGET GPIO" in contract and "100" in contract and
            "24-hour" in contract,
            "dual-SIM contract overclaims or omits target evidence")
    require("dual_sim_failover_controller: PORTABLE_SAFE_SEQUENCE_HOLD_RETRY_ICCID_QG1_QG2_PASS_TARGET_PENDING" in target and
            "dual_sim_gpio_power_binding:" in target,
            "target boundary for dual-SIM failover is not explicit")
    require("DEC-031" in decisions and
            "IMPLEMENTED_HOST_TARGET_BINDING_PENDING" in decisions,
            "dual-SIM portable implementation decision is not recorded")
    require("validate_dual_sim_failover_contract.py" in ci and
            "audit_dual_sim_failover_technical.py" in ci,
            "dual-SIM double control is not bound to CI")

    print("Dual-SIM safe failover QG-1 PASS")
    print("portable policy/order/identity traceability verified; target and assembled-station evidence OPEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
