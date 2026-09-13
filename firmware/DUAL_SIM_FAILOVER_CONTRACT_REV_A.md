# Dual-SIM single-standby failover contract Rev.A

Status: `PORTABLE POLICY AND SAFE-SEQUENCE QG-1/QG-2 PASS / TARGET GPIO,
MODEM POWER, PROVISIONED ICCID AND ASSEMBLED-STATION EVIDENCE OPEN / NOT FOR
RELEASE`

`zs_dual_sim` is a portable action sequencer between authenticated policy,
the existing BG95 automatic public-APN state machine, persistent queues and a
future STM32 target binding. `zs_dual_sim_bg95` joins only the modem-dependent
actions to BG95 power, full-ICCID and validated-online state. Neither module
drives board GPIO directly or claims that either physical SIM path works.

## Fixed policy

- two physical slots, one active slot and no hot switching;
- both expected full ICCIDs are supplied by station provisioning, contain 18 to
  22 decimal digits and must be different;
- a slot is eligible only after its DET input has remained present for at least
  20 ms;
- automatic failover accepts only attach timeout, PDP failure, DNS failure, TLS
  failure or sustained link loss;
- one slot/profile is retried at most three times before failover is considered;
- every successful activation starts a 900-second hold. Both automatic and
  authenticated manual changes obey it;
- a manual change without an authenticated BLE-or-mTLS assertion is rejected;
- an audit-intent action must complete before changing traffic or hardware and
  an audit-commit action must complete before queue resume.

The numeric profile index identifies an entry in the separately provisioned
approved public-APN list. The target binding must pass the same index to the
BG95 automatic network selection path; the portable controller never invents
an operator or APN.

## Action order

On boot or after a fault, the target must first apply safe-off: modem rail off
and SIM mux High-Z. Initial activation then executes audit intent, slot select,
modem rail enable, stable `PWR_GOOD` for at least 30 ms, mux enable and
verification, 700 ms PWRKEY, modem-on verification, full ICCID verification,
attach/DNS/TLS validation, audit commit and preserved-queue resume.

Switching an active slot has the mandatory prefix:

1. record audit intent;
2. stop new application traffic;
3. persist queue and session state;
4. close MQTT/HTTPS and detach;
5. request graceful modem power-off and verify `CELL_STATUS=LOW`;
6. disable the mux and verify U13 High-Z;
7. disable the modem rail;
8. only then select the pending slot and perform the initial-activation suffix.

The state machine rejects out-of-order action completion. A failed action,
malformed or mismatched ICCID, debounced removal of the active/pending card, or
brownout discards active-slot knowledge and requests safe-off. It exposes no
action that clears or renumbers queued events.

The portable BG95 bridge starts `AT+QPOWD`, but does not accept shutdown until
the caller supplies `CELL_STATUS=LOW`; the BG95 state then clears volatile
IMSI/ICCID. On power-up it uses the existing 700 ms PWRKEY state, requires
`CELL_STATUS=HIGH`, reads the full ICCID from BG95 runtime and completes link
validation only when automatic APN read-back and MQTT/TLS are online. A busy
UART leaves the action pending instead of skipping shutdown.

## Double control

- QG-1: `tools/validate_dual_sim_failover_contract.py` checks interface,
  fail-closed guards, policy, documentation, CMake and CI traceability.
- QG-2: `tools/audit_dual_sim_failover_technical.py` independently verifies the
  frozen constants and switch order, then compiles and runs the portable C test
  under strict warnings.
- Runtime: `firmware/tests/test_dual_sim.c` covers initial activation, bounded
  automatic failover, hold time, authentication, DET debounce, out-of-order
  rejection, power-good timing, exact ICCID, action failure and brownout.
- Bridge runtime: `firmware/tests/test_dual_sim_bg95.c` proves that QPOWD,
  physical-status assertions, PWRKEY, full ICCID and online network settings
  advance only their matching controller actions.

## Open target and EVT evidence

- STM32 GPIO/rail/PWRKEY binding for `SIM_MUX_SEL`, `SIM_MUX_EN`, `SIM1_DET`,
  `SIM2_DET`, `EN_MODEM`, `PWR_GOOD`, `CELL_STATUS` and U13 enable read-back;
- STM32 sampling of `CELL_STATUS` and the remaining GPIO/rail actions;
- durable audit backend and verified coupling of profile index to the existing
  approved public-APN catalog;
- exact provisioned ICCIDs and actual BG95 response behavior;
- power interruption in every switch phase, signal-integrity/ESD checks and 100
  SIM1/SIM2 cycles on assembled stations;
- operator matrix, queue recovery and 24-hour MQTT/TLS EVT after assembly.

Until those items pass, `REQ-CELL-004`, `PR-006` and `FW-005` retain partial
host evidence only.
