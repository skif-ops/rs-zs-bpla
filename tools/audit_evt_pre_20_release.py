#!/usr/bin/env python3
"""Second-pass EVT-PRE-20 release completeness audit.

Default mode reports blockers without failing CI. Use --strict for the actual release gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_GROUPS: dict[str, list[str]] = {
    "configuration": [
        "config/EVT_PRE_20_BASELINE.yaml",
        "docs/DELIVERABLE_REGISTER_EVT_PRE_20.csv",
        "docs/REQUIREMENTS_TRACEABILITY.csv",
        "docs/RISK_REGISTER.csv",
        "docs/DECISION_LOG.csv",
        "docs/OPEN_INPUTS_FOR_FREEZE.csv",
        "manufacturing/EVT_LOT_SELECTION_REV_A.csv",
        "manufacturing/EVT_LOT_SELECTION_REV_A.md",
    ],
    "pcb_source": [
        "hardware/EVT_PRE_20_BOM_REV_A.csv",
        "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
        "hardware/EVT_PRE_20_BOM_REV_A.xlsx",
        "hardware/EVT_PRE_20_BOM_POLICY_REV_A.md",
        "hardware/EVT_PRE_20_BOM_EVIDENCE_REV_A.md",
        "hardware/HARDWARE_PRODUCTION_RELEASE_GATE_REV_A.md",
        "hardware/reviews/FABRICATOR_PUBLIC_CAPABILITY_SCREEN_REV_A.md",
        "manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.json",
        "manufacturing/EVT_PRE_20_EXTERNAL_RESPONSE_BUNDLE_REV_A.md",
        "hardware/CHINA_PROCUREMENT_RFQ.csv",
        "hardware/kicad/README.md",
        "hardware/kicad/REV_A_CAPTURE_SPEC.md",
        "hardware/kicad/REV_A_CAPTURE_ADDENDUM_001_ENV_MIC.md",
        "hardware/ENVIRONMENT_REV_A.md",
        "hardware/T5838_AAD_INTERFACE_REV_A.md",
        "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
        "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv",
        "hardware/POWER_COMPONENT_FREEZE_REV_A.csv",
        "hardware/CONNECTOR_FREEZE_REV_A.csv",
        "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv",
        "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.md",
        "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv",
        "hardware/HARNESS_MANUFACTURING_DRAWING_REV_A.md",
        "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.json",
        "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.md",
        "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv",
        "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv",
        "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md",
        "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
        "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md",
        "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv",
        "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md",
        "hardware/PCB_MAIN_IPC_CANDIDATE_FOOTPRINTS_REV_A.md",
        "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json",
        "hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md",
        "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json",
        "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.md",
        "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv",
        "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json",
        "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.md",
        "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.json",
        "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.md",
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_CANDIDATE_REV_A.json",
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_CANDIDATE_REV_A.md",
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPROVAL_REV_A.json",
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPROVAL_REV_A.md",
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_REVIEW_COMMIT_MAPPING.json",
        "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPLICATION_REV_A.json",
        "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001/PCB-MAIN_RF_RETURN_BASE_REV_A.kicad_pcb",
        "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001/PCB-MAIN_RF_RETURN_CANDIDATE_REV_A.kicad_pcb",
        "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.json",
        "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.md",
        "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPROVAL_REV_A.json",
        "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPROVAL_REV_A.md",
        "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_REVIEW_COMMIT_MAPPING.json",
        "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPLICATION_REV_A.json",
        "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001/PCB-MAIN_GNSS_RF_ECO_001_BASE_REV_A.kicad_pcb",
        "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001/PCB-MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.kicad_pcb",
        "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb",
        "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_002_REV_A.json",
        "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_002_REV_A.md",
        "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json",
        "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.md",
        "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv",
        "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json",
        "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json",
        "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.md",
        "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv",
        "hardware/PCB_PWR_PASSIVE_AUTHORITY_REV_A.csv",
        "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.csv",
        "hardware/PCB_PWR_PLACEMENT_CANDIDATE_REV_A.md",
        "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv",
        "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.md",
        "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv",
        "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json",
        "hardware/PCB_PWR_REVIEW_A_PIN_NET_REV_A.md",
        "hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md",
        "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json",
        "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.md",
        "hardware/reviews/PCB_PWR_DIM_003_RESPONSE_REV_A.csv",
        "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json",
        "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md",
        "hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv",
        "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json",
        "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.md",
        "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md",
        "hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.json",
        "hardware/reviews/PCB_PWR_TI_PRIMARY_SOURCE_EVIDENCE_REV_A.md",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_QUALIFICATION_REV_A.json",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_QUALIFICATION_REV_A.md",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_TEST_MATRIX_REV_A.csv",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.json",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PRIMARY_SOURCE_EVIDENCE_REV_A.md",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.json",
        "hardware/reviews/PCB_PWR_INPUT_PROTECTION_PROCUREMENT_IDENTITY_REV_A.md",
        "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.json",
        "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.md",
        "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_sch",
        "hardware/kicad/native/PCB-PWR/PCB-PWR_01_INPUT_PROTECTION.kicad_sch",
        "hardware/kicad/native/PCB-PWR/PCB-PWR_02_3V8_MODEM.kicad_sch",
        "hardware/kicad/native/PCB-PWR/PCB-PWR_03_3V3_DIGITAL.kicad_sch",
        "hardware/kicad/native/PCB-PWR/PCB-PWR_04_AUX_HARNESS.kicad_sch",
        "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb",
        "hardware/PCB_DOUBLE_REVIEW_GATE.md",
        "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv",
        "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
        "tools/generate_evt_pre_20_bom_rev_a.py",
        "tools/validate_evt_pre_20_bom_qg1.py",
        "tools/audit_evt_pre_20_bom_qg2.py",
        "tools/audit_evt_pre_20_bom_workbook.py",
        "tools/audit_evt_pre_20_hardware_release.py",
        "tools/audit_evt_pre_20_external_response_bundle.py",
        "tools/build_evt_pre_20_packages.py",
        "tools/audit_evt_system_ots_procurement_identity_rev_a.py",
        "tools/audit_pcb_layer_count_authority_rev_a.py",
        "tools/audit_harness_manufacturing_rev_a.py",
        "tools/audit_pcb_mic_native_schematic_rev_a.py",
        "tools/audit_pcb_mic_manufacturing_handoff_rev_a.py",
        "tools/audit_pcb_main_capture_authority_rev_a.py",
        "tools/audit_pcb_main_placement_clearance_rev_a.py",
        "tools/generate_pcb_main_routing_authority_rev_a.py",
        "tools/audit_pcb_main_routing_authority_rev_a.py",
        "tools/audit_pcb_main_stackup_impedance_request_rev_a.py",
        "tools/audit_pcb_main_jlc06161h_3313_routing_basis_rev_a.py",
        "tools/generate_pcb_main_rf_return_001_candidate_rev_a.py",
        "tools/audit_pcb_main_rf_return_001_candidate_rev_a.py",
        "tools/generate_pcb_main_gnss_rf_eco_001_candidate_rev_a.py",
        "tools/audit_pcb_main_gnss_rf_eco_001_candidate_rev_a.py",
        "tools/generate_pcb_main_rf_remediation_application_rev_a.py",
        "tools/audit_pcb_main_rf_remediation_application_rev_a.py",
        "tools/audit_pcb_main_assembler_dfm_stencil_request_rev_a.py",
        "tools/verify_pcb_main_passive_support_authority_rev_a.py",
        "tools/verify_pcb_main_mechanical_placement_authority_rev_a.py",
        "tools/generate_pcb_pwr_layout_candidate_rev_a.py",
        "tools/audit_pcb_pwr_design_rev_a.py",
        "tools/audit_pcb_pwr_layout_candidate_rev_a.py",
        "tools/audit_pcb_pwr_native_schematic_rev_a.py",
        "tools/audit_pcb_pwr_native_completeness_rev_a.py",
        "tools/audit_pcb_pwr_passive_authority_rev_a.py",
        "tools/materialize_pcb_pwr_hierarchy_rev_a.py",
        "tools/pcb_pwr_schematic_hierarchy.py",
        "tools/audit_pcb_pwr_hierarchy_rev_a.py",
        "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        "tools/generate_pcb_pwr_routing_authority_rev_a.py",
        "tools/audit_pcb_pwr_routing_authority_rev_a.py",
        "tools/generate_pcb_pwr_evt_route_rules_rev_a.py",
        "tools/audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py",
        "tools/audit_pcb_pwr_dim_003_request_rev_a.py",
        "tools/audit_pcb_pwr_stackup_copper_request_rev_a.py",
        "tools/audit_pcb_pwr_input_protection_sources_rev_a.py",
        "tools/audit_pcb_pwr_input_protection_procurement_identity_rev_a.py",
        "tools/audit_pcb_pwr_input_protection_rev_a.py",
    ],
    "firmware_source": [
        "firmware/CMakeLists.txt",
        "firmware/BG95_MQTT_TLS_CONTRACT_REV_A.md",
        "firmware/DUAL_SIM_FAILOVER_CONTRACT_REV_A.md",
        "firmware/include/zs_bg95.h",
        "firmware/include/zs_dual_sim.h",
        "firmware/include/zs_dual_sim_bg95.h",
        "firmware/include/zs_bg95_command_transport.h",
        "firmware/include/zs_bg95_event_receipt.h",
        "firmware/include/zs_bg95_event_uplink.h",
        "firmware/include/zs_bg95_mqtt_binary.h",
        "firmware/include/zs_bg95_mqtt_session.h",
        "firmware/include/zs_command.h",
        "firmware/include/zs_command_channel.h",
        "firmware/include/zs_command_journal.h",
        "firmware/include/zs_command_trust.h",
        "firmware/include/zs_event_outbox.h",
        "firmware/include/zs_event_receipt.h",
        "firmware/include/zs_mqtt_event_transport.h",
        "firmware/include/zs_nor_command_journal.h",
        "firmware/include/zs_nor_event_outbox.h",
        "firmware/include/zs_nor_storage_layout.h",
        "firmware/src/zs_bg95.c",
        "firmware/src/zs_dual_sim.c",
        "firmware/src/zs_dual_sim_bg95.c",
        "firmware/src/zs_bg95_command_transport.c",
        "firmware/src/zs_bg95_event_receipt.c",
        "firmware/src/zs_bg95_event_uplink.c",
        "firmware/src/zs_bg95_mqtt_binary.c",
        "firmware/src/zs_bg95_mqtt_session.c",
        "firmware/src/zs_command.c",
        "firmware/src/zs_command_channel.c",
        "firmware/src/zs_command_journal.c",
        "firmware/src/zs_command_trust.c",
        "firmware/src/zs_event_outbox.c",
        "firmware/src/zs_event_receipt.c",
        "firmware/src/zs_mqtt_event_transport.c",
        "firmware/src/zs_nor_command_journal.c",
        "firmware/src/zs_nor_event_outbox.c",
        "firmware/src/zs_nor_storage_layout.c",
        "firmware/tests/test_bg95_transport.c",
        "firmware/tests/test_dual_sim.c",
        "firmware/tests/test_dual_sim_bg95.c",
        "firmware/tests/test_bg95_command_transport.c",
        "firmware/tests/test_bg95_mqtt_session.c",
        "firmware/tests/test_bg95_event_receipt.c",
        "firmware/tests/test_bg95_event_uplink.c",
        "firmware/tests/test_command_transport.c",
        "firmware/tests/test_command_channel.c",
        "firmware/tests/test_command_journal.c",
        "firmware/tests/test_command_trust.c",
        "firmware/tests/test_event_outbox.c",
        "firmware/tests/test_event_receipt.c",
        "firmware/tests/test_mqtt_event_transport.c",
        "firmware/tests/test_nor_command_journal.c",
        "firmware/tests/test_nor_event_outbox.c",
        "firmware/tests/test_nor_storage_layout.c",
        "firmware/generated/zs_command_vector.h",
        "firmware/generated/zs_event_receipt_vector.h",
        "firmware/targets/evt_pre_20/CMakeLists.txt",
        "firmware/targets/evt_pre_20/README.md",
        "firmware/targets/evt_pre_20/target_status.yaml",
        "firmware/targets/evt_pre_20/target_contract_manifest.json",
        "firmware/targets/evt_pre_20/include/evt_pre_20_board_pins.h",
        "firmware/targets/evt_pre_20/include/evt_pre_20_clock_policy.h",
        "firmware/targets/evt_pre_20/cubemx_generation_contract.json",
        "firmware/targets/evt_pre_20/dioneya_evt_pre_20_rev_a.ioc",
        "firmware/targets/evt_pre_20/stm32_memory_contract.json",
        "firmware/targets/evt_pre_20/stm32_scaffold_manifest.json",
        "firmware/targets/evt_pre_20/ld/STM32U585VITXQ_ENGINEERING_FLASH.ld",
        "firmware/targets/evt_pre_20/vendor/stm32cubeu5.lock.json",
        "firmware/targets/evt_pre_20/vendor/stm32cubemx_db.lock.json",
        "firmware/targets/evt_pre_20/vendor/cmsis_device_u5/LICENSE.md",
        "firmware/targets/evt_pre_20/vendor/cmsis_device_u5/startup_stm32u585xx.s",
        "firmware/targets/evt_pre_20/vendor/cmsis_device_u5/system_stm32u5xx.c",
        "firmware/tests/test_evt_pre_20_target_contract.c",
        "tools/import_evt_pre_20_stm32_vendor.py",
        "tools/generate_evt_pre_20_target_contract.py",
        "tools/validate_evt_pre_20_target_contract.py",
        "tools/audit_evt_pre_20_target_technical.py",
        "tools/validate_evt_pre_20_cubemx_ioc.py",
        "tools/audit_evt_pre_20_cubemx_ioc_technical.py",
        "tools/validate_evt_pre_20_stm32_scaffold.py",
        "tools/audit_evt_pre_20_stm32_scaffold_technical.py",
        "tools/validate_bg95_transport_contract_rev_a.py",
        "tools/validate_dual_sim_failover_contract.py",
        "tools/audit_dual_sim_failover_technical.py",
        "tools/validate_event_outbox_contract.py",
        "tools/validate_event_receipt_contract.py",
    ],
    "android_source": [
        "android/app/build.gradle.kts",
        "android/app/src/main/AndroidManifest.xml",
    ],
    "server_windows_ubuntu": [
        "server/requirements.lock.txt",
        "server/requirements-ci.lock.txt",
        "server/requirements-protocol.lock.txt",
        "server/sbom/server.cdx.json",
        "server/.dockerignore",
        "server/station/http_transport.py",
        "server/station/command_codec.py",
        "server/station/event_receipt_codec.py",
        "server/deploy/compose.windows.yml",
        "server/deploy/compose.windows.tls.yml",
        "server/deploy/compose.ubuntu.yml",
        "server/deploy/mosquitto/station_acl.conf",
        "server/deploy/scripts/start_windows.ps1",
        "server/deploy/scripts/start_ubuntu.sh",
        "tools/generate_command_signing_key.py",
        "tools/generate_mqtt_command_vector.py",
        "tools/generate_server_sbom.py",
        "tools/validate_server_supply_chain.py",
        "tools/audit_server_sbom_technical.py",
        "tools/validate_station_http_transport.py",
        "tools/audit_station_http_transport_technical.py",
        "tools/validate_mqtt_command_transport.py",
        "tools/audit_mqtt_command_transport_technical.py",
        "tools/generate_event_receipt_vector.py",
        "tools/audit_event_receipt_technical.py",
    ],
    "mechanics_source": [
        "mechanics/common/ACOUSTIC_GEOMETRY.csv",
        "mechanics/common/OPEN_DIMENSIONS.csv",
        "mechanics/3d_print/DESIGN_RULES.md",
        "mechanics/vacuum_casting/DESIGN_RULES.md",
        "mechanics/injection_molding/DESIGN_RULES.md",
    ],
    "evt_methods": [
        "tests/EVT_MASTER_PLAN.md",
        "tests/EVT_MATRIX.csv",
        "tests/DEVIATION_LOG.csv",
        "manufacturing/EOL_TEST_SPEC.md",
        "manufacturing/EOL_RESULT_REGISTER.csv",
    ],
}

STRICT_PRODUCTION_PATTERNS: dict[str, list[str]] = {
    "pcb_main_native": [
        "hardware/kicad/pcb_main/*.kicad_sch",
        "hardware/kicad/pcb_main/*.kicad_pcb",
        "hardware/kicad/pcb_main/gerber/*",
        "hardware/kicad/pcb_main/*bom*.csv",
        "hardware/kicad/pcb_main/*pos*.csv",
    ],
    "pcb_mic_native": [
        "hardware/kicad/pcb_mic/*.kicad_sch",
        "hardware/kicad/pcb_mic/*.kicad_pcb",
        "hardware/kicad/pcb_mic/gerber/*",
    ],
    "pcb_pwr_native": [
        "hardware/kicad/pcb_pwr/*.kicad_sch",
        "hardware/kicad/pcb_pwr/*.kicad_pcb",
        "hardware/kicad/pcb_pwr/gerber/*",
    ],
    "firmware_target": [
        "firmware/targets/evt_pre_20/output/*.elf",
        "firmware/targets/evt_pre_20/output/*.map",
        "firmware/targets/evt_pre_20/output/*.bin",
        "firmware/targets/evt_pre_20/output/*.hex",
        "firmware/targets/evt_pre_20/output/SHA256SUMS.txt",
    ],
    "android_apk": [
        "android/release/*.apk",
        "android/release/SHA256SUMS.txt",
    ],
    "mechanics_3d": [
        "mechanics/3d_print/*.step",
        "mechanics/3d_print/*.stl",
        "mechanics/3d_print/*.3mf",
        "mechanics/vacuum_casting/*.step",
        "mechanics/injection_molding/*.step",
    ],
    "release_docs": [
        "releases/evt-pre-20/*.zip",
        "releases/evt-pre-20/SHA256SUMS.txt",
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit() -> dict[str, object]:
    groups: dict[str, object] = {}
    blockers: list[str] = []

    for group, names in REQUIRED_GROUPS.items():
        missing = [name for name in names if not (ROOT / name).is_file()]
        groups[group] = {"required": names, "missing": missing, "pass": not missing}
        blockers.extend(f"missing required source: {name}" for name in missing)

    production: dict[str, object] = {}
    for group, patterns in STRICT_PRODUCTION_PATTERNS.items():
        pattern_results = []
        group_pass = True
        for pattern in patterns:
            matches = sorted(str(path.relative_to(ROOT)) for path in ROOT.glob(pattern) if path.is_file())
            if not matches:
                group_pass = False
            pattern_results.append({"pattern": pattern, "matches": matches})
        production[group] = {"patterns": pattern_results, "pass": group_pass}
        if not group_pass:
            blockers.append(f"production output incomplete: {group}")

    target_status = (ROOT / "firmware/targets/evt_pre_20/target_status.yaml").read_text(encoding="utf-8")
    if "do_not_release: true" in target_status:
        blockers.append("firmware target explicitly marked do_not_release")
    if "TARGET_PORT_REQUIRED" in target_status:
        blockers.append("firmware STM32 target port is not complete")

    baseline = (ROOT / "config/EVT_PRE_20_BASELINE.yaml").read_text(encoding="utf-8")
    if "operating_ambient_c: [-40, 70]" not in baseline:
        blockers.append("environment operating range is not locked to -40..+70 C")
    if "electronic_component_minimum_rating_c: [-40, 85]" not in baseline:
        blockers.append("electronic component temperature derating rule missing")
    if "selected_evt_quantity: 20" not in baseline:
        blockers.append("locked current-customer EVT purchase quantity is not 20")

    bom = ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv"
    if bom.is_file():
        bom_text = bom.read_text(encoding="utf-8")
        for forbidden in ("ESP32-C3", "JST_BM05B", "GHR-05V-S", "5040500591", "5040510501"):
            if forbidden in bom_text:
                blockers.append(f"generated Rev.A BOM contains forbidden/superseded token: {forbidden}")
        for required in ("MDBT50Q-P1MV2", "5040500691", "SN74LVC32APWR", "SN74AXC1T45DRLR", "LMR604403SRAKR"):
            if required not in bom_text:
                blockers.append(f"generated Rev.A BOM missing locked item: {required}")
        if "AAD_CFG" not in bom_text:
            blockers.append("generated Rev.A BOM does not document THSEL/AAD_CFG on MIC connector")

    bom_qg2 = ROOT / "artifacts/evt_pre_20_bom_qg2.json"
    if bom_qg2.is_file():
        qg2 = json.loads(bom_qg2.read_text(encoding="utf-8"))
        if not qg2.get("production_bom_complete"):
            blockers.append("production BOM QG-2 remains BLOCKED; see artifacts/evt_pre_20_bom_qg2.json")
    else:
        blockers.append("production BOM QG-2 report is missing")

    addendum = ROOT / "hardware/kicad/REV_A_CAPTURE_ADDENDUM_001_ENV_MIC.md"
    if addendum.is_file():
        addendum_text = addendum.read_text(encoding="utf-8")
        if "5040500691" not in addendum_text or "5040510601" not in addendum_text or "AAD_CFG" not in addendum_text:
            blockers.append("capture addendum does not lock the 6-pin THSEL-capable MIC connector set")

    aad_doc = ROOT / "hardware/T5838_AAD_INTERFACE_REV_A.md"
    if aad_doc.is_file():
        aad_text = aad_doc.read_text(encoding="utf-8")
        for required in ("PA15", "THSEL", "PA8", "WAKE", "5040500691"):
            if required not in aad_text:
                blockers.append(f"T5838 AAD interface document missing: {required}")

    manifest_inputs = [
        ROOT / "config/EVT_PRE_20_BASELINE.yaml",
        ROOT / "docs/DECISION_LOG.csv",
        ROOT / "manufacturing/EVT_LOT_SELECTION_REV_A.csv",
        ROOT / "manufacturing/EVT_LOT_SELECTION_REV_A.md",
        ROOT / "hardware/ENVIRONMENT_REV_A.md",
        ROOT / "hardware/T5838_AAD_INTERFACE_REV_A.md",
        ROOT / "hardware/AAD_CFG_PIN_ADDENDUM_REV_A.csv",
        ROOT / "hardware/EVT_PRE_20_BOM_REV_A.csv",
        ROOT / "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv",
        ROOT / "hardware/EVT_PRE_20_BOM_REV_A.xlsx",
        ROOT / "hardware/EVT_PRE_20_BOM_POLICY_REV_A.md",
        ROOT / "hardware/EVT_PRE_20_BOM_EVIDENCE_REV_A.md",
        ROOT / "hardware/CHINA_PROCUREMENT_RFQ.csv",
        ROOT / "hardware/HARNESS_LOGICAL_PINOUT_REV_A.csv",
        ROOT / "hardware/HARNESS_MANUFACTURING_SCHEDULE_REV_A.csv",
        ROOT / "hardware/HARNESS_MANUFACTURING_DRAWING_REV_A.md",
        ROOT / "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.json",
        ROOT / "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_REQUEST_REV_A.md",
        ROOT / "hardware/reviews/HARNESS_SUPPLIER_CAPABILITY_RESPONSE_REV_A.csv",
        ROOT / "hardware/EVT_PRE_20_PIN_MAP_REV_A.csv",
        ROOT / "hardware/MAIN_COMPONENT_FREEZE_REV_A.csv",
        ROOT / "hardware/POWER_COMPONENT_FREEZE_REV_A.csv",
        ROOT / "hardware/CONNECTOR_FREEZE_REV_A.csv",
        ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.csv",
        ROOT / "hardware/PCB_LAYER_COUNT_AUTHORITY_REV_A.md",
        ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.csv",
        ROOT / "hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md",
        ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.csv",
        ROOT / "hardware/PCB_MAIN_MECHANICAL_PLACEMENT_AUTHORITY_REV_A.md",
        ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv",
        ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md",
        ROOT / "hardware/PCB_MAIN_IPC_CANDIDATE_FOOTPRINTS_REV_A.md",
        ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_PLACEMENT_CLEARANCE_ERRATA_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_REQUEST_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_STACKUP_IMPEDANCE_RESPONSE_REV_A.csv",
        ROOT / "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_JLC06161H_3313_ROUTING_BASIS_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_CANDIDATE_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_CANDIDATE_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPROVAL_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPROVAL_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_REVIEW_COMMIT_MAPPING.json",
        ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPLICATION_REV_A.json",
        ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001/PCB-MAIN_RF_RETURN_BASE_REV_A.kicad_pcb",
        ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-RETURN-001/PCB-MAIN_RF_RETURN_CANDIDATE_REV_A.kicad_pcb",
        ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPROVAL_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPROVAL_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_REVIEW_COMMIT_MAPPING.json",
        ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPLICATION_REV_A.json",
        ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001/PCB-MAIN_GNSS_RF_ECO_001_BASE_REV_A.kicad_pcb",
        ROOT / "hardware/kicad/candidates/PCB-MAIN-GNSS-RF-ECO-001/PCB-MAIN_GNSS_RF_ECO_001_CANDIDATE_REV_A.kicad_pcb",
        ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb",
        ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_002_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_RF_SI_RETURN_PATH_REVIEW_002_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.json",
        ROOT / "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_REQUEST_REV_A.md",
        ROOT / "hardware/reviews/PCB_MAIN_ASSEMBLER_DFM_STENCIL_RESPONSE_REV_A.csv",
        ROOT / "hardware/PCB_MIC_CAPTURE_STATUS_REV_A.json",
        ROOT / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.json",
        ROOT / "hardware/reviews/PCB_MIC_MANUFACTURING_HANDOFF_REV_A.md",
        ROOT / "hardware/reviews/PCB_MIC_DFM_RESPONSE_REV_A.csv",
        ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.csv",
        ROOT / "hardware/PCB_PWR_ROUTING_AUTHORITY_REV_A.md",
        ROOT / "hardware/PCB_PWR_EVT_ROUTE_RULES_REV_A.csv",
        ROOT / "hardware/PCB_PWR_CAPTURE_STATUS_REV_A.json",
        ROOT / "hardware/PCB_PWR_REVIEW_A_PIN_NET_REV_A.md",
        ROOT / "hardware/reviews/PCB_PWR_PLACEMENT_CLEARANCE_REV_A.md",
        ROOT / "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.json",
        ROOT / "hardware/reviews/PCB_PWR_DIM_003_REQUEST_REV_A.md",
        ROOT / "hardware/reviews/PCB_PWR_DIM_003_RESPONSE_REV_A.csv",
        ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.json",
        ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_REQUEST_REV_A.md",
        ROOT / "hardware/reviews/PCB_PWR_STACKUP_COPPER_RESPONSE_REV_A.csv",
        ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.json",
        ROOT / "hardware/reviews/PCB_PWR_JLC04161H_3313_EVT_ROUTING_BASIS_REV_A.md",
        ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_CHECKLIST_REV_A.md",
        ROOT / "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.json",
        ROOT / "hardware/reviews/EVT_SYSTEM_OTS_PROCUREMENT_IDENTITY_REV_A.md",
        ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_sch",
        ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR_01_INPUT_PROTECTION.kicad_sch",
        ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR_02_3V8_MODEM.kicad_sch",
        ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR_03_3V3_DIGITAL.kicad_sch",
        ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR_04_AUX_HARNESS.kicad_sch",
        ROOT / "tools/generate_evt_pre_20_bom_rev_a.py",
        ROOT / "tools/validate_evt_pre_20_bom_qg1.py",
        ROOT / "tools/audit_evt_pre_20_bom_qg2.py",
        ROOT / "tools/audit_evt_system_ots_procurement_identity_rev_a.py",
        ROOT / "tools/audit_pcb_layer_count_authority_rev_a.py",
        ROOT / "tools/audit_harness_manufacturing_rev_a.py",
        ROOT / "tools/audit_pcb_mic_manufacturing_handoff_rev_a.py",
        ROOT / "tools/audit_pcb_main_capture_authority_rev_a.py",
        ROOT / "tools/audit_pcb_main_placement_clearance_rev_a.py",
        ROOT / "tools/generate_pcb_main_routing_authority_rev_a.py",
        ROOT / "tools/audit_pcb_main_routing_authority_rev_a.py",
        ROOT / "tools/audit_pcb_main_stackup_impedance_request_rev_a.py",
        ROOT / "tools/audit_pcb_main_jlc06161h_3313_routing_basis_rev_a.py",
        ROOT / "tools/generate_pcb_main_rf_return_001_candidate_rev_a.py",
        ROOT / "tools/audit_pcb_main_rf_return_001_candidate_rev_a.py",
        ROOT / "tools/generate_pcb_main_gnss_rf_eco_001_candidate_rev_a.py",
        ROOT / "tools/audit_pcb_main_gnss_rf_eco_001_candidate_rev_a.py",
        ROOT / "tools/generate_pcb_main_rf_remediation_application_rev_a.py",
        ROOT / "tools/audit_pcb_main_rf_remediation_application_rev_a.py",
        ROOT / "tools/audit_pcb_main_assembler_dfm_stencil_request_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_native_schematic_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_native_completeness_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_passive_authority_rev_a.py",
        ROOT / "tools/materialize_pcb_pwr_hierarchy_rev_a.py",
        ROOT / "tools/pcb_pwr_schematic_hierarchy.py",
        ROOT / "tools/audit_pcb_pwr_hierarchy_rev_a.py",
        ROOT / "tools/generate_pcb_pwr_routing_authority_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_routing_authority_rev_a.py",
        ROOT / "tools/generate_pcb_pwr_evt_route_rules_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_jlc04161h_3313_evt_routing_basis_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_placement_clearance_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_dim_003_request_rev_a.py",
        ROOT / "tools/audit_pcb_pwr_stackup_copper_request_rev_a.py",
        ROOT / "tools/verify_pcb_main_passive_support_authority_rev_a.py",
        ROOT / "tools/verify_pcb_main_mechanical_placement_authority_rev_a.py",
        ROOT / "hardware/kicad/REV_A_CAPTURE_SPEC.md",
        ROOT / "hardware/kicad/REV_A_CAPTURE_ADDENDUM_001_ENV_MIC.md",
        ROOT / "hardware/PCB_DOUBLE_REVIEW_GATE.md",
        ROOT / "mechanics/common/OPEN_DIMENSIONS.csv",
        ROOT / "firmware/targets/evt_pre_20/target_contract_manifest.json",
        ROOT / "firmware/targets/evt_pre_20/include/evt_pre_20_board_pins.h",
        ROOT / "firmware/targets/evt_pre_20/include/evt_pre_20_clock_policy.h",
        ROOT / "firmware/targets/evt_pre_20/stm32_scaffold_manifest.json",
        ROOT / "firmware/targets/evt_pre_20/stm32_memory_contract.json",
        ROOT / "firmware/targets/evt_pre_20/cubemx_generation_contract.json",
        ROOT / "firmware/targets/evt_pre_20/dioneya_evt_pre_20_rev_a.ioc",
        ROOT / "firmware/targets/evt_pre_20/ld/STM32U585VITXQ_ENGINEERING_FLASH.ld",
        ROOT / "firmware/targets/evt_pre_20/vendor/stm32cubeu5.lock.json",
        ROOT / "firmware/targets/evt_pre_20/vendor/stm32cubemx_db.lock.json",
    ]
    hashes = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in manifest_inputs
        if path.is_file()
    }

    return {
        "configuration": "EVT-PRE-20",
        "source_complete": all(bool(item["pass"]) for item in groups.values()),
        "production_complete": all(bool(item["pass"]) for item in production.values()),
        "release_ready": not blockers,
        "source_groups": groups,
        "production_groups": production,
        "baseline_hashes": hashes,
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="return non-zero while any release blocker remains")
    parser.add_argument("--output", default="artifacts/evt_pre_20_release_audit.json")
    args = parser.parse_args()

    result = audit()
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"EVT-PRE-20 second-pass release audit: {'PASS' if result['release_ready'] else 'BLOCKED'}")
    for blocker in result["blockers"]:
        print(f"- {blocker}")
    try:
        display_output = output.relative_to(ROOT)
    except ValueError:
        display_output = output
    print(f"report: {display_output}")

    return 1 if args.strict and not result["release_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
