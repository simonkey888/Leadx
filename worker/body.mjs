import { CRM_FIELDS, PRIORITY_VALUES, STATUS_VALUES, VERTICALS } from "./config.mjs";

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

  const output = { id, vertical: VERTICALS.has(input.vertical) ? input.vertical : "fotomultas" };
  const strings = {
    persona: 160, author: 160, provincia: 80, ciudad: 120, vehiculo: 80,
    patente: 16, platform: 80, source: 100, source_label: 100,
    source_url: 1200, url: 1200, title: 300, snippet: 3000, quoted_text: 1500,
    telefono_publico: 64, whatsapp_publico: 64, email_publico: 254,
    fb_username: 160, fb_author_id: 160, problem_category: 100,
    problem_summary: 500, label: 80, contact_source: 120, name: 160, province: 80,
    phone: 64, channel: 40, assigned_to: 160, status: 40, priority: 20,
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
  if (input.vertical_data && typeof input.vertical_data === "object" && !Array.isArray(input.vertical_data)) {
    const allowed = output.vertical === "fotomultas"
      ? { plate: 16, municipality: 120, violation_type: 160, due_date: 40 }
      : { brand: 120, machine_type: 120, model: 160, part_number: 80, urgency: 20 };
    output.vertical_data = {};
    for (const [field, max] of Object.entries(allowed)) {
      const value = cleanString(input.vertical_data[field], max); if (value !== undefined) output.vertical_data[field] = value;
    }
    for (const field of output.vertical === "fotomultas" ? ["estimated_amount"] : ["quantity"]) {
      if (Number.isFinite(input.vertical_data[field])) output.vertical_data[field] = Number(input.vertical_data[field]);
    }
  }
  return output;
}

export function preserveCrmState(incoming, existing) {
  const merged = { ...incoming };
  for (const field of CRM_FIELDS) if (existing && existing[field] !== undefined) merged[field] = existing[field];
  return merged;
}
