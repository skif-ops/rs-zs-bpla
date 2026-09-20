# PCB-MAIN P0 RF-routing candidate Rev.A

Date: 2026-09-19  
Configuration: EVT-PRE-20 Rev.A  
Candidate: `PCB-MAIN-RF-P0-001`

## Result

An isolated proposal routes all seven controlled `RF_50OHM` nets from the
accepted OctoSPI R8 baseline:

- `CELL_RF`, `CELL_RF_ANT`;
- `GNSS_RF_FILTERED`, `GNSS_RF_DC_BLOCK`, `GNSS_RF_ANT_BIASED`;
- `LORA_RF_MODULE`, `LORA_RF_ANT`.

The candidate adds 138 F.Cu segments, no signal vias, and closes exactly 15
local KiCad 7 unconnected items (`697 -> 682`).  It preserves all 838 accepted
track/via objects byte-semantically and uses a candidate-specific deterministic
UUID seed; all 976 candidate track/via UUIDs are unique.

## Controlled geometry

The engineering width is `0.1509 mm` on L1/F.Cu over L2, taken from the accepted
public JLCPCB `JLC06161H-3313` calculation recorded by DEC-070.  This is an
engineering-candidate input only.  It does not represent acceptance of the
final job construction, production impedance tolerance or coupon plan.

`GNSS_RF_FILTERED` uses a deterministic no-via escape from `U9.11` to `FL1.A`.
The generic grid route could not pass the already accepted `U9.10/U9.12` ground
escapes.  The guide leaves U9 normal to the module edge, passes east of the GNSS
bias/supervisor cluster and enters `FL1.A` from the east without changing the
accepted ground copper.

## Identity

- Base SHA-256: `04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f`
- Candidate SHA-256: `718e26555529f4076035ea2306826d8f2cd90b621b91bdff7d4e8f49962f1c43`
- Generator SHA-256: `c764be80c70c9f8aff3966367a064131d67ada9a6f42c900390fd45aa244a4c4`
- Candidate: `hardware/kicad/candidates/PCB-MAIN-RF-P0-001/PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb`
- Static audit: `tools/audit_pcb_main_rf_p0_candidate_rev_a.py`

## Decision boundary

The authoritative PCB-MAIN is unchanged.  KiCad 9 zone refill, comparative DRC,
independent RF/SI and return-path review, final fabricator stackup acceptance,
Review B, CAM, DFM and manufacturing release remain open.  This proposal must
not be applied until the commit-bound machine gate is green and reviewer Скиф
issues an explicit acceptance decision against the exact candidate hash.
