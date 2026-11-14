from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import cadquery as cq


folder = Path(sys.argv[1]).resolve()
release = json.loads((folder / "EVT_HOUSING_RELEASE_REV_A.json").read_text(encoding="utf-8"))
step = folder / release["master_step"]
model = cq.importers.importStep(str(step))
shape = model.val()
if not shape.isValid():
    raise RuntimeError("STEP shape is invalid")
solids = shape.Solids()
if len(solids) != 6:
    raise RuntimeError(f"STEP solid count {len(solids)} != 6")

validated_stl = []
for item in release["parts"]:
    path = folder / item["stl"]
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != item["stl_sha256"]:
        raise RuntimeError(f"STL checksum mismatch: {path.name}")
    if data.startswith(b"solid "):
        text = data.decode("ascii")
        facets = text.count("facet normal")
        vertices = text.count("vertex ")
        if facets <= 0 or vertices != facets * 3 or not text.rstrip().endswith("endsolid"):
            raise RuntimeError(f"invalid ASCII STL structure: {path.name}")
    else:
        if len(data) < 84:
            raise RuntimeError(f"invalid binary STL size: {path.name}")
        facets = int.from_bytes(data[80:84], "little")
        if len(data) != 84 + facets * 50:
            raise RuntimeError(f"invalid binary STL triangle table: {path.name}")
    validated_stl.append({"file": path.name, "facets": facets, "bytes": len(data)})

result = {
    "schema": "dioneya-evt-housing-validation-v1",
    "status": "PASS",
    "step_valid": True,
    "step_solids": len(solids),
    "step_sha256": hashlib.sha256(step.read_bytes()).hexdigest(),
    "stl_files": validated_stl,
    "drawing_pdf_bytes": (folder / release["drawing_pdf"]).stat().st_size,
    "drawing_pdf_sha256": hashlib.sha256((folder / release["drawing_pdf"]).read_bytes()).hexdigest(),
    "maximum_part_bbox_mm": release["maximum_part_bbox_mm"],
    "printer_build_volume_mm": release["printer_build_volume_mm"],
    "all_parts_fit_declared_printer": all(
        size <= limit
        for size, limit in zip(release["maximum_part_bbox_mm"], release["printer_build_volume_mm"])
    ),
    "physical_first_article_pending": True,
}
(folder / "EVT_HOUSING_VALIDATION_REV_A.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(result, indent=2, ensure_ascii=False))
