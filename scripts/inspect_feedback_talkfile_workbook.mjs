import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "feedback_output/TalkFile_V2_V3_정성산출물_비교표 _260814.xlsx.xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 16000,
  tableMaxRows: 8,
  tableMaxCols: 20,
  tableMaxCellChars: 140,
});

console.log(summary.ndjson);
