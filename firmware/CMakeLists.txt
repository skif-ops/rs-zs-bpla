cmake_minimum_required(VERSION 3.16)
project(zs_bpla_firmware_core C)
set(CMAKE_C_STANDARD 11)

add_subdirectory(targets/evt_pre_20)

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

add_library(zs_core
  src/zs_cbor.c
  src/zs_protocol.c
  src/zs_mesh.c
  src/zs_time.c
  src/zs_classifier.c
  src/zs_fft.c
  src/zs_dsp.c
  src/zs_bg95.c
  src/zs_gnss.c
  src/zs_sx1262.c
  src/zs_audio.c
  src/zs_archive.c
  src/zs_nor.c
  src/zs_nor_archive.c
  src/zs_adpcm.c
  src/zs_prehistory.c
  src/zs_spatial.c
  src/zs_position_trust.c
  src/zs_ina226.c
)
target_include_directories(zs_core PUBLIC include generated)
target_link_libraries(zs_core m)

add_executable(zs_core_tests tests/test_core.c)
target_link_libraries(zs_core_tests zs_core m)
add_executable(zs_driver_tests tests/test_drivers.c)
target_link_libraries(zs_driver_tests zs_core m)
add_executable(zs_bg95_transport_tests tests/test_bg95_transport.c)
target_link_libraries(zs_bg95_transport_tests zs_core m)
add_executable(zs_heartbeat_telemetry_tests tests/test_heartbeat_telemetry.c)
target_link_libraries(zs_heartbeat_telemetry_tests zs_core m)
add_executable(zs_archive_tests tests/test_archive.c)
target_link_libraries(zs_archive_tests zs_core m)
add_executable(zs_nor_tests tests/test_nor.c)
target_link_libraries(zs_nor_tests zs_core m)
add_executable(zs_prehistory_tests tests/test_prehistory.c)
target_link_libraries(zs_prehistory_tests zs_core m)
add_executable(zs_spatial_tests tests/test_spatial.c)
target_link_libraries(zs_spatial_tests zs_core m)
add_executable(zs_protocol_size_tests tests/test_protocol_size.c)
target_link_libraries(zs_protocol_size_tests zs_core m)
add_executable(zs_position_trust_tests tests/test_position_trust.c)
target_link_libraries(zs_position_trust_tests zs_core m)
add_executable(zs_ina226_tests tests/test_ina226.c)
target_link_libraries(zs_ina226_tests zs_core m)
add_executable(evt_pre_20_target_contract_tests tests/test_evt_pre_20_target_contract.c)
target_link_libraries(evt_pre_20_target_contract_tests PRIVATE evt_pre_20_target_contract)

# Release configuration defines NDEBUG globally. Tests must keep assert() active,
# otherwise validation expressions disappear and can hide both test failures and warnings.
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(zs_core_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_driver_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_bg95_transport_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_heartbeat_telemetry_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_archive_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_prehistory_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_spatial_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_protocol_size_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_position_trust_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_ina226_tests PRIVATE -UNDEBUG)
  target_compile_options(evt_pre_20_target_contract_tests PRIVATE -UNDEBUG)
endif()

enable_testing()
add_test(NAME core COMMAND zs_core_tests)
add_test(NAME drivers COMMAND zs_driver_tests)
add_test(NAME bg95_transport COMMAND zs_bg95_transport_tests)
add_test(NAME heartbeat_telemetry COMMAND zs_heartbeat_telemetry_tests)
add_test(NAME archive COMMAND zs_archive_tests)
add_test(NAME nor COMMAND zs_nor_tests)
add_test(NAME prehistory COMMAND zs_prehistory_tests)
add_test(NAME spatial COMMAND zs_spatial_tests)
add_test(NAME protocol_size COMMAND zs_protocol_size_tests)
add_test(NAME position_trust COMMAND zs_position_trust_tests)
add_test(NAME ina226 COMMAND zs_ina226_tests)
add_test(NAME evt_pre_20_target_contract COMMAND evt_pre_20_target_contract_tests)

add_executable(zs_emit_detection tools/emit_detection.c)
target_link_libraries(zs_emit_detection PRIVATE zs_core m)
add_executable(zs_emit_heartbeat tools/emit_heartbeat.c)
target_link_libraries(zs_emit_heartbeat PRIVATE zs_core m)

add_executable(zs_eval_golden tools/eval_golden.c)
target_link_libraries(zs_eval_golden PRIVATE zs_core m)
add_executable(zs_dump_spectrum tools/dump_spectrum.c)
target_link_libraries(zs_dump_spectrum PRIVATE zs_core m)
