import { readFileSync, readdirSync, existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();
const REPO = join(ROOT, "..");
const SRC = join(ROOT, "src");
const DIST = join(ROOT, "dist");
const worker = (await import(new URL("../../worker/runtime.mjs", import.meta.url))).default;
const workerFiles = ["worker.js", "worker/config.mjs", "worker/http.mjs", "worker/session.mjs", "worker/body.mjs", "worker/auth-handlers.mjs", "worker/data-handlers.mjs", "worker/runtime.mjs"];
const workerSource = workerFiles.map((path) => readFileSync(join(REPO, path), "utf8")).join("\n");
const readSource = (path) => readFileSync(join(SRC, path), "utf8");
const readAll = (directory) => {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? readAll(path) : [path];
  });
};
const distFiles = readAll(DIST);
const bundleJs = distFiles.find((file) => file.endsWith(".js"));
const bundleCss = distFiles.find((file) => file.endsWith(".css"));
const indexHtml = existsSync(join(DIST, "index.html")) ? readFileSync(join(DIST, "index.html"), "utf8") : "";
const bundleContent = bundleJs ? readFileSync(bundleJs, "utf8") : "";
const apiSource = readSource(join("lib", "api.ts"));
const appSource = readSource("App.tsx");
const sessionSource = readSource(join("lib", "session-state.ts"));
const styleSource = readSource("styles.css");
const kpiSource = readSource(join("components", "Kpis.tsx"));
const listSource = readSource(join("components", "LeadTable.tsx"));
const detailSource = readSource(join("components", "LeadDetail.tsx"));
const actionsSource = readSource(join("components", "Actions.tsx"));
const demoSource = readSource("demo-leads.ts");
const allClientSource = readAll(SRC).map((file) => readFileSync(file, "utf8")).join("\n");
const wranglerSource = readFileSync(join(REPO, "wrangler.toml"), "utf8");
const results = [];
function test(name, condition) {
  const ok = Boolean(condition);
  results.push({ control: `B${String(results.length + 1).padStart(3, "0")}`, name, ok });
  console[ok ? "log" : "error"](`${ok ? "✓" : "✗"} ${results.at(-1).control} ${name}`);
}

const names = ["Benitez", "Cadiboni", "Lotito", "Cepero", "Ecovictor", "Vlad Gold"];
test("bundle has no real-name sentinels", !names.some((name) => bundleContent.includes(name)));
test("HTML has no real-name sentinels", !names.some((name) => indexHtml.includes(name)));
test("client has no server secrets or digit-join credentials", !["DASHBOARD_PASSWORD", "SESSION_SECRET", "INGEST_SECRET"].some((name) => bundleContent.includes(name)) && !/\[\s*["']\d["'](?:\s*,\s*["']\d["']){2,}\s*\]\.join/.test(allClientSource));
test("login failure stays unauthenticated", apiSource.includes("return { ok: false") && !apiSource.includes("setSession"));
test("rate limit is fail-closed with Retry-After", workerSource.includes("env.LOGIN_RATE_LIMITER.limit") && workerSource.includes('"Retry-After": "60"') && workerSource.includes("429"));
test("successful login switches to real mode", appSource.includes("authenticated: true") && appSource.includes('mode: "real"'));
test("refresh checks server session", apiSource.includes("checkSession") && workerSource.includes('url.pathname === "/api/auth/session"'));
test("logout and expiry purge real state", appSource.includes("purgeRealSessionState(demoByVertical(vertical),clearCrmState)") && appSource.includes("setSelectedLead(null)") && sessionSource.includes("authenticated: false"));
test("session cookie is hardened", workerSource.includes("HttpOnly; Secure; SameSite=Strict; Path=/"));
const ingestStart = workerSource.indexOf("async function handleIngest");
const ingestEnd = workerSource.indexOf("async function serveAsset", ingestStart);
const ingestSection = workerSource.slice(ingestStart, ingestEnd);
test("ingest uses only INGEST_SECRET", ingestStart >= 0 && ingestSection.includes("env.INGEST_SECRET") && !ingestSection.includes("DASHBOARD_PASSWORD") && !ingestSection.includes("SESSION_SECRET"));
test("build emitted JS CSS and HTML", Boolean(bundleJs && bundleCss && indexHtml));
test("no Wrangler publish artifact", !existsSync(join(ROOT, ".wrangler", "published.json")) && !existsSync(join(REPO, ".wrangler", "published.json")));
test("anonymous metrics are fixed demo metrics", workerSource.includes('status: "demo"') && workerSource.includes("total_leads: 12") && workerSource.includes("qualified_leads"));
test("private responses are no-store and vary on Cookie", workerSource.includes('"Cache-Control": "no-store, private"') && workerSource.includes('"Vary": "Cookie"'));
test("rate limiter has no memory fallback", !workerSource.includes("globalThis[_rlKey]") && !workerSource.includes("new Map() // rate"));
test("Wrangler declares login rate limiter", wranglerSource.includes('name = "LOGIN_RATE_LIMITER"') && wranglerSource.includes("limit = 5") && wranglerSource.includes("period = 60"));
test("missing login rate limiter returns 503", workerSource.includes("if (!env.LOGIN_RATE_LIMITER) return json") && workerSource.includes("503"));
test("dashboard has four KPIs", (kpiSource.match(/className="kpi"/g) || []).length === 4);
test("mobile list uses real cards alongside the desktop table", listSource.includes("<article") && listSource.includes('className="mobile-cards"') && listSource.includes("<table"));
test("demo real modes and mobile login remain", appSource.includes("Desbloquear datos reales") && appSource.includes("Datos ficticios para explorar el CRM") && appSource.includes("Modo demo") && appSource.includes("Datos reales"));
test("lead detail is a dialog with actions", detailSource.includes('role="dialog"') && detailSource.includes("<Actions") && styleSource.includes(".lead-detail"));
test("mobile target sizing remains", styleSource.includes("min-height:44px") && styleSource.includes("@media(max-width:760px)"));
test("client does not persist CRM data", !allClientSource.includes("localStorage") && !allClientSource.includes("sessionStorage") && !allClientSource.includes("indexedDB"));
test("ASSETS is sole UI and demo contacts remain fictitious", !workerSource.includes("DASHBOARD_HTML") && !workerSource.includes("COOKIES_HTML") && !workerSource.includes("async scheduled") && workerSource.includes("env.ASSETS.fetch") && demoSource.includes("555"));

const PASSWORD = `baseline-${crypto.randomUUID()}`;
const SESSION_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const PRIVATE = "SYNTHETIC_PRIVATE_SENTINEL";
const privatePayload = { leads_all: [{ id: "private-fixture-1", persona: PRIVATE, score: 91, telefono_publico: "+5490000000000" }], leads_hot: [], meta: { source: "synthetic-test" } };
function environment(overrides = {}) {
  const calls = { get: 0, put: 0, assets: 0 };
  return { calls, env: {
    ASSETS: { fetch: async (request) => { calls.assets += 1; const path = new URL(request.url).pathname; return path === "/" || path === "/index.html" || path === "/app" ? new Response('<div id="root"></div>', { status: 200 }) : new Response("not found", { status: 404 }); } },
    LOGIN_RATE_LIMITER: { limit: async () => ({ success: true }) },
    LEADX_KV: { get: async (key) => { calls.get += 1; return key === "leads:live" ? JSON.stringify(privatePayload) : null; }, put: async () => { calls.put += 1; } },
    DASHBOARD_PASSWORD: PASSWORD, SESSION_SECRET, INGEST_SECRET: `${crypto.randomUUID()}${crypto.randomUUID()}`, ...overrides,
  } };
}
async function call(path, init = {}, context = environment()) {
  const response = await worker.fetch(new Request(`https://leadx.test${path}`, { ...init, headers: { "CF-Connecting-IP": "203.0.113.10", ...(init.headers || {}) } }), context.env, { waitUntil() {} });
  return { response, context };
}
async function login(context) {
  const { response } = await call("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: PASSWORD }) }, context);
  return { response, cookie: (response.headers.get("Set-Cookie") || "").split(";")[0] };
}
const anonymous = environment();
const sessionResponse = (await call("/api/auth/session", {}, anonymous)).response;
const sessionBody = await sessionResponse.json();
test("anonymous session returns 200", sessionResponse.status === 200);
test("anonymous session is demo unauthenticated", !sessionBody.authenticated && sessionBody.mode === "demo");
test("anonymous session skips KV", anonymous.calls.get === 0);
const leadsResponse = (await call("/api/leads", {}, anonymous)).response;
const leadsText = await leadsResponse.text();
const leads = JSON.parse(leadsText);
test("anonymous leads return 200", leadsResponse.status === 200);
test("anonymous has twelve leads", leads.leads_all?.length === 12);
test("anonymous leads are marked demo", leads.leads_all?.every((lead) => lead._isDemo));
test("demo leads have no contact destinations", leads.leads_all?.every((lead) => !lead.telefono_publico && !lead.whatsapp_publico && !lead.email_publico && !lead.fb_username && !lead.fb_author_id));
test("demo leads have no external URLs", leads.leads_all?.every((lead) => !lead.source_url && !lead.url));
test("anonymous leads omit private sentinel", !leadsText.includes(PRIVATE));
test("anonymous leads skip KV", anonymous.calls.get === 0);
test("anonymous metadata is demo", leads.meta?.source === "demo");
const metricsResponse = (await call("/api/metrics", {}, anonymous)).response;
const metricsText = await metricsResponse.text();
const metrics = JSON.parse(metricsText);
test("anonymous metrics return 200", metricsResponse.status === 200);
test("anonymous metrics are demo", metrics.status === "demo");
test("anonymous metrics use twelve records", metrics.total_leads === 12);
test("anonymous metrics have zero contactable", metrics.contactable_leads === 0);
test("anonymous metrics omit private sentinel", !metricsText.includes(PRIVATE));
test("anonymous metrics skip KV", anonymous.calls.get === 0);
const healthResponse = (await call("/api/health", {}, anonymous)).response;
const health = await healthResponse.json();
test("health returns 200", healthResponse.status === 200 && health.status === "ok");
test("health schema is sanitized", JSON.stringify(Object.keys(health).sort()) === JSON.stringify(["checked_at", "service", "status", "version"]));
test("health skips KV", anonymous.calls.get === 0);
const privateContext = environment();
const logged = await login(privateContext);
test("synthetic login returns 200", logged.response.status === 200 && Boolean(logged.cookie));
const setCookie = logged.response.headers.get("Set-Cookie") || "";
test("login cookie has required flags", /HttpOnly/i.test(setCookie) && /Secure/i.test(setCookie) && /SameSite=Strict/i.test(setCookie));
const privateLeads = (await call("/api/leads", { headers: { Cookie: logged.cookie } }, privateContext)).response;
const privateLeadsText = await privateLeads.text();
test("authenticated leads read synthetic private fixture", privateLeads.status === 200 && privateLeadsText.includes(PRIVATE));
test("authenticated leads are private no-store", privateLeads.headers.get("Cache-Control") === "no-store, private" && privateLeads.headers.get("Vary") === "Cookie");
const privateMetrics = (await call("/api/metrics", { headers: { Cookie: logged.cookie } }, privateContext)).response;
test("authenticated metrics use private fixture", privateMetrics.status === 200 && (await privateMetrics.json()).total_leads === 1);
const invalidCookie = (await call("/api/leads", { headers: { Cookie: `${logged.cookie}tampered` } }, privateContext)).response;
test("invalid cookie fails closed", invalidCookie.status === 401 && (invalidCookie.headers.get("Set-Cookie") || "").includes("Max-Age=0"));
const noLimiter = environment({ LOGIN_RATE_LIMITER: undefined });
test("missing limiter returns 503", (await call("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: PASSWORD }) }, noLimiter)).response.status === 503);
const blocked = environment({ LOGIN_RATE_LIMITER: { limit: async () => ({ success: false }) } });
const blockedResponse = (await call("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: "synthetic-wrong" }) }, blocked)).response;
test("rate-limited login returns 429", blockedResponse.status === 429 && blockedResponse.headers.get("Retry-After") === "60");
const root = environment();
const rootResponse = (await call("/app", {}, root)).response;
const unknownResponse = (await call("/api/legacy-dashboard", {}, environment())).response;
test("React assets are sole UI and unknown API is 404", rootResponse.status === 200 && root.calls.assets > 0 && unknownResponse.status === 404 && !workerSource.includes("DASHBOARD_HTML"));

const originalNow = Date.now;
let now = 1_800_000_000_000;
Date.now = () => now;
try {
  const sessionContext = environment();
  const first = await login(sessionContext);
  const decode = (cookie) => JSON.parse(atob(cookie.slice(cookie.indexOf("=") + 1).split(".")[0].replace(/-/g, "+").replace(/_/g, "/")));
  const firstPayload = decode(first.cookie);
  test("session payload has iat activity nonce", firstPayload.iat === now && firstPayload.lastActivity === now && firstPayload.nonce.length >= 16);
  const altered = `${first.cookie.slice(0, -1)}${first.cookie.endsWith("a") ? "b" : "a"}`;
  test("altered cookie is rejected", (await call("/api/leads", { headers: { Cookie: altered } }, sessionContext)).response.status === 401);
  now = firstPayload.iat + 20 * 60_000 + 1;
  const idle = (await call("/api/leads", { headers: { Cookie: first.cookie } }, sessionContext)).response;
  const idleBody = await idle.json();
  test("idle expires after twenty minutes", idle.status === 401 && idleBody.reason === "idle_expired");
  test("idle expiry clears cookie", (idle.headers.get("Set-Cookie") || "").includes("Max-Age=0"));
  now = 1_800_100_000_000;
  const renewal = await login(sessionContext);
  const before = decode(renewal.cookie);
  now += 61_000;
  const activity = (await call("/api/auth/activity", { method: "POST", headers: { Cookie: renewal.cookie, "X-LeadX-Activity": "user" } }, sessionContext)).response;
  const renewedCookie = (activity.headers.get("Set-Cookie") || "").split(";")[0];
  const after = decode(renewedCookie);
  test("activity renews lastActivity", activity.status === 200 && after.lastActivity === now);
  test("activity preserves iat", after.iat === before.iat);
  test("activity rotates nonce", after.nonce !== before.nonce);
  now = 1_800_200_000_000;
  const polling = await login(sessionContext);
  const pollingStart = decode(polling.cookie).iat;
  now += 10 * 60_000;
  const poll = (await call("/api/auth/session", { headers: { Cookie: polling.cookie } }, sessionContext)).response;
  test("polling validates without renewal", poll.status === 200 && !poll.headers.has("Set-Cookie"));
  now = pollingStart + 20 * 60_000 + 1;
  test("polling cannot prevent idle expiry", (await call("/api/leads", { headers: { Cookie: polling.cookie } }, sessionContext)).response.status === 401);
  now = 1_800_300_000_000;
  let absolute = (await login(sessionContext)).cookie;
  const absoluteIat = decode(absolute).iat;
  for (let index = 1; index <= 25; index += 1) {
    now = absoluteIat + index * 19 * 60_000;
    const response = (await call("/api/auth/activity", { method: "POST", headers: { Cookie: absolute } }, sessionContext)).response;
    const next = response.headers.get("Set-Cookie");
    if (next) absolute = next.split(";")[0];
  }
  now = absoluteIat + 8 * 60 * 60_000 + 1;
  const absoluteResponse = (await call("/api/leads", { headers: { Cookie: absolute } }, sessionContext)).response;
  const absoluteBody = await absoluteResponse.json();
  test("absolute timeout applies at eight hours", absoluteResponse.status === 401 && absoluteBody.reason === "absolute_expired");
  test("frontend purge restores demo-only state", sessionSource.includes("purgeRealSessionState") && sessionSource.includes("_isDemo: true") && sessionSource.includes("authenticated: false"));
  test("frontend purge closes selected lead", sessionSource.includes("selectedLead: null"));
  test("frontend purge avoids browser storage", !sessionSource.includes("localStorage") && !sessionSource.includes("sessionStorage") && !sessionSource.includes("indexedDB"));
} finally {
  Date.now = originalNow;
}

const passed = results.filter((result) => result.ok).length;
const failed = results.length - passed;
if (results.length !== 66) throw new Error(`baseline control count mismatch: ${results.length}`);
console.log(`BASELINE_COVERAGE=${passed}/${results.length}`);
writeFileSync(join(ROOT, "test-results.json"), JSON.stringify({ total: results.length, passed, failed, results }, null, 2));
process.exitCode = failed === 0 ? 0 : 1;
