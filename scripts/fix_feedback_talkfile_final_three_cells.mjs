import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "outputs/20260814_h200_vi_translation_talkfile_feedback_full_vi/TalkFile_V2_V3_qualitative_comparison_260814_full_vi.xlsx";
const outputPath = inputPath;
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheet = workbook.worksheets.getItem("04_So_sanh_theo_muc");
sheet.getRange("AB34").values = [["Không thể so sánh"]];
sheet.getRange("AC34").values = [["Không thể so sánh"]];
sheet.getRange("AC66").values = [["Hòa"]];

const check = await workbook.inspect({
  kind: "match",
  searchTerm: "[가-힣]",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 8000,
});
console.log(check.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }));
