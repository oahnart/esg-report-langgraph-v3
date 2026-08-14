import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "outputs/20260814_h200_vi_translation_talkfile_feedback/TalkFile_V2_V3_qualitative_comparison_260814_vi.xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const summary = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 8,
  tableMaxCellChars: 160,
});

console.log(summary.ndjson);
