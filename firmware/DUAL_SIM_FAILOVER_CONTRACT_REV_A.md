# Dual-SIM single-standby failover contract Rev.A

Status: `PORTABLE POLICY, BG95 BRIDGE AND EXACT REV.A GPIO INTERLOCK QG-1/QG-2
PASS / STM32 HAL, PHYSICAL U13/3V8, PROVISIONED ICCID AND ASSEMBLED-STATION
EVIDENCE OPEN / NOT FOR RELEASE`

`zs_dual_sim` is a portable action sequencer between authenticated policy,
the existing BG95 automatic public-APN state machine, persistent queues and a
the STM32 target boundary. `zs_dual_sim_bg95` joins only the modem-dependent
actions to BG95 power, full-ICCID and validated-online state. Neither module
drives board GPIO directly or claims that either physical SIM path works.
`evt_pre_20_dual_sim_gpio` now binds the portable policy to generated named
Rev.A pins and exact active levels without depending on STM32 HAL.

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

On boot or after a fault, the controller does not permit an immediate rail cut.
It first requests graceful shutdown when available, otherwise a 1000 ms
fallback PWRKEY pulse when `CELL_STATUS` is HIGH,
then requires `CELL_STATUS=LOW`, disables the SIM mux, verifies High-Z and only
then disables the modem rail. A failed recovery action remains current and
cannot advance. Initial activation then executes audit intent, slot select,
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

The state machine rejects out-of-order action completion. A failed normal action,
malformed or mismatched ICCID, debounced removal of the active/pending card, or
brownout discards active-slot knowledge and starts the explicit modem-off →
mux-High-Z → rail-off recovery. It exposes no action that clears or renumbers
queued events.

The portable BG95 bridge starts `AT+QPOWD`, but does not accept shutdown until
the caller supplies `CELL_STATUS=LOW`; the BG95 state then clears volatile
IMSI/ICCID. On power-up it uses the existing 700 ms PWRKEY state, requires
`CELL_STATUS=HIGH`, reads the full ICCID from BG95 runtime and completes link
validation only when automatic APN read-back and MQTT/TLS are online. A busy
UART leaves the action pending instead of skipping shutdown.

The target GPIO adapter maps PWRKEY to PD11, CELL_STATUS to PD13, mux select and
enable to PE0/PE2, both DET inputs to PE3/PE5, PWR_GOOD to PD0 and EN_MODEM to
PD4. It refuses fallback PWRKEY until graceful shutdown is reported unavailable,
requires the full 1000 ms fallback pulse, refuses rail removal before
CELL_STATUS LOW and mux-disable read-back, selects a slot only with the rail and
mux off, and requires a continuous 30 ms PWR_GOOD interval before enabling the
mux or asserting PWRKEY. PWR_GOOD is explicitly the Rev.A 3.3 V system PG; it is
not represented as a 3V8_MODEM voltage proof.

U13_EN_N is not routed to an MCU input on Rev.A. The adapter therefore returns
separate logical-only and physical-fixture verification results. Runtime can
verify the SIM_MUX_EN command/read-back and rely on the controlled pull-up plus
Q3 open-collector design, while production qualification must provide actual
U13_EN_N High/Low evidence through the fixture. Logical host success does not
close that physical gate.

## Double control

- QG-1: `tools/validate_dual_sim_failover_contract.py` checks interface,
  fail-closed guards, policy, documentation, CMake and CI traceability.
- QG-2: `tools/audit_dual_sim_failover_technical.py` independently verifies the
  frozen constants and switch order, then compiles and runs the portable C test
  under strict warnings.
- Runtime: `firmware/tests/test_dual_sim.c` covers initial activation, bounded
  automatic failover, hold time, authentication, DET debounce, out-of-order
  rejection, power-good timing, exact ICCID, action failure, non-skippable safe
  recovery and brownout.
- Bridge runtime: `firmware/tests/test_dual_sim_bg95.c` proves that QPOWD,
  physical-status assertions, PWRKEY, full ICCID and online network settings
  advance only their matching controller actions.
- Target-contract runtime: `firmware/tests/test_evt_pre_20_dual_sim_gpio.c`
  checks exact generated pin identifiers, active levels, fallback timing,
  shutdown interlocks, continuous PWR_GOOD timing and the explicit distinction
  between logical command read-back and physical U13 fixture evidence.

## Open target and EVT evidence

- STM32 HAL/LL implementation behind the exact generated GPIO contract;
- physical U13 enable read-back through the test fixture and measured
  `3V8_MODEM` stability after EN_MODEM;
- durable audit backend and verified coupling of profile index to the existing
  approved public-APN catalog;
- exact provisioned ICCIDs and actual BG95 response behavior;
- power interruption in every switch phase, signal-integrity/ESD checks and 100
  SIM1/SIM2 cycles on assembled stations;
- operator matrix, queue recovery and 24-hour MQTT/TLS EVT after assembly.

Until those items pass, `REQ-CELL-004`, `PR-006` and `FW-005` retain partial
host evidence only.
