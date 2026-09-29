#!/usr/bin/env python3
"""Classify each KiCad schematic-parity diagnostic in PCB-PWR Rev E."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "hardware/reviews/PCB_PWR_REVIEW_B_PACKAGE_REV_E"
INPUT = OUT / "PCB-PWR_parity_drc.json"
CSV = OUT / "PCB-PWR_parity_disposition.csv"
NOTE = OUT / "PCB-PWR_parity_disposition.md"
EXPECTED_BASE = {
    "HIERARCHICAL_NET_NAME_ONLY": 171,
    "INTENTIONALLY_UNCONNECTED_U5_NC": 1,
    "VALUE_FIELD_METADATA_PENDING_SYNC": 9,
    "BOM_ATTRIBUTE_PENDING_SYNC": 8,
}


def classify(entry: dict) -> tuple[str, str]:
    typ = entry["type"]
    desc = entry["description"]
    if typ == "net_conflict":
        if "unconnected-(U5-NC-Pad4)" in desc:
            return "INTENTIONALLY_UNCONNECTED_U5_NC", "No physical connection; retain NC."
        # KiCad localizes prose but keeps hierarchical net identifiers intact.
        nets = re.findall(r"\(([^()]*)\)", desc)
        hierarchical = [net for net in nets if net.startswith("/")]
        assert len(hierarchical) == 1, f"Unclassified net conflict: {desc}"
        schematic_net = hierarchical[0]
        board_net = schematic_net.rsplit("/", 1)[-1]
        assert board_net in nets and board_net != schematic_net, desc
        return "HIERARCHICAL_NET_NAME_ONLY", "Equivalent net suffix; primary 62-footprint net audit PASS."
    if typ == "footprint_symbol_field_mismatch":
        assert "Datasheet" in desc and "''" in desc, desc
        return "DATASHEET_FIELD_METADATA", "Board Datasheet blank; schematic field retained."
    if typ == "footprint_symbol_mismatch":
        item = entry["items"][0]
        ref = re.search(r"\b(?:R5|R9|R13|R14|R15|NT1|NT2|NT3)\b", item["description"])
        if ref:
            return "BOM_ATTRIBUTE_PENDING_SYNC", "DNP resistor or copper-only net tie; synchronize schematic BOM flag."
        assert "(" in desc and ")" in desc, desc
        return "VALUE_FIELD_METADATA_PENDING_SYNC", "Compare against controlled BOM; synchronize Value in a later ECO."
    raise AssertionError(f"Unclassified parity type: {typ}: {desc}")


def main() -> None:
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    diagnostics = data["schematic_parity"]
    rows = []
    for index, entry in enumerate(diagnostics, 1):
        disposition, follow_up = classify(entry)
        item = entry["items"][0]
        ref = re.search(r"(?:от |Посад\. место )(\w+)", item["description"])
        rows.append({
            "Index": index,
            "Type": entry["type"],
            "Reference": ref.group(1) if ref else "",
            "Item_UUID": item.get("uuid", ""),
            "X_mm": item.get("pos", {}).get("x", ""),
            "Y_mm": item.get("pos", {}).get("y", ""),
            "Disposition": disposition,
            "Follow_Up": follow_up,
            "Description": entry["description"],
        })
    counts = Counter(row["Disposition"] for row in rows)
    expected = EXPECTED_BASE | ({"DATASHEET_FIELD_METADATA": 62} if len(rows) == 251 else {})
    assert len(rows) in {189, 251} and dict(counts) == expected, counts
    with CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    NOTE.write_text(
        "# PCB-PWR Rev E — KiCad schematic-parity disposition\n\n"
        "Source: `PCB-PWR_parity_drc.json` from the same board and hierarchical schematic. "
        "Every diagnostic is indexed by item UUID in the accompanying CSV.\n\n"
        "| Class | Count | Disposition |\n|---|---:|---|\n"
        "| Hierarchical net name prefix | 171 | Equivalent final net name; primary connectivity audit PASS |\n"
        "| U5 NC pad 4 | 1 | Intentionally unconnected |\n"
        f"| Datasheet field | {counts['DATASHEET_FIELD_METADATA']} | Board field blank; schematic metadata retained |\n"
        "| Value field | 9 | Metadata sync against controlled BOM remains open |\n"
        "| Exclude-from-BOM attribute | 8 | Five DNP resistors and NT1–NT3; schematic flag sync remains open |\n\n"
        "There is no observed physical net mismatch. The KiCad parity command remains a "
        "diagnostic and is **not marked PASS** while the 17 Value/BOM attribute items are open. "
        "KiCad 9 reports 189 entries; KiCad 10 additionally reports 62 blank Datasheet fields. "
        "The Rev E R4 archive retains the 251-entry KiCad 10 disposition separately. "
        "This disposition does not replace the independent human Review B signature.\n",
        encoding="utf-8",
    )
    print(f"PCB-PWR parity disposition: {len(rows)} classified, 0 unexplained")


if __name__ == "__main__":
    main()
