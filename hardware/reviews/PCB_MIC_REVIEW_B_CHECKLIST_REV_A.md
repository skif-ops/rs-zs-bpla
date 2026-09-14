# PCB-MIC Rev.A Review B checklist

Status: `COPPER RETURN ACCEPTED / REVIEW B OPEN / NOT SIGNED / NOT FOR MANUFACTURE`

Review B is an independent PCB/CAM/assembly pass performed after signed Review A.
Repeat Review A is signed for the copper ECO source and the independent copper-return
subgate is accepted. No machine preflight or subgate signature completes the remaining
DFM, panelization, acoustic-stack, physical-EVT or final Review-B gates below.

- [x] Native PCB contains a routed candidate rather than an empty placement canvas.
- [x] Mechanical outline, mounting pattern and acoustic opening are represented in native CAD.
- [x] ECO candidate KiCad 9 DRC passes with zero violations and zero unrouted items.
- [x] Copper return path and T5838 decoupling placement are independently accepted after repeat Review A.
  - [x] Baseline machine evidence measured the 22.248973 mm return and absent GND Gerber region.
  - [x] Reviewer `Скиф` selected `ECO_REQUIRED` on `14.09.2026` against evidence commit `cb69c0bbc1457b498ee4f44ee7da1d566033c23f`.
  - [x] The ECO candidate removes the non-materialized zone and adds a direct explicit 0.50 mm B.Cu C1 return.
  - [x] Local independent parsing measures the candidate return at 7.108150 mm and loop at 8.766161 mm.
  - [x] Commit-bound candidate CAM and copper drawings are archived and independently checked for evidence integrity.
  - [x] Repeat Review A is signed by `Скиф` for commit `e17a86bc78ba979f74c5549b378e94f7f3447fe4` and PCB SHA-256 `a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031`.
  - [x] Decision-input PCB Native Gate #163 reconfirms source continuity, CAM topology and zero ERC/DRC/unrouted findings for commit `7aeec13aa0c7ba1b3cd9095b800c6d08755912a3`.
  - [x] Reviewer `Скиф` selected `ACCEPT_COPPER_RETURN` on `14.09.2026` for that commit and PCB SHA-256 `a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031`.
  - [x] Post-acceptance PCB Native Gate #164 verifies the signed state at commit `8aa4a3d21b55956625db643e22436f248f75b258`; the copper audit records the accepted disposition while Review B and manufacturing release remain false.
- [ ] The bottom acoustic port has no paste, mask, adhesive or coating obstruction.
  - [x] Baseline CAM proved zero paste flashes at acoustic and mounting holes and exact F/B mask openings.
  - [x] ECO candidate CAM reconfirms the baseline machine checks.
  - [ ] Adhesive and conformal-coating keepouts are accepted by the assembler.
- [x] Gerber/Excellon, IPC-356, PnP, BOM and assembly/fabrication drawings are regenerated from the ECO candidate commit.
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

- Review A: `PASS`, repeat signature recorded for commit `e17a86bc78ba979f74c5549b378e94f7f3447fe4`.
- Review B: `OPEN_REMAINING_REVIEW_B_GATES_AFTER_COPPER_RETURN_ACCEPTANCE`.
- Candidate design commit: `159068f2743904fc366a4a65ede5fee829797ed2`.
- Native PCB SHA-256: `a292a6ec2be555519a4fcc44f3d6cfdf0bc38a7f214caff6e71786942e3e4031`.
- Candidate evidence: `PASS_COPPER_RETURN_SUBGATE_ACCEPTED_REVIEW_B_REMAINS_OPEN`.
- Decision-input evidence commit: `7aeec13aa0c7ba1b3cd9095b800c6d08755912a3`.
- CI: [run #433](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34873892866), `success`.
- PCB Native Gate: [run #163](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34873892890), `success`.
- Artifact: [evt-pre-20-kicad-native-gate](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34873892890/artifacts/10360925100), ID `10360925100`, SHA-256 `1986effdd10fdef86d97ffecb139dd7beea13ff699adeff8f481440e74630321`.
- Hash control: 62 manifest entries, 12 controlled source hashes and 27 PCB-MIC output hashes verified.
- Copper-return subgate: reviewer `Скиф`, date `14.09.2026`, decision `ACCEPT_COPPER_RETURN`, scope `PCB_MIC_REVIEW_B_COPPER_RETURN_SUBGATE_ONLY`.
- Post-acceptance evidence: PCB Native Gate [#164](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34878120514), CI [#434](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34878120579), artifact [10361911939](https://github.com/skif-ops/rs-zs-bpla/actions/runs/34878120514/artifacts/10361911939), digest `960f84ff068ddf881f01008a6844bfbbf7ed8b7f3e1720b73e6dadae11ee863e`.
- Post-acceptance archive verification: 62 manifest entries, 12 controlled source hashes, 27 PCB-MIC output hashes, regenerated preflight and copper audit byte-identical.
- Overall Review-B decision: `OPEN`.
- Manufacturing release: `false`.

Physical calibration and acoustic EVT begin only after assembled boards exist and
cannot be replaced by this checklist.
