import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "feedback_output/TalkFile_V2_V3_정성산출물_비교표 _260814.xlsx.xlsx";
const outputDir = "outputs/20260814_h200_vi_translation_talkfile_feedback";
const outputPath = `${outputDir}/TalkFile_V2_V3_qualitative_comparison_260814_vi.xlsx`;
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
          "You are a professional Korean-to-Vietnamese translator for ESG/business analysis spreadsheets. Translate human-readable text into natural Vietnamese. Preserve numbers, percentages, dates, URLs, file names, sheet names, IDs, cell/range references, V2/V3 labels, EBX/Q IDs, model names, and formulas exactly. Return only valid JSON.",
      },
      {
        role: "user",
        content:
          "Translate each spreadsheet cell value into Vietnamese. Return a JSON array of strings in the same order and same length. Do not add notes.\n\n" +
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

function chunkItems(items, maxChars = 9000, maxItems = 8) {
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

function colName(index0) {
  let n = index0 + 1;
  let name = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function address(row0, col0) {
  return `${colName(col0)}${row0 + 1}`;
}

function shouldTranslate(value, formula) {
  if (typeof value !== "string") return false;
  const text = value.trim();
  if (!text) return false;
  if (formula && String(formula).trim()) return false;
  if (/^https?:\/\//i.test(text)) return false;
  if (/^[A-Z]{2,}[-_A-Z0-9]*$/.test(text)) return false;
  if (/^\d+(?:[.,]\d+)?%?$/.test(text)) return false;
  return /[\p{L}]/u.test(text);
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
const items = [];
const sheetPayloads = [];

for (const sheet of workbook.worksheets) {
  const used = sheet.getUsedRange();
  const values = used.values;
  const formulas = used.formulas;
  const rowCount = values.length;
  const colCount = values[0]?.length ?? 0;
  const replacements = [];

  for (let r = 0; r < rowCount; r += 1) {
    for (let c = 0; c < colCount; c += 1) {
      const value = values[r]?.[c];
      const formula = formulas[r]?.[c];
      if (!shouldTranslate(value, formula)) continue;
      const cellAddress = address(r, c);
      const key = `${sheet.name}!${cellAddress}`;
      const item = { key, sheetName: sheet.name, rowIndex: r, colIndex: c, text: value.trim() };
      replacements.push(item);
      if (typeof cache[key] !== "string") items.push(item);
    }
  }
  sheetPayloads.push({ sheet, values, replacements, rowCount, colCount });
}

console.log(
  JSON.stringify({
    baseUrl,
    model,
    sheets: sheetPayloads.length,
    cellsToTranslate: sheetPayloads.reduce((sum, payload) => sum + payload.replacements.length, 0),
    cached: sheetPayloads.reduce((sum, payload) => sum + payload.replacements.filter((item) => typeof cache[item.key] === "string").length, 0),
    remaining: items.length,
  }),
);

const chunks = chunkItems(items);
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
    cache[chunk[j].key] = translations[j];
  }
  await fs.writeFile(cachePath, JSON.stringify(cache, null, 2), "utf8");
  translatedCells += chunk.length;
  console.log(JSON.stringify({ batch: i + 1, batches: chunks.length, translatedCells, cached: Object.keys(cache).length }));
}

for (const payload of sheetPayloads) {
  for (const item of payload.replacements) {
    const translated = cache[item.key];
    if (typeof translated !== "string") {
      throw new Error(`Missing translation for ${item.key}`);
    }
    payload.values[item.rowIndex][item.colIndex] = translated;
  }
  payload.sheet.getRangeByIndexes(0, 0, payload.rowCount, payload.colCount).values = payload.values;
}

const firstSheetName = sheetPayloads[0]?.sheet.name;
if (firstSheetName) {
  const check = await workbook.inspect({
    kind: "table",
    sheetId: firstSheetName,
    range: "A1:D20",
    include: "values",
    tableMaxRows: 20,
    tableMaxCols: 4,
    tableMaxCellChars: 180,
    maxChars: 12000,
  });
  console.log(check.ndjson);
}

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100, matchFormulas: true },
  maxChars: 8000,
  summary: "final formula error scan",
});
console.log(errors.ndjson);

for (const payload of sheetPayloads) {
  const endCol = colName(Math.min(payload.colCount, 10) - 1);
  const endRow = Math.min(payload.rowCount, 30);
  const preview = await workbook.render({
    sheetName: payload.sheet.name,
    range: `A1:${endCol}${endRow}`,
    scale: 1,
    format: "png",
  });
  const safeSheetName = payload.sheet.name.replace(/[^A-Za-z0-9]+/g, "_") || "sheet";
  await fs.writeFile(`${outputDir}/${safeSheetName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }));
