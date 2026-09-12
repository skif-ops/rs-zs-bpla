# Дионея EVT-PRE-20 Rev.A — PCB-PWR footprint authority

Status: `Q1 MANUFACTURER COPPER/STENCIL VERIFIED / LAYOUT USE AUTHORIZED / NOT FOR MANUFACTURE`
Date: 2026-09-12
Board: `PCB-PWR`

## Q1 — Texas Instruments CSD18540Q5B

Controlled footprint: `DioneyaPWR:CSD18540Q5B_DNK`

Primary source: TI CSD18540Q5B data sheet SLPS488B Rev.B,
`https://www.ti.com/lit/ds/symlink/csd18540q5b.pdf`, retrieved SHA-256
`2e43c4a2ac82af8a089be0a9e413282326f8d7857254ac07390b458deca854e0`.

The footprint implements section 7.2 Recommended PCB Pattern and section 7.3
Recommended Stencil Pattern. The drawing is interpreted as the PCB copper view shown
by TI: pins 1–4 are the four right-side pads and pins 5–8 are the contiguous drain
land on the left. This agrees with the data-sheet top-view electrical diagram:
pins 1–3 SOURCE, pin 4 GATE, and pins 5–8 DRAIN.

### Copper authority

| Feature | Frozen geometry, mm |
|---|---:|
| Overall X extent | `-3.456 … +3.456` |
| Overall Y extent | `-2.260 … +2.260` |
| Pads 1–4 | `1.372 × 0.710`, pitch `1.270`, center X `+2.770` |
| Drain land overall | `4.440 × 4.520` envelope |
| Drain base | X `-2.866 … +0.984` |
| Drain lead tabs | `0.590 × 0.710`, pitch `1.270`, left edge `-3.456` |

The contiguous drain land is partitioned into touching same-net KiCad pads so all four
electrical numbers 5–8 remain present without changing the manufacturer copper union.

### Stencil authority

| Aperture group | Count | Size, mm | Placement |
|---|---:|---:|---|
| Drain lead edge | 4 | `0.766 × 0.508` | pitch `1.270` |
| Drain center | 8 | `1.294 × 0.746` | two columns; X gap `0.350`, Y gap `0.300` |
| Pins 1–4 | 4 | `1.072 × 0.562` | pitch `1.270` |

All sixteen paste apertures are explicit paste-only pads. Electrical copper pads carry
no implicit full-area paste opening, preventing accidental loss of TI's segmented
stencil pattern.

## Remaining controls

- TI does not define a solder-mask expansion in these two figures; the final mask rule
  remains an assembly-house/DFM control.
- Drain thermal spreading, via field, current density, gate-loop placement and SOA are
  PCB-PWR layout/Review-B controls.
- Q1 placement is not authorized until `PCB-PWR.kicad_pcb` is created from the reviewed
  board outline and mechanical authority.
- Manufacturing release remains blocked until layout DRC, thermal/fault evidence, DFM
  and both review gates pass.
