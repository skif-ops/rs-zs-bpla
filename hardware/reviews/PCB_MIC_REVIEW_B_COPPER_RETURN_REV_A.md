# PCB-MIC Rev.A Review B copper-return and decoupling packet

Status: `ECO_REQUIRED RECORDED / ECO CANDIDATE IMPLEMENTED / COMMIT-BOUND CI PENDING / REPEAT REVIEW A REQUIRED / REVIEW B BLOCKED / NOT FOR MANUFACTURE`

This packet records the independent copper-return decision, preserves the baseline
evidence that caused the hold, and defines the bounded PCB-MIC copper ECO. It does not
create a new Review-A signature, complete Review B, or grant manufacturing release.

## Controlled decision binding

| Item | Controlled value |
|---|---|
| Superseded signed Review-A commit | `3e215e26e0d4cb160b309de3d3fd5a3145a756bf` |
| Superseded native PCB SHA-256 | `aecd1a374b5f66d32a5ae056eb4ad452d68e2a2391e65f6068acc8cad37f2295` |
| Copper decision evidence commit | `cb69c0bbc1457b498ee4f44ee7da1d566033c23f` |
| PCB Native Gate | [run #158](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34840246015) |
| CI | [run #428](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34840245983) |
| Artifact | ID `10345408977`, SHA-256 `f535c183a3feda6b4e2d38a636987b30aacaa0767103bec39379fbf042d95664` |
| Independent measurement | `tools/audit_pcb_mic_copper_return_rev_a.py` |
| Reviewer | `Скиф` |
| Date | `14.09.2026` |
| Decision | `ECO_REQUIRED` |

The decision evidence verified all 62 manifest entries, 10 controlled source hashes
and 27 PCB-MIC output hashes. The vector F.Cu and B.Cu drawings were board-sized,
distinct and bound to the source hash above.

## Baseline blocking finding PCB-MIC-RB-CU-001

The signed baseline source contained a B.Cu GND zone named
`PCB_MIC_BCU_GND_REFERENCE` with zero cached filled polygons. Its KiCad 9.0.9 B.Cu
Gerber contained zero GND regions and only the five explicit GND conductor draws.
The emitted fabrication copper therefore used the long explicit backbone, not the
named zone.

| Baseline routed path | Trace length | Vias | Minimum width |
|---|---:|---:|---:|
| C1.1 to MK1.7 local VDD leg | 1.658011 mm | 0 | 0.300 mm |
| C1.2 to MK1.2 explicit GND return | 22.248973 mm | 2 | 0.160 mm |
| Complete decoupling loop | 23.906984 mm | 2 return vias | 0.160 mm |

Disposition recorded by the reviewer: `ECO_REQUIRED`.

- [x] Inspect the commit-bound F.Cu/B.Cu drawings and machine topology report.
- [x] Confirm that the absent B.Cu region is not intended fabrication copper.
- [x] Reject implicit acceptance based only on zero DRC or connectivity.
- [x] Select `ECO_REQUIRED` and reopen Review A for changed PCB bytes.

## Bounded ECO candidate

The ECO preserves placement, schematic, mechanical outline, holes, component set,
net assignments, via count and signal routing. It changes only the controlled GND
copper model:

1. Remove the non-materialized B.Cu zone from the native board and production generator.
2. Remove the remote B.Cu C1 branch from `(15.25, 13.25)` to `(9.00, 13.25)`.
3. Add one explicit 0.50 mm B.Cu local return from the C1 GND via at
   `(15.25, 13.25)` directly to the microphone-return via at `(15.00, 16.65)`.
4. Generate the board directly with `tools/generate_pcb_mic_clean_rev_a.py`; the
   obsolete zone-fill bypass wrapper is removed.

The local standard-library audit produces these candidate measurements before the
commit-bound KiCad run:

| ECO candidate routed path | Trace length | Vias | Layer length |
|---|---:|---:|---|
| J1.1 to C1.1 supply feed | 15.369931 mm | 2 | F.Cu 3.984774 mm; B.Cu 11.385157 mm |
| C1.1 to MK1.7 local VDD leg | 1.658011 mm | 0 | F.Cu 1.658011 mm |
| C1.2 to MK1.2 explicit GND return | 7.108150 mm | 2 | F.Cu 3.698972 mm; B.Cu 3.409178 mm |
| Complete decoupling loop | 8.766161 mm | 2 return vias | Reduction 15.140823 mm |
| J1.2 to MK1.2 connector return | 28.303419 mm | 2 | F.Cu 3.953418 mm; B.Cu 24.350001 mm |

Geometry checks calculate at least `0.802865 mm` copper-edge clearance from the new
segment to other-net B.Cu copper, against the project `0.2 mm` clearance, and
`2.35 mm` from the new segment edge to the acoustic-hole edge. KiCad 9 DRC and CAM
remain mandatory independent controls.

The project still has no frozen normative maximum for the decoupling loop. These
measurements prove the bounded topology change and regression, but cannot self-sign
Review A or Review B.

## Required next gates

- [ ] Commit and push the ECO candidate as one controlled source set.
- [ ] KiCad 9 ERC and DRC pass with zero violations and zero unrouted items.
- [ ] Commit-bound Gerber confirms explicit-routing-only B.Cu copper with zero GND regions.
- [ ] Updated copper SVGs, topology JSON, CAM reports and SHA-256 manifest are archived.
- [ ] Repeat Review A is signed against the ECO candidate commit and its archived evidence.
- [ ] Repeat the independent copper-return decision within Review B after Review A closes.
- [ ] Complete the remaining panelization, DFM, acoustic-stack and physical-EVT gates.

## Decision signature

- Reviewer: `Скиф`
- Date: `14.09.2026`
- Reviewed evidence commit: `cb69c0bbc1457b498ee4f44ee7da1d566033c23f`
- Workflow and artifact: PCB Native Gate `34840246015`, artifact `10345408977`
- Disposition: `ECO_REQUIRED`
- New Review A complete: `false`
- Review B complete: `false`
- Manufacturing release: `false`
