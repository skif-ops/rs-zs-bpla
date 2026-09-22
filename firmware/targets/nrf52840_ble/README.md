# nRF52840 BLE bridge (Zephyr / nRF Connect SDK)

Transparent GATT ↔ UART bridge of ICD BLE addendum B/C on top of the host-tested core
(`firmware/src/zs_ble_bridge.c`, `zs_ipc_link.c`, `zs_ble_framing.c`).

* Not built by the repository CI (no NCS toolchain there). Build with NCS v2.7+:
  `west build -b nrf52840dk/nrf52840 firmware/targets/nrf52840_ble` (DK bring-up: uart1 P1.01/P1.02),
  then flash with `west flash`. The Rev.A carrier gets its own board overlay once the module pinout is fixed.
* All station logic stays on the STM32U585 (`zs_ipc_service`); this application only advertises when told to,
  frames values, keeps read caches and forwards writes.
* Pairing: LE Secure Connections, passkey entry with a fixed passkey derived from the label secret
  (addendum B.7). The STM32 pushes the secret with PAIRING_SECRET_SET after provisioning.
* Characteristics other than `identity` require an authenticated link (MITM), so the phone is asked to pair
  on its first read of `config_read` / write of `config_write`.
