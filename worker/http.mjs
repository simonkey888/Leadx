import { SESSION_COOKIE } from "./config.mjs";

export function requestId(request) {
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

export function responseWithHeaders(response, extra = {}) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries({ ...securityHeaders(), ...extra })) headers.set(key, value);
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export function json(data, status = 200, extra = {}) {
  return responseWithHeaders(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
  }), extra);
}

export function logEvent(event, requestIdValue, status, fields = {}) {
  console.log(JSON.stringify({ event, timestamp: new Date().toISOString(), requestId: requestIdValue, status, ...fields }));
}

export function sameOriginAllowed(request, url) {
  const origin = request.headers.get("Origin");
  return !origin || origin === `${url.protocol}//${url.host}`;
}

export function cookieValue(request, name) {
  const cookie = request.headers.get("Cookie") || "";
  const match = cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return match ? match[1] : null;
}

export function base64UrlEncode(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export function base64UrlDecode(value) {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function digest(value) {
  return new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
}

export async function secureEqual(left, right) {
  if (typeof left !== "string" || typeof right !== "string") return false;
  const [a, b] = await Promise.all([digest(left), digest(right)]);
  let difference = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) difference |= (a[index] || 0) ^ (b[index] || 0);
  return difference === 0;
}

export async function hmac(value, secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return base64UrlEncode(new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value))));
}

export function randomNonce() {
  return base64UrlEncode(crypto.getRandomValues(new Uint8Array(18)));
}

export function expiredCookie() {
  return `${SESSION_COOKIE}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;
}
