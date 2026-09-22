# nRF52840 BLE bridge (Zephyr / nRF Connect SDK)

Transparent GATT ↔ UART bridge of ICD BLE addendum B/C on top of the host-tested core
(`firmware/src/zs_ble_bridge.c`, `zs_ipc_link.c`, `zs_ble_framing.c`).

* Not built by the repository CI (no NCS toolchain there). Build with NCS v2.7+:
  * Rev.A carrier: `west build -b evt_pre_20_ble firmware/targets/nrf52840_ble` — board definition in
    `boards/dioneya/evt_pre_20_ble/` (U11 Raytac MDBT50Q-P1MV2: UARTE TX P0.06 / RX P0.08, P0.18 = nRESET from BLE_EN,
    P0.15 = BLE_DFU_REQ, LFRC clock, no UART console — logs over RTT on the TP_BLE_SWD pads);
  * bench: `west build -b nrf52840dk/nrf52840 firmware/targets/nrf52840_ble` (uart1 P1.01/P1.02 overlay);
  then `west flash` (nrfjprog / J-Link / pyOCD through the separate nRF SWD pads).
* MCUboot (sysbuild): `sysbuild.conf` + `sysbuild/mcuboot.conf` + `pm_static.yml` (MCUboot 48 KiB, two 472 KiB
  slots, 32 KiB settings). Images are signed with the pilot key from the PKI (`muhoed-pki nrf-boot-key`,
  ECDSA P-256): `west build -b evt_pre_20_ble firmware/targets/nrf52840_ble -- -DSB_CONFIG_BOOT_SIGNATURE_KEY_FILE="/abs/nrf-boot.key.pem"`.
  Recovery: the STM32 asserts BLE_DFU_REQ (P0.15) through a reset (console `bledfu`), MCUboot stays in serial
  recovery on the IPC UART and the STM32 uploads the image over mcumgr SMP (addendum C.6). The application confirms
  itself on the first IDENTITY_SET from the STM32; an update that never talks to the STM32 is reverted at the next reset.
* All station logic stays on the STM32U585 (`zs_ipc_service`); this application only advertises when told to,
  frames values, keeps read caches and forwards writes.
* Pairing: LE Secure Connections, passkey entry with a fixed passkey derived from the label secret
  (addendum B.7). The STM32 pushes the secret with PAIRING_SECRET_SET after provisioning.
* Characteristics other than `identity` require an authenticated link (MITM), so the phone is asked to pair
  on its first read of `config_read` / write of `config_write`.
