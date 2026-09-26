#!/usr/bin/env python3
"""Export the PCB-PWR Review B package, Rev D (ECO-006 applied after the R2 decisions).

Run by .github/workflows/ci-apply.yml (docker available). Steps:
  1. current-carrying evidence for the authoritative ECO-006 board (tools/apply_pcb_pwr_current_evidence_rev_a.py,
     schema v2) -> hardware/kicad/candidates/PCB-PWR-ECO-006/CURRENT_EVIDENCE.json; copper is unchanged
     from ECO-005, so the numbers must match the Rev C evidence;
  2. the Rev B KiCad 9.0.9 exports (tools/apply_pcb_pwr_review_b_package_rev_b.py with the Rev D paths) on
     the authoritative board, project, rules and libraries;
  3. the R2/ECO-006 records: PCB_PWR_ECO_006_REV_A.md, PCB_PWR_REVIEW_B_R2_RESPONSE_REV_A.md and the
     ECO-006 candidate DFM register (as PCB_PWR_ECO_006_DFM_REGISTER.json);
  4. MANIFEST.json with the Rev C manifest as the previous round.
Rev A/B/C packages stay untouched. --check verifies the manifest binds the current board and inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import apply_pcb_pwr_current_evidence_rev_a as evidence_tool  # noqa: E402
import apply_pcb_pwr_review_b_package_rev_b as rev_b  # noqa: E402

OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_D"
ECO6 = ROOT / "hardware/kicad/candidates/PCB-PWR-ECO-006"
ECO6_BOARD = ECO6 / "PCB-PWR_ECO_006_CANDIDATE_REV_A.kicad_pcb"
EVIDENCE = ECO6 / "CURRENT_EVIDENCE.json"
REV_C_EVIDENCE = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_C/CURRENT_EVIDENCE.json"
REV_C_MANIFEST = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_C/MANIFEST.json"
ECO6_RECORD = ROOT / "hardware/reviews/PCB_PWR_ECO_006_REV_A.md"
R2_RECORD = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_R2_RESPONSE_REV_A.md"
DFM = ECO6 / "DFM_REGISTER.json"
ECO_006_SHA256 = "b8c1da6ca80b9e5d2795c4fee5b6926e4ab6169086795295e8e517a18def6ca7"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def use_rev_d_paths() -> None:
    rev_b.OUT = OUT
    rev_b.REL = OUT.relative_to(ROOT)
    rev_b.SCRATCH_ROOT = "build/review_b_rev_d_src"
    rev_b.SCRATCH = f"{rev_b.SCRATCH_ROOT}/PCB-PWR"
    rev_b.SRC_BOARD = f"{rev_b.SCRATCH}/PCB-PWR.kicad_pcb"
    rev_b.SRC_SCHEMATIC = f"{rev_b.SCRATCH}/PCB-PWR.kicad_sch"
    rev_b.EVIDENCE = EVIDENCE
    rev_b.ECO_RECORD = ECO6_RECORD


def evidence() -> dict:
    """Recompute the evidence on the ECO-006 board and compare it with the ECO-005 (Rev C) numbers."""
    evidence_tool.deps()
    data = evidence_tool.evaluate(ECO6_BOARD)
    EVIDENCE.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=float) + "\n", encoding="utf-8")
    assert not data["narrow_review"], "ECO-006 evidence leaves narrow copper for review"
    old = json.loads(REV_C_EVIDENCE.read_text(encoding="utf-8"))
    strip = lambda d: [{k: v for k, v in c.items()} for c in d["cases"]]  # noqa: E731
    same_cases = strip(old) == strip(data)
    same_narrow = [(g["net"], g["pads"], g["i_branch_a"], g["status"]) for g in old["narrow"]] == \
                  [(g["net"], g["pads"], g["i_branch_a"], g["status"]) for g in data["narrow"]]
    assert same_cases and same_narrow, "copper-unchanged ECO-006 must reproduce the ECO-005 evidence"
    return {"cases_identical_to_rev_c": same_cases, "narrow_identical_to_rev_c": same_narrow,
            "narrow_groups": len(data["narrow"]), "narrow_review": 0}


def generate() -> None:
    assert sha256(ROOT / "hardware/kicad/native/PCB-PWR/PCB-PWR.kicad_pcb") == ECO_006_SHA256, \
        "authoritative PCB-PWR is not the ECO-006 board"
    comparison = evidence()
    use_rev_d_paths()
    rev_b.generate()
    for path, name in ((ECO6_RECORD, ECO6_RECORD.name), (R2_RECORD, R2_RECORD.name),
                       (DFM, "PCB_PWR_ECO_006_DFM_REGISTER.json")):
        shutil.copyfile(path, OUT / name)
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest.update({
        "schema": "dioneya-pcb-pwr-review-b-package-v3",
        "revision": "REV_D",
        "responds_to": "Review B R2 decisions (DFM-PWR-02, DFM-PWR-03 fixed by ECO-006) - "
                       "hardware/reviews/PCB_PWR_ECO_006_REV_A.md",
        "previous_package_manifest_sha256": sha256(REV_C_MANIFEST),
        "eco_006_record_sha256": sha256(ECO6_RECORD), "r2_record_sha256": sha256(R2_RECORD),
        "dfm_register_sha256": sha256(DFM), "evidence_sha256": sha256(EVIDENCE),
        "evidence_comparison": comparison,
        "outputs": {str(p.relative_to(OUT)): sha256(p) for p in sorted(OUT.rglob("*"))
                    if p.is_file() and p.name != "MANIFEST.json"},
    })
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB-PWR Review B package Rev D: {len(manifest['outputs'])} files, DRC {manifest['drc']}, {comparison}")


def check() -> None:
    use_rev_d_paths()
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == "REV_D"
    assert manifest["board_sha256"] == sha256(ROOT / rev_b.BOARD) == ECO_006_SHA256, "package does not bind ECO-006"
    assert manifest["inputs"] == rev_b.inputs(), "package inputs (project/rules/schematic/libraries) drifted"
    assert manifest["evidence_sha256"] == sha256(EVIDENCE) and manifest["dfm_register_sha256"] == sha256(DFM)
    assert manifest["eco_006_record_sha256"] == sha256(ECO6_RECORD) and manifest["r2_record_sha256"] == sha256(R2_RECORD)
    for name, digest in manifest["outputs"].items():
        assert sha256(OUT / name) == digest, f"package output {name} differs from MANIFEST.json"
    assert manifest["drc"]["error_total"] == 0 and manifest["drc"]["unconnected_total"] == 0, "package DRC not clean"
    print(f"PCB-PWR Review B package Rev D: PASS {len(manifest['outputs'])} files, DRC {manifest['drc']['by_type']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
