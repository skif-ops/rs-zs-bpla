cmake_minimum_required(VERSION 3.16)
project(zs_bpla_firmware_core C)
set(CMAKE_C_STANDARD 11)

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
)
target_include_directories(zs_core PUBLIC include generated)
target_link_libraries(zs_core m)

add_executable(zs_core_tests tests/test_core.c)
target_link_libraries(zs_core_tests zs_core m)
add_executable(zs_driver_tests tests/test_drivers.c)
target_link_libraries(zs_driver_tests zs_core m)
add_executable(zs_archive_tests tests/test_archive.c)
target_link_libraries(zs_archive_tests zs_core m)
add_executable(zs_nor_tests tests/test_nor.c)
target_link_libraries(zs_nor_tests zs_core m)
add_executable(zs_prehistory_tests tests/test_prehistory.c)
target_link_libraries(zs_prehistory_tests zs_core m)

# Release configuration defines NDEBUG globally. Tests must keep assert() active,
# otherwise validation expressions disappear and can hide both test failures and warnings.
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(zs_core_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_driver_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_archive_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_nor_tests PRIVATE -UNDEBUG)
  target_compile_options(zs_prehistory_tests PRIVATE -UNDEBUG)
endif()

enable_testing()
add_test(NAME core COMMAND zs_core_tests)
add_test(NAME drivers COMMAND zs_driver_tests)
add_test(NAME archive COMMAND zs_archive_tests)
add_test(NAME nor COMMAND zs_nor_tests)
add_test(NAME prehistory COMMAND zs_prehistory_tests)

add_executable(zs_emit_detection tools/emit_detection.c)
target_link_libraries(zs_emit_detection PRIVATE zs_core m)

add_executable(zs_eval_golden tools/eval_golden.c)
target_link_libraries(zs_eval_golden PRIVATE zs_core m)
add_executable(zs_dump_spectrum tools/dump_spectrum.c)
target_link_libraries(zs_dump_spectrum PRIVATE zs_core m)
