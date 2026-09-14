# PCB-MIC Rev.A Review A checklist

Status: `PASS / SIGNED / NOT FOR MANUFACTURE`

Review A verifies the electrical source, exact identities, pin/net binding and
frozen mechanical interface. It does not approve layout manufacturing evidence.

- [x] Native KiCad schematic, board and project files are present.
- [x] Exact microphone is `MMICT5838-00-012`; all four station leaves use one PCB revision.
- [x] Exact six-circuit connector is Molex `5040500691` and its logical pin order is governed by the harness authority.
- [x] DIM-004 freezes the 24 x 22 x 1.0 mm board, two M2 holes and the 0.8 mm acoustic NPTH.
- [x] Fabrication metadata resolves to the active Rev.A mechanical addendum.
- [x] Independent structural audit binds all 19 pins, 17 endpoint labels and two explicit NC markers to the frozen four-leaf harness.
- [x] Exact MK1/J1/C1/R1 MPN, value, population and per-station quantity are reconciled to the production BOM.
- [x] Independent archiveable audit covers native-board and project-library T5838/Molex copper, mask, paste and drill geometry with source hashes and commit binding.
- [x] Commit-matched KiCad 9.0.9 ERC report has zero unexplained violations.
- [x] Remote gate run `34823813170` concluded `success` and archived the commit-matched JSON geometry reports and native `pcbnew` second-control logs in artifact `10339034239`.
- [x] Reviewer, date, reviewed commit SHA and evidence links are recorded in `PCB_MIC_CAPTURE_STATUS_REV_A.json`.

Decision: `PASS` for PCB-MIC Review A at reviewed commit
`3e215e26e0d4cb160b309de3d3fd5a3145a756bf`. GitHub Actions run
`34823813170` is successful; artifact `10339034239` contains KiCad 9.0.9 ERC
with zero errors and warnings, DRC with zero violations and unrouted items,
commit-bound geometry evidence, fabrication outputs and a 50-entry SHA-256
manifest independently verified without mismatch.

Reviewer signature: `Скиф`

Date: `14.09.2026`

This signature approves only Review A. Review B, independent CAM/DFM,
panelization, the acoustic membrane/cavity stack and physical calibration/EVT
remain mandatory. PCB-MIC remains `NOT FOR MANUFACTURE`.
