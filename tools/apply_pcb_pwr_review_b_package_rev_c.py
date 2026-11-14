#!/usr/bin/env python3
"""Export the PCB-PWR Review B package, Rev C (response to Review B R2, REQUEST_CHANGES_R2).

Run by .github/workflows/ci-apply.yml (docker available). Same KiCad 9.0.9 exports as Rev B
(tools/apply_pcb_pwr_review_b_package_rev_b.py, reused with the Rev C output paths) on the same
authoritative board, plus the R2 evidence:
  CURRENT_EVIDENCE.json              per-segment narrow-branch evidence, schema v2 (R2.001)
  PCB_PWR_DFM_REGISTER_REV_A.json    measured DFM register against the JLCPCB capabilities (R2.002)
  PCB_PWR_REVIEW_B_R2_RESPONSE_REV_A.md   the R2 response record
  REVIEW_B_CHECKLIST.md              reviewer checklist, R2 findings -> response -> evidence
  MANIFEST.json                      inputs, commands, return codes, SHA-256 of every output, the
                                     Rev B manifest as the previous round
The Rev A and Rev B packages stay untouched as records of the earlier rounds.
--check verifies that MANIFEST.json binds the current board, inputs, evidence and register.
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
import apply_pcb_pwr_review_b_package_rev_b as rev_b  # noqa: E402

OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_C"
REV_B_MANIFEST = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_B/MANIFEST.json"
DFM_REGISTER = ROOT / "hardware/reviews/PCB_PWR_DFM_REGISTER_REV_A.json"
R2_RECORD = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_R2_RESPONSE_REV_A.md"
EXTRA = (DFM_REGISTER, R2_RECORD)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def use_rev_c_paths() -> None:
    rev_b.OUT = OUT
    rev_b.REL = OUT.relative_to(ROOT)
    rev_b.SCRATCH_ROOT = "build/review_b_rev_c_src"
    rev_b.SCRATCH = f"{rev_b.SCRATCH_ROOT}/PCB-PWR"
    rev_b.SRC_BOARD = f"{rev_b.SCRATCH}/PCB-PWR.kicad_pcb"
    rev_b.SRC_SCHEMATIC = f"{rev_b.SCRATCH}/PCB-PWR.kicad_sch"


def preconditions() -> dict:
    board = sha256(ROOT / rev_b.BOARD)
    evidence = json.loads(rev_b.EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["board_sha256"] == board, "current evidence does not bind the current board"
    assert evidence["schema"] == "dioneya-pcb-pwr-current-evidence-v2", "evidence predates the R2.001 fix"
    assert not evidence["narrow_review"], "current evidence leaves narrow copper for review"
    register = json.loads(DFM_REGISTER.read_text(encoding="utf-8"))
    assert register["board_sha256"] == board, "DFM register does not bind the current board"
    return {"evidence_schema": evidence["schema"], "narrow_groups": len(evidence["narrow"]),
            "narrow_review": len(evidence["narrow_review"]),
            "loaded_path_check": evidence["loaded_path_check"], "dfm_counts": register["counts"]}


def generate() -> None:
    use_rev_c_paths()
    summary = preconditions()
    rev_b.generate()  # KiCad exports, DRC, evidence copy; writes a Rev B-shaped manifest into OUT
    for path in EXTRA:
        shutil.copyfile(path, OUT / path.name)
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest.update({
        "schema": "dioneya-pcb-pwr-review-b-package-v3",
        "revision": "REV_C",
        "responds_to": "Review B R2 (REQUEST_CHANGES_R2) - hardware/reviews/PCB_PWR_REVIEW_B_R2_RESPONSE_REV_A.md",
        "previous_package_manifest_sha256": sha256(REV_B_MANIFEST),
        "r2_record_sha256": sha256(R2_RECORD),
        "dfm_register_sha256": sha256(DFM_REGISTER),
        "evidence_sha256": sha256(rev_b.EVIDENCE),
        "r2_summary": summary,
        "outputs": {str(path.relative_to(OUT)): sha256(path)
                    for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "MANIFEST.json"},
    })
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PCB-PWR Review B package Rev C: {len(manifest['outputs'])} files, DRC {manifest['drc']}, R2 {summary}")


def check() -> None:
    use_rev_c_paths()
    manifest = json.loads((OUT / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["revision"] == "REV_C"
    assert manifest["board_sha256"] == sha256(ROOT / rev_b.BOARD), "Review B package does not bind the current board"
    assert manifest["inputs"] == rev_b.inputs(), "Review B package inputs (project/rules/schematic/libraries) drifted"
    assert manifest["evidence_sha256"] == sha256(rev_b.EVIDENCE), "current evidence changed after the package"
    assert manifest["dfm_register_sha256"] == sha256(DFM_REGISTER), "DFM register changed after the package"
    assert manifest["r2_record_sha256"] == sha256(R2_RECORD), "R2 record changed after the package"
    for name, digest in manifest["outputs"].items():
        assert sha256(OUT / name) == digest, f"package output {name} differs from MANIFEST.json"
    assert manifest["drc"]["error_total"] == 0 and manifest["drc"]["unconnected_total"] == 0, "package DRC not clean"
    print(f"PCB-PWR Review B package Rev C: PASS {len(manifest['outputs'])} files, DRC {manifest['drc']['by_type']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
