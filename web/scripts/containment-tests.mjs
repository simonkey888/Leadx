import { readFile } from "node:fs/promises";
import { Buffer } from "node:buffer";

const workerPath = new URL("../../worker.js", import.meta.url);
const workerSource = await readFile(workerPath, "utf8");
const wranglerSource = await readFile(new URL("../../wrangler.toml", import.meta.url), "utf8");
const workerModule = await import(
  `data:text/javascript;base64,${Buffer.from(workerSource).toString("base64")}`
);
const worker = workerModule.default;

const REAL_SENTINEL = "PRIVATE_KV_SENTINEL";
const PASSWORD = "test-dashboard-password";
const SESSION_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const INGEST_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const realPayload = {
  leads_all: [{
    id: "private-kv-1",
    persona: REAL_SENTINEL,
    score: 91,
    telefono_publico: "+5490000000000",
    url: "https://private.invalid/case",
  }],
  leads_hot: [],
  meta: { source: "local-test-kv", version: "test" },
};

function environment(overrides = {}) {
  return {
    ASSETS: { fetch: async () => new Response("asset", { status: 200 }) },
    LOGIN_RATE_LIMITER: { limit: async () => ({ success: true }) },
    LEADX_KV: {
      get: async (key) => key === "leads:live" ? JSON.stringify(realPayload) : null,
      put: async () => undefined,
    },
    DASHBOARD_PASSWORD: PASSWORD,
    SESSION_SECRET,
    INGEST_SECRET,
    ...overrides,
  };
}

async function request(path, init = {}, env = environment()) {
  const req = new Request(`https://leadx.test${path}`, {
    ...init,
    headers: {
      "CF-Connecting-IP": "203.0.113.10",
      ...(init.headers || {}),
    },
  });
  return worker.fetch(req, env, { waitUntil() {} });
}

let passed = 0;
let failed = 0;

function check(name, condition, detail = "") {
  if (condition) {
    passed += 1;
    console.log(`  ✓ ${name}`);
  } else {
    failed += 1;
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

console.log("\nLEADX PRODUCTION DATA CONTAINMENT — INTEGRATED WORKER TESTS\n");

const sessionResponse = await request("/api/auth/session");
const sessionBody = await sessionResponse.json();
check("Anonymous session endpoint returns 200", sessionResponse.status === 200);
check(
  "Anonymous session is explicitly unauthenticated demo mode",
  sessionBody.authenticated === false && sessionBody.mode === "demo",
);

const anonymousLeadsResponse = await request("/api/leads");
const anonymousLeadsText = await anonymousLeadsResponse.text();
const anonymousLeads = JSON.parse(anonymousLeadsText);
check("Anonymous leads endpoint returns 200", anonymousLeadsResponse.status === 200);
check("Anonymous response contains exactly 12 leads", anonymousLeads.leads_all?.length === 12);
check(
  "Every anonymous lead is marked as demo",
  anonymousLeads.leads_all?.every((lead) => lead._isDemo === true),
);
check("Anonymous leads never contain the KV sentinel", !anonymousLeadsText.includes(REAL_SENTINEL));
check("Anonymous leads never contain the private test phone", !anonymousLeadsText.includes("+5490000000000"));
check("Anonymous leads never contain the private test URL", !anonymousLeadsText.includes("private.invalid"));
check(
  "Anonymous leads metadata identifies demo source",
  anonymousLeads.meta?.source === "demo",
);

const anonymousMetricsResponse = await request("/api/metrics");
const anonymousMetricsText = await anonymousMetricsResponse.text();
const anonymousMetrics = JSON.parse(anonymousMetricsText);
check("Anonymous metrics endpoint returns 200", anonymousMetricsResponse.status === 200);
check("Anonymous metrics are explicitly demo", anonymousMetrics.status === "demo");
check("Anonymous metrics never contain the KV sentinel", !anonymousMetricsText.includes(REAL_SENTINEL));
check(
  "Anonymous metrics use the fixed demo population",
  anonymousMetrics.total_leads === 12 && anonymousMetrics.hot_leads === 4,
);

const loginResponse = await request("/api/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ password: PASSWORD }),
});
const setCookie = loginResponse.headers.get("Set-Cookie") || "";
const cookie = setCookie.split(";")[0];
check("Valid login returns 200", loginResponse.status === 200);
check("Login issues an HttpOnly cookie", /;\s*HttpOnly/i.test(setCookie));
check("Login cookie is Secure", /;\s*Secure/i.test(setCookie));
check("Login cookie is SameSite=Strict", /;\s*SameSite=Strict/i.test(setCookie));

const authenticatedLeadsResponse = await request("/api/leads", {
  headers: { Cookie: cookie },
});
const authenticatedLeadsText = await authenticatedLeadsResponse.text();
check("Authenticated leads return the KV sentinel", authenticatedLeadsText.includes(REAL_SENTINEL));
check(
  "Authenticated leads disable caching",
  authenticatedLeadsResponse.headers.get("Cache-Control") === "no-store, private",
);
check("Authenticated leads vary on Cookie", authenticatedLeadsResponse.headers.get("Vary") === "Cookie");

const authenticatedMetricsResponse = await request("/api/metrics", {
  headers: { Cookie: cookie },
});
const authenticatedMetrics = await authenticatedMetricsResponse.json();
check("Authenticated metrics are computed from KV", authenticatedMetrics.total_leads === 1);
check(
  "Authenticated metrics disable caching",
  authenticatedMetricsResponse.headers.get("Cache-Control") === "no-store, private",
);
check("Authenticated metrics vary on Cookie", authenticatedMetricsResponse.headers.get("Vary") === "Cookie");

const authenticatedSessionResponse = await request("/api/auth/session", {
  headers: { Cookie: cookie },
});
const authenticatedSession = await authenticatedSessionResponse.json();
check(
  "Valid cookie authenticates the session endpoint",
  authenticatedSessionResponse.status === 200 && authenticatedSession.authenticated === true,
);

const missingRateLimiterResponse = await request(
  "/api/auth/login",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: PASSWORD }),
  },
  environment({ LOGIN_RATE_LIMITER: undefined }),
);
check("Missing rate limiter fails safe with 503", missingRateLimiterResponse.status === 503);

const blockedRateLimiterResponse = await request(
  "/api/auth/login",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: "wrong" }),
  },
  environment({ LOGIN_RATE_LIMITER: { limit: async () => ({ success: false }) } }),
);
check("Exceeded rate limit returns 429", blockedRateLimiterResponse.status === 429);

check(
  "Worker requires all three secret names",
  ["DASHBOARD_PASSWORD", "SESSION_SECRET", "INGEST_SECRET"]
    .every((name) => workerSource.includes(`env.${name}`)),
);
check(
  "Static Assets binding points to the React build",
  wranglerSource.includes('[assets]') &&
    wranglerSource.includes('directory = "./web/dist"') &&
    wranglerSource.includes('binding = "ASSETS"'),
);
check(
  "Rate limiter is configured for 5 requests per 60 seconds",
  wranglerSource.includes('name = "LOGIN_RATE_LIMITER"') &&
    wranglerSource.includes("limit = 5") &&
    wranglerSource.includes("period = 60"),
);
check(
  "Wrangler configuration has no Scheduled Trigger",
  !/^\s*\[triggers\]/m.test(wranglerSource) && !/^\s*crons\s*=/m.test(wranglerSource),
);

console.log(`\nRESULT: ${passed}/${passed + failed} integrated containment tests passed`);
process.exitCode = failed === 0 ? 0 : 1;
