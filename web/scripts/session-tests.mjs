import { readFile } from "node:fs/promises";
import { Buffer } from "node:buffer";
import ts from "typescript";

const worker = (await import(new URL("../../worker/runtime.mjs", import.meta.url))).default;
const PASSWORD = "session-test-password";
const env = {
  ASSETS: { fetch: async () => new Response("asset") },
  LOGIN_RATE_LIMITER: { limit: async () => ({ success: true }) },
  LEADX_KV: {
    get: async (key) => key === "leads:live"
      ? JSON.stringify({ leads_all: [{ id: "real-1", persona: "REAL_ONLY", score: 90 }], meta: {} })
      : null,
    put: async () => undefined,
  },
  DASHBOARD_PASSWORD: PASSWORD,
  SESSION_SECRET: `${crypto.randomUUID()}${crypto.randomUUID()}`,
  INGEST_SECRET: `${crypto.randomUUID()}${crypto.randomUUID()}`,
};

let now = 1_800_000_000_000;
const originalNow = Date.now;
Date.now = () => now;

function request(path, init = {}) {
  return worker.fetch(new Request(`https://leadx.test${path}`, {
    ...init,
    headers: { "CF-Connecting-IP": "203.0.113.20", ...(init.headers || {}) },
  }), env, { waitUntil() {} });
}

async function login() {
  const response = await request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: PASSWORD }),
  });
  return (response.headers.get("Set-Cookie") || "").split(";")[0];
}

function decode(cookie) {
  const token = cookie.slice(cookie.indexOf("=") + 1);
  const payload = token.split(".")[0].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(atob(payload));
}

let passed = 0;
let failed = 0;
function check(name, condition) {
  if (condition) { passed += 1; console.log(`  ✓ ${name}`); }
  else { failed += 1; console.error(`  ✗ ${name}`); }
}

console.log("\nLEADX SESSION SECURITY — REAL CLOCK AND COOKIE TESTS\n");

try {
  now = 1_800_000_000_000;
  const originalCookie = await login();
  const originalPayload = decode(originalCookie);
  check("Login payload has iat, lastActivity and cryptographic nonce",
    originalPayload.iat === now && originalPayload.lastActivity === now && originalPayload.nonce.length >= 16);

  const policyResponse = await request("/api/auth/session", { headers: { Cookie: originalCookie } });
  const policyBody = await policyResponse.json();
  check("Session endpoint publishes a 60-minute idle expiry",
    policyBody.authenticated === true && policyBody.idleExpiresAt === originalPayload.iat + 60 * 60_000);
  check("Session endpoint publishes a 12-hour absolute expiry",
    policyBody.absoluteExpiresAt === originalPayload.iat + 12 * 60 * 60_000);

  const altered = `${originalCookie.slice(0, -1)}${originalCookie.endsWith("a") ? "b" : "a"}`;
  const alteredResponse = await request("/api/leads", { headers: { Cookie: altered } });
  check("Altered cookie is rejected", alteredResponse.status === 401);

  now = originalPayload.iat + 60 * 60_000 + 1;
  const idleResponse = await request("/api/leads", { headers: { Cookie: originalCookie } });
  const idleBody = await idleResponse.json();
  check("Idle session is rejected after 60 minutes",
    idleResponse.status === 401 && idleBody.reason === "idle_expired");
  check("Idle rejection expires the browser cookie",
    (idleResponse.headers.get("Set-Cookie") || "").includes("Max-Age=0"));

  now = 1_800_100_000_000;
  const renewalCookie = await login();
  const beforeRenewal = decode(renewalCookie);
  now += 61_000;
  const renewalResponse = await request("/api/auth/activity", {
    method: "POST",
    headers: { Cookie: renewalCookie, "X-LeadX-Activity": "user" },
  });
  const renewedCookie = (renewalResponse.headers.get("Set-Cookie") || "").split(";")[0];
  const afterRenewal = decode(renewedCookie);
  check("Explicit activity renews lastActivity",
    renewalResponse.status === 200 && afterRenewal.lastActivity === now);
  check("Explicit activity preserves original iat", afterRenewal.iat === beforeRenewal.iat);
  check("Explicit activity rotates nonce", afterRenewal.nonce !== beforeRenewal.nonce);

  now = 1_800_200_000_000;
  const pollingCookie = await login();
  const pollingStart = decode(pollingCookie).iat;
  now += 30 * 60_000;
  const pollingResponse = await request("/api/auth/session", { headers: { Cookie: pollingCookie } });
  check("Polling validates but does not renew", pollingResponse.status === 200 && !pollingResponse.headers.has("Set-Cookie"));
  now = pollingStart + 60 * 60_000 + 1;
  const afterPolling = await request("/api/leads", { headers: { Cookie: pollingCookie } });
  check("Polling cannot prevent idle expiration", afterPolling.status === 401);

  now = 1_800_300_000_000;
  let absoluteCookie = await login();
  const absoluteIat = decode(absoluteCookie).iat;
  for (let index = 1; index <= 15; index += 1) {
    now = absoluteIat + index * 45 * 60_000;
    const response = await request("/api/auth/activity", {
      method: "POST",
      headers: { Cookie: absoluteCookie, "X-LeadX-Activity": "user" },
    });
    const next = response.headers.get("Set-Cookie");
    if (next) absoluteCookie = next.split(";")[0];
  }
  now = absoluteIat + 12 * 60 * 60_000 + 1;
  const absoluteResponse = await request("/api/leads", { headers: { Cookie: absoluteCookie } });
  const absoluteBody = await absoluteResponse.json();
  check("Absolute timeout rejects an otherwise active session after 12 hours",
    absoluteResponse.status === 401 && absoluteBody.reason === "absolute_expired");

  let storageCalls = 0;
  globalThis.localStorage = new Proxy({}, { get() { storageCalls += 1; throw new Error("storage forbidden"); } });
  const stateSource = await readFile(new URL("../src/lib/session-state.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(stateSource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const stateModule = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
  const safe = stateModule.purgeRealSessionState(
    [{ id: "demo", persona: "Demo", score: 1 }],
    () => undefined,
    now,
  );
  check("Frontend cleanup replaces real state with demo-only state",
    safe.session.authenticated === false && safe.isDemo === true && safe.leads.every((lead) => lead._isDemo));
  check("Frontend cleanup closes selected lead", safe.selectedLead === null);
  check("Frontend cleanup never accesses localStorage", storageCalls === 0);
} finally {
  Date.now = originalNow;
  delete globalThis.localStorage;
}

console.log(`\nRESULT: ${passed}/${passed + failed} session tests passed`);
process.exitCode = failed === 0 ? 0 : 1;
