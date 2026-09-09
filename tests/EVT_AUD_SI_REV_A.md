# Дионея EVT-PRE-20 Rev.A — PDM harness signal-integrity gate

Status: `REQUIRED BEFORE PCB-MIC / HARNESS RELEASE`
Test ID: `EVT-AUD-SI-01`
Applies to: PCB-MIC, PCB-MAIN PDM level translation, 6-wire microphone harness, T5838, firmware PDM clock profile.

## 1. Purpose

Prove that the four external T5838 microphone leaves operate over the released harness geometry without marginal PDM clock/data signalling, data corruption or temperature/RF-induced failures.

TDK T5838 documentation is the primary device evidence. The project treats harness length around and above 150 mm as requiring explicit SI evidence rather than assuming room-temperature bench operation is sufficient.

## 2. Configurations under test

Test at minimum:

1. shortest production-representative harness;
2. 150 mm harness;
3. maximum mechanical-design harness length;
4. maximum released length plus 20 percent engineering margin.

All four channels are tested. Harness construction, conductor gauge, pairing/twist rule, connector revision and measured length are recorded.

The PCB-MIC DATA source-termination footprint `R1` is evaluated with:

- 0 ohm baseline;
- 22 ohm;
- 33 ohm;
- 47 ohm.

Only one value may be frozen in the production BOM after evidence review. Do not choose a value solely from simulation.

## 3. Environmental / aggressor conditions

Repeat the critical waveform and functional checks at:

- -40 °C stabilized operating condition;
- +23 °C nominal condition;
- +70 °C stabilized operating condition.

At nominal temperature, repeat the worst harness while the station creates representative RF/current aggressors:

- BG95 cellular transmit/reconnect traffic;
- LoRa RU868 transmit activity;
- GNSS active;
- storage write activity;
- normal four-channel acoustic processing.

## 4. Electrical measurements

Measure at both ends where practical:

- `PDM_CLK` at PCB-MIC T5838 CLK pin and PCB-MAIN source;
- `PDM_DATA` at T5838 DATA/source-termination side and PCB-MAIN receiver/translator input;
- `1V8_MIC` at the microphone during active PDM and AAD transitions;
- GND reference difference between MAIN and MIC leaf.

Capture:

- high and low levels;
- rise/fall times;
- overshoot/undershoot;
- ringing duration;
- clock duty cycle/frequency;
- data setup/hold relationship to the sampling edge;
- repeated captures during cellular and LoRa aggressor activity.

Probe loading and probe ground method must be documented. A long oscilloscope ground lead is not acceptable as release evidence for edge-quality measurements.

## 5. Functional measurements

Run continuous four-channel capture for each release candidate. Record:

- decoded PCM continuity;
- DMA overrun/underrun counters;
- MDF/PDM peripheral error counters;
- channel dropout count;
- timestamp continuity;
- channel-to-channel delay;
- re-entry from AAD to full PDM capture.

Use deterministic acoustic stimulus plus background/no-signal periods so that electrical failures can be separated from normal microphone noise.

## 6. Acceptance

PASS requires all of the following:

1. At the receiving input, every measured high and low level meets the applicable receiver VIH/VIL limits with documented engineering margin under all released temperature/supply cases.
2. Overshoot/undershoot remains within the absolute-maximum limits of every connected device, with margin documented in the report.
3. Clock waveform remains inside the T5838 clock requirements at the microphone pin.
4. No repeatable ringing creates additional threshold crossings at the receiver.
5. No PDM/DMA integrity error, unexplained channel dropout or electrical discontinuity is observed in the long-run capture attributable to the harness.
6. Four-channel timing remains within the acoustic/TDOA channel alignment requirement.
7. AAD-to-PDM transition remains reliable with the selected termination.
8. RF aggressor operation does not produce a new SI or data-integrity failure.

If more than one R1 value passes, choose the lowest-risk value from measured edge quality, temperature margin and EMC behaviour and record the rationale.

## 7. Buffer escalation rule

The direct T5838 -> R1 -> harness -> PCB-MAIN path is the Rev.A baseline.

A powered DATA buffer is not added merely because the harness is longer than a reference length. It becomes a Rev.A ECO candidate only if the direct path fails this test or lacks adequate receiver margin.

If a buffer is required, repeat this entire test plus:

- S0/AAD current measurement;
- power sequencing / unpowered-input test;
- propagation-delay/channel-skew measurement;
- -40/+70 °C test;
- fault behaviour with PDM clock disabled.

The buffer ECO must not reduce the 30-day no-sun autonomy target or break AAD operation.

## 8. Required evidence

Release evidence package must contain:

- harness drawing and actual measured lengths;
- R1 value / BOM revision;
- oscilloscope screenshots and raw waveform files;
- test temperature and supply voltage;
- RF aggressor state;
- firmware build hash and PDM clock configuration;
- PCM/raw diagnostic logs;
- failure/deviation log;
- signed Review A SI decision.

`PCB-MIC` remains `NOT FOR MANUFACTURE` while this gate is open if the final mechanical harness exceeds the already validated configuration.
