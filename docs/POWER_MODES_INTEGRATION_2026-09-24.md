# Power modes wired to the tasks — 2026-09-24

Until now the mode scheduler (`zs_power_modes`: S0 sleep → S1 listen → S2 DSP → S3 comms, S4 service) ran on
the target without any task feeding it events: after boot the station sat in S1 for one 3 s listen window and
went to S0, the pipeline only fetched windows in S2 (never entered), and the comms task ignored the modes while
`apply_power` toggled EN_MODEM under it. This change closes the loop; the scheduler policy itself is unchanged.

## Events from the tasks

| source | event | when |
|---|---|---|
| dsp task | `GATE_POSITIVE` | S1 and level 1 ≥ SUSPECT (S1 → S2) |
| dsp task | `DSP_DONE_EVENT` | S2 and the pipeline emitted an event (S2 → S3, outbox pending) |
| dsp task | `DSP_DONE_NOTHING` | S2 and `APP_DSP_QUIET_WINDOWS` (6 = 3 s) windows at level NONE (S2 → S1 / S3) |
| dsp task | `OUTBOX_PENDING` | an event emitted while still in S1 (comms requested after the listen window) |
| ble task (boot) | `OUTBOX_PENDING` | events left in the NOR outbox from before the reboot |
| comms task | `COMMS_DONE` | session up, ≥ 1 heartbeat published, outbox empty (checked every 5 s) |
| console | `OUTBOX_PENDING` | `comms on` (bench: pulls the scheduler into S3) |

The pipeline fetches windows in S1 and S2 (both keep the PDM clock): S1 runs the same pipeline as S2 for now —
the listen gate *is* the AIR gate + level 1 of the pipeline. A cheaper listen-only gate (S1 at a lower clock) is
low-power work; so is the S0 STOP2 entry (`stop2_allowed` is still ignored).

## Modem ownership

`apply_power` no longer touches EN_MODEM; it calls `app_comms_allow_modem(p.modem)` (true in S3 and S4). The comms
task runs only while allowed *and* enabled by the operator (`comms on|off`): a withdrawn policy sends `AT+QPOWD`,
waits for STATUS low (≤ 5 s), then drops the rail — through the dual-SIM orchestrator (`shutdown()` → safe-off
recovery, mux and rail off, no restart until `start()`) when dual SIM is engaged, or `bsp_gpio_modem_power(false)`
on the single-SIM path (new phase `COMMS_STOPPING`). A later allow restarts the bring-up from `COMMS_OFF`.

Consequences to keep in mind on the bench: after boot the modem stays off until something asks for S3 (an event,
a pending outbox, `comms on`, or the 6 h scheduler heartbeat); S3 is bounded by the scheduler's `comms_max_ms`
(180 s default) — if the BG95 bring-up + TLS takes longer the session is cut and retried on the next S3, which
is a policy number to tune on hardware (`zs_mode_policy_t` passed to `zs_mode_init`, currently the defaults).

Evidence: orchestrator host test extended with the shutdown/restart scenario (`test_evt_pre_20_sim_orchestrator.c`),
host 49/49; target Release FLASH 155 KB, RAM 83.8 %. The event wiring itself is target code — bench item: watch the
`modes` journal (S1 → S2 on a source, S2 → S3 on an event, S3 → S1 on `comms done`).
