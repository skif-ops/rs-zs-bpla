# PCB-MAIN P0 RF-routing candidate Rev.A

Date: 2026-09-20
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

KiCad 9 gate `#260` confirmed exact semantic regeneration of all 976 copper
objects and the expected `444 -> 429` connectivity reduction, then identified
four candidate-only clearance errors on the `CELL_RF` approaches to `C79.1`
and `R43.1`.  Four internal vertices were moved by one `0.0625 mm` grid step
away from adjacent pads `C79.2` and `R43.2`.  Segment count, total route length,
F.Cu-only topology, controlled width and zero-via inventory are unchanged.

The corrected candidate passed commit-bound PCB Native Gate
[#261](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35503166684) at
commit `06ba3959abf71c40e78731f9b0f6beb12e04a1e7` and tree
`7d85b7b20a698d3f94f559060e683061fdd7fe3e`.  KiCad 9 exact semantic
regeneration passed for all 976 copper objects, base/candidate zone refill
passed, total violations remained `226 -> 226` with `0 -> 0` errors, and
unconnected items fell exactly `444 -> 429`.  The comparative audit reports
`PASS_NO_NEW_KICAD9_DRC_ERRORS` with an empty new-error map.  General CI
[#533](https://github.com/skif-ops/rs-zs-bpla/actions/runs/35503166719) also
concluded successfully for the same commit.

## Commit-bound machine evidence

| Control | Value |
|---|---:|
| PCB Native Gate | `#261`, run `35503166684`, `success` |
| General CI | `#533`, run `35503166719`, `success` |
| Native artifact | `evt-pre-20-kicad-native-gate`, ID `10602564959` |
| Baseline DRC SHA-256 | `dc1c628e44d15893c9ca6af0da864a4721691d95f1d6b7236f32e8ff2ed0c54e` |
| Candidate DRC SHA-256 | `79130958c0fa2d69724a60528263cf86d90ba92d28eb9271c0ae1b350060d9ff` |
| Comparative audit SHA-256 | `a489451be7ca4023fdf36d6b3ec4ebd0add47e13b73a366d706425f24a65ddd7` |

## Identity

- Base SHA-256: `04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f`
- Candidate SHA-256: `9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`
- Generator SHA-256: `fe2051d54444d961cf3106b9a0b7862b3a929179c27d07fcd40232952ca2991a`
- Candidate: `hardware/kicad/candidates/PCB-MAIN-RF-P0-001/PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb`
- Static audit: `tools/audit_pcb_main_rf_p0_candidate_rev_a.py`

## Decision boundary

The authoritative PCB-MAIN is unchanged.  The commit-bound KiCad 9 zone-refill
and comparative-DRC gate is green.  Independent RF/SI and return-path review,
final fabricator stackup acceptance, Review B, CAM, DFM and manufacturing
release remain open.  This proposal must not be applied until reviewer Скиф
issues an explicit acceptance decision against candidate SHA-256
`9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040`.
