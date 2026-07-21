import { MAX_INGEST_BYTES, MAX_LEADS, RELEASE, VERTICALS, demoLeads } from "./config.mjs";
import { cleanString, cleanTimestamp, jsonContentTypeAllowed, parseJsonBytes, preserveCrmState, readBodyLimited, sanitizeLead } from "./body.mjs";
import { json, logEvent, secureEqual } from "./http.mjs";
import { expiredSession, privateHeaders, sessionConfigurationFailure, verifySession } from "./session.mjs";

function requestedVertical(request) {
  const value = new URL(request.url).searchParams.get("vertical");
  if (value === null || value === "") return { value: null, valid: true };
  return { value, valid: VERTICALS.has(value) };
}

function normalizeStoredLead(lead) {
  return { ...lead, vertical: VERTICALS.has(lead?.vertical) ? lead.vertical : "fotomultas" };
}

function canonicalStatus(lead) {
  const value = String(lead?._status || lead?.status || "Nuevo").toLowerCase();
  if (value === "revisado") return "Calificado";
  if (["en gestión", "en gestion", "esperando respuesta"].includes(value)) return "Propuesta";
  if (value === "cerrado") return "Ganado";
  if (value === "descartado") return "Perdido";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function metricsFor(leads, status) {
  return {
    total_leads: leads.length,
    new_leads: leads.filter((lead) => canonicalStatus(lead) === "Nuevo").length,
    qualified_leads: leads.filter((lead) => canonicalStatus(lead) === "Calificado").length,
    lost_leads: leads.filter((lead) => canonicalStatus(lead) === "Perdido").length,
    hot_leads: leads.filter((lead) => Number(lead.potential_score ?? lead.score ?? 0) >= 70).length,
    urgent_leads: leads.filter((lead) => Number(lead.potential_score ?? lead.score ?? 0) >= 85).length,
    contactable_leads: status === "demo" ? 0 : leads.filter((lead) => lead.whatsapp_publico || lead.telefono_publico || lead.phone || lead.email_publico || lead.email || lead.fb_username || lead.fb_author_id).length,
    status,
  };
}

async function readStoredLeads(env) {
  const raw = await env.LEADX_KV.get("leads:live");
  if (!raw) return { previous: [], previousData: null };
  try {
    const data = JSON.parse(raw);
    return { previous: Array.isArray(data.leads_all) ? data.leads_all.map(normalizeStoredLead) : [], previousData: data };
  } catch { return null; }
}

function sanitizeImportBody(body, { requiredMode = "upsert_vertical", requiredVertical = null } = {}) {
  if (!body || typeof body !== "object" || Array.isArray(body) || !Array.isArray(body.leads_all) || body.leads_all.length > MAX_LEADS) return { error: "invalid_payload" };
  const mode = body.mode;
  if (mode !== requiredMode) return { error: "invalid_mode" };
  const vertical = body.vertical;
  if (!VERTICALS.has(vertical) || (requiredVertical && vertical !== requiredVertical)) return { error: "invalid_vertical" };
  const sanitized = body.leads_all.map(sanitizeLead);
  if (sanitized.some((lead) => !lead)) return { error: "invalid_lead" };
  const ids = new Set();
  for (const lead of sanitized) {
    if (ids.has(lead.id)) return { error: "duplicate_id" };
    if (lead.vertical !== vertical) return { error: "mixed_vertical" };
    ids.add(lead.id);
  }
  return { mode, vertical, sanitized, ids };
}

async function storeImport(env, body, requirements = {}) {
  const parsed = sanitizeImportBody(body, requirements);
  if (parsed.error) return { error: parsed.error, status: 400 };
  const stored = await readStoredLeads(env);
  if (!stored) return { error: "existing_data_invalid", status: 503 };
  const { previous, previousData } = stored;
  const { mode, vertical, sanitized, ids } = parsed;

  const crossVerticalConflict = previous.some((lead) => ids.has(lead.id) && lead.vertical !== vertical);
  if (crossVerticalConflict) return { error: "cross_vertical_id_conflict", status: 409 };

  const previousById = new Map(
    previous.filter((lead) => lead.vertical === vertical).map((lead) => [lead.id, lead]),
  );
  const imported = sanitized.map((lead) => preserveCrmState(lead, previousById.get(lead.id)));
  const leads = [
    ...previous.filter((lead) => !(lead.vertical === vertical && ids.has(lead.id))),
    ...imported,
  ];
  const inserted = sanitized.filter((lead) => !previousById.has(lead.id)).length;
  const updated = sanitized.length - inserted;
  const generatedAt = cleanTimestamp(body.meta?.generated_at) || new Date().toISOString();
  const payload = {
    ...(previousData || {}),
    leads_all: leads,
    leads_hot: leads.filter((lead) => Number(lead.potential_score ?? lead.score ?? 0) >= 70),
    summary: { total_leads: leads.length, hot_leads: leads.filter((lead) => Number(lead.potential_score ?? lead.score ?? 0) >= 70).length },
    meta: {
      ...(previousData?.meta || {}),
      version: cleanString(body.meta?.version, 80) || RELEASE,
      source: cleanString(body.meta?.source, 100) || "vertical_upsert",
      generated_at: generatedAt,
      ingest_at: new Date().toISOString(),
      last_vertical_import: vertical,
    },
  };
  await env.LEADX_KV.put("leads:live", JSON.stringify(payload));
  return { total: leads.length, imported: sanitized.length, inserted, updated, vertical, mode };
}

async function parseImportRequest(request) {
  if (!jsonContentTypeAllowed(request.headers.get("Content-Type"))) return { error: "unsupported_media_type", status: 415 };
  const read = await readBodyLimited(request, MAX_INGEST_BYTES);
  if (read.tooLarge) return { error: "payload_too_large", status: 413 };
  try { return { body: parseJsonBytes(read.bytes) }; }
  catch { return { error: "invalid_json", status: 400 }; }
}

export async function handleLeads(request, env) {
  const requested = requestedVertical(request);
  if (!requested.valid) return json({ error: "invalid_vertical" }, 400);
  const verification = await verifySession(request, env);
  if (verification.reason === "configuration") return sessionConfigurationFailure();
  if (!verification.authenticated && verification.reason !== "missing") return expiredSession(verification.reason);
  if (!verification.authenticated) {
    const vertical = requested.value || "fotomultas";
    const leads = demoLeads(Date.now(), vertical);
    return json({
      leads_all: leads,
      leads_hot: leads.filter((lead) => Number(lead.score || 0) >= 70),
      summary: { total_leads: 12, hot_leads: leads.filter((lead) => Number(lead.score || 0) >= 70).length, with_whatsapp: leads.filter((lead) => lead.whatsapp_confirmed).length, with_messenger: 0, with_email: 0 },
      meta: { version: "demo-multiline-v1", source: "demo", vertical, generated_at: new Date().toISOString() },
    });
  }
  if (!env.LEADX_KV) return json({ error: "service_unavailable" }, 503, privateHeaders(verification));
  const stored = await readStoredLeads(env);
  if (!stored) return json({ error: "data_unavailable" }, 503, privateHeaders(verification));
  const all = stored.previous;
  const leads = requested.value ? all.filter((lead) => lead.vertical === requested.value) : all;
  return json({ ...(stored.previousData || {}), leads_all: leads, leads_hot: leads.filter((lead) => Number(lead.potential_score ?? lead.score ?? 0) >= 70), summary: { ...(stored.previousData?.summary || {}), total_leads: leads.length }, meta: { ...(stored.previousData?.meta || {}), ...(requested.value ? { vertical: requested.value } : {}) } }, 200, privateHeaders(verification));
}

export async function handleMetrics(request, env) {
  const requested = requestedVertical(request);
  if (!requested.valid) return json({ error: "invalid_vertical" }, 400);
  const verification = await verifySession(request, env);
  if (verification.reason === "configuration") return sessionConfigurationFailure();
  if (!verification.authenticated && verification.reason !== "missing") return expiredSession(verification.reason);
  if (!verification.authenticated) {
    const leads = demoLeads(Date.now(), requested.value || "fotomultas");
    const result = metricsFor(leads, "demo");
    return json({ ...result, status: "demo", total_leads: 12, contactable_leads: 0 });
  }
  if (!env.LEADX_KV) return json({ error: "service_unavailable" }, 503, privateHeaders(verification));
  const stored = await readStoredLeads(env);
  if (!stored) return json({ error: "data_unavailable" }, 503, privateHeaders(verification));
  const leads = requested.value ? stored.previous.filter((lead) => lead.vertical === requested.value) : stored.previous;
  return json(metricsFor(leads, leads.length ? "ok" : "empty"), 200, privateHeaders(verification));
}

export async function handleIngest(request, env, requestIdValue) {
  if (!env.INGEST_SECRET || !env.LEADX_KV) return json({ status: "rejected", reason: "service_unavailable" }, 503);
  const provided = request.headers.get("X-Ingest-Secret") || request.headers.get("X-Webhook-Secret") || "";
  if (!(await secureEqual(provided, env.INGEST_SECRET))) {
    logEvent("ingest.rejected", requestIdValue, "unauthorized");
    return json({ status: "rejected", reason: "auth_failed" }, 401);
  }
  const parsed = await parseImportRequest(request);
  if (parsed.error) return json({ status: "rejected", reason: parsed.error }, parsed.status);
  const result = await storeImport(env, parsed.body, { requiredMode: "upsert_vertical", requiredVertical: "fotomultas" });
  if (result.error) return json({ status: "rejected", reason: result.error }, result.status);
  logEvent("ingest.accepted", requestIdValue, "ok", { count: result.imported, mode: result.mode, vertical: result.vertical });
  return json({ status: "ok", ...result });
}

export async function handlePrivateImport(request, env, requestIdValue) {
  const verification = await verifySession(request, env, { renew: true });
  if (verification.reason === "configuration") return sessionConfigurationFailure();
  if (!verification.authenticated) return expiredSession(verification.reason);
  if (!env.LEADX_KV) return json({ status: "rejected", reason: "service_unavailable" }, 503, privateHeaders(verification));
  const parsed = await parseImportRequest(request);
  if (parsed.error) return json({ status: "rejected", reason: parsed.error }, parsed.status, privateHeaders(verification));
  const result = await storeImport(env, parsed.body, { requiredMode: "upsert_vertical" });
  if (result.error) return json({ status: "rejected", reason: result.error }, result.status, privateHeaders(verification));
  logEvent("private_import.accepted", requestIdValue, "ok", { count: result.imported, vertical: result.vertical });
  return json({ status: "ok", ...result }, 200, privateHeaders(verification));
}
