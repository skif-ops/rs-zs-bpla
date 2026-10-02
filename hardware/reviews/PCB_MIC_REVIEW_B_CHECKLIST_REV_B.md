# PCB-MIC Rev B — Review B approval

Status: `ACCEPT_CONTROLLED_FIRST_ARTICLE / SIGNED / RELEASED TO FAB AND PCBA`

Date: `2026-09-30`

Reviewer: `Скиф`

Reviewed design commit: `8d2e6229e453b186b10f2978e29c6df458c87b32`

Native board SHA-256: `c57cebbb3886247166551fd242fa51350bc9be7fee6299e63e7eaac60518d518`

Approval scope: `PCB_MIC_REVIEW_B_CONTROLLED_FIRST_ARTICLE`

## R1 disposition

- [x] Drill guide plotting is disabled in the authoritative board (`drillshape 0`).
- [x] Gerbers were regenerated without flashes at the acoustic or mounting NPTH centres.
- [x] PTH and NPTH Excellon files are separate; the acoustic port is NPTH Ø0.80 mm.
- [x] All 32 T5838 pad-3 segments are oriented radially in physical coordinates.
- [x] The uniform calculated copper-to-port clearance is 0.1125 mm.
- [x] T5838 paste follows Figure 33: four arcs, OD 1.525 mm, ID 1.025 mm, four 0.10 mm gaps.
- [x] Nominal stack is 2-layer, 1.0 mm FR-4, 35 µm copper, ENIG; the Gerber job carries Rev B and the stack.
- [x] KiCad 10.0.6 DRC: 0 violations and 0 unrouted items.
- [x] KiCad 10.0.6 ERC: 0 violations.
- [x] The 55 schematic-parity notices have an item-by-item disposition; none changes connectivity.
- [x] The PCBA BOM carries exact MPNs, including C1 `CGA2B3X7R1E104K050BB` and R1 `ERJ-2GE0R00X`.
- [x] Assembly instructions require the acoustic port to remain free from paste, adhesive and coating.

## Release decision

The reviewer decision provided in the project thread on 30.09.2026 authorizes the
corrected PCB-MIC Rev B for a controlled first-article order. Fabricate and assemble
one first article or one first panel, inspect the acoustic bore and stencil result,
then continue the remaining EVT-PRE-20 lot if that inspection passes.

Physical acoustic EVT remains an acceptance activity after assembly. It does not
block placing the controlled order. Any fabrication or assembly DFM observation is
handled through an ECO before changing the controlled files.

Decision: `ACCEPT_CONTROLLED_FIRST_ARTICLE`

Signed by reviewer: `Скиф`

Signed on: `2026-09-30`

