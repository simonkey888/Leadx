const RELEASE = "leadx-containment-v1";
const SESSION_COOKIE = "leadx_session";
const SESSION_IDLE_MS = 20 * 60 * 1000;
const SESSION_ABSOLUTE_MS = 8 * 60 * 60 * 1000;
const SESSION_RENEW_MIN_MS = 60 * 1000;
const MAX_LOGIN_BYTES = 4096;
const MAX_INGEST_BYTES = 2 * 1024 * 1024;
const MAX_LEADS = 500;

const STATUS_VALUES = new Set([
  "Nuevo", "Revisado", "Contactado", "En gestión",
  "Esperando respuesta", "Cerrado", "Descartado",
]);
const PRIORITY_VALUES = new Set(["Alta", "Media", "Baja"]);
const CRM_FIELDS = [
  "status", "priority", "notes", "owner", "amount", "contacted_at",
  "next_action_at", "last_activity_at", "resolution", "resolution_reason",
  "updated_at", "version", "_status", "_notes", "_monto",
];

function demoLeads(now = Date.now()) {
  const ago = (ms) => new Date(now - ms).toISOString();
  return [
    { id: "demo_001", score: 95, persona: "Carlos Demo", provincia: "Santa Fe", platform: "Foro público", source: "demo", source_label: "Foro público", title: "Multa de moto comprada usada", snippet: "Compré una moto usada y apareció una multa anterior. ¿Cómo puedo regularizarla?", vehiculo: "moto", fecha_iso: ago(6 * 3600000), _status: "Nuevo", _priority: "Alta", _isDemo: true },
    { id: "demo_002", score: 88, persona: "María Ejemplo", provincia: "CABA", platform: "Consulta pública", source: "demo", source_label: "Consulta pública", title: "Transferencia bloqueada por multas", snippet: "La transferencia quedó bloqueada por infracciones que no reconozco.", vehiculo: "moto", fecha_iso: ago(2 * 3600000), _status: "Nuevo", _priority: "Alta", _isDemo: true },
    { id: "demo_003", score: 75, persona: "Juan Prueba", provincia: "Buenos Aires", platform: "Foro público", source: "demo", source_label: "Foro público", title: "Multas del titular anterior", snippet: "La camioneta conserva dos multas del dueño anterior y necesito transferirla.", vehiculo: "camioneta", fecha_iso: ago(86400000), _status: "Contactado", _priority: "Alta", _isDemo: true },
    { id: "demo_004", score: 70, persona: "Ana Test", provincia: "Entre Ríos", platform: "Consulta pública", source: "demo", source_label: "Consulta pública", title: "Infracción asociada al primer dueño", snippet: "Apareció una infracción del primer titular y no sé cómo presentar el descargo.", vehiculo: "auto", fecha_iso: ago(4 * 3600000), _status: "Nuevo", _priority: "Media", _isDemo: true },
    { id: "demo_005", score: 65, persona: "Pedro Muestra", provincia: "CABA", platform: "Foro público", source: "demo", source_label: "Foro público", title: "Fotomulta por velocidad", snippet: "Recibí una fotomulta por una diferencia mínima de velocidad permitida.", vehiculo: "auto", fecha_iso: ago(12 * 3600000), _status: "En gestión", _priority: "Media", _isDemo: true },
    { id: "demo_006", score: 55, persona: "Lucía Ficticia", provincia: "Misiones", platform: "Consulta pública", source: "demo", source_label: "Consulta pública", title: "Prescripción de radar móvil", snippet: "Necesito saber qué documentación revisar para evaluar la prescripción.", vehiculo: "auto", fecha_iso: ago(18 * 3600000), _status: "Nuevo", _priority: "Media", _isDemo: true },
    { id: "demo_007", score: 50, persona: "Roberto Demo", provincia: "Santa Fe", platform: "Foro público", source: "demo", source_label: "Foro público", title: "Dominio cargado incorrectamente", snippet: "La infracción parece corresponder a otro vehículo con un dominio similar.", vehiculo: "auto", fecha_iso: ago(2 * 86400000), _status: "Cerrado", _priority: "Baja", _isDemo: true },
    { id: "demo_008", score: 45, persona: "Patricia Ejemplo", provincia: "Corrientes", platform: "Consulta pública", source: "demo", source_label: "Consulta pública", title: "Infracciones ausentes en la consulta", snippet: "Una oficina informa deuda pero el portal de consulta no muestra infracciones.", fecha_iso: ago(3 * 86400000), _status: "Revisado", _priority: "Baja", _isDemo: true },
    { id: "demo_009", score: 40, persona: "Diego Prueba", provincia: "Buenos Aires", platform: "Foro público", source: "demo", source_label: "Foro público", title: "Descargo por multas antiguas", snippet: "Quiero ordenar varias multas antiguas antes de iniciar una transferencia.", vehiculo: "moto", fecha_iso: ago(5 * 86400000), _status: "Descartado", _priority: "Baja", _isDemo: true },
    { id: "demo_010", score: 35, persona: "Sandra Test", provincia: "CABA", platform: "Consulta pública", source: "demo", source_label: "Consulta pública", title: "VTV y regularización", snippet: "Necesito regularizar VTV e infracciones antes de renovar documentación.", vehiculo: "auto", fecha_iso: ago(7 * 86400000), _status: "Nuevo", _priority: "Baja", _isDemo: true },
    { id: "demo_011", score: 80, persona: "Fernando Demo", provincia: "Santa Fe", platform: "Foro público", source: "demo", source_label: "Foro público", title: "Infracción en ruta provincial", snippet: "Recibí un acta en una ruta provincial y necesito revisar su información.", vehiculo: "camioneta", fecha_iso: ago(8 * 3600000), _status: "Nuevo", _priority: "Alta", _isDemo: true },
    { id: "demo_012", score: 60, persona: "Carolina Muestra", provincia: "Entre Ríos", platform: "Consulta pública", source: "demo", source_label: "Consulta pública", title: "Retención con grúa municipal", snippet: "El vehículo fue retirado por una grúa y necesito identificar los pasos de regularización.", vehiculo: "auto", fecha_iso: ago(14 * 3600000), _status: "Esperando respuesta", _priority: "Media", _isDemo: true },
  ];
}

function requestId(request) {
  return request.headers.get("CF-Ray") || request.headers.get("X-Request-ID") || crypto.randomUUID();
}

function securityHeaders() {
  return {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };
}

function responseWithHeaders(response, extra = {}) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries({ ...securityHeaders(), ...extra })) {
    headers.set(key, value);
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

function json(data, status = 200, extra = {}) {
  return responseWithHeaders(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  }), extra);
}

function logEvent(event, requestIdValue, status, fields = {}) {
  console.log(JSON.stringify({ event, timestamp: new Date().toISOString(), requestId: requestIdValue, status, ...fields }));
}

function sameOriginAllowed(request, url) {
  const origin = request.headers.get("Origin");
  return !origin || origin === url.origin;
}

function cookieValue(request, name) {
  const cookie = request.headers.get("Cookie") || "";
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return match ? match[1] : null;
}

function base64UrlEncode(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlDecode(value) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function digest(value) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

async function secureEqual(left, right) {
  if (typeof left !== "string" || typeof right !== "string") return false;
  const [a, b] = await Promise.all([digest(left), digest(right)]);
  let difference = 0;
  for (let index = 0; index < a.length; index += 1) difference |= a[index] ^ b[index];
  return difference === 0;
}

async function hmac(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return base64UrlEncode(new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value))));
}

function randomNonce() {
  return base64UrlEncode(crypto.getRandomValues(new Uint8Array(18)));
}

function expiredCookie() {
  return `${SESSION_COOKIE}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;
}

async function issueSession(payload, env, now) {
  const encoded = base64UrlEncode(new TextEncoder().encode(JSON.stringify(payload)));
  const signature = await hmac(encoded, env.SESSION_SECRET);
  const remaining = Math.max(0, Math.ceil((payload.iat + SESSION_ABSOLUTE_MS - now) / 1000));
  return `${SESSION_COOKIE}=${encoded}.${signature}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${remaining}`;
}

async function verifySession(request, env, { renew = false } = {}) {
  const token = cookieValue(request, SESSION_COOKIE);
  if (!token) return { authenticated: false, reason: "missing" };
  if (!env.SESSION_SECRET) return { authenticated: false, reason: "configuration" };
  const parts = token.split(".");
  if (parts.length !== 2 || !(await secureEqual(parts[1], await hmac(parts[0], env.SESSION_SECRET)))) {
    return { authenticated: false, reason: "invalid" };
  }
  try {
    const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(parts[0])));
    const now = Date.now();
    if (!Number.isFinite(payload.iat) || !Number.isFinite(payload.lastActivity) ||
        typeof payload.nonce !== "string" || payload.nonce.length < 16 ||
        payload.lastActivity < payload.iat || payload.lastActivity > now + 5000) {
      return { authenticated: false, reason: "invalid" };
    }
    if (now - payload.iat > SESSION_ABSOLUTE_MS) return { authenticated: false, reason: "absolute_expired" };
    if (now - payload.lastActivity > SESSION_IDLE_MS) return { authenticated: false, reason: "idle_expired" };

    let session = payload;
    let setCookie = null;
    if (renew && now - payload.lastActivity >= SESSION_RENEW_MIN_MS) {
      session = { ...payload, lastActivity: now, nonce: randomNonce() };
      setCookie = await issueSession(session, env, now);
    }
    return { authenticated: true, reason: "valid", session, setCookie };
  } catch {
    return { authenticated: false, reason: "invalid" };
  }
}

function privateHeaders(verification = {}) {
  const headers = { "Cache-Control": "no-store, private", "Pragma": "no-cache", "Vary": "Cookie" };
  if (verification.setCookie) headers["Set-Cookie"] = verification.setCookie;
  return headers;
}

function expiredSession(reason) {
  return json({ error: "session_expired", reason }, 401, { ...privateHeaders(), "Set-Cookie": expiredCookie() });
}

function bodyTooLarge(request, limit) {
  const length = Number(request.headers.get("Content-Length") || 0);
  return Number.isFinite(length) && length > limit;
}

function cleanString(value, maxLength) {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : undefined;
}

function cleanTimestamp(value) {
  if (typeof value !== "string" || value.length > 40) return undefined;
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time).toISOString() : undefined;
}

function sanitizeLead(input) {
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

function preserveCrmState(incoming, existing) {
  const merged = { ...incoming };
  for (const field of CRM_FIELDS) {
    if (existing && existing[field] !== undefined) merged[field] = existing[field];
  }
  return merged;
}

async function handleLogin(request, env, requestIdValue) {
  if (!env.LOGIN_RATE_LIMITER) return json({ ok: false, error: "Servicio no disponible." }, 503);
  const rate = await env.LOGIN_RATE_LIMITER.limit({ key: `login:${request.headers.get("CF-Connecting-IP") || "unknown"}` });
  if (!rate.success) {
    logEvent("auth.rate_limited", requestIdValue, "rejected");
    return json({ ok: false, error: "Demasiados intentos. Esperá 1 minuto." }, 429, { "Retry-After": "60" });
  }
  if (!env.DASHBOARD_PASSWORD || !env.SESSION_SECRET) return json({ ok: false, error: "Servicio no disponible." }, 503);
  if (bodyTooLarge(request, MAX_LOGIN_BYTES)) return json({ ok: false, error: "Solicitud inválida." }, 413);

  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "Solicitud inválida." }, 400); }
  if (!body || typeof body.password !== "string" || body.password.length < 1 || body.password.length > 256) {
    return json({ ok: false, error: "Solicitud inválida." }, 400);
  }
  if (!(await secureEqual(body.password, env.DASHBOARD_PASSWORD))) {
    logEvent("auth.login.failure", requestIdValue, "rejected");
    return json({ ok: false, error: "Contraseña incorrecta" }, 401);
  }

  const now = Date.now();
  const session = { iat: now, lastActivity: now, nonce: randomNonce() };
  const cookie = await issueSession(session, env, now);
  logEvent("auth.login.success", requestIdValue, "ok");
  return json({ ok: true }, 200, { ...privateHeaders(), "Set-Cookie": cookie });
}

async function handleSession(request, env) {
  const verification = await verifySession(request, env);
  const headers = verification.authenticated
    ? privateHeaders(verification)
    : verification.reason === "missing" ? {} : { "Set-Cookie": expiredCookie(), "Vary": "Cookie" };
  return json({
    authenticated: verification.authenticated,
    mode: verification.authenticated ? "real" : "demo",
    reason: verification.reason,
    ...(verification.authenticated ? {
      idleExpiresAt: verification.session.lastActivity + SESSION_IDLE_MS,
      absoluteExpiresAt: verification.session.iat + SESSION_ABSOLUTE_MS,
    } : {}),
  }, 200, headers);
}

async function handleActivity(request, env) {
  const verification = await verifySession(request, env, { renew: true });
  if (!verification.authenticated) return expiredSession(verification.reason);
  return json({
    ok: true,
    authenticated: true,
    idleExpiresAt: verification.session.lastActivity + SESSION_IDLE_MS,
    absoluteExpiresAt: verification.session.iat + SESSION_ABSOLUTE_MS,
  }, 200, privateHeaders(verification));
}

async function handleLeads(request, env) {
  const verification = await verifySession(request, env);
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

async function handleMetrics(request, env) {
  const verification = await verifySession(request, env);
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

async function handleIngest(request, env, requestIdValue) {
  if (!env.INGEST_SECRET || !env.LEADX_KV) return json({ status: "rejected", reason: "service_unavailable" }, 503);
  const provided = request.headers.get("X-Ingest-Secret") || request.headers.get("X-Webhook-Secret") || "";
  if (!(await secureEqual(provided, env.INGEST_SECRET))) {
    logEvent("ingest.rejected", requestIdValue, "unauthorized");
    return json({ status: "rejected", reason: "auth_failed" }, 401);
  }
  if (bodyTooLarge(request, MAX_INGEST_BYTES)) return json({ status: "rejected", reason: "payload_too_large" }, 413);

  let body;
  try { body = await request.json(); } catch { return json({ status: "rejected", reason: "invalid_json" }, 400); }
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

async function serveAsset(request, env) {
  if (!env.ASSETS) return json({ error: "static_assets_unavailable" }, 503);
  let response = await env.ASSETS.fetch(request);
  if (response.status === 404) {
    response = await env.ASSETS.fetch(new Request(new URL("/index.html", request.url), request));
  }
  const cache = new URL(request.url).pathname.startsWith("/assets/")
    ? "public, max-age=31536000, immutable"
    : "no-cache";
  return responseWithHeaders(response, { "Cache-Control": cache });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const requestIdValue = requestId(request);

    if (!sameOriginAllowed(request, url)) return json({ error: "cross_origin_forbidden" }, 403, { "Vary": "Origin" });
    if (request.method === "OPTIONS") {
      return responseWithHeaders(new Response(null, { status: 204 }), {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Ingest-Secret, X-Webhook-Secret, X-LeadX-Activity",
        "Access-Control-Max-Age": "600",
        "Vary": "Origin",
      });
    }

    try {
      if (url.pathname === "/api/auth/login" && request.method === "POST") return handleLogin(request, env, requestIdValue);
      if (url.pathname === "/api/auth/session" && request.method === "GET") return handleSession(request, env);
      if (url.pathname === "/api/auth/activity" && request.method === "POST") return handleActivity(request, env);
      if (url.pathname === "/api/auth/logout" && request.method === "POST") return json({ ok: true }, 200, { ...privateHeaders(), "Set-Cookie": expiredCookie() });
      if (url.pathname === "/api/leads" && request.method === "GET") return handleLeads(request, env);
      if (url.pathname === "/api/metrics" && request.method === "GET") return handleMetrics(request, env);
      if (url.pathname === "/api/ingest" && request.method === "POST") return handleIngest(request, env, requestIdValue);
      if (url.pathname === "/api/health" && request.method === "GET") {
        return json({ status: "ok", service: "leadx", version: RELEASE, checked_at: new Date().toISOString() });
      }
      if (url.pathname.startsWith("/api/")) return json({ error: "not_found" }, 404);
      return serveAsset(request, env);
    } catch {
      logEvent("request.failed", requestIdValue, "error", { route: url.pathname.startsWith("/api/") ? "api" : "asset" });
      return json({ error: "internal_error", request_id: requestIdValue }, 500);
    }
  },
};
