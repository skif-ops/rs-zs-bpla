cmake_minimum_required(VERSION 3.16)
project(zs_bpla_firmware_core C)
set(CMAKE_C_STANDARD 11)

add_subdirectory(targets/evt_pre_20)

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

add_library(zs_core
  src/zs_sha256.c
  src/zs_cbor.c
  src/zs_protocol.c
  src/zs_mesh.c
  src/zs_time.c
  src/zs_classifier.c
  src/zs_classifier_consensus.c
  src/zs_fft.c
  src/zs_dsp.c
  src/zs_bg95.c
  src/zs_dual_sim.c
  src/zs_dual_sim_bg95.c
  src/zs_bg95_command_transport.c
  src/zs_bg95_mqtt_binary.c
  src/zs_bg95_mqtt_session.c
  src/zs_bg95_event_receipt.c
  src/zs_bg95_event_uplink.c
  src/zs_command.c
  src/zs_command_channel.c
  src/zs_command_journal.c
  src/zs_command_trust.c
  src/zs_mqtt_command_transport.c
  src/zs_event_outbox.c
  src/zs_event_receipt.c
  src/zs_mqtt_event_transport.c
  src/zs_gnss.c
  src/zs_sx1262.c
  src/zs_audio.c
  src/zs_archive.c
  src/zs_nor.c
  src/zs_nor_archive.c
  src/zs_nor_command_journal.c
  src/zs_nor_event_outbox.c
  src/zs_nor_storage_layout.c
  src/zs_adpcm.c
  src/zs_prehistory.c
  src/zs_spatial.c
  src/zs_position_trust.c
  src/zs_installation_store.c
  src/zs_installation_commissioning.c
  src/zs_station_config.c
  src/zs_bg95_provision.c
  src/zs_power_modes.c
  src/zs_pdm_capture.c
  src/zs_pps_sync.c
  src/zs_selftest.c
  src/zs_fft_mixed.c
  src/zs_dsp_mcu.c
  src/zs_ina226.c
  src/zs_cbor_read.c
  src/zs_ble_framing.c
  src/zs_ipc_link.c
  src/zs_ble_bridge.c
  src/zs_ipc_service.c
  src/zs_nor_slot_store.c
  src/zs_air_gate.c
  src/zs_presence.c
  src/zs_mcumgr_serial.c
  src/zs_nor_image_store.c
  src/zs_station_pipeline.c
  src/zs_station_comms.c
  src/zs_boot_counter.c
  src/zs_station_secrets.c
  src/zs_ed25519.c
  src/zs_lora_frame.c
  src/zs_lora_uplink.c
)
target_include_directories(zs_core PUBLIC include generated)
target_link_libraries(zs_core m)

add_library(evt_pre_20_dual_sim_gpio
  targets/evt_pre_20/src/evt_pre_20_dual_sim_gpio.c
  targets/evt_pre_20/src/evt_pre_20_sim_orchestrator.c
)
target_link_libraries(evt_pre_20_dual_sim_gpio
  PUBLIC zs_core evt_pre_20_target_contract
)

add_executable(zs_core_tests tests/test_core.c)
target_link_libraries(zs_core_tests zs_core m)
add_executable(zs_driver_tests tests/test_drivers.c)
target_link_libraries(zs_driver_tests zs_core m)
add_executable(zs_classifier_consensus_tests tests/test_classifier_consensus.c)
target_link_libraries(zs_classifier_consensus_tests zs_core m)
add_executable(zs_bg95_transport_tests tests/test_bg95_transport.c)
target_link_libraries(zs_bg95_transport_tests zs_core m)
add_executable(zs_dual_sim_tests tests/test_dual_sim.c)
target_link_libraries(zs_dual_sim_tests zs_core m)
add_executable(zs_dual_sim_bg95_tests tests/test_dual_sim_bg95.c)
target_link_libraries(zs_dual_sim_bg95_tests zs_core m)
add_executable(zs_bg95_event_uplink_tests tests/test_bg95_event_uplink.c)
target_link_libraries(zs_bg95_event_uplink_tests zs_core m)
add_executable(zs_bg95_event_receipt_tests tests/test_bg95_event_receipt.c)
target_link_libraries(zs_bg95_event_receipt_tests zs_core m)
add_executable(zs_bg95_command_transport_tests tests/test_bg95_command_transport.c)
target_link_libraries(zs_bg95_command_transport_tests zs_core m)
add_executable(zs_bg95_mqtt_session_tests tests/test_bg95_mqtt_session.c)
target_link_libraries(zs_bg95_mqtt_session_tests zs_core m)
add_executable(zs_command_transport_tests tests/test_command_transport.c)
target_link_libraries(zs_command_transport_tests zs_core m)
add_executable(zs_command_channel_tests tests/test_command_channel.c)
target_link_libraries(zs_command_channel_tests zs_core m)
add_executable(zs_command_journal_tests tests/test_command_journal.c)
target_link_libraries(zs_command_journal_tests zs_core m)
add_executable(zs_command_trust_tests tests/test_command_trust.c)
target_link_libraries(zs_command_trust_tests zs_core m)
add_executable(zs_mqtt_command_binding_tests tests/test_mqtt_command_transport.c)
target_link_libraries(zs_mqtt_command_binding_tests zs_core m)
add_executable(zs_event_outbox_tests tests/test_event_outbox.c)
target_link_libraries(zs_event_outbox_tests zs_core m)
add_executable(zs_event_receipt_tests tests/test_event_receipt.c)
target_link_libraries(zs_event_receipt_tests zs_core m)
add_executable(zs_mqtt_event_transport_tests tests/test_mqtt_event_transport.c)
target_link_libraries(zs_mqtt_event_transport_tests zs_core m)
add_executable(zs_heartbeat_telemetry_tests tests/test_heartbeat_telemetry.c)
target_link_libraries(zs_heartbeat_telemetry_tests zs_core m)
add_executable(zs_archive_tests tests/test_archive.c)
target_link_libraries(zs_archive_tests zs_core m)
add_executable(zs_nor_tests tests/test_nor.c)
target_link_libraries(zs_nor_tests zs_core m)
add_executable(zs_nor_command_journal_tests tests/test_nor_command_journal.c)
target_link_libraries(zs_nor_command_journal_tests zs_core m)
add_executable(zs_nor_event_outbox_tests tests/test_nor_event_outbox.c)
target_link_libraries(zs_nor_event_outbox_tests zs_core m)
add_executable(zs_nor_storage_layout_tests tests/test_nor_storage_layout.c)
target_link_libraries(zs_nor_storage_layout_tests zs_core m)
add_executable(zs_prehistory_tests tests/test_prehistory.c)
target_link_libraries(zs_prehistory_tests zs_core m)
add_executable(zs_spatial_tests tests/test_spatial.c)
target_link_libraries(zs_spatial_tests zs_core m)
add_executable(zs_protocol_size_tests tests/test_protocol_size.c)
target_link_libraries(zs_protocol_size_tests zs_core m)
add_executable(zs_position_trust_tests tests/test_position_trust.c)
target_link_libraries(zs_position_trust_tests zs_core m)
add_executable(zs_installation_store_tests tests/test_installation_store.c)
target_link_libraries(zs_installation_store_tests zs_core m)
add_executable(zs_installation_commissioning_tests tests/test_installation_commissioning.c)
target_link_libraries(zs_installation_commissioning_tests zs_core m)
add_executable(zs_station_config_tests tests/test_station_config.c)
target_link_libraries(zs_station_config_tests zs_core m)
add_executable(zs_bg95_provision_tests tests/test_bg95_provision.c)
target_link_libraries(zs_bg95_provision_tests zs_core m)
add_executable(zs_platform_tests tests/test_platform.c)
target_link_libraries(zs_platform_tests zs_core m)
add_executable(zs_fft_mixed_tests tests/test_fft_mixed.c)
target_link_libraries(zs_fft_mixed_tests zs_core m)
add_executable(zs_dsp_mcu_tests tests/test_dsp_mcu.c)
target_link_libraries(zs_dsp_mcu_tests zs_core m)
add_executable(zs_ina226_tests tests/test_ina226.c)
target_link_libraries(zs_ina226_tests zs_core m)
add_executable(zs_ble_bridge_tests tests/test_ble_bridge.c)
target_link_libraries(zs_ble_bridge_tests zs_core m)
add_executable(zs_nor_slot_store_tests tests/test_nor_slot_store.c)
target_link_libraries(zs_nor_slot_store_tests zs_core m)
add_executable(zs_air_gate_tests tests/test_air_gate.c)
target_link_libraries(zs_air_gate_tests zs_core m)
add_executable(zs_presence_tests tests/test_presence.c)
target_link_libraries(zs_presence_tests zs_core m)
add_executable(zs_mcumgr_serial_tests tests/test_mcumgr_serial.c)
target_link_libraries(zs_mcumgr_serial_tests zs_core m)
add_executable(zs_nor_image_store_tests tests/test_nor_image_store.c)
target_link_libraries(zs_nor_image_store_tests zs_core m)
add_executable(zs_station_pipeline_tests tests/test_station_pipeline.c)
target_link_libraries(zs_station_pipeline_tests zs_core m)
add_executable(zs_station_comms_tests tests/test_station_comms.c)
target_link_libraries(zs_station_comms_tests zs_core m)
add_executable(zs_boot_counter_tests tests/test_boot_counter.c)
target_link_libraries(zs_boot_counter_tests zs_core m)
add_executable(zs_station_secrets_tests tests/test_station_secrets.c)
target_link_libraries(zs_station_secrets_tests zs_core m)
add_executable(zs_ed25519_tests tests/test_ed25519.c)
target_link_libraries(zs_ed25519_tests zs_core m)
add_executable(zs_lora_frame_tests tests/test_lora_frame.c)
target_link_libraries(zs_lora_frame_tests zs_core m)
add_executable(zs_lora_uplink_tests tests/test_lora_uplink.c)
target_link_libraries(zs_lora_uplink_tests zs_core m)
add_executable(evt_pre_20_target_contract_tests tests/test_evt_pre_20_target_contract.c)
target_link_libraries(evt_pre_20_target_contract_tests PRIVATE evt_pre_20_target_contract)
add_executable(evt_pre_20_dual_sim_gpio_tests tests/test_evt_pre_20_dual_sim_gpio.c)
target_link_libraries(evt_pre_20_dual_sim_gpio_tests
  PRIVATE evt_pre_20_dual_sim_gpio
)
add_executable(evt_pre_20_sim_orchestrator_tests tests/test_evt_pre_20_sim_orchestrator.c)
target_link_libraries(evt_pre_20_sim_orchestrator_tests PRIVATE evt_pre_20_dual_sim_gpio)
# the STM32 comms task compiled against a simulated clock, GPIO and a scripted BG95 (tests/host_sim)
add_executable(app_comms_sim_tests tests/test_app_comms_sim.c targets/evt_pre_20/app/app_comms.c)
target_include_directories(app_comms_sim_tests PRIVATE tests/host_sim targets/evt_pre_20/app)
target_link_libraries(app_comms_sim_tests PRIVATE evt_pre_20_dual_sim_gpio)

# station digital twin: portable stack + real comms task on the host against a scene, a scripted BG95 and the server twin
add_executable(zs_station_twin twin/station_twin.c twin/scene.c targets/evt_pre_20/app/app_comms.c)
target_include_directories(zs_station_twin PRIVATE twin tests/host_sim targets/evt_pre_20/app)
target_link_libraries(zs_station_twin PRIVATE evt_pre_20_dual_sim_gpio m)
target_compile_options(zs_station_twin PRIVATE -UNDEBUG)

# Release configuration defines NDEBUG globally. Tests must keep assert() active,
# otherwise validation expressions disappear and can hide both test failures and warnings.
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(zs_core_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_driver_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_classifier_consensus_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_transport_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_dual_sim_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_dual_sim_bg95_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_event_uplink_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_event_receipt_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_command_transport_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_mqtt_session_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_command_transport_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_command_channel_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_command_journal_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_command_trust_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_mqtt_command_binding_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_event_outbox_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_event_receipt_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_mqtt_event_transport_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_heartbeat_telemetry_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_archive_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_command_journal_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_event_outbox_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_storage_layout_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_prehistory_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_spatial_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_protocol_size_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_position_trust_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_installation_store_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_installation_commissioning_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_station_config_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_provision_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_platform_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_fft_mixed_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_dsp_mcu_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_ina226_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_ble_bridge_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_slot_store_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_air_gate_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_presence_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_mcumgr_serial_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_image_store_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_station_pipeline_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_station_comms_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_boot_counter_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_station_secrets_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_ed25519_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_lora_frame_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_lora_uplink_tests PRIVATE -UNDEBUG)
  target_compile_options(evt_pre_20_target_contract_tests PRIVATE -UNDEBUG)
  target_compile_options(evt_pre_20_dual_sim_gpio_tests PRIVATE -UNDEBUG)
  target_compile_options(evt_pre_20_sim_orchestrator_tests PRIVATE -UNDEBUG)
  target_compile_options(app_comms_sim_tests PRIVATE -UNDEBUG)
endif()

enable_testing()
add_test(NAME core COMMAND zs_core_tests)
add_test(NAME drivers COMMAND zs_driver_tests)
add_test(NAME classifier_consensus COMMAND zs_classifier_consensus_tests)
add_test(NAME bg95_transport COMMAND zs_bg95_transport_tests)
add_test(NAME dual_sim COMMAND zs_dual_sim_tests)
add_test(NAME dual_sim_bg95 COMMAND zs_dual_sim_bg95_tests)
add_test(NAME bg95_event_uplink COMMAND zs_bg95_event_uplink_tests)
add_test(NAME bg95_event_receipt COMMAND zs_bg95_event_receipt_tests)
add_test(NAME bg95_command_transport COMMAND zs_bg95_command_transport_tests)
add_test(NAME bg95_mqtt_session COMMAND zs_bg95_mqtt_session_tests)
add_test(NAME command_transport COMMAND zs_command_transport_tests)
add_test(NAME command_channel COMMAND zs_command_channel_tests)
add_test(NAME command_journal COMMAND zs_command_journal_tests)
add_test(NAME command_trust COMMAND zs_command_trust_tests)
add_test(NAME mqtt_command_binding COMMAND zs_mqtt_command_binding_tests)
add_test(NAME event_outbox COMMAND zs_event_outbox_tests)
add_test(NAME event_receipt COMMAND zs_event_receipt_tests)
add_test(NAME mqtt_event_transport COMMAND zs_mqtt_event_transport_tests)
add_test(NAME heartbeat_telemetry COMMAND zs_heartbeat_telemetry_tests)
add_test(NAME archive COMMAND zs_archive_tests)
add_test(NAME nor COMMAND zs_nor_tests)
add_test(NAME nor_command_journal COMMAND zs_nor_command_journal_tests)
add_test(NAME nor_event_outbox COMMAND zs_nor_event_outbox_tests)
add_test(NAME nor_storage_layout COMMAND zs_nor_storage_layout_tests)
add_test(NAME prehistory COMMAND zs_prehistory_tests)
add_test(NAME spatial COMMAND zs_spatial_tests)
add_test(NAME protocol_size COMMAND zs_protocol_size_tests)
add_test(NAME position_trust COMMAND zs_position_trust_tests)
add_test(NAME installation_store COMMAND zs_installation_store_tests)
add_test(NAME installation_commissioning COMMAND zs_installation_commissioning_tests)
add_test(NAME station_config COMMAND zs_station_config_tests)
add_test(NAME bg95_provision COMMAND zs_bg95_provision_tests)
add_test(NAME platform COMMAND zs_platform_tests)
add_test(NAME fft_mixed COMMAND zs_fft_mixed_tests)
add_test(NAME dsp_mcu COMMAND zs_dsp_mcu_tests)
add_test(NAME ina226 COMMAND zs_ina226_tests)
add_test(NAME ble_bridge COMMAND zs_ble_bridge_tests)
add_test(NAME nor_slot_store COMMAND zs_nor_slot_store_tests)
add_test(NAME air_gate COMMAND zs_air_gate_tests)
add_test(NAME presence COMMAND zs_presence_tests)
add_test(NAME mcumgr_serial COMMAND zs_mcumgr_serial_tests)
add_test(NAME nor_image_store COMMAND zs_nor_image_store_tests)
add_test(NAME station_pipeline COMMAND zs_station_pipeline_tests)
add_test(NAME station_comms COMMAND zs_station_comms_tests)
add_test(NAME boot_counter COMMAND zs_boot_counter_tests)
add_test(NAME station_secrets COMMAND zs_station_secrets_tests)
add_test(NAME ed25519 COMMAND zs_ed25519_tests)
add_test(NAME lora_frame COMMAND zs_lora_frame_tests)
add_test(NAME lora_uplink COMMAND zs_lora_uplink_tests)
add_test(NAME evt_pre_20_target_contract COMMAND evt_pre_20_target_contract_tests)
add_test(NAME evt_pre_20_dual_sim_gpio COMMAND evt_pre_20_dual_sim_gpio_tests)
add_test(NAME evt_pre_20_sim_orchestrator COMMAND evt_pre_20_sim_orchestrator_tests)
add_test(NAME app_comms_sim COMMAND app_comms_sim_tests)
# station twin smoke: a drone fly-by must produce at least one detection event (no server: the comms side is
# covered by app_comms_sim; the closed loop with server/twin/twin_server.py runs in the server CI job)
add_test(NAME station_twin_smoke COMMAND zs_station_twin --scene drone --seconds 70 --seed 3 --expect-events 1)
# closed loop with the Python server twin (needs server/requirements-protocol.lock.txt installed, as ci/firmware.sh does)
add_test(NAME station_twin_e2e COMMAND python3 ${CMAKE_CURRENT_SOURCE_DIR}/../server/tools/test_station_twin_e2e.py)
set_tests_properties(station_twin_e2e PROPERTIES ENVIRONMENT "ZS_STATION_TWIN=$<TARGET_FILE:zs_station_twin>" SKIP_RETURN_CODE 77)

add_executable(zs_emit_detection tools/emit_detection.c)
target_link_libraries(zs_emit_detection PRIVATE zs_core m)
add_executable(zs_emit_heartbeat tools/emit_heartbeat.c)
target_link_libraries(zs_emit_heartbeat PRIVATE zs_core m)

add_executable(zs_eval_golden tools/eval_golden.c)
target_link_libraries(zs_eval_golden PRIVATE zs_core m)
add_executable(zs_air_gate_eval tools/air_gate_eval.c)
target_link_libraries(zs_air_gate_eval PRIVATE zs_core m)
add_executable(zs_presence_eval tools/presence_eval.c)
target_link_libraries(zs_presence_eval PRIVATE zs_core m)
add_executable(zs_eval_golden_mcu tools/eval_golden_mcu.c)
target_link_libraries(zs_eval_golden_mcu PRIVATE zs_core m)
add_executable(zs_dump_spectrum tools/dump_spectrum.c)
target_link_libraries(zs_dump_spectrum PRIVATE zs_core m)
