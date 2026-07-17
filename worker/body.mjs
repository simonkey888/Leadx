import { CRM_FIELDS, PRIORITY_VALUES, STATUS_VALUES } from "./config.mjs";

export function bodyTooLargeFromHeader(request, limit) {
  const raw = request.headers.get("Content-Length");
  if (raw === null) return false;
  const length = Number(raw);
  return Number.isFinite(length) && length > limit;
}

export async function readBodyLimited(request, limit) {
  if (bodyTooLargeFromHeader(request, limit)) return { tooLarge: true, bytes: null };
  if (!request.body) return { tooLarge: false, bytes: new Uint8Array() };
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > limit) {
        await reader.cancel("payload_too_large").catch(() => undefined);
        return { tooLarge: true, bytes: null };
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return { tooLarge: false, bytes };
}

export function parseJsonBytes(bytes) {
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

export function jsonContentTypeAllowed(value) {
  return /^application\/json(?:\s*;\s*charset=utf-8)?$/i.test((value || "").trim());
}

export function cleanString(value, maxLength) {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : undefined;
}

export function cleanTimestamp(value) {
  if (typeof value !== "string" || value.length > 40) return undefined;
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time).toISOString() : undefined;
}

export function sanitizeLead(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const id = cleanString(input.id, 128);
  if (!id || !/^[A-Za-z0-9:_-]+$/.test(id)) return null;

  const output = { id };
  const strings = {
    persona: 160, author: 160, provincia: 80, ciudad: 120, vehiculo: 80,
    patente: 16, platform: 80, source: 100, source_label: 100,
    source_url: 1200, url: 1200, title: 300, snippet: 3000, quoted_text: 1500,
    telefono_publico: 64, whatsapp_publico: 64, email_publico: 254,
    fb_username: 160, fb_author_id: 160, problem_category: 100,
    problem_summary: 500, label: 80, contact_source: 120,
  };
  for (const [field, maxLength] of Object.entries(strings)) {
    const value = cleanString(input[field], maxLength);
    if (value !== undefined) output[field] = value;
  }
  for (const field of ["fecha_iso", "first_seen_at", "discovery_timestamp"]) {
    const value = cleanTimestamp(input[field]);
    if (value) output[field] = value;
  }
  if (Number.isFinite(input.score)) output.score = Math.max(0, Math.min(100, Number(input.score)));
  if (Array.isArray(input.score_explain)) {
    output.score_explain = input.score_explain.filter((item) => typeof item === "string").slice(0, 20).map((item) => item.slice(0, 200));
  }
  if (STATUS_VALUES.has(input._status)) output._status = input._status;
  if (PRIORITY_VALUES.has(input._priority)) output._priority = input._priority;
  output._isDemo = false;
  return output;
}

export function preserveCrmState(incoming, existing) {
  const merged = { ...incoming };
  for (const field of CRM_FIELDS) if (existing && existing[field] !== undefined) merged[field] = existing[field];
  return merged;
}
