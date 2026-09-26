#!/usr/bin/env python3
"""Regression tests for Review B R2.001 (narrow branched groups in PCB-PWR current evidence).

The Rev A evidence generator cut every narrow group once, in the middle of its longest segment.
When that segment was a dead-end branch the group read 0 A: 1V8_MIC (U5.5 -> J2.5 with branches to
C8 and TP7) was reported 0 A / PASS although its main path carries the full 0.3 A of out_1v8.

Run: python tools/test_pcb_pwr_current_evidence_rev_a.py   (also collected by pytest)
Tests 1-4 need no board and no solver; test 5 reads the committed CURRENT_EVIDENCE.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_pwr_current_evidence_rev_a as ev  # noqa: E402

EVIDENCE = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-005/CURRENT_EVIDENCE.json"


def _probe(width: float, length: float) -> dict:
    return {"layer": "F.Cu", "at_mm": [0.0, 0.0], "segment_width_mm": width, "segment_length_mm": length}


def _branched_group() -> dict:
    """Main path: two short 0.5 mm segments carrying the load; dead end: one long 0.25 mm stub."""
    return {"length_mm": 16.0, "probes": [_probe(0.5, 1.5), _probe(0.5, 2.5), _probe(0.25, 12.0)],
            "short_segments": [{"layer": "F.Cu", "width_mm": 0.2, "length_mm": 0.05}]}


def test_worst_segment_not_longest_segment() -> None:
    group = _branched_group()
    summary = ev.summarise_group(group, {"load": [0.3, 0.3, 0.0]}, bound_a=0.3)
    longest = max(range(len(group["probes"])), key=lambda k: group["probes"][k]["segment_length_mm"])
    assert [0.3, 0.3, 0.0][longest] == 0.0, "fixture must reproduce the Rev A failure (longest = dead end)"
    assert summary["i_branch_a"] == 0.3, summary["i_branch_a"]
    assert summary["worst_segment"]["i_a"] == 0.3
    assert summary["cases"][0]["i_max_a"] == 0.3
    # delta-U along every loaded segment: 0.3 A through 1.5 + 2.5 mm of 0.5 mm copper and, conservatively,
    # through the 0.05 mm x 0.2 mm short neck; the 0 A dead end adds nothing (35 um, 70 C)
    r_main = ev.RHO_70C * 4.0e-3 / (0.5e-3 * ev.T_CU_M) * 1e3
    r_neck = ev.RHO_70C * 0.05e-3 / (0.2e-3 * ev.T_CU_M) * 1e3
    assert abs(summary["cases"][0]["du_mv_along_segments"] - 0.3 * (r_main + r_neck)) < 0.002


def test_short_segment_never_screened_at_zero() -> None:
    summary = ev.summarise_group(_branched_group(), {"load": [0.3, 0.3, 0.0]}, bound_a=0.3)
    short = [s for s in summary["segments_detail"] if s["at_mm"] is None]
    assert len(short) == 1 and short[0]["i_a"] == 0.3 and short[0]["current_basis"] == "GROUP_MAX_MEASURED"
    no_cut = ev.summarise_group({"length_mm": 0.05, "probes": [],
                                 "short_segments": [{"layer": "F.Cu", "width_mm": 0.25, "length_mm": 0.05}]},
                                {"load": []}, bound_a=5.0)
    assert no_cut["i_branch_a"] == 5.0 and no_cut["segments_detail"][0]["current_basis"] == "NET_CASE_BOUND_NO_CUT"


def test_status_uses_each_segment_width() -> None:
    """1.0 A is fine in a 0.5 mm segment (IPC 1.447 A) but not in a 0.2 mm one (0.745 A) of a long group."""
    group = {"length_mm": 10.0, "probes": [_probe(0.5, 5.0), _probe(0.2, 5.0)], "short_segments": []}
    summary = ev.summarise_group(group, {"load": [1.0, 1.0]}, bound_a=1.0)
    assert summary["status"] == "REVIEW"
    assert summary["worst_segment"]["width_mm"] == 0.2


def test_loaded_path_guard_catches_zero_on_the_path() -> None:
    result = {"cases": [{"id": "out_1v8", "net": "1V8_MIC", "from": "U5.5", "to": "J2.5", "current_a": 0.3}],
              "narrow": [{"net": "1V8_MIC", "pads": ["C8.1", "J2.5", "TP7.1", "U5.5"],
                          "cases": [{"case": "out_1v8", "i_max_a": 0.0}]}]}
    try:
        ev.assert_loaded_paths(result)
    except AssertionError:
        pass
    else:
        raise AssertionError("a 0 A reading on the source-to-sink group must fail")
    result["narrow"][0]["cases"][0]["i_max_a"] = 0.3
    assert len(ev.assert_loaded_paths(result)) == 1


def test_committed_evidence_1v8_mic_counterexample() -> None:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert data["schema"] == "dioneya-pcb-pwr-current-evidence-v2", "evidence not regenerated after R2.001"
    group = next(g for g in data["narrow"] if g["net"] == "1V8_MIC" and {"U5.5", "J2.5"} <= set(g["pads"]))
    out_1v8 = next(c for c in group["cases"] if c["case"] == "out_1v8")
    assert out_1v8["i_max_a"] >= 0.29, out_1v8
    assert group["i_branch_a"] >= 0.29 and group["status"] != "REVIEW"
    assert all(len(g["segments_detail"]) == g["segments"] for g in data["narrow"])
    assert any(r["case"] == "out_1v8" for r in data["loaded_path_check"])


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"R2.001 regression: {len(tests)} tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
