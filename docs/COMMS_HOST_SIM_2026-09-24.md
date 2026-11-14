# Comms task on the host: simulated BG95, clock and GPIO — 2026-09-24

`test_app_comms_sim.c` compiles the real STM32 comms task (`targets/evt_pre_20/app/app_comms.c`, now split into
`app_comms_step()` + the FreeRTOS loop) against `tests/host_sim/` (FreeRTOS.h/task.h stand-ins with a simulated
millisecond clock), simulated GPIO (modem rail, PWRKEY, STATUS, SIM presence) and a scripted BG95 on the cell
UART: AT sync, SIM/IMSI/operator, APN and PDP context, TLS/MQTT configuration, QMTOPEN/QMTCONN, QMTSUB, the
QMTPUB prompt + payload + result URC, QPOWD → POWERED DOWN, silence while powered down or after a rail cut.
The outbox and the command journal are RAM fixtures; heartbeat/session_done hooks are the test's.

Scenarios: (1) policy allows the modem → single-SIM bring-up → the whole AT dialog in order → two subscriptions
→ heartbeat on `zs/v1/<tenant>/<id>/status` → `session_done` with an empty outbox; (2) policy withdrawn →
QPOWD, rail off, no restart until allowed → second session; (3) a detection in the outbox is published on
`.../up` (231 bytes) and stays pending until a receipt; (4) a dead modem → AT sync timeout → FAULT → back-off →
power cycle → online once the modem answers.

## Two defects it found

1. **`zs_bg95` AT sync** re-sent `AT` every second only while no command was pending — but the first `AT`
   (sent the moment PWRKEY is released, while the module still boots) sets `command_pending` for the 120 s
   command timeout. On hardware every bring-up would have waited 120 s, failed, power-cycled and repeated: the
   modem would never have come up. Now the sync probe is sent every second regardless, with its own 30 s deadline.
2. **Policy withdrawal mid-publish**: the comms task issued `AT+QPOWD` while a `QMTPUB` payload was in flight, so
   the modem would have taken the command text as payload bytes; the task now lets the session owner finish
   (≤ 3 s) before the power-down.

Host: 51/51 (the existing bg95/session tests are unchanged by the driver fix). Target FLASH 162 KB, RAM 85.1 %.
Not simulated here: the dual-SIM path (its orchestrator has its own host test) and receipts/commands on the
down channel (covered by the session tests).
