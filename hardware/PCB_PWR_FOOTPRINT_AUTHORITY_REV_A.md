# Дионея EVT-PRE-20 Rev.A — PCB-PWR footprint authority

Status: `Q1 AND U3/U4 MANUFACTURER LAND/STENCIL VERIFIED / LAYOUT USE AUTHORIZED / NOT FOR MANUFACTURE`
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

## U3/U4 — Texas Instruments LMR604403SRAKR

Controlled footprint: `DioneyaPWR:LMR60440_RAK0009A`

Primary source: TI LMR60440 data sheet SNAS877, package drawing RAK0009A
`4229353/J` dated 04/2025, pages 35–37,
`https://www.ti.com/lit/ds/symlink/lmr60440.pdf`, retrieved SHA-256
`d2feebeb32432de6f7d7da1e45d0d7dcad01f0ddd14fc1a403941efb2c0387db`.

The footprint implements the drawing's `EXAMPLE BOARD LAYOUT` and `EXAMPLE
STENCIL DESIGN`. Repeated touching KiCad pads with the same electrical number form
the asymmetric L-shaped lands for pins 1, 3, 5 and 8 without altering the specified
copper union. Pin 2 uses the drawing's solder-mask-defined thermal-land treatment.

### Copper and solder-mask authority

| Feature | Frozen geometry, mm |
|---|---:|
| Pin 1 / pin 3 L-land | `0.600 × 0.345` plus `0.250 × 0.695`; centers X `-0.900/-0.725`, Y `±0.9275/±1.1025` |
| Pin 9 / pin 4 | `0.250 × 0.650`; center X `-0.075`, Y `-1.125/+1.125` |
| Pin 8 / pin 5 L-land | `0.300 × 0.550` plus `0.700 × 0.200`; centers X `+0.700/+0.900`, Y `∓1.175/∓1.000` |
| Pin 7 / pin 6 | `0.650 × 0.250`; center X `+0.875`, Y `-0.525/+0.525` |
| Pin 2 metal under mask | `2.500 × 0.550`; center `0,0` |
| Pin 2 mask opening | controlled stepped polygon, X `-1.200 … +1.200`; left height `0.450`, right height `0.300` |
| Other mask openings | explicit `0.050` expansion around copper |

### Stencil authority

| Aperture group | Count | Geometry, mm |
|---|---:|---:|
| Pin 1 / pin 3 L-land | 4 | `0.560 × 0.345` and `0.210 × 0.695` per L-land |
| Pin 2 thermal land | 2 | `1.100 × 0.410` and `1.100 × 0.300` |
| Pins 4–9 other than L-land split portions | implicit per the TI stencil outline | same as controlled copper pad |

The controlled footprint contains 13 numbered copper primitives, one explicit
paste-free thermal copper land, one custom mask aperture and six explicit paste-only
apertures: 20 KiCad pad/aperture objects in total. Optional thermal vias shown by TI
are deliberately excluded until placement and stack-up are fixed in PCB-PWR Review B.

## Remaining controls

- TI does not define a Q1 solder-mask expansion in the cited figures; its final mask
  rule remains an assembly-house/DFM control. U3/U4 mask geometry is controlled by
  drawing `4229353/J`.
- Drain thermal spreading, via field, current density, gate-loop placement and SOA are
  PCB-PWR layout/Review-B controls.
- Q1 and U3/U4 placement is not authorized until `PCB-PWR.kicad_pcb` is created from
  the reviewed board outline and mechanical authority.
- Manufacturing release remains blocked until layout DRC, thermal/fault evidence, DFM
  and both review gates pass.
