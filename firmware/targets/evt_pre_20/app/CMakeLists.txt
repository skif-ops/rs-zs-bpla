# STM32U585 target application (EVT-PRE-20 Rev.A): FreeRTOS + STM32CubeU5 HAL + zs_core.
#
#   cmake -S firmware/targets/evt_pre_20/app -B build-target \
#         -DCMAKE_TOOLCHAIN_FILE=firmware/targets/evt_pre_20/app/cmake/arm-none-eabi.cmake -DCMAKE_BUILD_TYPE=Release
#   cmake --build build-target
#
# Vendor code is fetched at the commits pinned in ../vendor/stm32cubeu5.lock.json
# (STM32CubeU5 v1.9.0 submodules) and FreeRTOS-Kernel V11.1.0; nothing vendor-side
# is committed except the CMSIS startup/system files already in ../vendor.
cmake_minimum_required(VERSION 3.20)
project(dioneya_evt_pre_20_app C ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_EXTENSIONS OFF)

include(FetchContent)
set(FETCHCONTENT_QUIET OFF)
FetchContent_Declare(stm32u5_hal
  GIT_REPOSITORY https://github.com/STMicroelectronics/stm32u5xx-hal-driver
  GIT_TAG 2552682ee5a0d6f826a6435750fc9267be65868b   # STM32CubeU5 v1.9.0 / Drivers/STM32U5xx_HAL_Driver
  GIT_SHALLOW OFF)
FetchContent_Declare(cmsis_device_u5
  GIT_REPOSITORY https://github.com/STMicroelectronics/cmsis-device-u5
  GIT_TAG 624374fa1e21ca195d6f2102ac0caaa50d0ea4c8   # STM32CubeU5 v1.9.0 / Drivers/CMSIS/Device/ST/STM32U5xx
  GIT_SHALLOW OFF)
FetchContent_Declare(cmsis_core
  GIT_REPOSITORY https://github.com/STMicroelectronics/cmsis-core
  GIT_TAG v5.9.0
  GIT_SHALLOW ON)
FetchContent_Declare(freertos_kernel
  GIT_REPOSITORY https://github.com/FreeRTOS/FreeRTOS-Kernel
  GIT_TAG V11.1.0
  GIT_SHALLOW ON)
FetchContent_MakeAvailable(stm32u5_hal cmsis_device_u5 cmsis_core)

# ---- FreeRTOS kernel (Cortex-M33, TrustZone disabled): the config target must exist before the kernel is added ----
add_library(freertos_config INTERFACE)
target_include_directories(freertos_config SYSTEM INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})
set(FREERTOS_HEAP 4 CACHE STRING "" FORCE)
set(FREERTOS_PORT GCC_ARM_CM33_NTZ_NONSECURE CACHE STRING "" FORCE)
FetchContent_MakeAvailable(freertos_kernel)

set(ZS_FW_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/../../..)
set(ZS_TARGET_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)

# ---- HAL (only the modules enabled in stm32u5xx_hal_conf.h) ----
set(HAL_SRC ${stm32u5_hal_SOURCE_DIR}/Src)
add_library(stm32u5_hal STATIC
  ${HAL_SRC}/stm32u5xx_hal.c
  ${HAL_SRC}/stm32u5xx_hal_cortex.c
  ${HAL_SRC}/stm32u5xx_hal_rcc.c
  ${HAL_SRC}/stm32u5xx_hal_rcc_ex.c
  ${HAL_SRC}/stm32u5xx_hal_pwr.c
  ${HAL_SRC}/stm32u5xx_hal_pwr_ex.c
  ${HAL_SRC}/stm32u5xx_hal_gpio.c
  ${HAL_SRC}/stm32u5xx_hal_dma.c
  ${HAL_SRC}/stm32u5xx_hal_dma_ex.c
  ${HAL_SRC}/stm32u5xx_hal_mdf.c
  ${HAL_SRC}/stm32u5xx_hal_tim.c
  ${HAL_SRC}/stm32u5xx_hal_tim_ex.c
  ${HAL_SRC}/stm32u5xx_hal_uart.c
  ${HAL_SRC}/stm32u5xx_hal_uart_ex.c
  ${HAL_SRC}/stm32u5xx_hal_flash.c
  ${HAL_SRC}/stm32u5xx_hal_flash_ex.c
  ${HAL_SRC}/stm32u5xx_hal_i2c.c
  ${HAL_SRC}/stm32u5xx_hal_i2c_ex.c
  ${HAL_SRC}/stm32u5xx_hal_icache.c
  ${HAL_SRC}/stm32u5xx_hal_exti.c
  ${HAL_SRC}/stm32u5xx_hal_ospi.c
  ${HAL_SRC}/stm32u5xx_hal_rng.c
  ${HAL_SRC}/stm32u5xx_hal_timebase_tim_template.c
)
target_include_directories(stm32u5_hal PUBLIC
  ${stm32u5_hal_SOURCE_DIR}/Inc
  ${stm32u5_hal_SOURCE_DIR}/Inc/Legacy
  ${cmsis_device_u5_SOURCE_DIR}/Include
  ${cmsis_core_SOURCE_DIR}/Include
  ${CMAKE_CURRENT_SOURCE_DIR}          # stm32u5xx_hal_conf.h
)
target_compile_definitions(stm32u5_hal PUBLIC STM32U585xx USE_HAL_DRIVER USE_FULL_LL_DRIVER=0)
target_compile_options(stm32u5_hal PRIVATE -Os -w)

# ---- portable station core (host-proven modules) ----
file(GLOB ZS_CORE_SOURCES ${ZS_FW_ROOT}/src/zs_*.c)
list(FILTER ZS_CORE_SOURCES EXCLUDE REGEX "zs_dsp\\.c$")   # double-precision host extractor stays on the host (zs_dsp_mcu on the target); zs_fft.c (float radix-2) serves the AIR gate
add_library(zs_core_target STATIC ${ZS_CORE_SOURCES})
target_include_directories(zs_core_target PUBLIC ${ZS_FW_ROOT}/include ${ZS_FW_ROOT}/generated ${ZS_TARGET_ROOT}/include)
target_compile_options(zs_core_target PRIVATE -Os -Wall -Wextra -Wpedantic -fstack-usage)   # .su files for tools/check_stack_usage.py

# ---- application ----
add_executable(dioneya_evt_pre_20.elf
  app_main.c
  bsp_clock.c
  bsp_gpio.c
  bsp_mdf.c
  bsp_tim2_pps.c
  bsp_uart.c
  bsp_nor.c
  bsp_rng.c
  bsp_i2c.c
  tasks.c
  app_nrf_update.c
  app_comms.c
  app_power.c
  hal_msp.c
  stm32u5xx_it.c
  syscalls.c
  ${ZS_TARGET_ROOT}/vendor/cmsis_device_u5/startup_stm32u585xx.s
  ${ZS_TARGET_ROOT}/vendor/cmsis_device_u5/system_stm32u5xx.c
  ${ZS_TARGET_ROOT}/src/evt_pre_20_dual_sim_gpio.c
  ${ZS_TARGET_ROOT}/src/evt_pre_20_sim_orchestrator.c
)
target_include_directories(dioneya_evt_pre_20.elf PRIVATE ${CMAKE_CURRENT_SOURCE_DIR} ${ZS_TARGET_ROOT}/include)
target_link_libraries(dioneya_evt_pre_20.elf PRIVATE zs_core_target stm32u5_hal freertos_kernel m)
target_compile_options(dioneya_evt_pre_20.elf PRIVATE -Os -Wall -Wextra -Wpedantic -Werror -fstack-usage)
target_link_options(dioneya_evt_pre_20.elf PRIVATE
  -T${ZS_TARGET_ROOT}/ld/STM32U585VITXQ_ENGINEERING_FLASH.ld
  -Wl,-Map=${CMAKE_BINARY_DIR}/dioneya_evt_pre_20.map,--print-memory-usage)
add_custom_command(TARGET dioneya_evt_pre_20.elf POST_BUILD
  COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:dioneya_evt_pre_20.elf> ${CMAKE_BINARY_DIR}/dioneya_evt_pre_20.bin
  COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:dioneya_evt_pre_20.elf> ${CMAKE_BINARY_DIR}/dioneya_evt_pre_20.hex
  COMMAND ${CMAKE_SIZE} $<TARGET_FILE:dioneya_evt_pre_20.elf>)
