# Dioneya nRF52840 BLE bridge — Zephyr / nRF Connect SDK application.
# NOT built by the repository CI (no NCS there): build with west on a machine with NCS v2.7+:
#   west build -b nrf52840dk/nrf52840 firmware/targets/nrf52840_ble
# The bridge logic itself (zs_ble_bridge, zs_ipc_link, zs_ble_framing) is host-tested in firmware/tests.
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(dioneya_nrf52840_ble)

set(ZS_FW_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../..)
target_sources(app PRIVATE
  src/main.c
  src/gatt.c
  src/ipc_uart.c
  ${ZS_FW_ROOT}/src/zs_ble_framing.c
  ${ZS_FW_ROOT}/src/zs_ipc_link.c
  ${ZS_FW_ROOT}/src/zs_ble_bridge.c
  ${ZS_FW_ROOT}/src/zs_sha256.c
)
target_include_directories(app PRIVATE ${ZS_FW_ROOT}/include src)
