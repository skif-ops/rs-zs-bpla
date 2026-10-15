# EVT-PRE-20 current-source CAM candidate — 2026-10-16

Status: **CANDIDATE / HOLD FOR ENGINEERING REVIEW.** This directory is a reproducible export from commit `b6d9d620`. It is intentionally not marked as a manufacturing release.

For PCB-MAIN, PCB-PWR and PCB-MIC it contains native KiCad sources, Gerber, Excellon drill/maps, IPC-D-356, centroid/CPL, manufacturing/JLC BOM, schematic PDF, board STEP, ERC/DRC JSON, fabrication notes and per-board status.

The export records the actual state rather than suppressing it: PCB-MAIN authoritative 6-layer native source remains unrouted and has DRC errors/unconnected items; PCB-PWR has no unconnected items but retains seven native silkscreen warnings; PCB-MIC is DRC clean. `review_b` remains `OPEN` in every `STATUS.json`.

Altium projects and their separately hash-bound outputs are included in the external full candidate archive. They do not override the six-layer PCB-MAIN authority or close Review B.
