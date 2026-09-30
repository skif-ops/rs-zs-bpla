# PCB-MIC Rev B — controlled fabrication and assembly handoff

Release: `ACCEPT_CONTROLLED_FIRST_ARTICLE`

Build 80 PCBAs for the EVT-PRE-20 first lot of 20 stations. Process one board or one
panel first. Continue the remainder after bore, stencil, placement, solder and PDM
functional inspection passes.

## Bare board

- 24.00 × 22.00 mm, finished thickness 1.00 mm.
- Two copper layers, 35 µm nominal copper, FR-4, ENIG.
- H1/H2: NPTH Ø2.20 mm. Acoustic port: NPTH Ø0.80 mm at X12.00/Y16.65 in KiCad coordinates.
- Use the separate PTH and NPTH Excellon files. The acoustic port must never be plated.
- Electrical test: 100% against the supplied IPC-D-356 file.

## Assembly

- Fit MK1, J1, C1 and R1 on the top side.
- Exact C1 MPN: TDK `CGA2B3X7R1E104K050BB`.
- Exact R1 MPN: Panasonic `ERJ-2GE0R00X`.
- The T5838 stencil feature is the controlled four-arc pattern: OD 1.525 mm,
  ID 1.025 mm and four 0.10 mm gaps.
- Keep the Ø0.80 mm acoustic bore free from paste, adhesive, conformal coating,
  cleaning residue and mechanical obstruction.
- Use a MEMS-safe panel and depanel process that does not bend the PCB at MK1.

## First-article acceptance

Inspect the acoustic bore from both sides, solder alignment and contamination under
magnification. Run continuity and PDM data/clock/wake checks. Record the result before
releasing the rest of the lot. Acoustic calibration and membrane/cavity EVT follow
assembly under the programme and method documents.

Any requested change to stack, drill definition, land pattern, stencil, BOM, panel or
assembly process must be returned as a DFM comment and implemented by a controlled ECO.

