import { readFile } from "node:fs/promises";

const files = ["../../worker.js", "../../worker/config.mjs", "../../worker/http.mjs", "../../worker/session.mjs", "../../worker/body.mjs", "../../worker/auth-handlers.mjs", "../../worker/data-handlers.mjs", "../../worker/runtime.mjs"];
const source = (await Promise.all(files.map((p) => readFile(new URL(p, import.meta.url), "utf8")))).join("\n");
const inventory = await readFile(new URL("../../docs/api-inventory.md", import.meta.url), "utf8");
const worker = (await import(new URL("../../worker/runtime.mjs", import.meta.url))).default;
const PASSWORD = `runtime-${crypto.randomUUID()}`;
const SESSION_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const INGEST_SECRET = `${crypto.randomUUID()}${crypto.randomUUID()}`;
const BASE = 1_800_000_000_000;
const realNow = Date.now;
let now = BASE;
Date.now = () => now;
let passed = 0;

function env(remove = [], options = {}) {
  const calls = { get: 0, put: 0, assets: 0, last: null };
  const value = {
    ASSETS: { fetch: async () => { calls.assets += 1; return new Response("<div id=root></div>"); } },
    LOGIN_RATE_LIMITER: { limit: async () => ({ success: true }) },
    LEADX_KV: {
      get: async () => { calls.get += 1; if (options.throwGet) throw new Error("synthetic storage failure"); return options.initial ?? null; },
      put: async (_key, body) => { calls.put += 1; calls.last = body; },
    },
    DASHBOARD_PASSWORD: PASSWORD,
    SESSION_SECRET,
    INGEST_SECRET,
  };
  for (const key of remove) delete value[key];
  return { env: value, calls };
}

async function call(path, init = {}, context = env(), base = "https://leadx.invalid") {
  const options = { ...init, headers: { "CF-Connecting-IP": "203.0.113.22", ...(init.headers || {}) } };
  if (options.body instanceof ReadableStream) options.duplex = "half";
  const response = await worker.fetch(new Request(`${base}${path}`, options), context.env, { waitUntil() {} });
  return { response, context };
}

async function login(context) {
  const { response } = await call("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password: PASSWORD }) }, context);
  return (response.headers.get("Set-Cookie") || "").split(";")[0];
}

const lead = (i) => ({ id: `fixture_${i}`, score: 70 + i, persona: `Persona sintética ${i}`, provincia: "Santa Fe", title: "Consulta sintética", snippet: "Fixture sin datos personales.", fecha_iso: new Date(BASE - i * 1000).toISOString(), _status: "Nuevo", _priority: "Media" });
const payload = () => JSON.stringify({ leads_all: Array.from({ length: 5 }, (_, i) => lead(i)), meta: { source: "fixture", version: "test" } });
function check(name, condition) { if (!condition) throw new Error(`FAIL: ${name}`); passed += 1; console.log(`✓ ${name}`); }

try {
  for (const path of ["/api/auth/session", "/api/leads", "/api/metrics", "/api/health"]) {
    const c = env([], { throwGet: true }); const { response } = await call(path, {}, c);
    check(`${path} anonymous skips KV`, response.status === 200 && c.calls.get === 0);
  }
  const { response: demo } = await call("/api/leads"); const demoBody = await demo.json();
  check("demo is fixed synthetic non-contact data", demoBody.leads_all?.length === 12 && demoBody.leads_all.every((x) => x._isDemo && x.source === "demo" && /fictici/i.test(x.platform) && !["telefono_publico", "whatsapp_publico", "email_publico", "fb_username", "fb_author_id", "url", "source_url"].some((k) => k in x)));

  const methods = [["GET", "/api/auth/login", "POST"], ["POST", "/api/auth/session", "GET"], ["GET", "/api/auth/activity", "POST"], ["GET", "/api/auth/logout", "POST"], ["POST", "/api/leads", "GET"], ["POST", "/api/metrics", "GET"], ["GET", "/api/ingest", "POST"], ["POST", "/api/health", "GET"]];
  for (const [method, path, allow] of methods) { const c = env(); const { response } = await call(path, { method }, c); check(`${method} ${path} 405`, response.status === 405 && response.headers.get("Allow") === allow && c.calls.assets === 0); }

  const removed = [["GET", "/api/kv"], ["POST", "/api/kv"], ["GET", "/api/ml-questions"], ["GET", "/api/reddit-bio"], ["GET", "/api/ddg-foromoto"], ["GET", "/api/clasificar-webhook"], ["POST", "/api/clasificar-webhook"], ["GET", "/api/clasificar-patente"], ["POST", "/api/clasificar-patente"], ["GET", "/api/clasificar-basic"], ["POST", "/api/apify-facebook"], ["GET", "/cookies"], ["GET", "/cookies.html"], ["GET", "/api/cookies"], ["POST", "/api/cookies"], ["POST", "/api/whatsapp-validate"], ["POST", "/api/whatsapp-webhook"], ["POST", "/api/apify-webhook"], ["POST", "/api/enrich-patente"], ["POST", "/api/analyze-acta"], ["POST", "/api/forensic-case"], ["GET", "/api/cron-run"], ["POST", "/api/cron-run"], ["GET", "/api/enrich-all"], ["POST", "/api/enrich-all"], ["GET", "/api/reddit-profile-links"], ["GET", "/api/shadow-osint"], ["GET", "/api/ventafe-debug"]];
  for (const [method, path] of removed) { const c = env(); const { response } = await call(path, { method }, c); check(`REMOVE ${method} ${path}`, response.status === 404 && c.calls.assets + c.calls.get + c.calls.put === 0 && inventory.includes(`\`${path}\``)); }
  const unknown = env(); check("unknown API never reaches ASSETS", (await call("/api/not-a-route", {}, unknown)).response.status === 404 && unknown.calls.assets === 0);
  const spa = env(); check("SPA route uses ASSETS", (await call("/crm", {}, spa)).response.status === 200 && spa.calls.assets === 1);

  for (const type of ["text/plain", "application/x-www-form-urlencoded", "application/json; charset=latin1", "application/json; profile=test"]) { const c = env(); const { response } = await call("/api/ingest", { method: "POST", headers: { "Content-Type": type, "X-Ingest-Secret": INGEST_SECRET }, body: payload() }, c); check(`${type} -> 415`, response.status === 415 && c.calls.get + c.calls.put === 0); }
  for (const type of ["application/json", "application/json; charset=utf-8", "Application/JSON; Charset=UTF-8"]) { const c = env(); const { response } = await call("/api/ingest", { method: "POST", headers: { "Content-Type": type, "X-Ingest-Secret": INGEST_SECRET }, body: payload() }, c); check(`${type} accepted`, response.status === 200 && c.calls.put === 1); }
  const header = env(); check("Content-Length cap", (await call("/api/ingest", { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": String(2 * 1024 * 1024 + 1), "X-Ingest-Secret": INGEST_SECRET }, body: "{}" }, header)).response.status === 413 && header.calls.get + header.calls.put === 0);
  const chunk = new Uint8Array(1024 * 1024 + 1).fill(32); const stream = new ReadableStream({ start(c) { c.enqueue(chunk); c.enqueue(chunk); c.close(); } }); const streamed = env();
  check("incremental streaming cap", (await call("/api/ingest", { method: "POST", headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: stream }, streamed)).response.status === 413 && streamed.calls.get + streamed.calls.put === 0);

  for (const [missing, path, method] of [["INGEST_SECRET", "/api/ingest", "POST"], ["LEADX_KV", "/api/ingest", "POST"], ["DASHBOARD_PASSWORD", "/api/auth/login", "POST"], ["SESSION_SECRET", "/api/auth/login", "POST"], ["SESSION_SECRET", "/api/auth/session", "GET"], ["SESSION_SECRET", "/api/auth/activity", "POST"]]) { const c = env([missing]); const init = { method, headers: { "Content-Type": "application/json", "X-Ingest-Secret": INGEST_SECRET }, body: method === "POST" ? (path.includes("login") ? JSON.stringify({ password: PASSWORD }) : payload()) : undefined }; const { response } = await call(path, init, c); check(`${path} missing ${missing} -> 503`, response.status === 503 && c.calls.get + c.calls.put === 0); }

  now = BASE; const idle = env(); const idleCookie = await login(idle); now = BASE + 20 * 60 * 1000 + 1; const idleResponse = (await call("/api/leads", { headers: { Cookie: idleCookie } }, idle)).response; check("idle expiry skips KV", idleResponse.status === 401 && idle.calls.get === 0);
  now = BASE; const absolute = env(); const absoluteCookie = await login(absolute); now = BASE + 8 * 60 * 60 * 1000 + 1; const absoluteResponse = (await call("/api/metrics", { headers: { Cookie: absoluteCookie } }, absolute)).response; check("absolute expiry skips KV", absoluteResponse.status === 401 && absolute.calls.get === 0);
  now = BASE; const noKv = env(); const cookie = await login(noKv); delete noKv.env.LEADX_KV; for (const path of ["/api/leads", "/api/metrics"]) check(`${path} missing KV -> 503`, (await call(path, { headers: { Cookie: cookie } }, noKv)).response.status === 503);

  for (const origin of ["http://leadx.invalid", "https://leadx.invalid:444", "https://sub.leadx.invalid", "https://leadx.invalid.attacker.invalid", "https://attacker.invalid"]) { const c = env(); check(`CORS rejects ${origin}`, (await call("/api/leads", { headers: { Origin: origin } }, c)).response.status === 403 && c.calls.assets + c.calls.get === 0); }
  check("CORS accepts exact origin", (await call("/api/leads", { headers: { Origin: "https://leadx.invalid" } })).response.status === 200);
  const pre = (await call("/api/leads", { method: "OPTIONS", headers: { Origin: "https://leadx.invalid" } })).response; check("preflight bounded", pre.status === 204 && pre.headers.get("Allow") === "GET, OPTIONS" && !pre.headers.has("Access-Control-Allow-Origin") && !pre.headers.has("Access-Control-Allow-Credentials"));

  now = BASE; const broken = env([], { throwGet: true }); const brokenCookie = await login(broken); const error = (await call("/api/leads", { headers: { Cookie: brokenCookie } }, broken)).response; const text = await error.text(); check("async errors redacted", error.status === 500 && !text.includes("synthetic storage failure") && !text.includes("stack"));
  check("legacy UI and cron absent", !source.includes("DASHBOARD_HTML") && !source.includes("COOKIES_HTML") && !source.includes("scheduled(") && !source.includes("runPipelineCron"));
  console.log(`SECURITY_RUNTIME_TESTS=${passed}/${passed}`); console.log(`REMOVED_ENDPOINTS_TESTED=${removed.length}`);
} finally { Date.now = realNow; }
