#!/usr/bin/env bash
# Executed inside the pinned KiCad 9.0.9 container by ci/pcb_pwr_eco_004_drc.sh.
set -euo pipefail
evidence="$1"
for kind in without_rule with_rule; do
  project="$(mktemp -d)"
  cp hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pro hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb "$project/"
  if [ "$kind" = with_rule ]; then cp hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_dru "$project/"; fi
  /usr/bin/python3 - "$project/PCB-PWR.kicad_pcb" <<'PY'
import sys
import pcbnew
board = pcbnew.LoadBoard(sys.argv[1])
assert board is not None
pcbnew.ZONE_FILLER(board).Fill(board.Zones())
board.Save(sys.argv[1])
PY
  kicad-cli pcb drc --format json --severity-all -o "$evidence/drc_$kind.json" "$project/PCB-PWR.kicad_pcb"
done
chmod -R a+rwX artifacts
