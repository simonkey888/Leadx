import { MAX_INGEST_BYTES, MAX_LEADS, RELEASE, demoLeads } from "./config.mjs";
import { cleanString, cleanTimestamp, jsonContentTypeAllowed, parseJsonBytes, preserveCrmState, readBodyLimited, sanitizeLead } from "./body.mjs";
import { json, logEvent, secureEqual } from "./http.mjs";
import { expiredSession, privateHeaders, sessionConfigurationFailure, verifySession } from "./session.mjs";

export async function handleLeads(request, env) {
  const verification = await verifySession(request, env);
  if (verification.reason === "configuration") return sessionConfigurationFailure();
  if (!verification.authenticated && verification.reason !== "missing") return expiredSession(verification.reason);
  if (!verification.authenticated) {
    const leads = demoLeads();
    return json({
      leads_all: leads,
      leads_hot: leads.filter((lead) => lead.score >= 70),
      summary: { total_leads: 12, hot_leads: 5, with_whatsapp: 0, with_messenger: 0, with_email: 0 },
      meta: { version: "demo-v2", source: "demo", generated_at: new Date().toISOString() },
    });
  }
  if (!env.LEADX_KV) return json({ error: "service_unavailable" }, 503, privateHeaders(verification));
  const raw = await env.LEADX_KV.get("leads:live");
  if (!raw) return json({ leads_all: [], leads_hot: [], summary: { total_leads: 0, hot_leads: 0, with_whatsapp: 0, with_messenger: 0, with_email: 0 }, meta: { source: "empty" } }, 200, privateHeaders(verification));
  try {
    const data = JSON.parse(raw);
    const leads = Array.isArray(data.leads_all) ? data.leads_all : [];
    return json({ ...data, leads_all: leads, leads_hot: Array.isArray(data.leads_hot) ? data.leads_hot : leads.filter((lead) => Number(lead.score || 0) >= 70) }, 200, privateHeaders(verification));
  } catch {
    return json({ error: "data_unavailable" }, 503, privateHeaders(verification));
  }
}

export async function handleMetrics(request, env) {
  const verification = await verifySession(request, env);
  if (verification.reason === "configuration") return sessionConfigurationFailure();
  if (!verification.authenticated && verification.reason !== "missing") return expiredSession(verification.reason);
  if (!verification.authenticated) {
    return json({ total_leads: 12, hot_leads: 5, urgent_leads: 2, contactable_leads: 0, status: "demo" });
  }
  if (!env.LEADX_KV) return json({ error: "service_unavailable" }, 503, privateHeaders(verification));
  const raw = await env.LEADX_KV.get("leads:live");
  if (!raw) return json({ total_leads: 0, hot_leads: 0, urgent_leads: 0, contactable_leads: 0, status: "empty" }, 200, privateHeaders(verification));
  try {
    const data = JSON.parse(raw);
    const leads = Array.isArray(data.leads_all) ? data.leads_all : [];
    return json({
      total_leads: leads.length,
      hot_leads: leads.filter((lead) => Number(lead.score || 0) >= 70).length,
      urgent_leads: leads.filter((lead) => Number(lead.score || 0) >= 85).length,
      contactable_leads: leads.filter((lead) => lead.whatsapp_publico || lead.telefono_publico || lead.email_publico || lead.fb_username || lead.fb_author_id).length,
      status: "ok",
    }, 200, privateHeaders(verification));
  } catch {
    return json({ error: "data_unavailable" }, 503, privateHeaders(verification));
  }
}

export async function handleIngest(request, env, requestIdValue) {
  if (!jsonContentTypeAllowed(request.headers.get("Content-Type"))) {
    return json({ status: "rejected", reason: "unsupported_media_type" }, 415);
  }
  if (!env.INGEST_SECRET || !env.LEADX_KV) return json({ status: "rejected", reason: "service_unavailable" }, 503);
  const provided = request.headers.get("X-Ingest-Secret") || request.headers.get("X-Webhook-Secret") || "";
  if (!(await secureEqual(provided, env.INGEST_SECRET))) {
    logEvent("ingest.rejected", requestIdValue, "unauthorized");
    return json({ status: "rejected", reason: "auth_failed" }, 401);
  }

  const read = await readBodyLimited(request, MAX_INGEST_BYTES);
  if (read.tooLarge) return json({ status: "rejected", reason: "payload_too_large" }, 413);

  let body;
  try { body = parseJsonBytes(read.bytes); } catch { return json({ status: "rejected", reason: "invalid_json" }, 400); }
  if (!body || typeof body !== "object" || Array.isArray(body) || !Array.isArray(body.leads_all) || body.leads_all.length > MAX_LEADS) {
    return json({ status: "rejected", reason: "invalid_payload" }, 400);
  }

  const sanitized = body.leads_all.map(sanitizeLead);
  if (sanitized.some((lead) => !lead)) return json({ status: "rejected", reason: "invalid_lead" }, 400);
  const ids = new Set();
  for (const lead of sanitized) {
    if (ids.has(lead.id)) return json({ status: "rejected", reason: "duplicate_id" }, 400);
    ids.add(lead.id);
  }

  let previous = [];
  const priorRaw = await env.LEADX_KV.get("leads:live");
  if (priorRaw) {
    try {
      const parsed = JSON.parse(priorRaw);
      previous = Array.isArray(parsed.leads_all) ? parsed.leads_all : [];
    } catch {
      return json({ status: "rejected", reason: "existing_data_invalid" }, 503);
    }
  }
  if (sanitized.length < 5 && previous.length >= 5) return json({ status: "rejected", reason: "anti_wipe" }, 409);

  const previousById = new Map(previous.map((lead) => [lead.id, lead]));
  const merged = sanitized.map((lead) => preserveCrmState(lead, previousById.get(lead.id)));
  const payload = {
    leads_all: merged,
    leads_hot: merged.filter((lead) => Number(lead.score || 0) >= 70),
    summary: { total_leads: merged.length, hot_leads: merged.filter((lead) => Number(lead.score || 0) >= 70).length },
    meta: {
      version: cleanString(body.meta?.version, 80) || RELEASE,
      source: cleanString(body.meta?.source, 100) || "hunter",
      generated_at: cleanTimestamp(body.meta?.generated_at) || new Date().toISOString(),
      ingest_at: new Date().toISOString(),
    },
  };
  await env.LEADX_KV.put("leads:live", JSON.stringify(payload));
  logEvent("ingest.accepted", requestIdValue, "ok", { count: merged.length });
  return json({ status: "ok", total: merged.length });
}
