# STM32U585 target, EVT-PRE-20 Rev.A

This directory binds the firmware target to the exact `STM32U585VIT6Q` in
`LQFP100_14x14`. The generated C headers are derived from the locked Rev.A pin
map, the AAD configuration addendum and the locked no-HSE clock policy.

Regenerate and run both quality gates from the repository root:

```sh
python tools/generate_evt_pre_20_target_contract.py
python tools/validate_evt_pre_20_target_contract.py
python tools/audit_evt_pre_20_target_technical.py
python tools/validate_evt_pre_20_cubemx_ioc.py
python tools/audit_evt_pre_20_cubemx_ioc_technical.py
python tools/import_evt_pre_20_stm32_vendor.py --check
python tools/validate_evt_pre_20_stm32_scaffold.py
python tools/audit_evt_pre_20_stm32_scaffold_technical.py
```

QG-1 checks completeness, ordering and SHA-256 traceability. QG-2 separately
checks package-pin uniqueness, critical peripheral mappings, voltage-domain
bindings and the clock-policy invariants. The second gate pair checks the pinned
STM32CubeU5/CMSIS provenance, the exact 142-entry STM32U585 vector table and the
engineering memory layout independently.

The generated `dioneya_evt_pre_20_rev_a.ioc` is a deterministic pinout import
candidate for STM32CubeMX 6.12.0 / DB.6.0.120. It contains all 65 locked
assignments and the DEC-022 EXTI split: LoRa DIO1 on PC2/EXTI2 and microphone
wake on PA8/EXTI8. QG-1 verifies full source representation and provenance;
QG-2 independently rejects duplicate EXTI sources, HSE activation and critical
peripheral drift.

The GCC startup and CMSIS system template are byte-for-byte imports from the
CMSIS commit pinned by STM32CubeU5 v1.9.0. The linker covers the full 2 MiB flash,
the contiguous 768 KiB SRAM1-3 and the separate 16 KiB SRAM4 retained section,
but is restricted to TrustZone-disabled engineering bring-up. SRAM4 placement
does not claim low-power retention until PWR configuration is measured.

The target remains non-releasable. The generated `.ioc` must still be opened,
reviewed and regenerated with STM32CubeMX 6.12.0. Clock-tree, internal MCU power
supply mode and peripheral runtime parameters are deliberately not released by
the pinout generator. HAL/LL integration, measured clocks, secure boot, A/B OTA,
production target build and hardware evidence remain blockers.
