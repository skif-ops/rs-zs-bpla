# PCB-MIC Rev.A Review A checklist

Status: `REOPENED AFTER COPPER ECO / SIGNATURE REQUIRED / NOT FOR MANUFACTURE`

Review A was reopened because the native PCB bytes changed after the copper-return
review selected `ECO_REQUIRED`. The schematic, exact component identities, pin/net
binding and frozen mechanical interface remain controlled, but the new PCB commit
must receive fresh commit-bound evidence and a new human signature. The evidence is
now complete for design commit `159068f2743904fc366a4a65ede5fee829797ed2`;
the signature remains open.

## ECO candidate controls

- [x] Native KiCad schematic, board and project files are present.
- [x] Exact MK1/J1/C1/R1 identities, values, footprints and production-BOM bindings remain unchanged.
- [x] The independent structural audit still binds all 19 pins, 17 endpoint labels and two explicit NC markers to the frozen four-leaf harness.
- [x] DIM-004 still freezes the 24 x 22 x 1.0 mm board, two M2 holes and the 0.8 mm acoustic NPTH.
- [x] The `ECO_REQUIRED` decision is recorded against evidence commit `cb69c0bbc1457b498ee4f44ee7da1d566033c23f`.
- [x] The non-materialized B.Cu zone is removed from the source and generator.
- [x] The remote C1 return branch is replaced by one explicit 0.50 mm B.Cu segment from `(15.25, 13.25)` to `(15.00, 16.65)`.
- [x] The independent standard-library parser measures C1.2-to-MK1.2 return `7.108150 mm` and full decoupling loop `8.766161 mm`.
- [x] Commit-bound KiCad 9 ERC and DRC reports pass with zero violations and zero unrouted items for the ECO candidate commit.
- [x] Committed and regenerated geometry reports, CAM files, copper SVGs and SHA-256 manifest are archived for the ECO candidate commit.
- [ ] Reviewer, date, reviewed commit SHA and evidence links are recorded in `PCB_MIC_CAPTURE_STATUS_REV_A.json`.

## ECO candidate evidence

- Design commit: `159068f2743904fc366a4a65ede5fee829797ed2`.
- Native PCB SHA-256: `a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031`.
- CI: [run #430](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34850294478), `success`.
- PCB Native Gate: [run #160](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34850294515), `success`.
- Artifact: [evt-pre-20-kicad-native-gate](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34850294515/artifacts/10350416547), ID `10350416547`.
- Artifact ZIP SHA-256 and GitHub digest: `cc32b9f7327d9c1c8870c68f70419f96aa83b412973b2d7cde9ded711fb9f31d`.
- Hash control: all 62 manifest entries, 12 controlled source hashes and 27 PCB-MIC output hashes independently verified.
- KiCad 9.0.9: ERC `0`, DRC `0`, unrouted `0`, schematic parity `0`.
- Internal CAM preflight: `PASS_ECO_CANDIDATE_CAM_PREFLIGHT_REPEAT_REVIEW_A_REQUIRED`.
- Copper audit: `ECO_CANDIDATE_EXPLICIT_LOCAL_RETURN_READY_FOR_REPEAT_REVIEW_A`.
- Copper drawings: F.Cu SHA-256 `49d0cc972078861b5e790788bc9c36c6c84cf1ab98eec70e93949be74253a20c`; B.Cu SHA-256 `71f6100685f32c91a9eff8ff784ce6a5e1735044282ce4d80691b32101bfe3ed`.

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
