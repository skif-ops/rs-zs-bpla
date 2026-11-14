from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "releases" / "EVT_PRE_20_REV_D11" / "_documents"
SOURCE_MD = ROOT / "docs" / "evt_pre_20_rev_e"
FONT = "Times New Roman"
BODY_SIZE = 14
TABLE_SIZE = 12
FIRST_LINE_CM = 1.25

MARKDOWN_DOCUMENTS = (
    "00_Опись_и_статус_комплекта_Rev_E",
    "01_Техническое_задание_EVT_PRE_20_Rev_E",
    "02_Развертывание_Мухоеда_Windows11_Ubuntu2404",
    "03_Руководство_администратора_Мухоед",
    "04_Руководство_пользователя_Мухоед",
    "05_Выпуск_сертификатов_и_регистрация_станций",
    "06_Инструкция_монтажника_обновление_станции",
    "07_Методика_дополнительного_дообучения_Мухоед",
    "08_Проверка_сервера_dioneya_ru",
    "09_Пошаговая_инструкция_сборщика_EVT_PRE_20",
)

CURRENT_DOCX = (
    "EVT_PRE_20_ASSEMBLY_SETUP_INSTRUCTION_REV_B",
    "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_PROTOCOL_REV_A",
    "EVT_PRE_20_DIO_EVT_B01_PHYSICAL_EOL_PROGRAM_REV_B",
    "EVT_PRE_20_FIRMWARE_COMMISSIONING_TEST_MANUAL_REV_D",
    "EVT_PRE_20_FIRMWARE_LOCK_INTERLOCK_REV_A",
    "EVT_PRE_20_HARNESS_MANUFACTURING_WORK_INSTRUCTION_REV_B",
    "EVT_PRE_20_INSTALLATION_COMMISSIONING_INSTRUCTION_REV_B",
    "EVT_PRE_20_INSTRUCTION_REGISTER_REV_B",
    "EVT_PRE_20_LONG_RANGE_ACOUSTIC_HEAD_TRADE_STUDY_REV_C",
    "EVT_PRE_20_PKI_CERTIFICATE_LIFECYCLE_INSTRUCTION_REV_A",
    "EVT_PRE_20_PROCUREMENT_VARIANTS_21_41_NOTICE_REV_D8",
    "EVT_PRE_20_SERVER_DEPLOYMENT_BACKUP_OPERATIONS_INSTRUCTION_REV_A",
    "EVT_PRE_20_TIME_SYNCHRONIZATION_TRUST_INSTRUCTION_REV_A",
)

DASH_TRANSLATION = str.maketrans({"\u2011": "-", "\u2013": "-", "\u2014": "-"})


def clean_text(value: str) -> str:
    value = value.translate(DASH_TRANSLATION)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
    return value.strip()


def set_run_font(run, size: int, bold: bool | None = None) -> None:
    run.font.name = FONT
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attribute}"), FONT)


def set_paragraph_format(paragraph, *, table: bool, heading: bool = False) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(0)
    fmt.line_spacing = 1.0
    fmt.left_indent = Cm(0)
    fmt.right_indent = Cm(0)
    fmt.first_line_indent = Cm(0 if table else FIRST_LINE_CM)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for run in paragraph.runs:
        set_run_font(run, TABLE_SIZE if table else BODY_SIZE, True if heading else None)


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top: int = 60, start: int = 80, bottom: int = 60, end: int = 80) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def iter_table_paragraphs(table):
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                yield paragraph
            for nested in cell.tables:
                yield from iter_table_paragraphs(nested)


def replace_forbidden_dashes(doc: Document) -> None:
    paragraphs = list(doc.paragraphs)
    for table in doc.tables:
        paragraphs.extend(iter_table_paragraphs(table))
    for section in doc.sections:
        paragraphs.extend(section.header.paragraphs)
        paragraphs.extend(section.footer.paragraphs)
    for paragraph in paragraphs:
        for run in paragraph.runs:
            run.text = run.text.translate(DASH_TRANSLATION)


def configure_styles(doc: Document) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(BODY_SIZE)
    normal._element.rPr.rFonts.set(qn("w:ascii"), FONT)
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        if style_name not in styles:
            styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
        style = styles[style_name]
        style.font.name = FONT
        style.font.size = Pt(BODY_SIZE)
        style.font.bold = True
        style._element.rPr.rFonts.set(qn("w:ascii"), FONT)
        style._element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)
        style.paragraph_format.line_spacing = 1.0
        style.paragraph_format.first_line_indent = Cm(FIRST_LINE_CM)


def apply_document_format(doc: Document) -> None:
    configure_styles(doc)
    replace_forbidden_dashes(doc)
    for paragraph in doc.paragraphs:
        style_name = paragraph.style.name if paragraph.style else ""
        heading = style_name == "Title" or style_name.startswith("Heading")
        set_paragraph_format(paragraph, table=False, heading=heading)
    for table in doc.tables:
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = True
        for row_index, row in enumerate(table.rows):
            for cell in row.cells:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                set_cell_margins(cell)
                if row_index == 0:
                    set_cell_shading(cell, "D9EAF7")
                for paragraph in cell.paragraphs:
                    set_paragraph_format(paragraph, table=True, heading=False)
                    for run in paragraph.runs:
                        set_run_font(run, TABLE_SIZE, row_index == 0 or run.bold)
    for section in doc.sections:
        for paragraph in section.header.paragraphs:
            set_paragraph_format(paragraph, table=False)
        for paragraph in section.footer.paragraphs:
            set_paragraph_format(paragraph, table=False)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.first_line_indent = Cm(0)


def add_markdown_table(doc: Document, lines: list[str]) -> None:
    rows = [[clean_text(cell) for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in rows[1]):
        rows.pop(1)
    width = max(len(row) for row in rows)
    table = doc.add_table(rows=len(rows), cols=width)
    table.style = "Table Grid"
    for row_index, values in enumerate(rows):
        for col_index in range(width):
            text = values[col_index] if col_index < len(values) else ""
            paragraph = table.cell(row_index, col_index).paragraphs[0]
            run = paragraph.add_run(text)
            run.bold = row_index == 0


def markdown_to_docx(source: Path, destination: Path) -> None:
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(1.5)
    lines = source.read_text(encoding="utf-8").splitlines()
    index = 0
    in_code = False
    while index < len(lines):
        raw = lines[index].rstrip()
        if raw.strip().startswith("```"):
            in_code = not in_code
            index += 1
            continue
        if raw.strip().startswith("|") and raw.strip().endswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|") and lines[index].strip().endswith("|"):
                table_lines.append(lines[index])
                index += 1
            add_markdown_table(doc, table_lines)
            continue
        if not raw.strip():
            index += 1
            continue
        heading_match = re.match(r"^(#{1,4})\s+(.+)$", raw.strip())
        if heading_match:
            level = min(len(heading_match.group(1)), 4)
            paragraph = doc.add_paragraph(style="Title" if level == 1 else f"Heading {level - 1}")
            paragraph.add_run(clean_text(heading_match.group(2))).bold = True
        else:
            text = raw.strip()
            text = re.sub(r"^[-*+]\s+", "• ", text)
            paragraph = doc.add_paragraph()
            paragraph.add_run(clean_text(text))
        index += 1
    footer = section.footer.paragraphs[0]
    footer.text = "Дионея EVT-PRE-20. Производственный комплект REV_D11"
    doc.core_properties.author = "Проект Дионея"
    doc.core_properties.title = clean_text(lines[0].lstrip("# ")) if lines else destination.stem
    apply_document_format(doc)
    doc.save(destination)


def normalize_docx(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)
    doc = Document(destination)
    apply_document_format(doc)
    for section in doc.sections:
        footer = section.footer.paragraphs[0]
        footer.text = "Дионея EVT-PRE-20. Производственный комплект REV_D11"
        set_paragraph_format(footer, table=False)
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer.paragraph_format.first_line_indent = Cm(0)
    doc.core_properties.author = "Проект Дионея"
    doc.save(destination)


def audit_docx(path: Path) -> dict[str, object]:
    doc = Document(path)
    errors: list[str] = []
    body_count = 0
    table_count = 0
    for number, paragraph in enumerate(doc.paragraphs, start=1):
        if not paragraph.text.strip():
            continue
        body_count += 1
        style_name = paragraph.style.name if paragraph.style else ""
        heading = style_name == "Title" or style_name.startswith("Heading")
        fmt = paragraph.paragraph_format
        if fmt.line_spacing != 1.0:
            errors.append(f"paragraph {number}: line spacing")
        if fmt.space_before is None or fmt.space_before.pt != 0 or fmt.space_after is None or fmt.space_after.pt != 0:
            errors.append(f"paragraph {number}: paragraph spacing")
        if fmt.first_line_indent is None or abs(fmt.first_line_indent.cm - FIRST_LINE_CM) > 0.01:
            errors.append(f"paragraph {number}: first-line indent")
        if paragraph.alignment != WD_ALIGN_PARAGRAPH.JUSTIFY:
            errors.append(f"paragraph {number}: alignment")
        for run in paragraph.runs:
            if not run.text:
                continue
            if run.font.name != FONT:
                errors.append(f"paragraph {number}: font")
            if run.font.size is None or round(run.font.size.pt, 2) != BODY_SIZE:
                errors.append(f"paragraph {number}: size")
            if heading and run.bold is not True:
                errors.append(f"paragraph {number}: heading bold")
    for table_number, table in enumerate(doc.tables, start=1):
        table_count += 1
        for paragraph in iter_table_paragraphs(table):
            if not paragraph.text.strip():
                continue
            fmt = paragraph.paragraph_format
            indent = fmt.first_line_indent
            if indent is None or abs(indent.cm) > 0.01:
                errors.append(f"table {table_number}: first-line indent")
            if fmt.line_spacing != 1.0:
                errors.append(f"table {table_number}: line spacing")
            if fmt.space_before is None or fmt.space_before.pt != 0 or fmt.space_after is None or fmt.space_after.pt != 0:
                errors.append(f"table {table_number}: paragraph spacing")
            for run in paragraph.runs:
                if not run.text:
                    continue
                if run.font.name != FONT:
                    errors.append(f"table {table_number}: font")
                if run.font.size is None or round(run.font.size.pt, 2) != TABLE_SIZE:
                    errors.append(f"table {table_number}: size")
    all_text = "\n".join(p.text for p in doc.paragraphs)
    all_text += "\n" + "\n".join(p.text for table in doc.tables for p in iter_table_paragraphs(table))
    for character in ("\u2011", "\u2013", "\u2014"):
        if character in all_text:
            errors.append(f"forbidden character U+{ord(character):04X}")
    return {
        "file": path.name,
        "body_paragraphs": body_count,
        "tables": table_count,
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(set(errors)),
    }


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for stem in MARKDOWN_DOCUMENTS:
        markdown_to_docx(SOURCE_MD / f"{stem}.md", OUT / f"{stem}.docx")
    for stem in CURRENT_DOCX:
        normalize_docx(ROOT / "docs" / f"{stem}.docx", OUT / f"{stem}.docx")
    reports = [audit_docx(path) for path in sorted(OUT.glob("*.docx"))]
    failed = [report for report in reports if report["status"] != "PASS"]
    (OUT / "КОНТРОЛЬ_ФОРМАТА_DOCX.json").write_text(
        json.dumps({"documents": reports, "overall": "PASS" if not failed else "FAIL"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if failed:
        raise RuntimeError(json.dumps(failed, ensure_ascii=False, indent=2))
    print(json.dumps({"documents": len(reports), "overall": "PASS"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
