import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = path.resolve(import.meta.dirname, "..");
const inputPath = path.join(root, "manufacturing", "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.json");
const outputPath = path.join(root, "manufacturing", "EVT_PRE_20_B01_HARDWARE_QUALIFICATION_REV_A.xlsx");
const previewDir = path.join(root, "outputs", "qa_b01_qualification_xlsx");
const record = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const summary = workbook.worksheets.add("Сводный лист");
const matrix = workbook.worksheets.add("Матрица испытаний");
const evidence = workbook.worksheets.add("Вложения");
const font = "Times New Roman";
const dark = "#1F4E78";
const light = "#D9EAF7";
const amber = "#FFF2CC";
const red = "#FCE4D6";
const green = "#E2F0D9";
const gray = "#E7E6E6";

for (const sheet of [summary, matrix, evidence]) {
  sheet.showGridLines = false;
  sheet.getRange("A1:N120").format.font = { name: font, size: 12, color: "#000000" };
  sheet.getRange("A1:N120").format.verticalAlignment = "center";
}

summary.getRange("A2:H2").merge();
summary.getRange("A2").values = [["Квалификация DIO-EVT-B01 / DIO-EVT-B01 qualification"]];
summary.getRange("A2:H2").format.font = { name: font, size: 14, bold: true, color: "#1F1F1F" };
summary.getRange("A2:H2").format.rowHeight = 28;
summary.getRange("A3:H3").format.borders = { bottom: { style: "thin", color: dark } };
summary.getRange("A5:B13").values = [
  ["Параметр / Field", "Значение / Value"],
  ["Протокол / Protocol", record.protocol_id],
  ["Изделие / Unit", record.unit.serial],
  ["Station ID", record.unit.station_id],
  ["Tenant", record.unit.tenant],
  ["Release ID", record.release.release_id],
  ["Release code", record.release.release_code],
  ["STM32 SHA-256", record.release.stm32_image_sha256],
  ["nRF signed SHA-256", record.release.nrf52840_signed_image_sha256],
];
summary.getRange("A5:B5").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("A6:A13").format.font = { name: font, size: 12, bold: true };
summary.getRange("B6:B13").format.wrapText = true;
summary.getRange("A15:B24").values = [
  ["Ворота / Gate", "Состояние / State"],
  ["Общий результат / Overall", null],
  ["Утверждены численные пределы / Numeric limits approved", "NO"],
  ["Полная регрессия / Full regression", "NOT_RUN"],
  ["Ответственный за выпуск / Release approver", ""],
  ["Контролер качества / Quality approver", ""],
  ["Production release ID", ""],
  ["Production option-byte profile", ""],
  ["Допуск / Eligibility", null],
  ["Состояние блокировки / Lock state", "DENIED"],
];
const firstTestRow = 5;
const lastTestRow = firstTestRow + record.tests.length - 1;
const evFirst = 5;
const evLast = evFirst + record.evidence_inventory.length - 1;
summary.getRange("B16").formulas = [[`=IF(AND(COUNTIFS('Матрица испытаний'!$E$${firstTestRow}:$E$${lastTestRow},"YES",'Матрица испытаний'!$F$${firstTestRow}:$F$${lastTestRow},"PASS")=COUNTIFS('Матрица испытаний'!$E$${firstTestRow}:$E$${lastTestRow},"YES"),COUNTIFS('Вложения'!$B$${evFirst}:$B$${evLast},"YES",'Вложения'!$G$${evFirst}:$G$${evLast},"PASS")=COUNTIFS('Вложения'!$B$${evFirst}:$B$${evLast},"YES")),"PASS",IF(COUNTIFS('Матрица испытаний'!$F$${firstTestRow}:$F$${lastTestRow},"FAIL")+COUNTIFS('Матрица испытаний'!$F$${firstTestRow}:$F$${lastTestRow},"HOLD")+COUNTIFS('Вложения'!$G$${evFirst}:$G$${evLast},"FAIL")+COUNTIFS('Вложения'!$G$${evFirst}:$G$${evLast},"HOLD")>0,"FAIL/HOLD","NOT_RUN/OPEN"))`]];
summary.getRange("B23").formulas = [["=IF(AND(B16=\"PASS\",B17=\"YES\",B18=\"PASS\",B19<>\"\",B20<>\"\",B19<>B20,B21<>\"\",B21<>B10,B22<>\"\",B22<>\"option_bytes_bench_rev_a.json\"),\"ELIGIBLE_FOR_SEPARATE_PRODUCTION_PROFILE\",\"DENIED\")"]];
summary.getRange("A15:B15").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("A16:A24").format.font = { name: font, size: 12, bold: true };
summary.getRange("B17:B22").format.fill = amber;
summary.getRange("B17").dataValidation = { rule: { type: "list", values: ["NO", "YES"] } };
summary.getRange("B18").dataValidation = { rule: { type: "list", values: ["NOT_RUN", "OPEN", "PASS", "FAIL", "HOLD"] } };
summary.getRange("B16:B24").format.wrapText = true;
summary.getRange("B16:B24").conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { bold: true, color: "#375623" } } });
summary.getRange("B16:B24").conditionalFormats.add("containsText", { text: "DENIED", format: { fill: red, font: { bold: true, color: "#9C0006" } } });
summary.getRange("B16:B24").conditionalFormats.add("containsText", { text: "NOT_RUN", format: { fill: gray, font: { bold: true, color: "#595959" } } });
summary.getRange("D5:H12").values = [
  ["Правило / Rule", "Описание / Description", null, null, null],
  ["PASS", "Все обязательные строки PASS, evidence и подписи полны.", null, null, null],
  ["OPEN / NOT_RUN", "Испытание или evidence не завершены. Допуск запрещен.", null, null, null],
  ["FAIL / HOLD", "Есть отказ или отклонение. Допуск запрещен до закрытия.", null, null, null],
  ["LOCK", "Эта форма не включает блокировку. Она разрешает подготовить отдельный production release.", null, null, null],
  ["RDP Level 2", "Запрещен без отдельного решения о необратимости.", null, null, null],
  ["Подписи", "Ответственный за выпуск и контролер качества должны быть разными лицами.", null, null, null],
  ["Секреты", "Закрытые ключи, pairing secret и пароли в evidence не прикладывают.", null, null, null],
];
for (let row = 5; row <= 12; row++) summary.getRange(`E${row}:H${row}`).merge();
summary.getRange("D5:H5").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("D6:D12").format.font = { name: font, size: 12, bold: true };
summary.getRange("E6:H12").format.wrapText = true;
summary.getRange("A5:B13").format.borders = { preset: "outside", style: "thin", color: "#B4C7E7" };
summary.getRange("A15:B24").format.borders = { preset: "outside", style: "thin", color: "#B4C7E7" };
summary.getRange("D5:H12").format.borders = { preset: "outside", style: "thin", color: "#B4C7E7" };
summary.getRange("A:A").format.columnWidth = 38;
summary.getRange("B:B").format.columnWidth = 72;
summary.getRange("C:C").format.columnWidth = 4;
summary.getRange("D:D").format.columnWidth = 22;
summary.getRange("E:H").format.columnWidth = 18;
summary.getRange("A5:H24").format.autofitRows();

matrix.getRange("A2:N2").merge();
matrix.getRange("A2").values = [["Матрица испытаний / Qualification test matrix"]];
matrix.getRange("A2:N2").format.font = { name: font, size: 14, bold: true };
const matrixHeaders = [["ID", "Группа / Group", "Проверка / Test RU", "Test EN", "Обяз. / Mandatory", "Статус / Status", "Результат / Measurement", "Предел / Limit", "Evidence path", "Evidence SHA-256", "Оператор / Operator", "Контролер / Reviewer", "UTC", "Примечание / Notes"]];
matrix.getRange("A4:N4").values = matrixHeaders;
matrix.getRange("A4:N4").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
const matrixRows = record.tests.map((t) => [t.id, t.group, t.test_ru, t.test_en, t.mandatory ? "YES" : "NO", t.status, t.measurement, t.approved_limit, t.evidence, t.evidence_sha256, t.operator, t.reviewer, t.timestamp_utc, t.notes]);
matrix.getRange(`A${firstTestRow}:N${lastTestRow}`).values = matrixRows;
matrix.getRange(`F${firstTestRow}:F${lastTestRow}`).dataValidation = { rule: { type: "list", values: record.allowed_test_statuses } };
matrix.getRange(`F${firstTestRow}:N${lastTestRow}`).format.fill = amber;
matrix.getRange(`A${firstTestRow}:N${lastTestRow}`).format.wrapText = true;
matrix.getRange(`F${firstTestRow}:F${lastTestRow}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { bold: true, color: "#375623" } } });
for (const state of ["FAIL", "HOLD"]) matrix.getRange(`F${firstTestRow}:F${lastTestRow}`).conditionalFormats.add("containsText", { text: state, format: { fill: red, font: { bold: true, color: "#9C0006" } } });
matrix.getRange(`F${firstTestRow}:F${lastTestRow}`).conditionalFormats.add("containsText", { text: "NOT_RUN", format: { fill: gray, font: { bold: true, color: "#595959" } } });
matrix.tables.add(`A4:N${lastTestRow}`, true, "B01QualificationTests").style = "TableStyleMedium2";
matrix.freezePanes.freezeRows(4);
matrix.freezePanes.freezeColumns(2);
const widths = [15, 20, 48, 48, 13, 15, 28, 34, 30, 22, 20, 20, 22, 28];
for (let i = 0; i < widths.length; i++) matrix.getRangeByIndexes(0, i, lastTestRow, 1).format.columnWidth = widths[i];
matrix.getRange(`A4:N${lastTestRow}`).format.autofitRows();

evidence.getRange("A2:G2").merge();
evidence.getRange("A2").values = [["Реестр доказательств / Evidence inventory"]];
evidence.getRange("A2:G2").format.font = { name: font, size: 14, bold: true };
evidence.getRange("A4:G4").values = [["ID", "Обяз. / Required", "Описание / Description RU", "Description EN", "Путь / Path", "SHA-256", "Статус / Status"]];
evidence.getRange("A4:G4").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
evidence.getRange(`A${evFirst}:G${evLast}`).values = record.evidence_inventory.map((e) => [e.id, e.required ? "YES" : "NO", e.description_ru, e.description_en, e.path, e.sha256, e.status]);
evidence.getRange(`E${evFirst}:G${evLast}`).format.fill = amber;
evidence.getRange(`G${evFirst}:G${evLast}`).dataValidation = { rule: { type: "list", values: record.allowed_test_statuses } };
evidence.getRange(`A${evFirst}:G${evLast}`).format.wrapText = true;
evidence.getRange(`G${evFirst}:G${evLast}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { bold: true, color: "#375623" } } });
for (const state of ["FAIL", "HOLD"]) evidence.getRange(`G${evFirst}:G${evLast}`).conditionalFormats.add("containsText", { text: state, format: { fill: red, font: { bold: true, color: "#9C0006" } } });
evidence.getRange(`G${evFirst}:G${evLast}`).conditionalFormats.add("containsText", { text: "NOT_RUN", format: { fill: gray, font: { bold: true, color: "#595959" } } });
evidence.tables.add(`A4:G${evLast}`, true, "B01EvidenceInventory").style = "TableStyleMedium2";
evidence.freezePanes.freezeRows(4);
evidence.getRange("A:A").format.columnWidth = 12;
evidence.getRange("B:B").format.columnWidth = 16;
evidence.getRange("C:D").format.columnWidth = 45;
evidence.getRange("E:E").format.columnWidth = 36;
evidence.getRange("F:F").format.columnWidth = 24;
evidence.getRange("G:G").format.columnWidth = 15;
evidence.getRange(`A4:G${evLast}`).format.autofitRows();

workbook.recalculate();
const summaryCheck = await workbook.inspect({ kind: "table", sheetId: "Сводный лист", range: "A5:H24", include: "values,formulas", tableMaxRows: 24, tableMaxCols: 8, maxChars: 12000 });
const matrixCheck = await workbook.inspect({ kind: "table", sheetId: "Матрица испытаний", range: `A4:N${lastTestRow}`, include: "values,formulas", tableMaxRows: 30, tableMaxCols: 14, maxChars: 16000 });
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan", maxChars: 6000 });
await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, fileName] of [["Сводный лист", "summary.png"], ["Матрица испытаний", "matrix.png"], ["Вложения", "evidence.png"]]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
await fs.writeFile(path.join(previewDir, "inspect_summary.ndjson"), summaryCheck.ndjson ?? String(summaryCheck), "utf8");
await fs.writeFile(path.join(previewDir, "inspect_matrix.ndjson"), matrixCheck.ndjson ?? String(matrixCheck), "utf8");
await fs.writeFile(path.join(previewDir, "inspect_errors.ndjson"), errors.ndjson ?? String(errors), "utf8");
console.log(`wrote ${outputPath}`);
console.log(`test rows ${record.tests.length}; evidence rows ${record.evidence_inventory.length}`);
