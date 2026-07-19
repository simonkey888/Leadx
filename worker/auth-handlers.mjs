import { MAX_LOGIN_BYTES, SESSION_ABSOLUTE_MS, SESSION_IDLE_MS } from "./config.mjs";
import { bodyTooLargeFromHeader } from "./body.mjs";
import { expiredCookie, json, logEvent, randomNonce, secureEqual } from "./http.mjs";
import { expiredSession, issueSession, privateHeaders, sessionConfigurationFailure, verifySession } from "./session.mjs";

export async function handleLogin(request, env, requestIdValue) {
  if (!env.DASHBOARD_PASSWORD || !env.SESSION_SECRET) return json({ ok: false, error: "Servicio no disponible." }, 503);
  if (!env.LOGIN_RATE_LIMITER) return json({ ok: false, error: "Servicio no disponible." }, 503);
  const rate = await env.LOGIN_RATE_LIMITER.limit({ key: `login:${request.headers.get("CF-Connecting-IP") || "unknown"}` });
  if (!rate.success) {
    logEvent("auth.rate_limited", requestIdValue, "rejected");
    return json({ ok: false, error: "Demasiados intentos. Esperá 1 minuto." }, 429, { "Retry-After": "60" });
  }
  if (bodyTooLargeFromHeader(request, MAX_LOGIN_BYTES)) return json({ ok: false, error: "Solicitud inválida." }, 413);

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

export async function handleSession(request, env) {
  if (!env.SESSION_SECRET) return sessionConfigurationFailure();
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

export async function handleActivity(request, env) {
  if (!env.SESSION_SECRET) return sessionConfigurationFailure();
  const verification = await verifySession(request, env, { renew: true });
  if (!verification.authenticated) return expiredSession(verification.reason);
  return json({
    ok: true,
    authenticated: true,
    idleExpiresAt: verification.session.lastActivity + SESSION_IDLE_MS,
    absoluteExpiresAt: verification.session.iat + SESSION_ABSOLUTE_MS,
  }, 200, privateHeaders(verification));
}
