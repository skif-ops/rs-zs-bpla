# Дионея EVT-PRE-20 Rev.A - PCB-MAIN ground-domain authority

Status: `AUTHORITATIVE CAPTURE INPUT / REVIEW A PENDING / NOT FOR MANUFACTURE`

## Decision

PCB-MAIN preserves three independent return domains:

- `GND_MODEM` returns through `J_PWR` pin 2;
- `GND_DIGITAL` returns through `J_PWR` pin 4;
- `GND_MIC` returns through `J_PWR` pin 6.

The three domains have no net-tie, zero-ohm link or copper-plane alias on PCB-MAIN. Their only controlled joins are `NT1`, `NT2` and `NT3` to `GND_PWR` on PCB-PWR, as verified by the PCB-PWR Review-A authority.

## Native mapping rule

The pre-capture electrical authorities historically use logical `GND` for non-modem endpoints. Native capture resolves that logical name as follows:

- the 21 exact microphone endpoints in `PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.csv` map to `GND_MIC`;
- every remaining logical `GND` endpoint maps to `GND_DIGITAL`;
- endpoints already named `GND_MODEM`, `GND_DIGITAL` or `GND_MIC` retain their names.

`U7` and `U18`, including their 1.8 V-side decoupling, use `GND_DIGITAL` because they bridge directly into the MCU digital domain. `U17`, the four microphone harness returns, their WAKE pull-downs, the four microphone ESD arrays and the 1V8_MIC entry bulk capacitor use `GND_MIC`.

## Review constraints

- Native PCB-MAIN must contain no unresolved net named `GND`.
- No PCB-MAIN component may connect two different return domains.
- Each non-NC native net must have at least two controlled endpoints.
- Layout must preserve continuous local return paths under each controlled-impedance or edge-sensitive signal and must not cross a return-domain split.
- Review A must confirm exact endpoint mapping and KiCad ERC.
- Review B must confirm plane geometry, return-path continuity and absence of unintended copper joins.
- Physical EVT must measure microphone noise, false-wake behavior and modem-burst coupling before production release.

This authority does not close Review A, Review B, DFM or physical EVT.
