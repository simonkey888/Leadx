import { SESSION_ABSOLUTE_MS, SESSION_COOKIE, SESSION_IDLE_MS, SESSION_RENEW_MIN_MS } from "./config.mjs";
import { base64UrlDecode, base64UrlEncode, cookieValue, expiredCookie, hmac, json, randomNonce, secureEqual } from "./http.mjs";

export async function issueSession(payload, env, now) {
  const encoded = base64UrlEncode(new TextEncoder().encode(JSON.stringify(payload)));
  const signature = await hmac(encoded, env.SESSION_SECRET);
  const remaining = Math.max(0, Math.ceil((payload.iat + SESSION_ABSOLUTE_MS - now) / 1000));
  return `${SESSION_COOKIE}=${encoded}.${signature}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${remaining}`;
}

export async function verifySession(request, env, { renew = false } = {}) {
  if (!env.SESSION_SECRET) return { authenticated: false, reason: "configuration" };
  const token = cookieValue(request, SESSION_COOKIE);
  if (!token) return { authenticated: false, reason: "missing" };
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

export function privateHeaders(verification = {}) {
  const headers = { "Cache-Control": "no-store, private", "Pragma": "no-cache", "Vary": "Cookie" };
  if (verification.setCookie) headers["Set-Cookie"] = verification.setCookie;
  return headers;
}

export function expiredSession(reason) {
  return json({ error: "session_expired", reason }, 401, { ...privateHeaders(), "Set-Cookie": expiredCookie() });
}

export function sessionConfigurationFailure() {
  return json({ error: "service_unavailable" }, 503, { ...privateHeaders(), "Set-Cookie": expiredCookie() });
}
