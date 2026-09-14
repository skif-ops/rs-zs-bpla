# PCB-MIC Rev.A Review A checklist

Status: `REOPENED AFTER COPPER ECO / SIGNATURE REQUIRED / NOT FOR MANUFACTURE`

Review A was reopened because the native PCB bytes changed after the copper-return
review selected `ECO_REQUIRED`. The schematic, exact component identities, pin/net
binding and frozen mechanical interface remain controlled, but the new PCB commit
must receive fresh commit-bound evidence and a new human signature.

## ECO candidate controls

- [x] Native KiCad schematic, board and project files are present.
- [x] Exact MK1/J1/C1/R1 identities, values, footprints and production-BOM bindings remain unchanged.
- [x] The independent structural audit still binds all 19 pins, 17 endpoint labels and two explicit NC markers to the frozen four-leaf harness.
- [x] DIM-004 still freezes the 24 x 22 x 1.0 mm board, two M2 holes and the 0.8 mm acoustic NPTH.
- [x] The `ECO_REQUIRED` decision is recorded against evidence commit `cb69c0bbc1457b498ee4f44ee7da1d566033c23f`.
- [x] The non-materialized B.Cu zone is removed from the source and generator.
- [x] The remote C1 return branch is replaced by one explicit 0.50 mm B.Cu segment from `(15.25, 13.25)` to `(15.00, 16.65)`.
- [x] The independent standard-library parser measures C1.2-to-MK1.2 return `7.108150 mm` and full decoupling loop `8.766161 mm`.
- [ ] Commit-bound KiCad 9 ERC and DRC reports pass with zero violations and zero unrouted items for the ECO candidate commit.
- [ ] Committed and regenerated geometry reports, CAM files, copper SVGs and SHA-256 manifest are archived for the ECO candidate commit.
- [ ] Reviewer, date, reviewed commit SHA and evidence links are recorded in `PCB_MIC_CAPTURE_STATUS_REV_A.json`.

Decision: `OPEN - REPEAT REVIEW A REQUIRED`.

Reviewer signature: `OPEN`

Date: `OPEN`

Reviewed ECO candidate commit: `OPEN`

## Superseded signature history

The previous Review-A signature by `Скиф`, dated `14.09.2026`, remains an immutable
historical record for commit `3e215e26e0d4cb160b309de3d3fd5a3145a756bf` and native
PCB SHA-256 `aecd1a374b5f66d32a5ae056eb4ad452d68e2a2391e65f6068acc8cad37f2295`.
It does not approve the changed PCB bytes and is marked
`SUPERSEDED_BY_COPPER_ECO_BOARD_BYTE_CHANGE` in the controlled status record.
The last pre-ECO status/checklist snapshot is commit
`ac124df132a911a2326c678d2ccebf37804c2444`.

Review B, independent CAM/DFM, panelization, the acoustic membrane/cavity stack and
physical calibration/EVT remain mandatory. PCB-MIC remains `NOT FOR MANUFACTURE`.
