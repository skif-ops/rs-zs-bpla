#!/usr/bin/env python3
"""Run the clean PCB-MIC generator without invoking KiCad's crashing Python ZONE_FILLER.

The zone object and its GND net remain in the native .kicad_pcb. This wrapper changes
only the Python-time fill operation. KiCad 9 CLI remains the independent authority for
DRC and manufacturing export. If CLI does not materialize/validate the zone correctly,
the gate must fail and the board stays NOT FOR MANUFACTURE.
"""
from __future__ import annotations

import pcbnew
import generate_pcb_mic_clean_rev_a as base


class _NoPythonZoneFill:
    def __init__(self, board):
        self.board = board

    def Fill(self, zones):
        print("Python ZONE_FILLER intentionally skipped; zone retained for KiCad CLI", flush=True)
        return None


pcbnew.ZONE_FILLER = _NoPythonZoneFill

if __name__ == "__main__":
    raise SystemExit(base.main())
