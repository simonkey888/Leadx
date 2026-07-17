import { readFile } from "node:fs/promises";
import { Buffer } from "node:buffer";

const workerSource = await readFile(new URL("../../worker.js", import.meta.url), "utf8");
const inventorySource = await readFile(new URL("../../docs/api-inventory.md", import.meta.url), "utf8");
const worker = (await import(`data:text/javascript;base64,${Buffer.from(workerSource).toString("base64")}`)).default;

const PASSWORD = `runtime-${crypto.randomUUID()}`;
const SESSION_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const INGEST_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;

function createEnvironment(options = {}) {
  const calls = { get: 0, put: 0, lastValue: null };
  const initial = options.initial ?? null;
  const env = {
    ASSETS: { fetch: async () => new Response('<div id="root"></div>', { headers: { "Content-Type": "text/html" } }) },
    LOGIN_RATE_LIMITER: { limit: async () => ({ success: true }) },
    LEADX_KV: {
      get: async () => {
        calls.get += 1;
        if (options.throwOnGet) throw new Error("synthetic storage failure");
        return initial;
      },
      put: async (_key, value) => {
        calls.put += 1;
        calls.lastValue = value;
        if (options.throwOnPut) throw new Error("synthetic storage failure");
      },
    },
    DASHBOARD_PASSWORD: PASSWORD,
    SESSION_SECRET,
    INGEST_SECRET,
  };
  return { env, calls };
}

async function call(path, init = {}, context = createEnvironment()) {
  const request = new Request(`https://leadx.test${path}`, {
    ...init,
    headers: { "CF-Connecting-IP": "203.0.113.22", ...(init.headers || {}) },
  });
  return { response: await worker.fetch(request, context.env, { waitUntil() {} }), context };
}

async function login(context) {
  const { response } = await call("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: PASSWORD }),
  }, context);
  return (response.headers.get("Set-Cookie") || "").split(";")[0];
}

function lead(index) {
  return {
    id: `fixture_${index}`,
    score: 70 + index,
    persona: `Persona sintética ${index}`,
    provincia: "Santa Fe",
    title: "Consulta vehicular sintética",
    snippet: "Fixture sin datos personales ni destino de contacto.",
    fecha_iso: new Date(1_800_000_000_000 - index * 1000).toISOString(),
    _status: "Nuevo",
    _priority: "Media",
  };
}

let passed = 0;
let failed = 0;
function check(name, condition) {
  if (condition) { passed += 1; console.log(`  ✓ ${name}`); }
  else { failed += 1; console.error(`  ✗ ${name}`); }
}

console.log("\nLEADX NEW SECURITY RUNTIME TESTS\n");

const noSecret = createEnvironment();
const { response: noSecretResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ leads_all: Array.from({ length: 5 }, (_, index) => lead(index)) }),
}, noSecret);
check("1. Ingest without INGEST_SECRET is rejected before KV access", noSecretResponse.status === 401 && noSecret.calls.get === 0 && noSecret.calls.put === 0);

const sessionOnly = createEnvironment();
const sessionCookie = await login(sessionOnly);
const { response: sessionOnlyResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", Cookie: sessionCookie }, body: JSON.stringify({ leads_all: Array.from({ length: 5 }, (_, index) => lead(index)) }),
}, sessionOnly);
check("2. Dashboard session cannot authorize ingest", sessionOnlyResponse.status === 401 && sessionOnly.calls.put === 0);

const dashboardSecret = createEnvironment();
const { response: dashboardSecretResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": PASSWORD }, body: JSON.stringify({ leads_all: Array.from({ length: 5 }, (_, index) => lead(index)) }),
}, dashboardSecret);
check("3. Dashboard password cannot authorize ingest", dashboardSecretResponse.status === 401 && dashboardSecret.calls.put === 0);

const validIngest = createEnvironment();
const { response: validIngestResponse } = await call("/api/ingest", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET },
  body: JSON.stringify({ leads_all: Array.from({ length: 5 }, (_, index) => lead(index)), meta: { source: "fixture", version: "test" } }),
}, validIngest);
const stored = JSON.parse(validIngest.calls.lastValue || "{}");
check("4. Valid INGEST_SECRET accepts a synthetic payload", validIngestResponse.status === 200 && validIngest.calls.put === 1 && stored.leads_all?.length === 5);
check("5. Ingest strips unrecognized fields and forces non-demo records", stored.leads_all?.every((item) => item._isDemo === false && item.constructor === Object));

const malformed = createEnvironment();
const { response: malformedResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: "{",
}, malformed);
check("6. Malformed ingest JSON returns 400 without KV mutation", malformedResponse.status === 400 && malformed.calls.put === 0);

const invalidSchema = createEnvironment();
const { response: invalidSchemaResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: JSON.stringify({ leads_all: "not-an-array" }),
}, invalidSchema);
check("7. Invalid ingest schema returns 400", invalidSchemaResponse.status === 400 && invalidSchema.calls.put === 0);

const invalidLead = createEnvironment();
const { response: invalidLeadResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: JSON.stringify({ leads_all: [{ id: "../../bad" }] }),
}, invalidLead);
check("8. Invalid lead identifiers are rejected", invalidLeadResponse.status === 400 && invalidLead.calls.put === 0);

const duplicate = createEnvironment();
const duplicated = Array.from({ length: 5 }, (_, index) => lead(index));
duplicated[4].id = duplicated[0].id;
const { response: duplicateResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: JSON.stringify({ leads_all: duplicated }),
}, duplicate);
check("9. Duplicate lead identifiers are rejected", duplicateResponse.status === 400 && duplicate.calls.put === 0);

const oversized = createEnvironment();
const { response: oversizedResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "Content-Length": String(2 * 1024 * 1024 + 1), "X-Ingest-Secret": INGEST_SECRET }, body: "{}",
}, oversized);
check("10. Oversized ingest payload is rejected with 413", oversizedResponse.status === 413 && oversized.calls.get === 0 && oversized.calls.put === 0);

const existingPayload = JSON.stringify({ leads_all: Array.from({ length: 7 }, (_, index) => lead(index)), meta: {} });
const antiWipe = createEnvironment({ initial: existingPayload });
const { response: antiWipeResponse } = await call("/api/ingest", {
  method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: JSON.stringify({ leads_all: [lead(20)] }),
}, antiWipe);
check("11. Anti-wipe rejects a destructive small replacement", antiWipeResponse.status === 409 && antiWipe.calls.put === 0);

const healthNoKv = createEnvironment({ throwOnGet: true });
const { response: healthNoKvResponse } = await call("/api/health", {}, healthNoKv);
const healthNoKvBody = await healthNoKvResponse.json();
check("12. Public health succeeds even when KV would throw", healthNoKvResponse.status === 200 && healthNoKv.calls.get === 0 && healthNoKvBody.service === "leadx");
check("13. Public health omits operational metadata", !["lead_count", "freshness_minutes", "last_ingest_utc", "cron_active", "cron_schedule", "pipeline_status"].some((key) => key in healthNoKvBody));

const crossOrigin = createEnvironment();
const { response: crossOriginResponse } = await call("/api/leads", { headers: { Origin: "https://attacker.invalid" } }, crossOrigin);
check("14. Cross-origin CRM request is rejected", crossOriginResponse.status === 403 && crossOrigin.calls.get === 0);

const sameOriginOptions = createEnvironment();
const { response: optionsResponse } = await call("/api/leads", { method: "OPTIONS", headers: { Origin: "https://leadx.test" } }, sameOriginOptions);
check("15. Same-origin preflight is bounded and does not enable credentialed CORS", optionsResponse.status === 204 && !optionsResponse.headers.has("Access-Control-Allow-Origin") && !optionsResponse.headers.has("Access-Control-Allow-Credentials"));

const headersContext = createEnvironment();
const { response: headersResponse } = await call("/api/health", {}, headersContext);
check("16. Security headers are present on API responses", headersResponse.headers.get("X-Content-Type-Options") === "nosniff" && headersResponse.headers.get("X-Frame-Options") === "DENY" && Boolean(headersResponse.headers.get("Content-Security-Policy")));

const errorContext = createEnvironment({ throwOnGet: true });
const errorCookie = await login(errorContext);
const { response: errorResponse } = await call("/api/leads", { headers: { Cookie: errorCookie } }, errorContext);
const errorText = await errorResponse.text();
check("17. Internal errors are generic and do not leak exception details", errorResponse.status === 500 && !errorText.includes("synthetic storage failure") && !errorText.includes("stack"));

const keptRoutes = [
  "/api/auth/login", "/api/auth/session", "/api/auth/activity", "/api/auth/logout",
  "/api/leads", "/api/metrics", "/api/ingest", "/api/health",
];
check("18. Every retained inventory endpoint is implemented", keptRoutes.every((route) => inventorySource.includes(`\`${route}\``) && workerSource.includes(`\"${route}\"`)));

const removedRoutes = [
  "/api/kv", "/api/ml-questions", "/api/reddit-bio", "/api/ddg-foromoto",
  "/api/clasificar-webhook", "/api/clasificar-patente", "/api/clasificar-basic",
  "/api/apify-facebook", "/api/cookies", "/api/whatsapp-validate",
  "/api/whatsapp-webhook", "/api/apify-webhook", "/api/enrich-patente",
  "/api/analyze-acta", "/api/forensic-case", "/api/cron-run", "/api/enrich-all",
  "/api/reddit-profile-links", "/api/shadow-osint", "/api/ventafe-debug",
];
check("19. Every removed inventory endpoint is absent from the Worker", removedRoutes.every((route) => inventorySource.includes(`\`${route}\``) && !workerSource.includes(`\"${route}\"`)));
check("20. Legacy embedded UI and Worker cron are absent", !workerSource.includes("DASHBOARD_HTML") && !workerSource.includes("COOKIES_HTML") && !workerSource.includes("scheduled(") && !workerSource.includes("runPipelineCron"));

console.log(`\nRESULT: ${passed}/${passed + failed} new security tests passed`);
process.exitCode = failed === 0 ? 0 : 1;
