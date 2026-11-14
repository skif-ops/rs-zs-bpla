# LoRa on the EVT-PRE-20 target — dry-run wiring (2026-09-25)

The LoRa fallback of the twin (phase 2) is now wired on the STM32 target behind the regional gate of
`LORA_BACKUP_ICD_v0_1`: `APP_LORA_TX_ENABLED 0` keeps the transmitter off until the signed RU868 profile and the RF
gate are closed. Nothing here changes that gate; it only removes the software work between "gate closed" and
"LoRa live" and lets the bench exercise everything that is not RF.

## What runs on the board now
- `bsp_spi`: SPI1 (PA5/6/7, AF5, mode 0, 5 MHz), NSS PA4 as GPIO, DIO1 PC2, TXEN PB15, RXEN PD8, BUSY PD9,
  RESET_N PD10 — the pins of `evt_pre_20_board_pins.h`. `HAL_SPI_MODULE_ENABLED`, `HAL_SPI_MspInit` in hal_msp.c.
- `zs_sx1262` packet path (host-tested on a mock SPI, `test_sx1262_packet.c`): configure (STDBY, DC-DC, calibrate,
  LoRa packet type, RU868-gated carrier, modulation, PA table for the SX1262, +14 dBm, private sync word 0x1424,
  buffer bases, DIO1 IRQ mask), transmit (packet params, WriteBuffer, SetTx with timeout), receive window,
  IRQ read/clear with the RF switch, packet read-back, packet status.
- `app_lora` task (prio 3, 768 words): brings the radio up at boot (reset, configure, sleep) — on the bench the
  console line `lora: radio up (868900000 Hz, SF9, DRY ...)` proves SPI, BUSY and RESET; `lora: radio NOT responding`
  points at the wiring. Drives `zs_lora_uplink` with the route hint from the supervisor (`comms: DEGRADED ...`).
  DRY: every frame the uplink would send is encoded, its airtime booked against the 1 % budget and logged
  (`lora: DRY frame N (38 B, airtime 268 ms, budget ...)`), TXEN never asserted, SetTx never issued, so the outbox
  keeps the event for the GSM probe. LIVE (`APP_LORA_TX_ENABLED 1`): SetTx -> TxDone -> 3 s receive window ->
  RxDone -> ACK to the uplink -> delivered.
- `tasks.c`: the LoRa key comes from the station secrets record (engineer key, rebound when secrets change),
  the frame summary from the DSP task at emit time, console `lora` (status) and `lora on|off` (force the route hint
  on the bench).

## Bench checks before the RF gate (no antenna needed)
1. `lora` after boot: radio up, DRY, route gsm.
2. `comms off` + `lora on` + `dsp` event (or a bench detection): `lora: DRY frame 1 ...` every 30 s -> 60 -> ...
   (per-event backoff, since no ACK can arrive), budget decreasing by 268 ms per frame.
3. `lora off`: no more frames; `comms on`: the outbox drains over GSM.

## To go live
Signed RU868 profile + RF gate (conducted power <= 14 dBm on the pilot channel, harmonics) -> `APP_LORA_TX_ENABLED 1`
-> the gateway (server side of `twin_server.py` becomes a real gateway service) -> field test with the twin's
scenario 2 as the acceptance criterion (events during a GSM outage delivered exactly once over LoRa).
