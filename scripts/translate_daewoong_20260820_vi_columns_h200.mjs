import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "data/outputs/daewoong/2026_08_20/run_20260820T080949769457Z_9ee82a19/[langgraph][Daewoong]report-2026.08.20_6.xlsx";
const outputDir = "outputs/20260820_h200_vi_columns_daewoong_20260820_6";
const outputPath = `${outputDir}/[langgraph][Daewoong]report-2026.08.20_6_vi_columns.xlsx`;
const cachePath = `${outputDir}/translations_cache.json`;
const maxBatchesThisRun = Number(process.env.MAX_BATCHES || 0);

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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stripJsonFence(text) {
  return text
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function coerceTranslationArray(content, expected) {
  const parsed = JSON.parse(stripJsonFence(content));
  if (!Array.isArray(parsed)) {
    throw new Error("Translation response was not a JSON array.");
  }
  if (parsed.length !== expected) {
    throw new Error(`Translation response length ${parsed.length} did not match ${expected}.`);
  }
  return parsed.map((item) => {
    if (typeof item === "string") return item.trim();
    if (item && typeof item.translation === "string") return item.translation.trim();
    throw new Error("Translation item did not contain a string translation.");
  });
}

async function translateBatch({ baseUrl, apiKey, model, batch, attempt = 1 }) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 120000);
  const body = {
    model,
    temperature: 0,
    max_tokens: 7000,
    messages: [
      {
        role: "system",
        content:
          "You are a professional ESG translator. Translate Korean ESG report evidence and final answers into natural Vietnamese. Preserve facts, numbers, dates, company names, source references, IDs, ESG terms, URLs, and units. Do not add explanations. Return only valid JSON.",
      },
      {
        role: "user",
        content:
          "Translate each item into Vietnamese. Return a JSON array of strings in the same order and same length. If an item is empty, return an empty string.\n\n" +
          JSON.stringify(batch, null, 2),
      },
    ],
  };

  let response;
  try {
    response = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeout);
    if (attempt < 3) {
      await sleep(1500 * attempt);
      return translateBatch({ baseUrl, apiKey, model, batch, attempt: attempt + 1 });
    }
    throw err;
  }
  clearTimeout(timeout);

  if (!response.ok) {
    const detail = await response.text();
    if (attempt < 3 && (response.status === 429 || response.status >= 500)) {
      await sleep(1500 * attempt);
      return translateBatch({ baseUrl, apiKey, model, batch, attempt: attempt + 1 });
    }
    throw new Error(`HallMDR request failed ${response.status}: ${detail.slice(0, 500)}`);
  }

  const json = await response.json();
  const content = json?.choices?.[0]?.message?.content;
  if (typeof content !== "string") {
    throw new Error("HallMDR response did not include choices[0].message.content.");
  }

  try {
    return coerceTranslationArray(content, batch.length);
  } catch (err) {
    if (attempt < 2 && batch.length > 1) {
      const midpoint = Math.ceil(batch.length / 2);
      const left = await translateBatch({ baseUrl, apiKey, model, batch: batch.slice(0, midpoint), attempt: 1 });
      const right = await translateBatch({ baseUrl, apiKey, model, batch: batch.slice(midpoint), attempt: 1 });
      return [...left, ...right];
    }
    throw err;
  }
}

function chunkItems(items, maxChars = 3500, maxItems = 2) {
  const chunks = [];
  let chunk = [];
  let chars = 0;
  for (const item of items) {
    const size = item.text.length + 220;
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

function splitLongText(text, maxChars = 2800) {
  if (text.length <= maxChars) return [text];
  const segments = [];
  let remaining = text;
  while (remaining.length > maxChars) {
    const windowText = remaining.slice(0, maxChars);
    const breakAt = Math.max(
      windowText.lastIndexOf("\n\n"),
      windowText.lastIndexOf("\n"),
      windowText.lastIndexOf(". "),
      windowText.lastIndexOf("。"),
      windowText.lastIndexOf("다. "),
      windowText.lastIndexOf("요. "),
      windowText.lastIndexOf(" "),
    );
    const cut = breakAt > maxChars * 0.45 ? breakAt + 1 : maxChars;
    segments.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) segments.push(remaining);
  return segments;
}

const env = parseEnv(await fs.readFile(".env", "utf8"));
const apiKey = env.HALLMDR_API_KEY || env.ESG_LLM_API_KEY;
const baseUrl = normalizeBaseUrl(env.ESG_LLM_BASE_URL || env.HALLMDR_API_BASE_URL);
const model = env.ESG_QUICK_THINK_LLM || "llm/gemma4";

if (!apiKey) throw new Error("HALLMDR_API_KEY or ESG_LLM_API_KEY is required.");
if ((env.ESG_LLM_PROVIDER || "hallmdr").toLowerCase() !== "hallmdr") {
  throw new Error("ESG_LLM_PROVIDER must be hallmdr for this translation task.");
}

await fs.mkdir(outputDir, { recursive: true });
let cache = {};
try {
  cache = JSON.parse(await fs.readFile(cachePath, "utf8"));
} catch {
  cache = {};
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const qualitative = workbook.worksheets.getItem("Qualitative");
const used = qualitative.getUsedRange();
const rowCount = used.values.length;

const headers = qualitative.getRange("A1:F1").values[0];
const originalEvidenceCol = headers.indexOf("Original Evidence");
const finalAnswerCol = headers.indexOf("Final Answer");
if (originalEvidenceCol === -1 || finalAnswerCol === -1) {
  throw new Error("Could not locate Original Evidence and Final Answer columns.");
}

const evidenceValues = qualitative
  .getRangeByIndexes(1, originalEvidenceCol, rowCount - 1, 1)
  .values.map((row) => row[0]);
const answerValues = qualitative
  .getRangeByIndexes(1, finalAnswerCol, rowCount - 1, 1)
  .values.map((row) => row[0]);

const items = [];
for (let i = 0; i < rowCount - 1; i += 1) {
  if (typeof evidenceValues[i] === "string" && evidenceValues[i].trim()) {
    items.push({ key: `Original Evidence!D${i + 2}`, rowIndex: i, target: "evidence", text: evidenceValues[i].trim() });
  }
  if (typeof answerValues[i] === "string" && answerValues[i].trim()) {
    items.push({ key: `Final Answer!F${i + 2}`, rowIndex: i, target: "answer", text: answerValues[i].trim() });
  }
}

const remainingItems = items.filter((item) => typeof cache[item.key] !== "string");
const remainingUnits = [];
for (const item of remainingItems) {
  const parts = splitLongText(item.text);
  for (let partIndex = 0; partIndex < parts.length; partIndex += 1) {
    const key = parts.length === 1 ? item.key : `${item.key}::part:${partIndex + 1}`;
    if (typeof cache[key] !== "string") {
      remainingUnits.push({
        key,
        itemKey: item.key,
        partIndex,
        partCount: parts.length,
        text: parts[partIndex],
      });
    }
  }
}
console.log(
  JSON.stringify({
    baseUrl,
    model,
    rows: rowCount - 1,
    cellsToTranslate: items.length,
    cached: items.length - remainingItems.length,
    remainingCells: remainingItems.length,
    remainingUnits: remainingUnits.length,
  }),
);

const chunks = chunkItems(remainingUnits);
let translatedUnits = 0;
for (let i = 0; i < chunks.length; i += 1) {
  if (maxBatchesThisRun > 0 && i >= maxBatchesThisRun) {
    await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");
    console.log(JSON.stringify({ partial: true, processedBatches: i, remainingBatches: chunks.length - i, cachePath }));
    process.exit(0);
  }
  const chunk = chunks[i];
  const translations = await translateBatch({ baseUrl, apiKey, model, batch: chunk.map((item) => item.text) });
  for (let j = 0; j < chunk.length; j += 1) {
    cache[chunk[j].key] = translations[j];
  }
  await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");
  translatedUnits += chunk.length;
  console.log(JSON.stringify({ batch: i + 1, batches: chunks.length, translatedUnits, cached: Object.keys(cache).length }));
}

for (const item of remainingItems) {
  if (typeof cache[item.key] === "string") continue;
  const parts = splitLongText(item.text);
  const translatedParts = [];
  for (let partIndex = 0; partIndex < parts.length; partIndex += 1) {
    const partKey = parts.length === 1 ? item.key : `${item.key}::part:${partIndex + 1}`;
    if (typeof cache[partKey] !== "string") {
      throw new Error(`Translation cache is missing ${partKey}.`);
    }
    translatedParts.push(cache[partKey]);
  }
  cache[item.key] = translatedParts.join("\n");
}
await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");

const evidenceTranslations = [];
const answerTranslations = [];
let missing = 0;
for (let i = 0; i < rowCount - 1; i += 1) {
  const evidenceKey = `Original Evidence!D${i + 2}`;
  const answerKey = `Final Answer!F${i + 2}`;
  const hasEvidence = typeof evidenceValues[i] === "string" && evidenceValues[i].trim();
  const hasAnswer = typeof answerValues[i] === "string" && answerValues[i].trim();
  const evidenceVi = hasEvidence ? cache[evidenceKey] : null;
  const answerVi = hasAnswer ? cache[answerKey] : null;
  if (hasEvidence && typeof evidenceVi !== "string") missing += 1;
  if (hasAnswer && typeof answerVi !== "string") missing += 1;
  evidenceTranslations.push([evidenceVi ?? null]);
  answerTranslations.push([answerVi ?? null]);
}
if (missing > 0) throw new Error(`Translation cache is missing ${missing} expected cells.`);

qualitative.getRange("G1:H1").values = [["Original Evidence VI", "Final Answer Vi"]];
qualitative.getRangeByIndexes(1, 6, rowCount - 1, 1).values = evidenceTranslations;
qualitative.getRangeByIndexes(1, 7, rowCount - 1, 1).values = answerTranslations;

qualitative.getRange("G1:H1").format = {
  fill: "#0F4C5C",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
qualitative.getRange(`G2:H${rowCount}`).format.wrapText = true;
qualitative.getRange("G:G").format.columnWidth = 70;
qualitative.getRange("H:H").format.columnWidth = 70;
qualitative.getRange("A1:H1").format.rowHeight = 28;
qualitative.getRange(`A2:H${rowCount}`).format.rowHeight = 96;
qualitative.freezePanes.freezeRows(1);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Qualitative",
  range: "A1:H8",
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 8,
  tableMaxCellChars: 160,
  maxChars: 12000,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100, matchFormulas: true },
  maxChars: 8000,
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const renderTargets = [
  { sheetName: "Qualitative", range: "A1:H20" },
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
