#!/usr/bin/env bash
# KiCad 9.0.9 DRC of the authoritative PCB-PWR board without and with the ECO-004
# U3/U4 land rule (hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_dru).
set -euo pipefail
IMAGE="ghcr.io/kicad/kicad:9.0.9@sha256:e638b79b0321f29395a5b783e94bb9f3c73303e8da15da27b8f5cb4b67a37729"
EVIDENCE="artifacts/kicad-native/PCB-PWR/eco-004-u3-u4-land-rule"
mkdir -p "$EVIDENCE"
docker run --rm --user root -v "$PWD":/w -w /w "$IMAGE" bash ci/pcb_pwr_eco_004_drc_inner.sh "$EVIDENCE"
python tools/audit_pcb_pwr_eco_004_drc_rev_a.py \
  --drc-without-rule "$EVIDENCE/drc_without_rule.json" \
  --drc-with-rule "$EVIDENCE/drc_with_rule.json" \
  --output "$EVIDENCE/eco_004_drc_audit.json"
