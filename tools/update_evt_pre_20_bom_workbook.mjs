#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

const toolRoot = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES;
if (!toolRoot) throw new Error("CODEX_PRIMARY_RUNTIME_NODE_MODULES is not set");
const toolUrl = pathToFileURL(path.join(toolRoot, "@oai/artifact-tool/dist/artifact_tool.mjs")).href;
const { FileBlob, SpreadsheetFile, Workbook } = await import(toolUrl);

const root = process.cwd();
const workbookPath = path.join(root, "hardware/EVT_PRE_20_BOM_REV_A.xlsx");
const mode = process.argv[2] ?? "render";

const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

async function savePreview(filename, sheetName = "Engineering BOM", range = "A1:AC18") {
  const preview = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(filename, new Uint8Array(await preview.arrayBuffer()));
}

if (mode === "render") {
  const inspection = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 6000,
    tableMaxRows: 4,
    tableMaxCols: 8,
    tableMaxCellChars: 80,
  });
  console.log(inspection.ndjson);
  await savePreview("/tmp/evt_pre_20_bom_before.png");
  console.log("rendered=/tmp/evt_pre_20_bom_before.png");
} else if (mode === "update") {
  const sources = [
    ["Engineering BOM", "hardware/EVT_PRE_20_BOM_REV_A.csv"],
    ["Procurement", "hardware/EVT_PRE_20_BOM_PROCUREMENT_REV_A.csv"],
    ["Program 41", "hardware/EVT_PROGRAM_2X20_PLUS_1_PROCUREMENT_REV_A.csv"],
    ["RFQ", "hardware/CHINA_PROCUREMENT_RFQ.csv"],
  ];
  for (const [sheetName, relativeCsv] of sources) {
    const csvText = await fs.readFile(path.join(root, relativeCsv), "utf8");
    const csvWorkbook = await Workbook.fromCSV(csvText, { sheetName: "ImportedData" });
    const values = csvWorkbook.worksheets.getItem("ImportedData").getUsedRange().values;
    let sheet;
    let created = false;
    try {
      sheet = workbook.worksheets.getItem(sheetName);
    } catch {
      sheet = workbook.worksheets.add(sheetName);
      created = true;
    }
    const target = sheet.getRangeByIndexes(
      0, 0, values.length, values[0].length,
    );
    target.values = values;
    if (sheetName === "Program 41") {
      sheet.showGridLines = false;
      sheet.freezePanes.freezeRows(1);
      target.format = {
        font: { name: "Aptos", size: 10 },
        verticalAlignment: "top",
        wrapText: true,
        borders: { preset: "all", style: "thin", color: "#D9E2F3" },
      };
      sheet.getRangeByIndexes(0, 0, 1, values[0].length).format = {
        fill: "#1F4E78",
        font: { name: "Aptos Display", size: 10, bold: true, color: "#FFFFFF" },
        verticalAlignment: "center",
        wrapText: true,
      };
      sheet.getRange("A:E").format.columnWidth = 16;
      sheet.getRange("F:H").format.columnWidth = 26;
      sheet.getRange("I:S").format.columnWidth = 14;
      sheet.getRange("T:U").format.columnWidth = 24;
      sheet.getRange("V:Y").format.columnWidth = 34;
      if (created) sheet.tables.add(`A1:Y${values.length}`, true, "Program41Table");
    }
  }
  workbook.recalculate();
  const formulaErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    maxChars: 4000,
  });
  console.log(formulaErrors.ndjson);
  await savePreview("/tmp/evt_pre_20_bom_after.png");
  await savePreview("/tmp/evt_pre_20_rfq_after.png", "RFQ", "A1:S28");
  await savePreview("/tmp/evt_program_41_after.png", "Program 41", "A1:Y20");
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(workbookPath);
  console.log("updated=" + workbookPath);
  console.log("rendered=/tmp/evt_pre_20_bom_after.png");
  console.log("rendered=/tmp/evt_pre_20_rfq_after.png");
  console.log("rendered=/tmp/evt_program_41_after.png");
} else {
  throw new Error(`unknown mode: ${mode}`);
}
