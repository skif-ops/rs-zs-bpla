#!/usr/bin/env bash
# KiCad 9.0.9 comparative DRC for the PCB-PWR J2 placement ECO-003 candidate.
# Runs KiCad in the pinned official image (same digest as the engineering
# snapshot workflow), then the independent candidate audit on the host.
set -euo pipefail
IMAGE="ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
EVIDENCE="artifacts/kicad-native/PCB-PWR/j2-placement-eco-003"
python -m pip install --disable-pip-version-check kiutils==1.4.8
python tools/generate_pcb_pwr_j2_placement_eco_003_candidate_rev_a.py --output-dir "$EVIDENCE/boards"
docker run --rm --user root -v "$PWD":/w -w /w "$IMAGE" bash ci/pcb_pwr_eco_003_drc_inner.sh "$EVIDENCE"
python tools/audit_pcb_pwr_j2_placement_eco_003_candidate_rev_a.py \
  --drc-base "$EVIDENCE/baseline_drc.json" \
  --drc-candidate "$EVIDENCE/candidate_drc.json" \
  --output "$EVIDENCE/candidate_audit.json"
