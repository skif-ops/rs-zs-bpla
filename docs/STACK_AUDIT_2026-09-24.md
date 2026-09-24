# Target stack audit — 2026-09-24

A `-fstack-usage` pass over the STM32 Release build (application + zs_core) found three frames that would have
overflowed their FreeRTOS task stacks on the first run:

| frame | bytes | task / thread (stack) | fix |
|---|---:|---|---|
| `f0_one_frame` (zs_dsp_mcu, YIN `d[]` + `cumulative_energy[]`) | 6472 | dsp (6144) | static scratch like `g_yin` (module is single-instance) |
| `push_value` (zs_ipc_service, 2 + 4096 payload copy) | 4128 | ble (4096) | `zs_ipc_encode2`: frame COBS-encoded straight from (id, value), no copy |
| `zs_ipc_encode` (zs_ipc_link, 4 KB raw copy for CRC + COBS) | 4128 | ble (4096), nRF BT RX thread | streaming CRC + COBS over parts |
| `zs_ble_bridge_on_gatt_write` (4 KB payload copy) | 4136 | nRF BT RX thread | `zs_ipc_encode2` from the reassembly buffer |

`configCHECK_FOR_STACK_OVERFLOW 2` would have halted the board, costing bench time; on the nRF the BT RX
thread stack is even smaller than 4 KB.

Now: largest frame `zs_ed25519_verify` 2304 B (comms task, 8 KB), everything else < 1.4 KB. Estimated worst
chains: comms ≈ 5 KB of 8 KB (session feed → command verify), dsp ≈ 2.5 KB of 6 KB (emit → outbox enqueue),
ble ≈ 2.5 KB of 5 KB (config commit / nRF image update; stack raised 1024 → 1280 words).

Guard: the target build now emits `.su` files and CI runs `firmware/tools/check_stack_usage.py build-target`
(limit 2560 B per frame, one documented exception). GCC 13 `-fanalyzer` over zs_core: no findings.

RAM after the changes: 85.1 % (static YIN scratch +6.4 KB, BLE stack +1 KB); FLASH 162 KB.
