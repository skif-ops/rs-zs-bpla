import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const nodeModules = process.env.CODEX_NODE_MODULES;
if (!nodeModules) throw new Error("CODEX_NODE_MODULES is required");
const artifactModule = pathToFileURL(path.join(nodeModules, "@oai", "artifact-tool", "dist", "artifact_tool.mjs")).href;
const { SpreadsheetFile, Workbook } = await import(artifactModule);

const root = path.resolve(import.meta.dirname, "..");
const inputPath = path.join(root, "manufacturing", "MFG_004_DIO_EVT_B01_EOL_PROGRAM_REV_A.json");
const outputPath = path.join(root, "manufacturing", "MFG_004_DIO_EVT_B01_EOL_MEASUREMENT_REGISTER_REV_A.xlsx");
const previewDir = path.join(root, "outputs", "qa_mfg004_b01_eol_xlsx");
const record = JSON.parse(await fs.readFile(inputPath, "utf8"));

const workbook = Workbook.create();
// Keep worksheet identifiers ASCII-only. The XLSX exporter used by the build
// environment preserves Cyrillic cell text, but corrupts non-ASCII worksheet
// names embedded in formula references. Bilingual titles remain in every tab.
const summary = workbook.worksheets.add("Summary");
const contacts = workbook.worksheets.add("Contacts");
const measurements = workbook.worksheets.add("Measurements");
const msa = workbook.worksheets.add("MSA");
const evidence = workbook.worksheets.add("Evidence");
const sheets = [summary, contacts, measurements, msa, evidence];
const font = "Times New Roman";
const dark = "#1F4E78";
const light = "#D9EAF7";
const amber = "#FFF2CC";
const red = "#FCE4D6";
const green = "#E2F0D9";
const gray = "#E7E6E6";
const border = "#B4C7E7";

for (const sheet of sheets) {
  sheet.showGridLines = false;
  sheet.getRange("A1:AA160").format.font = { name: font, size: 12, color: "#000000" };
  sheet.getRange("A1:AA160").format.verticalAlignment = "center";
}

summary.getRange("A2:H2").merge();
summary.getRange("A2").values = [["DIO-EVT-B01 и EOL оснастка MFG-004 / Measurement register"]];
summary.getRange("A2:H2").format.font = { name: font, size: 14, bold: true, color: "#000000" };
summary.getRange("A3:H3").format.borders = { bottom: { style: "thin", color: dark } };
summary.getRange("A5:B13").values = [
  ["Параметр / Field", "Значение / Value"],
  ["Программа / Program", record.program_id],
  ["Статус исходного файла / Initial status", record.status],
  ["Оснастка / Fixture", record.fixture.id],
  ["Контактов pogo / Pogo contacts", record.fixture.contact_count],
  ["Изделие / Unit", record.unit.serial],
  ["Station ID", record.unit.station_id],
  ["Tenant", record.unit.tenant],
  ["Release ID", record.release_id],
];
summary.getRange("A5:B5").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("A6:A13").format.font = { name: font, size: 12, bold: true };
summary.getRange("B6:B13").format.wrapText = true;

const firstMeasurement = 5;
const lastMeasurement = firstMeasurement + record.steps.length - 1;
const firstMsa = 5;
const lastMsa = firstMsa + record.msa.length - 1;
summary.getRange("A15:B26").values = [
  ["Ворота / Gate", "Состояние / State"],
  ["Строки программы / Program rows", record.steps.length],
  ["PASS строк / PASS rows", null],
  ["FAIL строк / FAIL rows", null],
  ["HOLD строк / HOLD rows", null],
  ["OPEN limits", null],
  ["Готовых строк / Ready rows", null],
  ["MSA PASS", null],
  ["Полная регрессия / Full regression", "NOT_RUN"],
  ["Ответственный за выпуск / Release approver", ""],
  ["Контролер качества / Quality reviewer", ""],
  ["Общий результат / Overall", null],
];
summary.getRange("B17").formulas = [[`=COUNTIF('Measurements'!$X$${firstMeasurement}:$X$${lastMeasurement},"PASS")`]];
summary.getRange("B18").formulas = [[`=COUNTIF('Measurements'!$X$${firstMeasurement}:$X$${lastMeasurement},"FAIL")`]];
summary.getRange("B19").formulas = [[`=COUNTIF('Measurements'!$X$${firstMeasurement}:$X$${lastMeasurement},"HOLD")`]];
summary.getRange("B20").formulas = [[`=COUNTIF('Measurements'!$K$${firstMeasurement}:$K$${lastMeasurement},"*OPEN*")+COUNTIF('Measurements'!$K$${firstMeasurement}:$K$${lastMeasurement},"PARTIAL*")`]];
summary.getRange("B21").formulas = [[`=COUNTIF('Measurements'!$AA$${firstMeasurement}:$AA$${lastMeasurement},"READY")`]];
summary.getRange("B22").formulas = [[`=COUNTIF('MSA'!$E$${firstMsa}:$E$${lastMsa},"PASS")`]];
summary.getRange("B26").formulas = [[`=IF(B18>0,"FAIL",IF(AND(B21=B16,B22=${record.msa.length},B23="PASS",B24<>"",B25<>"",B24<>B25),"PASS",IF(COUNTIF('Measurements'!$X$${firstMeasurement}:$X$${lastMeasurement},"NOT_RUN")=B16,"NOT_RUN","HOLD")))`]];
summary.getRange("A15:B15").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("A16:A26").format.font = { name: font, size: 12, bold: true };
summary.getRange("B23:B25").format.fill = amber;
summary.getRange("B23").dataValidation = { rule: { type: "list", values: record.allowed_statuses } };
summary.getRange("B16:B26").format.wrapText = true;
summary.getRange("B26").conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { bold: true, color: "#375623" } } });
summary.getRange("B26").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: red, font: { bold: true, color: "#9C0006" } } });
summary.getRange("B26").conditionalFormats.add("containsText", { text: "HOLD", format: { fill: amber, font: { bold: true, color: "#9C6500" } } });
summary.getRange("D5:H14").values = [
  ["Правило / Rule", "Описание / Description", null, null, null],
  ["NOT_RUN", "Строка не выполнялась.", null, null, null],
  ["MEASURED", "Значение получено, приемочный предел еще не утвержден.", null, null, null],
  ["PASS", "Предел утвержден, результат соответствует, evidence и подписи полны.", null, null, null],
  ["FAIL", "Результат вне утвержденного предела или функция отказала.", null, null, null],
  ["HOLD", "Нет предела, калибровки, evidence или однозначного решения.", null, null, null],
  ["Open limit", "OPEN_B01_FREEZE и PARTIAL не допускают общий PASS.", null, null, null],
  ["Reviewer", "Оператор и контролер должны быть разными лицами.", null, null, null],
  ["Secrets", "Закрытые ключи, pairing secret, IMSI и пароли не прикладывают.", null, null, null],
  ["Lock", "Общий PASS не включает блокировку прошивки автоматически.", null, null, null],
];
for (let row = 5; row <= 14; row++) summary.getRange(`E${row}:H${row}`).merge();
summary.getRange("D5:H5").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
summary.getRange("D6:D14").format.font = { name: font, size: 12, bold: true };
summary.getRange("E6:H14").format.wrapText = true;
summary.getRange("A5:B13").format.borders = { preset: "outside", style: "thin", color: border };
summary.getRange("A15:B26").format.borders = { preset: "outside", style: "thin", color: border };
summary.getRange("D5:H14").format.borders = { preset: "outside", style: "thin", color: border };
summary.getRange("A:A").format.columnWidth = 42;
summary.getRange("B:B").format.columnWidth = 72;
summary.getRange("C:C").format.columnWidth = 4;
summary.getRange("D:D").format.columnWidth = 20;
summary.getRange("E:H").format.columnWidth = 18;
summary.getRange("A5:H26").format.autofitRows();

contacts.getRange("A2:N2").merge();
contacts.getRange("A2").values = [["Контакты EOL оснастки / EOL fixture contacts"]];
contacts.getRange("A2:N2").format.font = { name: font, size: 14, bold: true };
contacts.getRange("A4:N4").values = [["Group", "Contact", "X board", "Y board", "X fixture", "Y fixture", "Pad", "Pitch", "Pin name", "DUT direction", "Net", "Required network", "Safety class", "Status"]];
contacts.getRange("A4:N4").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
const contactRows = record.contacts.map((c) => [c.Fixture_Group, c.Contact, Number(c.Board_View_X_mm), Number(c.Board_View_Y_mm), Number(c.Bottom_Fixture_View_X_mm), Number(c.Bottom_Fixture_View_Y_mm), c.Pad, Number(c.Pitch_mm), c.Pin_Name, c.Direction_at_DUT, c.Net, c.Required_Network, c.Safety_Class, c.Initial_State]);
const contactFirst = 5;
const contactLast = contactFirst + contactRows.length - 1;
contacts.getRange(`A${contactFirst}:N${contactLast}`).values = contactRows;
contacts.getRange(`C${contactFirst}:F${contactLast}`).format.numberFormat = "0.00";
contacts.getRange(`H${contactFirst}:H${contactLast}`).format.numberFormat = "0.00";
contacts.getRange(`A${contactFirst}:N${contactLast}`).format.wrapText = true;
contacts.tables.add(`A4:N${contactLast}`, true, "MFG004Contacts").style = "TableStyleMedium2";
contacts.freezePanes.freezeRows(4);
contacts.freezePanes.freezeColumns(2);
const contactWidths = [18, 10, 12, 12, 12, 12, 18, 10, 22, 20, 24, 54, 38, 14];
for (let i = 0; i < contactWidths.length; i++) contacts.getRangeByIndexes(0, i, contactLast, 1).format.columnWidth = contactWidths[i];
contacts.getRange(`A4:N${contactLast}`).format.autofitRows();

measurements.getRange("A2:AA2").merge();
measurements.getRange("A2").values = [["Реестр измерений DIO-EVT-B01 / DIO-EVT-B01 measurement register"]];
measurements.getRange("A2:AA2").format.font = { name: font, size: 14, bold: true };
const measurementHeaders = [["Order", "Test ID", "Phase", "Fixture group", "Contacts", "Action RU", "Action EN", "Metric", "Unit", "Engineering target", "Limit state", "Approved lower", "Approved upper", "Approved discrete", "Actual numeric", "Actual text", "Instrument ID", "Calibration due", "Evidence path", "Evidence SHA-256", "Operator", "Reviewer", "UTC", "Status", "NCR/deviation", "Notes", "Row gate"]];
measurements.getRange("A4:AA4").values = measurementHeaders;
measurements.getRange("A4:AA4").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
const measurementRows = record.steps.map((t) => [t.order, t.test_id, t.phase, t.fixture_group, t.contacts, t.action_ru, t.action_en, t.metric, t.unit, t.engineering_target, t.limit_state, t.lower_limit === "" ? null : t.lower_limit, t.upper_limit === "" ? null : t.upper_limit, t.expected_discrete, null, "", "", "", "", "", "", "", "", t.initial_status, "", "", null]);
measurements.getRange(`A${firstMeasurement}:AA${lastMeasurement}`).values = measurementRows;
for (let row = firstMeasurement; row <= lastMeasurement; row++) {
  measurements.getRange(`AA${row}`).formulas = [[`=IF(X${row}<>"PASS","NOT_PASS",IF(OR(ISNUMBER(SEARCH("OPEN",K${row})),ISNUMBER(SEARCH("PARTIAL",K${row}))),"LIMIT_OPEN",IF(AND(OR(L${row}<>"",M${row}<>"",N${row}<>""),OR(O${row}<>"",P${row}<>""),Q${row}<>"",R${row}<>"",S${row}<>"",LEN(T${row})=64,U${row}<>"",V${row}<>"",U${row}<>V${row},W${row}<>""),"READY","INCOMPLETE")))`]];
}
measurements.getRange(`K${firstMeasurement}:Z${lastMeasurement}`).format.fill = amber;
measurements.getRange(`X${firstMeasurement}:X${lastMeasurement}`).dataValidation = { rule: { type: "list", values: record.allowed_statuses } };
measurements.getRange(`K${firstMeasurement}:K${lastMeasurement}`).dataValidation = { rule: { type: "list", values: ["APPROVED_DOCUMENTARY", "APPROVED_NUMERIC", "OPEN_B01_FREEZE", "PARTIAL_APPROVED_MIN_ONLY"] } };
measurements.getRange(`A${firstMeasurement}:AA${lastMeasurement}`).format.wrapText = true;
measurements.getRange(`X${firstMeasurement}:X${lastMeasurement}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { bold: true, color: "#375623" } } });
measurements.getRange(`X${firstMeasurement}:X${lastMeasurement}`).conditionalFormats.add("containsText", { text: "FAIL", format: { fill: red, font: { bold: true, color: "#9C0006" } } });
measurements.getRange(`X${firstMeasurement}:X${lastMeasurement}`).conditionalFormats.add("containsText", { text: "HOLD", format: { fill: amber, font: { bold: true, color: "#9C6500" } } });
measurements.getRange(`AA${firstMeasurement}:AA${lastMeasurement}`).conditionalFormats.add("containsText", { text: "READY", format: { fill: green, font: { bold: true, color: "#375623" } } });
measurements.getRange(`AA${firstMeasurement}:AA${lastMeasurement}`).conditionalFormats.add("containsText", { text: "OPEN", format: { fill: red, font: { bold: true, color: "#9C0006" } } });
measurements.tables.add(`A4:AA${lastMeasurement}`, true, "B01EOLMeasurements").style = "TableStyleMedium2";
measurements.freezePanes.freezeRows(4);
measurements.freezePanes.freezeColumns(2);
const measurementWidths = [9, 19, 20, 18, 15, 56, 56, 26, 12, 46, 28, 16, 16, 24, 18, 30, 24, 18, 36, 24, 20, 20, 22, 15, 22, 30, 18];
for (let i = 0; i < measurementWidths.length; i++) measurements.getRangeByIndexes(0, i, lastMeasurement, 1).format.columnWidth = measurementWidths[i];
measurements.getRange(`A4:AA${lastMeasurement}`).format.autofitRows();

msa.getRange("A2:J2").merge();
msa.getRange("A2").values = [["MSA и known-fault проверки / MSA and known-fault tests"]];
msa.getRange("A2:J2").format.font = { name: font, size: 14, bold: true };
msa.getRange("A4:J4").values = [["ID", "Action", "Acceptance", "Actual result", "Status", "Evidence path", "SHA-256", "Operator", "Reviewer", "UTC"]];
msa.getRange("A4:J4").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
const msaRows = record.msa.map((t) => [t.id, t.action, t.acceptance, "", t.status, "", "", "", "", ""]);
msa.getRange(`A${firstMsa}:J${lastMsa}`).values = msaRows;
msa.getRange(`D${firstMsa}:J${lastMsa}`).format.fill = amber;
msa.getRange(`E${firstMsa}:E${lastMsa}`).dataValidation = { rule: { type: "list", values: record.allowed_statuses } };
msa.getRange(`A${firstMsa}:J${lastMsa}`).format.wrapText = true;
msa.getRange(`E${firstMsa}:E${lastMsa}`).conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { bold: true, color: "#375623" } } });
msa.getRange(`E${firstMsa}:E${lastMsa}`).conditionalFormats.add("containsText", { text: "FAIL", format: { fill: red, font: { bold: true, color: "#9C0006" } } });
msa.tables.add(`A4:J${lastMsa}`, true, "MFG004MSA").style = "TableStyleMedium2";
msa.freezePanes.freezeRows(4);
const msaWidths = [18, 58, 44, 30, 15, 36, 24, 20, 20, 22];
for (let i = 0; i < msaWidths.length; i++) msa.getRangeByIndexes(0, i, lastMsa, 1).format.columnWidth = msaWidths[i];
msa.getRange(`A4:J${lastMsa}`).format.autofitRows();

evidence.getRange("A2:F2").merge();
evidence.getRange("A2").values = [["Структура evidence / Evidence structure"]];
evidence.getRange("A2:F2").format.font = { name: font, size: 14, bold: true };
evidence.getRange("A4:F4").values = [["Folder", "Contents RU", "Contents EN", "Required", "Path", "SHA-256 manifest"]];
evidence.getRange("A4:F4").format = { fill: dark, font: { name: font, size: 12, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", wrapText: true };
const evidenceRows = [
  ["00_identity", "Фото маркировки, traveller, release manifest", "Identity photo, traveller, release manifest", "YES", "", ""],
  ["01_fixture", "Схема, карта pogo, приемка и MSA MFG-004", "MFG-004 schematic, pogo map, acceptance and MSA", "YES", "", ""],
  ["02_power", "Сопротивления, rail waveforms, ток и thermal", "Resistance, rail waveforms, current and thermal", "YES", "", ""],
  ["03_programming", "STM32 и nRF logs, option bytes, verify", "STM32 and nRF logs, option bytes and verify", "YES", "", ""],
  ["04_modem", "BG95 debug, USB recovery и redacted AT logs", "BG95 debug, USB recovery and redacted AT logs", "YES", "", ""],
  ["05_audio", "WAV, mapping, THSEL, wake и calibration", "WAV, mapping, THSEL, wake and calibration", "YES", "", ""],
  ["06_rf_time", "GNSS PPS, LTE, LoRa и setup calibration", "GNSS PPS, LTE, LoRa and setup calibration", "YES", "", ""],
  ["07_server", "Heartbeat, event, receipt и reconnect", "Heartbeat, event, receipt and reconnect", "YES", "", ""],
  ["08_ota_recovery", "A/B, power cuts, rollback и recovery", "A/B, power cuts, rollback and recovery", "YES", "", ""],
  ["09_review", "Подписанные XLSX, JSON, NCR и manifest", "Signed XLSX, JSON, NCR and manifest", "YES", "", ""],
];
const evFirst = 5;
const evLast = evFirst + evidenceRows.length - 1;
evidence.getRange(`A${evFirst}:F${evLast}`).values = evidenceRows;
evidence.getRange(`E${evFirst}:F${evLast}`).format.fill = amber;
evidence.getRange(`A${evFirst}:F${evLast}`).format.wrapText = true;
evidence.tables.add(`A4:F${evLast}`, true, "B01EvidenceStructure").style = "TableStyleMedium2";
evidence.freezePanes.freezeRows(4);
const evidenceWidths = [24, 48, 48, 14, 40, 28];
for (let i = 0; i < evidenceWidths.length; i++) evidence.getRangeByIndexes(0, i, evLast, 1).format.columnWidth = evidenceWidths[i];
evidence.getRange(`A4:F${evLast}`).format.autofitRows();

workbook.recalculate();
const summaryCheck = await workbook.inspect({ kind: "table", sheetId: "Summary", range: "A5:H26", include: "values,formulas", tableMaxRows: 30, tableMaxCols: 8, maxChars: 14000 });
const measurementCheck = await workbook.inspect({ kind: "table", sheetId: "Measurements", range: `A4:AA${lastMeasurement}`, include: "values,formulas", tableMaxRows: 60, tableMaxCols: 27, maxChars: 26000 });
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 200 }, summary: "final formula error scan", maxChars: 8000 });
await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, fileName] of [["Summary", "summary.png"], ["Contacts", "contacts.png"], ["Measurements", "measurements.png"], ["MSA", "msa.png"], ["Evidence", "evidence.png"]]) {
  const preview = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  await fs.writeFile(path.join(previewDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
await fs.writeFile(path.join(previewDir, "inspect_summary.ndjson"), summaryCheck.ndjson ?? String(summaryCheck), "utf8");
await fs.writeFile(path.join(previewDir, "inspect_measurements.ndjson"), measurementCheck.ndjson ?? String(measurementCheck), "utf8");
await fs.writeFile(path.join(previewDir, "inspect_errors.ndjson"), errors.ndjson ?? String(errors), "utf8");
console.log(`wrote ${outputPath}`);
console.log(`contacts ${record.contacts.length}; measurement rows ${record.steps.length}; MSA rows ${record.msa.length}`);
