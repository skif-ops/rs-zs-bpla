#!/usr/bin/env bash
# Executed inside the pinned KiCad 9.0.9 container by ci/pcb_pwr_eco_003_drc.sh.
set -euo pipefail
evidence="$1"
mkdir -p "$evidence"
project="$(mktemp -d)"
src="$evidence/boards"
for kind in BASE CANDIDATE; do
  cp hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pro "$project/PCB-PWR_J2_PLACEMENT_ECO_003_${kind}_REV_A.kicad_pro"
  cp "$src/PCB-PWR_J2_PLACEMENT_ECO_003_${kind}_REV_A.kicad_pcb" "$project/PCB-PWR_J2_PLACEMENT_ECO_003_${kind}_REV_A.kicad_pcb"
done
kicad-cli version
/usr/bin/python3 - "$project/PCB-PWR_J2_PLACEMENT_ECO_003_BASE_REV_A.kicad_pcb" \
  "$project/PCB-PWR_J2_PLACEMENT_ECO_003_CANDIDATE_REV_A.kicad_pcb" <<'PY'
import sys
import pcbnew
for path in sys.argv[1:]:
    board = pcbnew.LoadBoard(path)
    assert board is not None
    assert len(board.GetFootprints()) == 66
    assert len(list(board.GetTracks())) == 53
    assert len(list(board.Zones())) == 2
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(path)
print("PCB-PWR J2 placement ECO-003 KiCad 9 parse and fill: PASS")
PY
kicad-cli pcb drc --format json --severity-all -o "$evidence/baseline_drc.json" \
  "$project/PCB-PWR_J2_PLACEMENT_ECO_003_BASE_REV_A.kicad_pcb"
kicad-cli pcb drc --format json --severity-all -o "$evidence/candidate_drc.json" \
  "$project/PCB-PWR_J2_PLACEMENT_ECO_003_CANDIDATE_REV_A.kicad_pcb"
chmod -R a+rwX artifacts
