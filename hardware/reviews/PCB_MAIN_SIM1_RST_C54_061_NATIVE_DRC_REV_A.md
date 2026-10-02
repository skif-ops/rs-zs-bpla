# PCB-MAIN candidate 061 — native KiCad 9 comparative DRC (2026-09-27)

- Working branch: `feature/pcb-main-completion`, draft PR #93; candidate
  remains separate from authoritative PCB-MAIN 003.
- Actions run: https://github.com/skif-ops/rs-zs-bpla/actions/runs/36304585746
  (`PCB-MAIN candidate 061 KiCad DRC`, success).
- KiCad CLI 9.0.9 after zone fill: unconnected items **81 → 80** across
  **59 nets**; no new DRC errors relative to candidate 060. The
  `SIM1_RST_CONN` open item is gone.
- Candidate SHA-256:
  `b733b350b14dcbad0c62e91f7b58a715a891b418bdeac28d17f88277e724b4d0`.
- Reproduced with
  `python3 tools/apply_pcb_main_sim1_rst_c54_061_rev_a.py --check` using
  `hardware/kicad/candidates/PCB-ROUTING-P2-SIM1-RST-C54-061/SUMMARY.json`
  and `drc_candidate.json` from the run artifact.

The 0.25/0.15 mm through via is allowed only by the candidate process
overlay. SIM reset return, the nearby GND_MIC plane, job-specific via DFM,
complete connectivity and SI/PI Review B still need review. This result is
not a PCB-MAIN production release.
