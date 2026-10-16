import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "file:///C:/Users/skifn/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";

const ROOT = "C:/Users/skifn/.codex/.chatgpt-projects/g-p-6a9a94a158908191920dd91e212ea701/evt_rev_d10_work";
const MFG = `${ROOT}/manufacturing`;
const OUTPUT = `${MFG}/EVT_PRE_20_OPERATION_CARDS_AND_CHECKLISTS_REV_B.xlsx`;
const PREVIEW = `${ROOT}/workbook_preview`;
const REPO = "F:/Проекты/Codex/rs-zs-bpla-evt-pre-20-release-final-lf-2026-10-16";

const serials = [...Array.from({ length: 40 }, (_, index) => `DIO-EVT-${String(index + 1).padStart(3, "0")}`), "DIO-EVT-B01"];
const harnesses = ["H-MIC1", "H-MIC2", "H-MIC3", "H-MIC4", "H-MAIN-PWR", "H-BAT-PWR"];
const stationLot = (serial) => serial === "DIO-EVT-B01" ? "BENCH" : Number(serial.slice(-3)) <= 20 ? "LOT-1" : "LOT-2";

async function csvMatrix(filePath, sheetName = "Data") {
  const text = (await fs.readFile(filePath, "utf8")).replace(/^\uFEFF/, "");
  const temp = await Workbook.fromCSV(text, { sheetName });
  const range = temp.worksheets.getItem(sheetName).getUsedRange(true);
  return range.values;
}

function colName(index) {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    value = Math.floor((value - 1) / 26);
  }
  return name;
}

function titleBlock(sheet, lastColumn, title, subtitle) {
  sheet.showGridLines = false;
  sheet.mergeCells(`A1:${lastColumn}1`);
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A1:${lastColumn}1`).format.fill = "#1F4E78";
  sheet.getRange(`A1:${lastColumn}1`).format.font = { name: "Arial", size: 16, bold: true, color: "#FFFFFF" };
  sheet.getRange(`A1:${lastColumn}1`).format.rowHeight = 28;
  sheet.mergeCells(`A2:${lastColumn}2`);
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A2:${lastColumn}2`).format.fill = "#D9EAF7";
  sheet.getRange(`A2:${lastColumn}2`).format.font = { name: "Arial", size: 9, italic: true, color: "#1F4E78" };
  sheet.getRange(`A2:${lastColumn}2`).format.wrapText = true;
  sheet.getRange(`A2:${lastColumn}2`).format.rowHeight = 34;
  sheet.freezePanes.freezeRows(4);
}

function styleTable(sheet, rowCount, colCount, widths, tableName) {
  const last = colName(colCount - 1);
  const header = sheet.getRange(`A4:${last}4`);
  header.format.fill = "#4472C4";
  header.format.font = { name: "Arial", size: 9, bold: true, color: "#FFFFFF" };
  header.format.wrapText = true;
  header.format.verticalAlignment = "center";
  header.format.rowHeight = 32;
  const body = sheet.getRange(`A5:${last}${rowCount + 4}`);
  body.format.font = { name: "Arial", size: 8.5, color: "#000000" };
  body.format.verticalAlignment = "center";
  body.format.wrapText = true;
  body.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  for (let index = 0; index < widths.length; index += 1) {
    sheet.getRangeByIndexes(0, index, rowCount + 4, 1).format.columnWidth = widths[index];
  }
  const table = sheet.tables.add(`A4:${last}${rowCount + 4}`, true, tableName);
  table.style = "TableStyleMedium2";
  table.showBandedRows = true;
  table.showFilterButton = true;
}

function statusRules(range) {
  range.conditionalFormats.add("containsText", { text: "PASS", format: { fill: "#C6EFCE", font: { color: "#006100", bold: true } } });
  range.conditionalFormats.add("containsText", { text: "READY", format: { fill: "#C6EFCE", font: { color: "#006100", bold: true } } });
  range.conditionalFormats.add("containsText", { text: "HOLD", format: { fill: "#FFEB9C", font: { color: "#9C6500", bold: true } } });
  range.conditionalFormats.add("containsText", { text: "OPEN", format: { fill: "#FCE4D6", font: { color: "#C65911", bold: true } } });
  range.conditionalFormats.add("containsText", { text: "FAIL", format: { fill: "#FFC7CE", font: { color: "#9C0006", bold: true } } });
  range.conditionalFormats.add("containsText", { text: "NOT_RUN", format: { fill: "#E7E6E6", font: { color: "#595959" } } });
}

function resultValidation(range) {
  range.dataValidation = { rule: { type: "list", values: ["NOT_RUN", "PASS", "FAIL", "HOLD", "N/A"] } };
}

function writeMatrixSheet(workbook, name, title, subtitle, matrix, widths, tableName) {
  const sheet = workbook.worksheets.getItem(name);
  const cols = matrix[0].length;
  const last = colName(cols - 1);
  titleBlock(sheet, last, title, subtitle);
  sheet.getRange("A4").write(matrix);
  styleTable(sheet, matrix.length - 1, cols, widths, tableName);
  return sheet;
}

const parameterMatrix = await csvMatrix(`${MFG}/MANUFACTURING_PARAMETER_APPROVAL_REGISTER_REV_B.csv`, "Parameters");
const routeMatrix = await csvMatrix(`${MFG}/ASSEMBLY_ROUTE_REV_B.csv`, "Route");
const harnessCardMatrix = await csvMatrix(`${MFG}/HARNESS_OPERATION_CARDS_REV_B.csv`, "HarnessCards");
const assemblyMatrix = await csvMatrix(`${MFG}/STATION_ASSEMBLY_CHECKLIST_REV_B.csv`, "Assembly");
const powerMatrix = await csvMatrix(`${MFG}/FIRST_POWER_CHECKLIST_REV_B.csv`, "Power");
const installationMatrix = await csvMatrix(`${MFG}/INSTALLATION_COMMISSIONING_CHECKLIST_REV_B.csv`, "Installation");
const travellerMatrix = await csvMatrix(`${MFG}/EVT_PRE_20_41_STATION_TRAVELLER_REGISTER_REV_B.csv`, "Travellers");
const eolMatrix = await csvMatrix(`${REPO}/manufacturing/EOL_RESULT_REGISTER.csv`, "EOL");

const workbook = Workbook.create();
for (const sheetName of ["Сводка", "Параметры", "Маршрут", "Карта жгутов", "Жгуты 41", "Сборка 41", "Первое включение", "EOL 41", "Монтаж 41", "Трэвеллер 41"]) {
  workbook.worksheets.add(sheetName);
}
const summary = workbook.worksheets.getItem("Сводка");
titleBlock(summary, "H", "СБОРКА, КОНТРОЛЬ И ОТЧЁТЫ EVT-PRE-20 REV_D10", "41 идентичность: DIO-EVT-001…040 + DIO-EVT-B01. Пустое обязательное поле или OPEN параметр блокируют PASS. / A blank mandatory field or OPEN parameter blocks PASS.");
summary.getRange("A4:C4").values = [["Показатель / Metric", "Значение / Value", "Статус / Status"]];
summary.getRange("A5:A13").values = [
  ["Операции маршрута / Route operations"],
  ["Контролируемые параметры / Controlled parameters"],
  ["Утверждено параметров / Approved parameters"],
  ["Открыто параметров / Open parameters"],
  ["Серий в реестре / Serial identities"],
  ["Сборка PASS / Assembly PASS"],
  ["Первое включение PASS / First power PASS"],
  ["EOL PASS"],
  ["Монтаж PASS / Installation PASS"],
];
summary.getRange("B5:B13").formulas = [
  ["=COUNTA('Маршрут'!A5:A36)"],
  ["=COUNTA('Параметры'!A5:A28)"],
  ["=COUNTIF('Параметры'!F5:F28,\"APPROVED\")"],
  ["=B6-B7"],
  ["=COUNTA('Сборка 41'!A5:A45)"],
  ["=COUNTIF('Сборка 41'!S5:S45,\"PASS\")"],
  ["=COUNTIF('Первое включение'!V5:V45,\"PASS\")"],
  ["=COUNTIF('EOL 41'!Q5:Q45,\"PASS\")"],
  ["=COUNTIF('Монтаж 41'!X5:X45,\"PASS\")"],
];
summary.getRange("C5:C13").formulas = [
  ["=IF(B5=32,\"READY\",\"HOLD\")"],
  ["=IF(B6=24,\"READY\",\"HOLD\")"],
  ["=IF(B7=B6,\"READY\",\"HOLD\")"],
  ["=IF(B8=0,\"READY\",\"HOLD\")"],
  ["=IF(B9=41,\"READY\",\"HOLD\")"],
  ["=IF(B10=41,\"READY\",\"HOLD\")"],
  ["=IF(B11=41,\"READY\",\"HOLD\")"],
  ["=IF(B12=41,\"READY\",\"HOLD\")"],
  ["=IF(B13=40,\"READY\",\"HOLD\")"],
];
summary.getRange("A15:E15").values = [["Решение / Decision", "Условие / Requirement", "Ответственный / Owner", "Статус / Status", "Комментарий / Comment"]];
summary.getRange("A16:C19").values = [
  ["Параметры утверждены / Parameters frozen", "24 parameter records APPROVED with source and evidence", "Chief engineer + QA"],
  ["41 stations assembled", "assembly + initial power + EOL PASS for 41", "Manufacturing + Test"],
  ["40 field stations ready", "installation PASS for DIO-EVT-001…040", "Field QA"],
  ["Final production lock", "hardware qualification, factory FA and firmware lock closed", "Release board"],
];
summary.getRange("D16:D19").formulas = [
  ["=IF(B8=0,\"READY\",\"HOLD\")"],
  ["=IF(AND(B10=41,B11=41,B12=41),\"READY\",\"HOLD\")"],
  ["=IF(B13=40,\"READY\",\"HOLD\")"],
  ["=IF(AND(D16=\"READY\",D17=\"READY\",D18=\"READY\"),\"READY\",\"HOLD\")"],
];
summary.getRange("E16:E19").values = [["OPEN parameters currently keep HOLD"], ["B01 and every field unit require records"], ["B01 is bench unless separately approved"], ["No automatic claim of final production readiness"]];
summary.getRange("A4:C13").format.borders = { preset: "all", style: "thin", color: "#B4C7E7" };
summary.getRange("A15:E19").format.borders = { preset: "all", style: "thin", color: "#B4C7E7" };
summary.getRange("A4:C4").format.fill = "#4472C4";
summary.getRange("A15:E15").format.fill = "#4472C4";
summary.getRange("A4:C4").format.font = { name: "Arial", size: 9, bold: true, color: "#FFFFFF" };
summary.getRange("A15:E15").format.font = { name: "Arial", size: 9, bold: true, color: "#FFFFFF" };
summary.getRange("A5:E19").format.font = { name: "Arial", size: 9, color: "#000000" };
summary.getRange("A5:E19").format.wrapText = true;
summary.getRange("A1:H19").format.verticalAlignment = "center";
summary.getRangeByIndexes(0, 0, 19, 1).format.columnWidth = 34;
summary.getRangeByIndexes(0, 1, 19, 1).format.columnWidth = 18;
summary.getRangeByIndexes(0, 2, 19, 1).format.columnWidth = 22;
summary.getRangeByIndexes(0, 3, 19, 1).format.columnWidth = 18;
summary.getRangeByIndexes(0, 4, 19, 1).format.columnWidth = 38;
statusRules(summary.getRange("C5:C13"));
statusRules(summary.getRange("D16:D19"));

const parameters = writeMatrixSheet(workbook, "Параметры", "РЕЕСТР УТВЕРЖДЕНИЯ ПАРАМЕТРОВ", "Численное значение становится приемочным только после APPROVED, источника, подписей и evidence SHA-256. / A numeric value becomes an acceptance limit only after approval, source, signatures and evidence SHA-256.", parameterMatrix, [14, 34, 38, 18, 18, 28, 20, 16, 38, 30], "ParametersRevB");
parameters.getRange("F5:F28").dataValidation = { rule: { type: "list", values: ["APPROVED", "OPEN_SUPPLIER_FIRST_ARTICLE", "OPEN_SUPPLIER_REVIEW", "OPEN_MECHANICAL_APPROVAL", "OPEN_VENDOR_APPROVAL", "OPEN_B01_FIRST_ARTICLE", "OPEN_B01_MEASUREMENT", "OPEN_SITE_DESIGN", "REJECTED"] } };
statusRules(parameters.getRange("F5:F28"));

const route = writeMatrixSheet(workbook, "Маршрут", "МАРШРУТ ПРОИЗВОДСТВА И КОНТРОЛЯ", "32 операции от проверки выпуска до lot release; применяется к двум группам по 20 и B01. / 32 operations from release verification through lot release for two groups of 20 plus B01.", routeMatrix, [12, 8, 44, 20, 32, 34, 34, 26, 14], "AssemblyRouteRevB");
route.getRange("I5:I36").dataValidation = { rule: { type: "list", values: ["OPEN", "IN_PROGRESS", "PASS", "FAIL", "HOLD", "N/A"] } };
statusRules(route.getRange("I5:I36"));

const harnessCards = writeMatrixSheet(workbook, "Карта жгутов", "ОПЕРАЦИОННАЯ КАРТА ЖГУТОВ", "First-off, crimp setup, 100 percent continuity, cross-short, resistance and evidence are mandatory. / Все обязательные операции выполняются по каждому применимому жгуту.", harnessCardMatrix, [13, 42, 20, 30, 34, 24, 18, 18, 38, 14], "HarnessOpsRevB");
harnessCards.getRange("J5:J21").dataValidation = { rule: { type: "list", values: ["NOT_RUN", "PASS", "FAIL", "HOLD", "N/A"] } };
statusRules(harnessCards.getRange("J5:J21"));

const harnessResultHeader = ["Serial", "Lot", "Harness", "Length_spec_mm", "Tolerance_mm", "First_Off", "Continuity", "Cross_Short", "Resistance", "Length", "Visual", "Tester_Log_SHA256", "Operator", "QC", "Overall"];
const harnessResultRows = [];
for (const serial of serials) {
  for (const harness of harnesses) {
    const length = harness.startsWith("H-MIC") ? 275 : harness === "H-MAIN-PWR" ? 440 : 330;
    harnessResultRows.push([serial, stationLot(serial), harness, length, 5, "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "NOT_RUN", "", "", "", ""]);
  }
}
const harnessResults = writeMatrixSheet(workbook, "Жгуты 41", "РЕЗУЛЬТАТЫ ЖГУТОВ ДЛЯ 41 СТАНЦИИ", "246 строк: шесть жгутов на каждую идентичность. PASS требует first-off, полного электрического и визуального контроля, исходного лога и двух подписей.", [harnessResultHeader, ...harnessResultRows], [16, 10, 16, 16, 14, 13, 13, 13, 13, 13, 13, 38, 18, 18, 14], "HarnessResults41");
harnessResults.getRange("O5").formulas = [["=IF(COUNTIF(F5:K5,\"NOT_RUN\")=6,\"NOT_RUN\",IF(AND(COUNTIF(F5:K5,\"PASS\")=6,L5<>\"\",M5<>\"\",N5<>\"\"),\"PASS\",\"HOLD\"))"]];
harnessResults.getRange("O5:O250").fillDown();
resultValidation(harnessResults.getRange("F5:K250"));
statusRules(harnessResults.getRange("O5:O250"));

for (let row = 1; row < assemblyMatrix.length; row += 1) {
  for (let col = 3; col <= 13; col += 1) assemblyMatrix[row][col] = "NOT_RUN";
  assemblyMatrix[row][18] = "";
}
const assembly = writeMatrixSheet(workbook, "Сборка 41", "СБОРКА 41 СТАНЦИИ", "Каждая строка связана с traveller. PASS требует 11 принятых операций, evidence SHA-256 и две подписи. / Each row is tied to a traveller and requires 11 accepted operations, evidence and two signatures.", assemblyMatrix, [16, 10, 18, 16, 18, 18, 18, 20, 18, 18, 16, 18, 16, 16, 38, 16, 18, 18, 14], "Assembly41");
assembly.getRange("S5").formulas = [["=IF(COUNTIF(D5:N5,\"NOT_RUN\")=11,\"NOT_RUN\",IF(AND(COUNTIF(D5:N5,\"PASS\")=11,O5<>\"\",Q5<>\"\",R5<>\"\"),\"PASS\",\"HOLD\"))"]];
assembly.getRange("S5:S45").fillDown();
resultValidation(assembly.getRange("D5:N45"));
statusRules(assembly.getRange("S5:S45"));

for (let row = 1; row < powerMatrix.length; row += 1) {
  powerMatrix[row][6] = "NOT_RUN";
  powerMatrix[row][7] = "NOT_RUN";
  powerMatrix[row][15] = "NOT_RUN";
  powerMatrix[row][21] = "";
}
const power = writeMatrixSheet(workbook, "Первое включение", "ПЕРВОЕ ВКЛЮЧЕНИЕ 41 СТАНЦИИ", "PAR-P01/P02/P03 must be APPROVED. Values are recorded, never inferred. Source power and thermal logs are mandatory. / Все фактические значения и исходные логи обязательны.", powerMatrix, [16, 9, 22, 18, 18, 18, 16, 18, 13, 16, 13, 13, 13, 13, 13, 16, 38, 38, 15, 18, 18, 14], "FirstPower41");
power.getRange("D5:D45").formulas = Array.from({ length: 41 }, () => ["='Параметры'!F23"]);
power.getRange("E5:E45").formulas = Array.from({ length: 41 }, () => ["='Параметры'!F24"]);
power.getRange("F5:F45").formulas = Array.from({ length: 41 }, () => ["='Параметры'!F25"]);
power.getRange("V5").formulas = [["=IF(COUNTIF(G5:P5,\"NOT_RUN\")=3,\"NOT_RUN\",IF(AND(D5=\"APPROVED\",E5=\"APPROVED\",F5=\"APPROVED\",G5=\"PASS\",H5=\"PASS\",I5<>\"\",J5<>\"\",K5<>\"\",L5<>\"\",M5<>\"\",N5<>\"\",O5<>\"\",P5=\"PASS\",Q5<>\"\",R5<>\"\",T5<>\"\",U5<>\"\"),\"PASS\",\"HOLD\"))"]];
power.getRange("V5:V45").fillDown();
resultValidation(power.getRange("G5:H45"));
resultValidation(power.getRange("P5:P45"));
statusRules(power.getRange("V5:V45"));

for (let row = 1; row < eolMatrix.length; row += 1) {
  for (let col = 8; col <= 15; col += 1) eolMatrix[row][col] = "NOT_RUN";
  eolMatrix[row][16] = "";
}
const eol = writeMatrixSheet(workbook, "EOL 41", "EOL ЖУРНАЛ ДЛЯ 41 ИДЕНТИЧНОСТИ", "Eight mandatory result groups plus original evidence, operator and reviewer. Rework requires complete regression EOL. / После ремонта выполняется полный повторный EOL.", eolMatrix, [16, 9, 22, 12, 22, 16, 16, 18, 14, 14, 14, 14, 14, 14, 16, 15, 14, 38, 15, 18, 18], "EOLRecords41");
eol.getRange("Q5").formulas = [["=IF(COUNTIF(I5:P5,\"NOT_RUN\")=8,\"NOT_RUN\",IF(AND(COUNTIF(I5:P5,\"PASS\")=8,R5<>\"\",T5<>\"\",U5<>\"\"),\"PASS\",\"HOLD\"))"]];
eol.getRange("Q5:Q45").fillDown();
resultValidation(eol.getRange("I5:P45"));
statusRules(eol.getRange("Q5:Q45"));

for (let row = 1; row < installationMatrix.length; row += 1) {
  for (let col = 8; col <= 17; col += 1) installationMatrix[row][col] = "NOT_RUN";
  installationMatrix[row][23] = "";
}
const installation = writeMatrixSheet(workbook, "Монтаж 41", "МОНТАЖ И ВВОД НА ОБЪЕКТЕ", "40 field units plus B01 record. B01 remains bench unless separately approved. Site parameters PAR-I01/I02/I03 are mandatory for PASS.", installationMatrix, [16, 18, 13, 13, 13, 18, 18, 18, 16, 16, 16, 14, 12, 12, 16, 16, 14, 15, 38, 38, 15, 18, 18, 14], "Installation41");
installation.getRange("F5:F45").formulas = Array.from({ length: 41 }, () => ["='Параметры'!F26"]);
installation.getRange("G5:G45").formulas = Array.from({ length: 41 }, () => ["='Параметры'!F27"]);
installation.getRange("H5:H45").formulas = Array.from({ length: 41 }, () => ["='Параметры'!F28"]);
installation.getRange("X5").formulas = [["=IF(COUNTIF(I5:R5,\"NOT_RUN\")=10,\"NOT_RUN\",IF(AND(F5=\"APPROVED\",G5=\"APPROVED\",H5=\"APPROVED\",COUNTIF(I5:R5,\"PASS\")=10,S5<>\"\",T5<>\"\",V5<>\"\",W5<>\"\"),\"PASS\",\"HOLD\"))"]];
installation.getRange("X5:X45").fillDown();
resultValidation(installation.getRange("I5:R45"));
statusRules(installation.getRange("X5:X45"));

for (let row = 1; row < travellerMatrix.length; row += 1) {
  for (let col = 3; col <= 12; col += 1) travellerMatrix[row][col] = "NOT_RUN";
  travellerMatrix[row][13] = 0;
  travellerMatrix[row][16] = "";
}
const travellers = writeMatrixSheet(workbook, "Трэвеллер 41", "СКВОЗНОЙ РЕЕСТР 41 СТАНЦИИ", "The register tracks every identity across procurement, PCBA, harnesses, assembly, first power, provisioning, EOL, installation and passport closure.", travellerMatrix, [16, 10, 18, 18, 14, 14, 14, 14, 16, 14, 14, 14, 16, 14, 38, 18, 14], "Traveller41");
travellers.getRange("Q5").formulas = [["=IF(COUNTIF(D5:M5,\"NOT_RUN\")=10,\"NOT_RUN\",IF(AND(COUNTIF(D5:M5,\"PASS\")=10,N5=0,O5<>\"\",P5<>\"\"),\"PASS\",\"HOLD\"))"]];
travellers.getRange("Q5:Q45").fillDown();
resultValidation(travellers.getRange("D5:M45"));
statusRules(travellers.getRange("Q5:Q45"));

await workbook.recalculate();

const inspect = await workbook.inspect({ kind: "workbook,sheet,table", maxChars: 12000, tableMaxRows: 7, tableMaxCols: 8, tableMaxCellChars: 90 });
console.log(inspect.ndjson ?? inspect);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, maxChars: 5000 });
console.log("FORMULA_ERROR_SCAN");
console.log(errors.ndjson ?? errors);

await fs.mkdir(MFG, { recursive: true });
await fs.mkdir(PREVIEW, { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(OUTPUT);

const previewSpecs = [
  ["Сводка", "A1:H19", "summary.png"],
  ["Параметры", "A1:J18", "parameters_top.png"],
  ["Маршрут", "A1:I18", "route_top.png"],
  ["Карта жгутов", "A1:J21", "harness_cards.png"],
  ["Сборка 41", "A1:S16", "assembly_top.png"],
  ["Первое включение", "A1:V14", "first_power_top.png"],
  ["EOL 41", "A1:U14", "eol_top.png"],
  ["Монтаж 41", "A1:X14", "installation_top.png"],
];
for (const [sheetName, range, filename] of previewSpecs) {
  const image = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(PREVIEW, filename), new Uint8Array(await image.arrayBuffer()));
  console.log(`RENDERED ${sheetName}!${range} -> ${filename}`);
}

console.log(`OUTPUT ${OUTPUT}`);
