# PCB-MIC Rev.A Review B checklist

Status: `BLOCKED ON REPEAT REVIEW A AFTER COPPER ECO / NOT SIGNED / NOT FOR MANUFACTURE`

Review B is an independent PCB/CAM/assembly pass performed only after signed
Review A. The earlier Review-A signature is superseded for the changed board bytes,
so no Review-B item below can grant release until the ECO candidate receives a new
Review-A signature.

- [x] Native PCB contains a routed candidate rather than an empty placement canvas.
- [x] Mechanical outline, mounting pattern and acoustic opening are represented in native CAD.
- [ ] ECO candidate KiCad 9 DRC passes with zero violations and zero unrouted items.
- [ ] Copper return path and T5838 decoupling placement are independently accepted after repeat Review A.
  - [x] Baseline machine evidence measured the 22.248973 mm return and absent GND Gerber region.
  - [x] Reviewer `Скиф` selected `ECO_REQUIRED` on `14.09.2026` against evidence commit `cb69c0bbc1457b498ee4f44ee7da1d566033c23f`.
  - [x] The ECO candidate removes the non-materialized zone and adds a direct explicit 0.50 mm B.Cu C1 return.
  - [x] Local independent parsing measures the candidate return at 7.108150 mm and loop at 8.766161 mm.
  - [ ] Commit-bound candidate CAM and copper drawings are archived and independently reviewed.
- [ ] The bottom acoustic port has no paste, mask, adhesive or coating obstruction.
  - [x] Baseline CAM proved zero paste flashes at acoustic and mounting holes and exact F/B mask openings.
  - [ ] ECO candidate CAM reconfirms the baseline machine checks.
  - [ ] Adhesive and conformal-coating keepouts are accepted by the assembler.
- [ ] Gerber/Excellon, IPC-356, PnP, BOM and assembly/fabrication drawings are regenerated from the ECO candidate commit.
- [ ] Panelization, tooling rails and depanel method protect the MEMS microphone.
- [ ] PCB fabricator and assembler accept the T5838 fine-feature rule and close all DFM comments.
- [ ] Membrane/cavity tolerance stack and service assembly are frozen.
- [ ] Reviewer, date, Review-B commit SHA, source/output hashes and evidence links are recorded.

## Superseded baseline machine evidence

- Signed source commit: `3e215e26e0d4cb160b309de3d3fd5a3145a756bf`.
- Source PCB SHA-256: `aecd1a374b5f66d32a5ae056eb4ad452d68e2a2391e65f6068acc8cad37f2295`.
- CI: [run #428](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34840245983), `success`.
- PCB Native Gate: [run #158](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34840246015), `success`.
- Artifact: [evt-pre-20-kicad-native-gate](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34840246015/artifacts/10345408977), ID `10345408977`.
- Artifact digest: `sha256:f535c183a3feda6b4e2d38a636987b30aacaa0767103bec39379fbf042d95664`.
- Hash control: 62 manifest entries, 10 controlled source hashes and 27 PCB-MIC output hashes verified.
- Baseline KiCad 9.0.9: ERC `0`, DRC `0`, unrouted `0`.
- Baseline copper disposition: `ECO_REQUIRED`.

This evidence remains valid history for the superseded source bytes. It does not
validate or sign the ECO candidate.

## ECO candidate state

- Review A: `REVIEW_REQUIRED_AFTER_COPPER_ECO`.
- Review B: `BLOCKED_PENDING_REPEAT_REVIEW_A_AFTER_COPPER_ECO`.
- Candidate evidence: `PENDING_COMMIT_BOUND_CI`.
- Review-B decision: `OPEN` after repeat Review A.
- Manufacturing release: `false`.

Physical calibration and acoustic EVT begin only after assembled boards exist and
cannot be replaced by this checklist.
