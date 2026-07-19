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
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return { tooLarge: false, bytes };
}

export function parseJsonBytes(bytes) { return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
export function jsonContentTypeAllowed(value) { return /^application\/json(?:\s*;\s*charset=utf-8)?$/i.test((value || "").trim()); }
export function cleanString(value, maxLength) { return typeof value === "string" ? value.trim().slice(0, maxLength) : undefined; }
export function cleanTimestamp(value) {
  if (typeof value !== "string" || value.length > 40) return undefined;
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time).toISOString() : undefined;
}

function sanitizeStringArray(value, maxItems = 30, maxLength = 180) {
  if (!Array.isArray(value)) return undefined;
  const clean = value
    .filter((item) => typeof item === "string")
    .map((item) => item.trim().slice(0, maxLength))
    .filter(Boolean)
    .slice(0, maxItems);
  return clean.length ? [...new Set(clean)] : undefined;
}

function sanitizeHistory(value) {
  if (!Array.isArray(value)) return undefined;
  return value.slice(0, 100).map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
    const output = {};
    const at = cleanTimestamp(entry.at); if (at) output.at = at;
    const action = cleanString(entry.action, 120); if (action) output.action = action;
    const detail = cleanString(entry.detail, 1000); if (detail) output.detail = detail;
    return Object.keys(output).length ? output : null;
  }).filter(Boolean);
}

export function sanitizeLead(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const id = cleanString(input.id, 128);
  if (!id || !/^[A-Za-z0-9:_-]+$/.test(id)) return null;
  if (input.vertical !== undefined && !VERTICALS.has(input.vertical)) return null;
  const vertical = input.vertical || "fotomultas";
  const output = { id, vertical };
  const strings = {
    persona: 160, author: 160, provincia: 80, ciudad: 120, vehiculo: 80, patente: 16,
    platform: 80, source: 100, source_label: 100, source_url: 1200, url: 1200,
    title: 300, snippet: 5000, quoted_text: 3000, telefono_publico: 64, whatsapp_publico: 64,
    email_publico: 254, fb_username: 160, fb_author_id: 160, problem_category: 100,
    problem_summary: 1000, label: 80, contact_source: 120, name: 160, company: 200,
    contact_name: 160, province: 80, city: 120, phone: 64, channel: 40,
    assigned_to: 160, status: 80, priority: 20, notes: 5000, website: 1200,
    outreach_state: 40, response_state: 160, temperature: 40, executive_bucket: 40,
    next_action: 2000, suggested_message: 5000, reengagement_message: 5000,
    literal_response: 5000, commercial_reading: 5000, objections: 3000,
    missing_information: 4000, purchase_capacity: 500, decision_authority: 500,
  };
  for (const [field, maxLength] of Object.entries(strings)) {
    const value = cleanString(input[field], maxLength);
    if (value !== undefined) output[field] = value;
  }
  for (const field of ["fecha_iso", "first_seen_at", "discovery_timestamp", "created_at", "contacted_at", "next_action_at", "last_activity_at", "follow_up_date", "last_contact_at"]) {
    const value = cleanTimestamp(input[field]);
    if (value) output[field] = value;
  }
  if (Number.isFinite(input.score)) output.score = Math.max(0, Math.min(100, Number(input.score)));
  if (Number.isFinite(input.potential_score)) output.potential_score = Math.max(0, Math.min(100, Number(input.potential_score)));
  if (Number.isFinite(input.amount)) output.amount = Number(input.amount);
  if (Array.isArray(input.score_explain)) output.score_explain = input.score_explain.filter((item) => typeof item === "string").slice(0, 20).map((item) => item.slice(0, 200));
  for (const field of ["brands", "applications", "products_interest", "emails", "alternate_phones"]) {
    const value = sanitizeStringArray(input[field], field === "products_interest" ? 50 : 20, field === "emails" ? 254 : 240);
    if (value) output[field] = value;
  }
  if (STATUS_VALUES.has(input._status)) output._status = input._status;
  if (PRIORITY_VALUES.has(input._priority)) output._priority = input._priority;
  for (const field of ["whatsapp_confirmed", "authenticity_required", "invoice_required"]) {
    if (typeof input[field] === "boolean") output[field] = input[field];
  }
  const history = sanitizeHistory(input.history); if (history) output.history = history;
  output._isDemo = false;

  if (input.vertical_data !== undefined && (!input.vertical_data || typeof input.vertical_data !== "object" || Array.isArray(input.vertical_data))) return null;
  if (input.vertical_data) {
    const allowed = vertical === "fotomultas"
      ? { plate: 16, municipality: 120, violation_type: 160, due_date: 40 }
      : { brand: 120, machine_type: 120, model: 160, part_number: 80, urgency: 20, special_lot: 160 };
    output.vertical_data = {};
    for (const [field, maxLength] of Object.entries(allowed)) {
      const value = cleanString(input.vertical_data[field], maxLength);
      if (value !== undefined) output.vertical_data[field] = value;
    }
    for (const field of vertical === "fotomultas" ? ["estimated_amount"] : ["quantity"]) {
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
