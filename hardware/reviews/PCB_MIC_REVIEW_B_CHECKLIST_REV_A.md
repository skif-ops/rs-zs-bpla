# PCB-MIC Rev.A Review B checklist

Status: `OPEN / NOT SIGNED / NOT FOR MANUFACTURE`

Review B is an independent PCB/CAM/assembly pass performed after signed Review A.

- [x] Native PCB contains a routed candidate rather than an empty placement canvas.
- [x] Mechanical outline, mounting pattern and acoustic opening are represented in native CAD.
- [ ] KiCad 9 DRC passes with zero blocker/critical violations and zero unrouted items.
- [ ] Copper return path and T5838 decoupling placement are independently reviewed.
- [ ] The bottom acoustic port has no paste, mask, adhesive or coating obstruction.
- [ ] Gerber/Excellon, IPC-356, PnP, BOM and assembly/fabrication drawings are generated from one reviewed commit.
- [ ] Independent CAM comparison confirms outline, drills, layers, polarity and connector orientation.
- [ ] Panelization, tooling rails and depanel method protect the MEMS microphone.
- [ ] PCB fabricator and assembler accept the T5838 fine-feature rule and close all DFM comments.
- [ ] Membrane/cavity tolerance stack and service assembly are frozen.
- [ ] Reviewer, date, commit SHA, source/output hashes and evidence links are recorded.

Decision: `HOLD`. Physical calibration and acoustic EVT begin only after assembled
boards exist; they cannot be replaced by this checklist.
