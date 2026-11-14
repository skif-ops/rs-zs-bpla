#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "tools" / "build_evt_pre_20_firmware_manual_rev_d.py"
DOCUMENTS = (
    (
        ROOT / "docs" / "evt_pre_20_rev_e" / "06_Инструкция_монтажника_обновление_станции.md",
        "Rev F",
        "Дионея EVT-PRE-20. Инструкция монтажника Rev F",
        "Инструкция монтажника EVT-PRE-20 Rev F",
        "Прошивка, commissioning, связь, LoRa, обновление и откат",
    ),
    (
        ROOT / "docs" / "evt_pre_20_rev_e" / "09_Пошаговая_инструкция_сборщика_EVT_PRE_20.md",
        "Rev B",
        "Дионея EVT-PRE-20. Инструкция сборщика Rev B",
        "Пошаговая инструкция сборщика станции Дионея EVT-PRE-20 Rev B",
        "Сборка, жгуты, антенны, питание, контроль и передача на EOL",
    ),
)


def load_builder():
    spec = importlib.util.spec_from_file_location("evt_role_doc_builder", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    builder = load_builder()
    for source, revision, footer, title, subject in DOCUMENTS:
        markdown = builder.normalize(source.read_text(encoding="utf-8"))
        output = source.with_suffix(".docx")
        builder.build_docx(markdown, output, footer, title, subject)
        builder.audit_docx(output, revision)
        print(f"wrote {output}")
    print("role instruction DOCX audits: PASS")


if __name__ == "__main__":
    main()
