import { readFileSync, readdirSync, existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();
const DIST = join(ROOT, "dist");
const SRC = join(ROOT, "src");
const REPO = join(ROOT, "..");
let passed = 0;
let failed = 0;
const results = [];

function test(name, condition, detail = "") {
  const ok = Boolean(condition);
  results.push({ name, ok, detail });
  if (ok) { passed += 1; console.log(`  ✓ ${name}`); }
  else { failed += 1; console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`); }
}

function readAllFiles(directory) {
  if (!existsSync(directory)) return [];
  const output = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) output.push(...readAllFiles(path));
    else output.push(path);
  }
  return output;
}

const distFiles = readAllFiles(DIST);
const bundleJs = distFiles.find((file) => file.endsWith(".js"));
const bundleCss = distFiles.find((file) => file.endsWith(".css"));
const indexHtml = existsSync(join(DIST, "index.html")) ? readFileSync(join(DIST, "index.html"), "utf8") : "";
const bundleContent = bundleJs ? readFileSync(bundleJs, "utf8") : "";
const readSource = (path) => readFileSync(join(SRC, path), "utf8");
const apiSource = readSource(join("lib", "api.ts"));
const appSource = readSource("App.tsx");
const sessionSource = readSource(join("lib", "session-state.ts"));
const styleSource = readSource("styles.css");
const kpiSource = readSource(join("components", "Kpis.tsx"));
const listSource = readSource(join("components", "LeadTable.tsx"));
const detailSource = readSource(join("components", "LeadDetail.tsx"));
const actionsSource = readSource(join("components", "Actions.tsx"));
const demoSource = readSource("demo-leads.ts");
const allClientSource = readAllFiles(SRC).map((file) => readFileSync(file, "utf8")).join("\n");
const workerSource = readFileSync(join(REPO, "worker.js"), "utf8");
const wranglerSource = readFileSync(join(REPO, "wrangler.toml"), "utf8");

console.log("\nLEADX COMPATIBILITY SUITE — 24 TESTS\n");

const realNameSentinels = ["Benitez", "Cadiboni", "Lotito", "Cepero", "Ecovictor", "Vlad Gold"];
test("1. Production bundle contains no known real-name sentinels", !realNameSentinels.some((name) => bundleContent.includes(name)));
test("2. Production HTML contains no known real-name sentinels", !realNameSentinels.some((name) => indexHtml.includes(name)));
test("3. Client bundle contains no server secret identifiers or digit-join credential construction",
  !["DASHBOARD_PASSWORD", "SESSION_SECRET", "INGEST_SECRET"].some((name) => bundleContent.includes(name)) &&
  !/\[\s*["']\d["'](?:\s*,\s*["']\d["']){2,}\s*\]\.join/.test(allClientSource));
test("4. Login failure path returns a non-authenticated result", apiSource.includes("return { ok: false") && !apiSource.includes("setSession"));
test("5. Login rate limiting is fail-closed and emits Retry-After", workerSource.includes("env.LOGIN_RATE_LIMITER.limit") && workerSource.includes('"Retry-After": "60"') && workerSource.includes("429"));
test("6. Successful login switches the application to real mode", appSource.includes("authenticated: true") && appSource.includes('mode: "real"'));
test("7. Refresh validates the server-side session", apiSource.includes("checkSession") && workerSource.includes('url.pathname === "/api/auth/session"'));
test("8. Logout and expiry share the real-state purge path", appSource.includes("purgeRealSessionState(DEMO_LEADS, clearCrmState)") && appSource.includes("setSelectedLead(null)") && sessionSource.includes("authenticated: false"));
test("9. Session cookie is HttpOnly, Secure and SameSite=Strict", workerSource.includes("HttpOnly; Secure; SameSite=Strict; Path=/"));
const ingestStart = workerSource.indexOf("async function handleIngest");
const ingestEnd = workerSource.indexOf("async function serveAsset", ingestStart);
const ingestSection = workerSource.slice(ingestStart, ingestEnd);
test("10. Ingest uses only INGEST_SECRET for authorization", ingestStart >= 0 && ingestSection.includes("env.INGEST_SECRET") && !ingestSection.includes("DASHBOARD_PASSWORD") && !ingestSection.includes("SESSION_SECRET"));
test("11. Production build emitted JS, CSS and HTML", Boolean(bundleJs && bundleCss && indexHtml));
test("12. Test workspace contains no Wrangler publish artifact", !existsSync(join(ROOT, ".wrangler", "published.json")) && !existsSync(join(REPO, ".wrangler", "published.json")));
test("13. Anonymous metrics are fixed demo metrics", workerSource.includes('status: "demo"') && workerSource.includes("total_leads: 12") && workerSource.includes("contactable_leads: 0"));
test("14. Authenticated responses disable private caching", workerSource.includes('"Cache-Control": "no-store, private"') && workerSource.includes('"Vary": "Cookie"'));
test("15. Rate limiting has no in-memory fallback", !workerSource.includes("globalThis[_rlKey]") && !workerSource.includes("new Map() // rate"));
test("16. Wrangler declares the required login rate limiter", wranglerSource.includes('name = "LOGIN_RATE_LIMITER"') && wranglerSource.includes("limit = 5") && wranglerSource.includes("period = 60"));
test("17. Missing login rate limiter fails with 503", workerSource.includes("if (!env.LOGIN_RATE_LIMITER) return json") && workerSource.includes("503"));
test("18. Dashboard renders exactly four KPIs", (kpiSource.match(/className="kpi"/g) || []).length === 4);
test("19. Mobile lead list uses cards, not a transformed table", listSource.includes("<article") && !listSource.includes("<table"));
test("20. Demo and real modes plus mobile login are visible", appSource.includes("Desbloquear datos reales") && appSource.includes("Datos ficticios para explorar el CRM") && appSource.includes("Modo demo") && appSource.includes("Datos reales"));
test("21. Lead detail is a dialog with shared contact actions", detailSource.includes('role="dialog"') && detailSource.includes("<Actions") && styleSource.includes(".lead-detail"));
test("22. Mobile target sizing and breakpoint remain present", styleSource.includes("min-height:44px") && styleSource.includes("@media(max-width:760px)"));
test("23. Client source does not persist CRM data in browser storage", !allClientSource.includes("localStorage") && !allClientSource.includes("sessionStorage") && !allClientSource.includes("indexedDB"));
test("24. React Static Assets are the only UI and demo actions are non-routable",
  !workerSource.includes("DASHBOARD_HTML") && !workerSource.includes("COOKIES_HTML") && !workerSource.includes("async scheduled") &&
  workerSource.includes("env.ASSETS.fetch") && actionsSource.includes("if (lead._isDemo)") &&
  actionsSource.includes("disabled") && !/telefono_publico|whatsapp_publico|fb_username|email_publico/.test(demoSource));

console.log(`\nRESULT: ${passed}/${passed + failed} compatibility tests passed`);
writeFileSync(join(ROOT, "test-results.json"), JSON.stringify({ total: passed + failed, passed, failed, results }, null, 2));
process.exitCode = failed === 0 ? 0 : 1;
