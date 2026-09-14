# PCB-MIC Rev.A Review B checklist

Status: `INTERNAL CAM PREFLIGHT PASS / REVIEW B OPEN / NOT SIGNED / NOT FOR MANUFACTURE`

Review B is an independent PCB/CAM/assembly pass performed after signed Review A.

- [x] Native PCB contains a routed candidate rather than an empty placement canvas.
- [x] Mechanical outline, mounting pattern and acoustic opening are represented in native CAD.
- [x] KiCad 9 DRC passes with zero violations and zero unrouted items.
- [ ] Copper return path and T5838 decoupling placement are independently reviewed.
- [ ] The bottom acoustic port has no paste, mask, adhesive or coating obstruction.
  - [x] Internal CAM proves zero paste flashes at the acoustic and mounting holes and exact F/B mask openings.
  - [ ] Adhesive and conformal-coating keepouts are accepted by the assembler.
- [x] Gerber/Excellon, IPC-356, PnP, BOM and assembly/fabrication drawings are generated from one commit-bound preflight source set.
- [x] Independent machine CAM comparison confirms outline, drills, layers, polarity and connector orientation.
- [ ] Panelization, tooling rails and depanel method protect the MEMS microphone.
- [ ] PCB fabricator and assembler accept the T5838 fine-feature rule and close all DFM comments.
- [ ] Membrane/cavity tolerance stack and service assembly are frozen.
- [ ] Reviewer, date, commit SHA, source/output hashes and evidence links are recorded.

## Internal preflight evidence

- Evidence commit: `8264c6b8bc2ced3e0852a6e7f3d00318bffbc904`.
- CI: [run #424](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34834219791), `success`.
- PCB Native Gate: [run #154](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34834219819), `success`.
- Artifact: [evt-pre-20-kicad-native-gate](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34834219819/artifacts/10342982895), ID `10342982895`.
- Artifact digest: `sha256:11701d079ab95c2046fb14553fea822d84e70900af2f4a6e8f9ffbe5aa8b4188`.
- Audit result: `PASS_INTERNAL_CAM_PREFLIGHT_REVIEW_B_REMAINS_OPEN`.
- KiCad 9.0.9: ERC `0`, DRC `0`, unrouted `0`.
- Hash control: all `59` artifact-manifest entries and all `24` PCB-MIC output hashes independently verified.
- Signed source continuity: Review-A board SHA-256 `aecd1a374b5f66d32a5ae056eb4ad452d68e2a2391e65f6068acc8cad37f2295`.
- Controlled CAM derivative SHA-256: `3768ba97b0c21aca933795a52876aaa351f7dd19f5b39da2c7324c45e7d0e4c0`; design geometry unchanged.

This evidence closes only the internal machine-verifiable preflight. Human copper-return
review, panelization, fabricator/assembler DFM, adhesive/coating acceptance, acoustic
stack validation, physical EVT, independent Review-B signature and manufacturing
release remain open.

Decision: `HOLD`. Physical calibration and acoustic EVT begin only after assembled
boards exist; they cannot be replaced by this checklist.
