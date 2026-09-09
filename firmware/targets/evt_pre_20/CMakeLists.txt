add_library(evt_pre_20_target_contract INTERFACE)
target_include_directories(
  evt_pre_20_target_contract
  INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Source-only engineering scaffold. It is intentionally not compiled by the
# host build; the ARM target build remains a separate release gate.
add_custom_target(
  evt_pre_20_stm32_scaffold
  SOURCES
    vendor/cmsis_device_u5/startup_stm32u585xx.s
    vendor/cmsis_device_u5/system_stm32u5xx.c
    ld/STM32U585VITXQ_ENGINEERING_FLASH.ld
    stm32_memory_contract.json
    cubemx_generation_contract.json
    dioneya_evt_pre_20_rev_a.ioc
    stm32_scaffold_manifest.json
    vendor/stm32cubemx_db.lock.json
)
