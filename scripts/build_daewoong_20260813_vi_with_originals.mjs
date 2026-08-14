import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "data/outputs/daewoong/2026_08_13/run_20260813T101701905575Z_6c5b4a8e/[langgraph][Daewoong]report-2026.08.13_10.xlsx";
const priorOutputDir = "outputs/20260814_h200_vi_translation_daewoong_20260813_10";
const cachePath = `${priorOutputDir}/translations_cache.json`;
const outputDir = "outputs/20260814_h200_vi_translation_daewoong_20260813_10_keep_original";
const outputPath = `${outputDir}/[langgraph][Daewoong]report-2026.08.13_10_vi_keep_original.xlsx`;

const cache = JSON.parse(await fs.readFile(cachePath, "utf8"));
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const qualitative = workbook.worksheets.getItem("Qualitative");
const used = qualitative.getUsedRange();
const rowCount = used.values.length;

const headers = qualitative.getRange("A1:H1").values[0];
const originalEvidenceCol = headers.indexOf("Original Evidence");
const finalAnswerCol = headers.indexOf("Final Answer");
if (originalEvidenceCol === -1 || finalAnswerCol === -1) {
  throw new Error("Could not locate Original Evidence and Final Answer columns.");
}

const originalEvidenceValues = qualitative
  .getRangeByIndexes(1, originalEvidenceCol, rowCount - 1, 1)
  .values.map((row) => row[0]);
const finalAnswerValues = qualitative
  .getRangeByIndexes(1, finalAnswerCol, rowCount - 1, 1)
  .values.map((row) => row[0]);

const evidenceTranslations = [];
const answerTranslations = [];
let missing = 0;
for (let i = 0; i < rowCount - 1; i += 1) {
  const evidenceKey = `D${i + 2}`;
  const answerKey = `H${i + 2}`;
  const hasEvidence = typeof originalEvidenceValues[i] === "string" && originalEvidenceValues[i].trim();
  const hasAnswer = typeof finalAnswerValues[i] === "string" && finalAnswerValues[i].trim();
  const evidenceVi = hasEvidence ? cache[evidenceKey] : null;
  const answerVi = hasAnswer ? cache[answerKey] : null;
  if (hasEvidence && typeof evidenceVi !== "string") missing += 1;
  if (hasAnswer && typeof answerVi !== "string") missing += 1;
  evidenceTranslations.push([evidenceVi ?? null]);
  answerTranslations.push([answerVi ?? null]);
}
if (missing > 0) {
  throw new Error(`Translation cache is missing ${missing} expected cells.`);
}

await fs.mkdir(outputDir, { recursive: true });

qualitative.getRange("I1:J1").values = [["Original Evidence Vietnamese", "Final Answer Vietnamese"]];
qualitative.getRangeByIndexes(1, 8, rowCount - 1, 1).values = evidenceTranslations;
qualitative.getRangeByIndexes(1, 9, rowCount - 1, 1).values = answerTranslations;

qualitative.getRange("I1:J1").format = {
  fill: "#0F4C5C",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
qualitative.getRange(`I2:J${rowCount}`).format.wrapText = true;
qualitative.getRange("I:I").format.columnWidth = 70;
qualitative.getRange("J:J").format.columnWidth = 70;
qualitative.getRange("A1:J1").format.rowHeight = 28;
qualitative.getRange(`A2:J${rowCount}`).format.rowHeight = 96;
qualitative.freezePanes.freezeRows(1);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Qualitative",
  range: "A1:J8",
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 10,
  tableMaxCellChars: 140,
  maxChars: 12000,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 8000,
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const renderTargets = [
  { sheetName: "Qualitative", range: "A1:J20" },
  { sheetName: "Qualitative Table Metrics", range: "A1:I30" },
  { sheetName: "Quantitative", range: "A1:I30" },
];
for (const target of renderTargets) {
  const preview = await workbook.render({
    sheetName: target.sheetName,
    range: target.range,
    scale: 1,
    format: "png",
  });
  const safeSheetName = target.sheetName.replace(/[^A-Za-z0-9]+/g, "_");
  await fs.writeFile(`${outputDir}/${safeSheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }));
