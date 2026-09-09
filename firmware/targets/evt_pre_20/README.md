# STM32U585 target, EVT-PRE-20 Rev.A

This directory binds the firmware target to the exact `STM32U585VIT6Q` in
`LQFP100_14x14`. The generated C headers are derived from the locked Rev.A pin
map, the AAD configuration addendum and the locked no-HSE clock policy.

Regenerate and run both quality gates from the repository root:

```sh
python tools/generate_evt_pre_20_target_contract.py
python tools/validate_evt_pre_20_target_contract.py
python tools/audit_evt_pre_20_target_technical.py
```

QG-1 checks completeness, ordering and SHA-256 traceability. QG-2 separately
checks package-pin uniqueness, critical peripheral mappings, voltage-domain
bindings and the clock-policy invariants.

The target remains non-releasable. The committed contract is an input to the
exact CubeMX project; it is not a substitute for the missing `.ioc`, startup,
linker, HAL/LL integration, secure boot, A/B OTA, production target build or
hardware validation evidence. Runtime clock frequencies are intentionally not
declared until the reviewed CubeMX configuration is measured on Rev.A hardware.
