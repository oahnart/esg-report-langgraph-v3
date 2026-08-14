import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "data/outputs/daewoong/2026_08_13/run_20260813T101701905575Z_6c5b4a8e/[langgraph][Daewoong]report-2026.08.13_10.xlsx";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 20,
  tableMaxCellChars: 120,
});

console.log(summary.ndjson);
