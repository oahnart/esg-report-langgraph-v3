import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "data/outputs/daewoong/2026_08_20/run_20260820T080949769457Z_9ee82a19/[langgraph][Daewoong]report-2026.08.20_6.xlsx";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 20,
  tableMaxCellChars: 140,
});

console.log(summary.ndjson);
