# PCB-MIC Rev.A Review A checklist

Status: `PASS / REPEAT REVIEW A SIGNED / NOT FOR MANUFACTURE`

Review A was reopened because the native PCB bytes changed after the copper-return
review selected `ECO_REQUIRED`. The bounded ECO, unchanged schematic and mechanical
contract, exact component identities, pin/net binding, commit-bound evidence and
archived CAM outputs were reviewed again. Reviewer `Скиф` approved the controlled
evidence commit and exact PCB hash recorded below.

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
- [x] Reviewer, date, reviewed commit SHA and evidence links are recorded in `PCB_MIC_CAPTURE_STATUS_REV_A.json`.

## ECO candidate evidence

- Design commit: `159068f2743904fc366a4a65ede5fee829797ed2`.
- Reviewed controlled evidence commit: `e17a86bc78ba979f74c5549b378e94f7f3447fe4`.
- Native PCB SHA-256: `a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031`.
- CI: [run #431](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34851982915), `success`.
- PCB Native Gate: [run #161](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34851983013), `success`.
- Artifact: [evt-pre-20-kicad-native-gate](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34851983013/artifacts/10350269024), ID `10350269024`.
- Artifact ZIP SHA-256 and GitHub digest: `c54b6669b40fa4de3cd3b0515e4bdb742d90f4ab6f40a789eb1f7bb82dfd19ba`.
- Hash control: all 62 manifest entries, 12 controlled source hashes and 27 PCB-MIC output hashes independently verified.
- KiCad 9.0.9: ERC `0`, DRC `0`, unrouted `0`, schematic parity `0`.
- Archived internal CAM preflight: `PASS_ECO_CANDIDATE_CAM_PREFLIGHT_REPEAT_REVIEW_A_REQUIRED`.
- Copper audit: `ECO_CANDIDATE_EXPLICIT_LOCAL_RETURN_READY_FOR_REPEAT_REVIEW_A`.
- Copper drawings: F.Cu SHA-256 `fb5299746e8c6cc75bd71dd5915b05eae81e577aea1ac0b16d6262546143fe95`; B.Cu SHA-256 `66dc3609592146848e5f61cbd3a8a03ac56df8c3bb844164091cd6b9e195b901`.

Decision: `PASS` for repeat PCB-MIC Review A at controlled evidence commit
`e17a86bc78ba979f74c5549b378e94f7f3447fe4` and native PCB SHA-256
`a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031`.

Reviewer signature: `Скиф`

Date: `14.09.2026`

Reviewed ECO candidate commit: `e17a86bc78ba979f74c5549b378e94f7f3447fe4`

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
