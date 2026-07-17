import { readFile } from "node:fs/promises";
import { Buffer } from "node:buffer";

const workerSource = await readFile(new URL("../../worker.js", import.meta.url), "utf8");
const worker = (await import(`data:text/javascript;base64,${Buffer.from(workerSource).toString("base64")}`)).default;
const PASSWORD = `test-${crypto.randomUUID()}`;
const SESSION_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const INGEST_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const PRIVATE_SENTINEL = "SYNTHETIC_PRIVATE_SENTINEL";
const privatePayload = {
  leads_all: [{ id: "private-fixture-1", persona: PRIVATE_SENTINEL, score: 91, telefono_publico: "+5490000000000" }],
  leads_hot: [],
  meta: { source: "synthetic-test" },
};

function environment(overrides = {}) {
  const calls = { get: 0, put: 0, assets: 0 };
  const env = {
    ASSETS: {
      fetch: async (request) => {
        calls.assets += 1;
        const path = new URL(request.url).pathname;
        if (path === "/" || path === "/index.html" || path === "/app") {
          return new Response('<!doctype html><div id="root"></div><script type="module" src="/assets/app.js"></script>', { status: 200, headers: { "Content-Type": "text/html" } });
        }
        return new Response("not found", { status: 404 });
      },
    },
    LOGIN_RATE_LIMITER: { limit: async () => ({ success: true }) },
    LEADX_KV: {
      get: async (key) => { calls.get += 1; return key === "leads:live" ? JSON.stringify(privatePayload) : null; },
      put: async () => { calls.put += 1; },
    },
    DASHBOARD_PASSWORD: PASSWORD,
    SESSION_SECRET,
    INGEST_SECRET,
    ...overrides,
  };
  return { env, calls };
}

async function request(path, init = {}, context = environment()) {
  const req = new Request(`https://leadx.test${path}`, {
    ...init,
    headers: { "CF-Connecting-IP": "203.0.113.10", ...(init.headers || {}) },
  });
  const response = await worker.fetch(req, context.env, { waitUntil() {} });
  return { response, context };
}

async function login(context) {
  const { response } = await request("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: PASSWORD }),
  }, context);
  return { response, cookie: (response.headers.get("Set-Cookie") || "").split(";")[0] };
}

let passed = 0;
let failed = 0;
function check(name, condition) {
  if (condition) { passed += 1; console.log(`  ✓ ${name}`); }
  else { failed += 1; console.error(`  ✗ ${name}`); }
}

console.log("\nLEADX CONTAINMENT COMPATIBILITY — 29 TESTS\n");

const anonymousContext = environment();
const { response: sessionResponse } = await request("/api/auth/session", {}, anonymousContext);
const sessionBody = await sessionResponse.json();
check("1. Anonymous session returns 200", sessionResponse.status === 200);
check("2. Anonymous session is demo and unauthenticated", sessionBody.authenticated === false && sessionBody.mode === "demo");
check("3. Anonymous session does not read KV", anonymousContext.calls.get === 0);

const { response: anonymousLeadsResponse } = await request("/api/leads", {}, anonymousContext);
const anonymousLeadsText = await anonymousLeadsResponse.text();
const anonymousLeads = JSON.parse(anonymousLeadsText);
check("4. Anonymous leads return 200", anonymousLeadsResponse.status === 200);
check("5. Anonymous leads contain exactly 12 records", anonymousLeads.leads_all?.length === 12);
check("6. Every anonymous lead is explicitly demo", anonymousLeads.leads_all?.every((lead) => lead._isDemo === true));
check("7. Demo leads contain no contact destination fields", anonymousLeads.leads_all?.every((lead) => !lead.telefono_publico && !lead.whatsapp_publico && !lead.email_publico && !lead.fb_username && !lead.fb_author_id));
check("8. Demo leads contain no external source URL", anonymousLeads.leads_all?.every((lead) => !lead.source_url && !lead.url));
check("9. Anonymous leads contain no private sentinel", !anonymousLeadsText.includes(PRIVATE_SENTINEL));
check("10. Anonymous leads do not read KV", anonymousContext.calls.get === 0);
check("11. Anonymous metadata identifies demo source", anonymousLeads.meta?.source === "demo");

const { response: metricsResponse } = await request("/api/metrics", {}, anonymousContext);
const metricsText = await metricsResponse.text();
const metrics = JSON.parse(metricsText);
check("12. Anonymous metrics return 200", metricsResponse.status === 200);
check("13. Anonymous metrics are explicitly demo", metrics.status === "demo");
check("14. Anonymous metrics use the 12-record demo population", metrics.total_leads === 12);
check("15. Anonymous metrics expose zero contactable demo records", metrics.contactable_leads === 0);
check("16. Anonymous metrics contain no private sentinel", !metricsText.includes(PRIVATE_SENTINEL));
check("17. Anonymous metrics do not read KV", anonymousContext.calls.get === 0);

const { response: healthResponse } = await request("/api/health", {}, anonymousContext);
const health = await healthResponse.json();
const healthKeys = Object.keys(health).sort();
check("18. Public health returns 200", healthResponse.status === 200 && health.status === "ok");
check("19. Public health exposes only the sanitized public schema", JSON.stringify(healthKeys) === JSON.stringify(["checked_at", "service", "status", "version"]));
check("20. Public health does not read KV", anonymousContext.calls.get === 0);

const privateContext = environment();
const { response: loginResponse, cookie } = await login(privateContext);
const setCookie = loginResponse.headers.get("Set-Cookie") || "";
check("21. Valid synthetic login returns 200", loginResponse.status === 200 && Boolean(cookie));
check("22. Login cookie has HttpOnly, Secure and SameSite=Strict", /HttpOnly/i.test(setCookie) && /Secure/i.test(setCookie) && /SameSite=Strict/i.test(setCookie));
const { response: privateLeadsResponse } = await request("/api/leads", { headers: { Cookie: cookie } }, privateContext);
const privateLeadsText = await privateLeadsResponse.text();
check("23. Authenticated leads read the private synthetic fixture", privateLeadsResponse.status === 200 && privateLeadsText.includes(PRIVATE_SENTINEL));
check("24. Authenticated leads are private and no-store", privateLeadsResponse.headers.get("Cache-Control") === "no-store, private" && privateLeadsResponse.headers.get("Vary") === "Cookie");
const { response: privateMetricsResponse } = await request("/api/metrics", { headers: { Cookie: cookie } }, privateContext);
const privateMetrics = await privateMetricsResponse.json();
check("25. Authenticated metrics are computed from private fixture", privateMetricsResponse.status === 200 && privateMetrics.total_leads === 1);
const { response: invalidCookieResponse } = await request("/api/leads", { headers: { Cookie: `${cookie}tampered` } }, privateContext);
check("26. Invalid cookie fails closed", invalidCookieResponse.status === 401 && (invalidCookieResponse.headers.get("Set-Cookie") || "").includes("Max-Age=0"));
const noLimiter = environment({ LOGIN_RATE_LIMITER: undefined });
const { response: noLimiterResponse } = await request("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: PASSWORD }) }, noLimiter);
check("27. Missing rate limiter fails closed with 503", noLimiterResponse.status === 503);
const blocked = environment({ LOGIN_RATE_LIMITER: { limit: async () => ({ success: false }) } });
const { response: blockedResponse } = await request("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: "synthetic-wrong-value" }) }, blocked);
check("28. Rate-limited login returns 429 and Retry-After", blockedResponse.status === 429 && blockedResponse.headers.get("Retry-After") === "60");
const { response: rootResponse, context: rootContext } = await request("/app", {}, environment());
const { response: unknownApiResponse } = await request("/api/legacy-dashboard", {}, environment());
check("29. React assets are the sole UI and unknown APIs fail closed", rootResponse.status === 200 && rootContext.calls.assets > 0 && unknownApiResponse.status === 404 && !workerSource.includes("DASHBOARD_HTML"));

console.log(`\nRESULT: ${passed}/${passed + failed} containment tests passed`);
process.exitCode = failed === 0 ? 0 : 1;
