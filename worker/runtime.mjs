import { API_METHODS, HEALTH_DATA_KEY, HEALTH_KV_TIMEOUT_MS, RELEASE, REMOVED_PATHS } from "./config.mjs";
import { handleActivity, handleLogin, handleSession } from "./auth-handlers.mjs";
import { handleIngest, handleLeads, handleMetrics, handlePrivateImport } from "./data-handlers.mjs";
import { expiredCookie, json, logEvent, requestId, responseWithHeaders, sameOriginAllowed } from "./http.mjs";
import { privateHeaders } from "./session.mjs";

const PRIVATE_IMPORT_PATH = "/api/admin/import";

async function serveAsset(request, env) {
  if (!env.ASSETS) return json({ error: "static_assets_unavailable" }, 503);
  let response = await env.ASSETS.fetch(request);
  if (response.status === 404) response = await env.ASSETS.fetch(new Request(new URL("/index.html", request.url), request));
  const cache = new URL(request.url).pathname.startsWith("/assets/") ? "public, max-age=31536000, immutable" : "no-cache";
  return responseWithHeaders(response, { "Cache-Control": cache });
}

function methodsFor(pathname) {
  if (pathname === PRIVATE_IMPORT_PATH) return ["POST"];
  return API_METHODS.get(pathname);
}

function methodNotAllowed(allowed) {
  return json({ error: "method_not_allowed" }, 405, { Allow: allowed.join(", ") });
}

function preflight(allowed) {
  return responseWithHeaders(new Response(null, { status: 204 }), {
    Allow: `${allowed.join(", ")}, OPTIONS`,
    "Access-Control-Allow-Methods": `${allowed.join(", ")}, OPTIONS`,
    "Access-Control-Allow-Headers": "Content-Type, X-Ingest-Secret, X-Webhook-Secret, X-LeadX-Activity",
    "Access-Control-Max-Age": "600",
    "Vary": "Origin",
  });
}

async function health(env, requestIdValue) {
  const checkedAt = new Date().toISOString();
  const response = (kvStatus, status) => json({
    status: kvStatus === "ok" ? "ok" : "degraded",
    service: "leadx",
    version: RELEASE,
    checked_at: checkedAt,
    checks: { kv: kvStatus },
  }, status);

  if (!env.LEADX_KV) {
    logEvent("health.degraded", requestIdValue, "error", { check: "kv", reason: "binding_missing" });
    return response("fail", 503);
  }

  let timeoutId;
  try {
    const timeout = new Promise((_, reject) => {
      timeoutId = setTimeout(() => reject(new Error("kv_timeout")), HEALTH_KV_TIMEOUT_MS);
    });
    const stored = await Promise.race([
      env.LEADX_KV.get(HEALTH_DATA_KEY, { type: "stream" }),
      timeout,
    ]);
    if (stored === null) throw new Error("kv_data_missing");
    if (typeof stored?.cancel === "function") {
      try { await stored.cancel(); } catch { /* best-effort stream cleanup */ }
    }
    return response("ok", 200);
  } catch {
    logEvent("health.degraded", requestIdValue, "error", { check: "kv", reason: "read_failed" });
    return response("fail", 503);
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const requestIdValue = requestId(request);
    const allowed = methodsFor(url.pathname);

    if (REMOVED_PATHS.has(url.pathname)) return json({ error: "not_found" }, 404);
    if (url.pathname.startsWith("/api/") && !allowed) return json({ error: "not_found" }, 404);
    if (!sameOriginAllowed(request, url)) return json({ error: "cross_origin_forbidden" }, 403, { "Vary": "Origin" });
    if (allowed && request.method === "OPTIONS") return preflight(allowed);
    if (allowed && !allowed.includes(request.method)) return methodNotAllowed(allowed);

    try {
      if (url.pathname === "/api/auth/login") return await handleLogin(request, env, requestIdValue);
      if (url.pathname === "/api/auth/session") return await handleSession(request, env);
      if (url.pathname === "/api/auth/activity") return await handleActivity(request, env);
      if (url.pathname === "/api/auth/logout") return json({ ok: true }, 200, { ...privateHeaders(), "Set-Cookie": expiredCookie() });
      if (url.pathname === "/api/leads") return await handleLeads(request, env);
      if (url.pathname === "/api/metrics") return await handleMetrics(request, env);
      if (url.pathname === "/api/ingest") return await handleIngest(request, env, requestIdValue);
      if (url.pathname === PRIVATE_IMPORT_PATH) return await handlePrivateImport(request, env, requestIdValue);
      if (url.pathname === "/api/health") return await health(env, requestIdValue);
      return await serveAsset(request, env);
    } catch {
      logEvent("request.failed", requestIdValue, "error", { route: url.pathname.startsWith("/api/") ? "api" : "asset" });
      return json({ error: "internal_error", request_id: requestIdValue }, 500);
    }
  },
};
