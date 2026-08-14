import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "outputs/20260814_h200_vi_translation_talkfile_feedback/TalkFile_V2_V3_qualitative_comparison_260814_vi.xlsx";
const outputDir = "outputs/20260814_h200_vi_translation_talkfile_feedback_full_vi";
const outputPath = `${outputDir}/TalkFile_V2_V3_qualitative_comparison_260814_full_vi.xlsx`;
const cachePath = `${outputDir}/leftover_hangul_cache.json`;

function parseEnv(text) {
  const env = {};
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx === -1) continue;
    env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return env;
}

function normalizeBaseUrl(raw) {
  let base = (raw || "https://api.hallmdr.com").replace(/\/+$/, "");
  if (!base.toLowerCase().endsWith("/v1")) base += "/v1";
  return base;
}

function stripJsonFence(text) {
  return text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

async function translateBatch({ baseUrl, apiKey, model, batch }) {
  const response = await fetch(`${baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": "Mozilla/5.0",
    },
    body: JSON.stringify({
      model,
      temperature: 0,
      max_tokens: 5000,
      messages: [
        {
          role: "system",
          content:
            "Translate remaining Korean text into Vietnamese. Preserve V2/V3 labels, numbers, percentages, file names, IDs, URLs, sheet references, and formulas exactly. Return only valid JSON.",
        },
        {
          role: "user",
          content:
            "Translate each string into Vietnamese, preserving non-Korean technical tokens. Return a JSON array of strings in the same order.\n\n" +
            JSON.stringify(batch, null, 2),
        },
      ],
    }),
  });
  if (!response.ok) {
    throw new Error(`HallMDR request failed ${response.status}: ${(await response.text()).slice(0, 500)}`);
  }
  const json = await response.json();
  const parsed = JSON.parse(stripJsonFence(json.choices[0].message.content));
  if (!Array.isArray(parsed) || parsed.length !== batch.length) {
    throw new Error("Unexpected translation response shape.");
  }
  return parsed.map((item) => String(item).trim());
}

function chunkItems(items, maxChars = 7000, maxItems = 10) {
  const chunks = [];
  let chunk = [];
  let chars = 0;
  for (const item of items) {
    const size = item.text.length + 160;
    if (chunk.length && (chunk.length >= maxItems || chars + size > maxChars)) {
      chunks.push(chunk);
      chunk = [];
      chars = 0;
    }
    chunk.push(item);
    chars += size;
  }
  if (chunk.length) chunks.push(chunk);
  return chunks;
}

const env = parseEnv(await fs.readFile(".env", "utf8"));
const apiKey = env.HALLMDR_API_KEY || env.ESG_LLM_API_KEY;
const baseUrl = normalizeBaseUrl(env.ESG_LLM_BASE_URL || env.HALLMDR_API_BASE_URL);
const model = env.ESG_QUICK_THINK_LLM || "llm/gemma4";
if (!apiKey) throw new Error("HALLMDR_API_KEY or ESG_LLM_API_KEY is required.");

await fs.mkdir(outputDir, { recursive: true });
let cache = {};
try {
  cache = JSON.parse(await fs.readFile(cachePath, "utf8"));
} catch {
  cache = {};
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const items = [];
const payloads = [];
const sheetPayloads = [];

function cleanup(text) {
  return String(text)
    .replaceAll("02_종합비교", "02_So_sanh_tong_hop")
    .replaceAll("04_항목별비교", "04_So_sanh_theo_muc")
    .replaceAll("03_지표실측", "03_Chi_so_thuc_do")
    .replaceAll("01_평가기준", "01_Tieu_chi_danh_gia")
    .replaceAll("00_결론요약", "00_Tom_tat_ket_luan")
    .replaceAll("05_대표사례", "05_Truong_hop_tieu_bieu")
    .replaceAll("V2 우세", "V2 ưu thế")
    .replaceAll("V3 우세", "V3 ưu thế")
    .replaceAll("3건 동률", "3 mục hòa")
    .replaceAll("비교불가", "Không thể so sánh")
    .replaceAll("동률", "Hòa")
    .replaceAll("(전체)", "(Toàn bộ)")
    .replaceAll("3문장 이상 28건만", "chỉ 28 trường hợp từ 3 câu trở lên")
    .replaceAll("길이 통제", "kiểm soát độ dài")
    .replaceAll("외부 평가 자료상 또한,", "theo tài liệu đánh giá bên ngoài,")
    .replaceAll("건", "trường hợp");
}

for (const sheet of workbook.worksheets) {
  const used = sheet.getUsedRange();
  const values = used.values;
  const formulas = used.formulas;
  const rowCount = values.length;
  const colCount = values[0]?.length ?? 0;
  const sheetPayload = { sheet, values, rowCount, colCount };
  sheetPayloads.push(sheetPayload);
  for (let r = 0; r < rowCount; r += 1) {
    for (let c = 0; c < colCount; c += 1) {
      const value = values[r]?.[c];
      const formula = formulas[r]?.[c];
      if (typeof value !== "string" || (formula && String(formula).trim())) continue;
      const cleaned = cleanup(value);
      if (cleaned !== value) {
        values[r][c] = cleaned;
      }
      if (!/[가-힣]/.test(cleaned)) continue;
      const key = `${sheet.name}!R${r + 1}C${c + 1}`;
      payloads.push({ sheetPayload, key, rowIndex: r, colIndex: c, text: cleaned });
      if (typeof cache[key] !== "string") items.push({ key, text: cleaned });
    }
  }
}

console.log(JSON.stringify({ leftoverHangulCells: payloads.length, cached: payloads.length - items.length, remaining: items.length }));

for (const chunk of chunkItems(items)) {
  const translations = await translateBatch({ baseUrl, apiKey, model, batch: chunk.map((item) => item.text) });
  for (let i = 0; i < chunk.length; i += 1) {
    cache[chunk[i].key] = translations[i];
  }
  await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");
  console.log(JSON.stringify({ translated: Object.keys(cache).length }));
}

for (const payload of payloads) {
  payload.sheetPayload.values[payload.rowIndex][payload.colIndex] = cleanup(cache[payload.key]);
}
for (const payload of sheetPayloads) {
  payload.sheet.getRangeByIndexes(0, 0, payload.rowCount, payload.colCount).values = payload.values;
}

const names = [
  "00_Tom_tat_ket_luan",
  "01_Tieu_chi_danh_gia",
  "02_So_sanh_tong_hop",
  "03_Chi_so_thuc_do",
  "04_So_sanh_theo_muc",
  "05_Truong_hop_tieu_bieu",
  "06_Appendix_Canh_bao",
];
let index = 0;
for (const sheet of workbook.worksheets) {
  sheet.name = names[index] ?? sheet.name;
  index += 1;
}

const check = await workbook.inspect({
  kind: "match",
  searchTerm: "[가-힣]",
  options: { useRegex: true, maxResults: 50 },
  maxChars: 6000,
});
console.log(check.ndjson);

for (const sheet of workbook.worksheets) {
  const used = sheet.getUsedRange();
  const values = used.values;
  const endColCode = Math.min(values[0]?.length ?? 1, 10);
  let n = endColCode;
  let endCol = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    endCol = String.fromCharCode(65 + rem) + endCol;
    n = Math.floor((n - 1) / 26);
  }
  const preview = await workbook.render({
    sheetName: sheet.name,
    range: `A1:${endCol}${Math.min(values.length, 30)}`,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(`${outputDir}/${sheet.name}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }));
