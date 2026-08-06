import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/vincent/Downloads/[langgraph][Daewoong]report-2026.08.04_1.xlsx";
const outputDir = "outputs/20260805_h200_vi_translation";
const outputPath = `${outputDir}/[langgraph][Daewoong]report-2026.08.04_1_vi.xlsx`;
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
    max_tokens: 6000,
    messages: [
      {
        role: "system",
        content:
          "You are a professional ESG translator. Translate Korean ESG report evidence and answers into natural Vietnamese. Preserve facts, numbers, dates, company names, source references, IDs, and ESG terminology. Do not add explanations. Return only valid JSON.",
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

function chunkItems(items, maxChars = 4500, maxItems = 3) {
  const chunks = [];
  let chunk = [];
  let chars = 0;
  for (const item of items) {
    const size = item.text.length + 200;
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

if (!apiKey) {
  throw new Error("HALLMDR_API_KEY or ESG_LLM_API_KEY is required.");
}
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

const headers = qualitative.getRange("A1:H1").values[0];
const originalEvidenceCol = headers.indexOf("Original Evidence");
const finalAnswerCol = headers.indexOf("Final Answer");
if (originalEvidenceCol === -1 || finalAnswerCol === -1) {
  throw new Error("Could not locate Original Evidence and Final Answer columns.");
}

const evidenceRange = qualitative.getRangeByIndexes(1, originalEvidenceCol, rowCount - 1, 1);
const answerRange = qualitative.getRangeByIndexes(1, finalAnswerCol, rowCount - 1, 1);
const evidenceValues = evidenceRange.values.map((row) => row[0]);
const answerValues = answerRange.values.map((row) => row[0]);

const items = [];
for (let i = 0; i < evidenceValues.length; i += 1) {
  if (typeof evidenceValues[i] === "string" && evidenceValues[i].trim()) {
    items.push({ key: `D${i + 2}`, rowIndex: i, target: "evidence", text: evidenceValues[i].trim() });
  }
  if (typeof answerValues[i] === "string" && answerValues[i].trim()) {
    items.push({ key: `H${i + 2}`, rowIndex: i, target: "answer", text: answerValues[i].trim() });
  }
}

for (const item of items) {
  if (typeof cache[item.key] === "string") {
    if (item.target === "evidence") evidenceValues[item.rowIndex] = cache[item.key];
    if (item.target === "answer") answerValues[item.rowIndex] = cache[item.key];
  }
}

const remainingItems = items.filter((item) => typeof cache[item.key] !== "string");
console.log(JSON.stringify({ baseUrl, model, rows: rowCount - 1, cellsToTranslate: items.length, cached: items.length - remainingItems.length, remaining: remainingItems.length }));

const chunks = chunkItems(remainingItems);
let translatedCells = 0;
for (let i = 0; i < chunks.length; i += 1) {
  if (maxBatchesThisRun > 0 && i >= maxBatchesThisRun) {
    await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");
    console.log(JSON.stringify({ partial: true, processedBatches: i, remainingBatches: chunks.length - i, cachePath }));
    process.exit(0);
  }
  const chunk = chunks[i];
  const translations = await translateBatch({ baseUrl, apiKey, model, batch: chunk.map((item) => item.text) });
  for (let j = 0; j < chunk.length; j += 1) {
    const item = chunk[j];
    if (item.target === "evidence") evidenceValues[item.rowIndex] = translations[j];
    if (item.target === "answer") answerValues[item.rowIndex] = translations[j];
    cache[item.key] = translations[j];
  }
  await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");
  translatedCells += chunk.length;
  console.log(JSON.stringify({ batch: i + 1, batches: chunks.length, translatedCells, cached: Object.keys(cache).length }));
}

evidenceRange.values = evidenceValues.map((value) => [value ?? null]);
answerRange.values = answerValues.map((value) => [value ?? null]);
evidenceRange.format.wrapText = true;
answerRange.format.wrapText = true;
qualitative.getRange("D:D").format.columnWidth = 70;
qualitative.getRange("H:H").format.columnWidth = 70;
qualitative.getRange("A1:H1").format.rowHeight = 28;
qualitative.getRange(`A2:H${rowCount}`).format.rowHeight = 96;
qualitative.freezePanes.freezeRows(1);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Qualitative",
  range: "A1:H6",
  include: "values",
  tableMaxRows: 6,
  tableMaxCols: 8,
  tableMaxCellChars: 160,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "formula",
  maxChars: 2000,
  summary: "final formula scan",
});
console.log(errors.ndjson);

const renderTargets = [
  { sheetName: "Qualitative", range: "A1:H20" },
  { sheetName: "Quantitative", range: "A1:I30" },
];
for (const target of renderTargets) {
  const preview = await workbook.render({
    sheetName: target.sheetName,
    range: target.range,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(`${outputDir}/${target.sheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }));
