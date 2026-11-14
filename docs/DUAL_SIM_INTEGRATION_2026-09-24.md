# Dual SIM in the comms task — 2026-09-24

`evt_pre_20_sim_orchestrator` (targets/evt_pre_20/src) drives the three existing, host-tested pieces from
`app_comms`: the policy controller `zs_dual_sim` (states, presence debounce, attempt budget, 15 min hold),
the Rev.A GPIO binding `evt_pre_20_dual_sim_gpio` (SIM_MUX_SEL PE0, SIM_MUX_EN PE2, SIM1/2_DET PE3/PE5,
CELL_STATUS PD13, EN_MODEM PD4, PWR_GOOD PD0, CELL_PWRKEY_CMD PD11) and the BG95 bridge `zs_dual_sim_bg95`.

## Behaviour

- Boot: recovery to safe-off first (hard PWRKEY 1000 ms pulse if STATUS is high, mux off, rail off), then
  the preferred slot from the station configuration (`preferred_sim`) is brought up: slot select → rail →
  PWR_GOOD stable 30 ms → mux → PWRKEY 700 ms → STATUS high → ICCID read by the modem driver is compared
  with the expected one → endpoint/MQTT bring-up by the comms task → link confirmed → ACTIVE.
- Failures before ACTIVE (no STATUS in 15 s, modem error, wrong card, no link in 180 s) count per slot;
  after 3 the other slot is used; after both are exhausted the station sits in safe-off and retries
  every `APP_SIM_SAFE_OFF_RETRY_MS` (10 min) with the counters cleared.
- Failures while ACTIVE (MQTT lost, modem error): the first two restart the same slot through the safe-off
  recovery; from the third the controller is asked to switch, which it grants only after the 15 min hold
  since the last activation and only if the other card is present — otherwise the same slot is retried.
  A granted switch is graceful: the comms task drops the session (the outbox is durable NOR), `AT+QPOWD`,
  STATUS low, mux off, rail off, the other slot up.
- A pulled card (presence debounce 20 ms) takes the modem down through the same recovery.
- Console: `simiccid 1 <iccid>` / `simiccid 2 <iccid>` provision the expected ICCIDs (both needed) and
  commit them to the station secrets record in NOR (`zs_station_secrets`, two blocks @0x03F79000 before the
  boot counter, together with the B.9 engineer key set by `engkey`); they are loaded and applied at every boot.
  Without them the single-SIM path of #48 is used unchanged. `secrets` shows what is provisioned (presence
  only), `secrets clear` wipes the record. `comms` prints the dual-SIM line (state, slot, card presence,
  STATUS, counters).

## Evidence

`test_evt_pre_20_sim_orchestrator.c`: boot recovery with the modem still on, bring-up on slot 1, three
link failures retried on the same slot, graceful switch to slot 2 after the hold (QPOWD observed, mux
re-selected), wrong card ×3 exhausting a slot with fallback to the other one, no SIM → safe-off with nothing
driven. Target Release: FLASH 147 KB, RAM 83.7 %.

## Open on hardware

- SIMx_DET polarity (`APP_SIM_DET_ACTIVE_HIGH`), CELL_STATUS level-shifter sense, U13_EN_N high-Z evidence
  (no MCU read-back in Rev.A: logical completion only, as in the GPIO binding).
- ~~The supervisor's mode power policy (`apply_power`) still drives EN_MODEM on mode changes~~ — resolved:
  `apply_power` only tells the comms task whether the mode allows the modem (`app_comms_allow_modem`); the comms
  task owns EN_MODEM and takes the modem down gracefully (`POWER_MODES_INTEGRATION_2026-09-24.md`).
