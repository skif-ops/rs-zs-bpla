# PCB-MIC Rev.A Review A checklist

Status: `OPEN / NOT SIGNED / NOT FOR MANUFACTURE`

Review A verifies the electrical source, exact identities, pin/net binding and
frozen mechanical interface. It does not approve layout manufacturing evidence.

- [x] Native KiCad schematic, board and project files are present.
- [x] Exact microphone is `MMICT5838-00-012`; all four station leaves use one PCB revision.
- [x] Exact six-circuit connector is Molex `5040500691` and its logical pin order is governed by the harness authority.
- [x] DIM-004 freezes the 24 x 22 x 1.0 mm board, two M2 holes and the 0.8 mm acoustic NPTH.
- [x] Fabrication metadata resolves to the active Rev.A mechanical addendum.
- [ ] Commit-matched KiCad 9 ERC report has zero unexplained violations.
- [ ] Independent schematic pin/net audit is archived against the reviewed commit.
- [ ] T5838 and Molex copper, mask, paste and drill geometry audits are archived against the reviewed commit.
- [ ] Exact passive MPN/value/population and the per-station quantity of four are reconciled to the production BOM.
- [ ] Reviewer, date, commit SHA and evidence links are recorded in the status file.

Decision: `OPEN`. Review B and physical acoustic evidence remain mandatory after
Review A is signed.
