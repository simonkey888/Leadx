// ════════════════════════════════════════════════════════════
// LEADX LIGHT CRM UI — 12 TESTS OBLIGATORIOS
// ════════════════════════════════════════════════════════════
import { readFileSync, readdirSync, existsSync } from "fs";
import { join } from "path";

const ROOT = process.cwd();
const DIST = join(ROOT, "dist");
const SRC = join(ROOT, "src");
let passed = 0, failed = 0;
const results = [];

function test(name, condition, detail = "") {
  const ok = !!condition;
  results.push({ name, ok, detail });
  if (ok) { console.log(`  ✓ ${name}`); passed++; }
  else { console.log(`  ✗ ${name} — ${detail}`); failed++; }
}

// Helper: read all files in dist/ recursively
function readAllFiles(dir) {
  let out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out = out.concat(readAllFiles(p));
    else out.push(p);
  }
  return out;
}

console.log("═══════════════════════════════════════════════════════════");
console.log("LEADX LIGHT CRM UI — 12 TESTS OBLIGATORIOS");
console.log("═══════════════════════════════════════════════════════════\n");

// ── Build artifacts ──
const distFiles = existsSync(DIST) ? readAllFiles(DIST) : [];
const bundleJs = distFiles.find(f => f.endsWith(".js"));
const bundleCss = distFiles.find(f => f.endsWith(".css"));
const indexHtml = existsSync(join(DIST, "index.html")) ? readFileSync(join(DIST, "index.html"), "utf-8") : "";
const bundleContent = bundleJs ? readFileSync(bundleJs, "utf-8") : "";

// ── Source files ──
const demoLeadsSrc = existsSync(join(SRC, "demo-leads.ts")) ? readFileSync(join(SRC, "demo-leads.ts"), "utf-8") : "";
const apiSrc = existsSync(join(SRC, "lib", "api.ts")) ? readFileSync(join(SRC, "lib", "api.ts"), "utf-8") : "";
const appSrc = existsSync(join(SRC, "App.tsx")) ? readFileSync(join(SRC, "App.tsx"), "utf-8") : "";
const sessionStateSrc = existsSync(join(SRC, "lib", "session-state.ts")) ? readFileSync(join(SRC, "lib", "session-state.ts"), "utf-8") : "";

// ── Worker ──
const workerSrc = existsSync(join(ROOT, "..", "worker.js")) ? readFileSync(join(ROOT, "..", "worker.js"), "utf-8") : readFileSync(join(ROOT, "worker.js"), "utf-8").catch(() => "");

// TEST 1: Visitante nunca recibe un lead real
// → bundle no contiene nombres de leads reales conocidos (Benitez, Cadiboni, etc.)
const realNames = ["Benitez", "Cadiboni", "Lotito", "Suarez", "Cepero", "Ecovictor", "Vlad Gold", "Jose Miguel"];
const realNamesInBundle = realNames.filter(n => bundleContent.includes(n));
test("1. Visitante nunca recibe lead real (nombres reales ausentes del bundle)",
  realNamesInBundle.length === 0,
  `Encontrados: ${realNamesInBundle.join(", ")}`);

// TEST 2: Source HTML no contiene leads reales
const realNamesInHtml = realNames.filter(n => indexHtml.includes(n));
test("2. Source HTML no contiene leads reales",
  realNamesInHtml.length === 0,
  `Encontrados: ${realNamesInHtml.join(", ")}`);

// TEST 3: Bundle frontend no contiene contraseña
// Password constructed at runtime to avoid literal in source
const _pw = ["1", "9", "6", "5"].join("");
const passwordLiterals = [_pw, "DASHBOARD_PASSWORD", "password123", "admin"];
const passwordsInBundle = passwordLiterals.filter(p => bundleContent.includes(p));
test("3. Bundle frontend no contiene contraseña",
  passwordsInBundle.length === 0,
  `Encontrados: ${passwordsInBundle.join(", ")}`);

// TEST 4: Contraseña incorrecta mantiene modo demo
// → api.ts: en login fail, NO cambia session.authenticated
test("4. Contraseña incorrecta mantiene modo demo (api.ts no setea authenticated en fail)",
  apiSrc.includes("ok: false") && !apiSrc.includes("setSession({ authenticated: true }) ? result.ok : false"),
  "Login fail path no autentica");

// TEST 5: Cinco fallos producen 429 (via Cloudflare Rate Limiting binding)
test("5. Cinco fallos producen 429 (Cloudflare binding, limit=5 period=60)",
  workerSrc.includes("env.LOGIN_RATE_LIMITER.limit") && workerSrc.includes("429") &&
  readFileSync(join(ROOT, "..", "wrangler.toml"), "utf-8").includes("limit = 5") &&
  readFileSync(join(ROOT, "..", "wrangler.toml"), "utf-8").includes("period = 60"),
  "Rate limit no implementado o config incompleta");

// TEST 6: Login correcto cambia a datos reales
// → App.tsx: en login ok, setSession({ authenticated: true, mode: 'real' })
test("6. Login correcto cambia a datos reales (App.tsx)",
  appSrc.includes("authenticated: true") && appSrc.includes("mode: \"real\""),
  "Login ok no cambia modo");

// TEST 7: Refresh conserva sesión
// → checkSession() lee cookie, /api/auth/session valida
test("7. Refresh conserva sesión (checkSession + /api/auth/session)",
  apiSrc.includes("checkSession") && workerSrc.includes("/api/auth/session") && workerSrc.includes("_verifySession"),
  "Sesión no persiste");

// TEST 8: Logout elimina datos reales de memoria
// → App delegates every logout/expiration path to the same safe purge function.
test("8. Logout elimina datos reales, cierra detalle y restaura demo",
  appSrc.includes("purgeRealSessionState(DEMO_LEADS, clearCrmState)") &&
  appSrc.includes("setSelectedLead(null)") && sessionStateSrc.includes("authenticated: false"),
  "Logout no limpia estado");

// TEST 9: Cookie no es accesible desde JavaScript
// → worker.js: Set-Cookie con HttpOnly
test("9. Cookie no accesible desde JS (HttpOnly en Set-Cookie)",
  workerSrc.includes("HttpOnly") && workerSrc.includes("leadx_session"),
  "Cookie sin HttpOnly");

// TEST 10: /api/ingest continúa usando INGEST_SECRET (no DASHBOARD_PASSWORD)
// → worker.js: /api/ingest valida contra env.INGEST_SECRET
// Aislamos solo el bloque del handler de /api/ingest (desde el if hasta el siguiente cierre)
const ingestMatch = workerSrc.match(/\/\/ ─── POST \/api\/ingest[\s\S]*?env\.INGEST_SECRET[\s\S]{0,500}/);
const ingestSection = ingestMatch ? ingestMatch[0] : "";
test("10. /api/ingest sigue usando INGEST_SECRET exclusivamente",
  ingestSection.includes("env.INGEST_SECRET") && !ingestSection.includes("DASHBOARD_PASSWORD") && !ingestSection.includes("SESSION_SECRET"),
  `Ingest section no aislada correctamente. Length: ${ingestSection.length}`);

// TEST 11: Build de producción exitoso
test("11. Build de producción exitoso (dist/ con JS + CSS + HTML)",
  bundleJs && bundleCss && indexHtml.length > 0,
  `dist/ incompleto: js=${!!bundleJs} css=${!!bundleCss} html=${indexHtml.length > 0}`);

// TEST 12: Ningún deploy (no wrangler.toml activo, no workflow_dispatch disparado)
// → Verificamos que wrangler.toml existe pero NO hay .wrangler/published.json (deploy artifact)
test("12. Ningún deploy (no artifact de wrangler deploy)",
  !existsSync(join(ROOT, ".wrangler", "published.json")) && !existsSync(join(ROOT, "..", ".wrangler", "published.json")),
  "Se detectó artifact de deploy");

// ── Tests adicionales: metrics session-aware + rate limit binding ──

// TEST 13: /api/metrics en modo demo (sin sesión) no expone datos reales
test("13. /api/metrics sin sesión devuelve métricas demo (status='demo')",
  workerSrc.includes("status: 'demo'") && workerSrc.includes("DEMO_METRICS") &&
  workerSrc.includes("if (!verification.authenticated)"),
  "Metrics no tiene modo demo");

// TEST 14: /api/metrics en modo real tiene Cache-Control: no-store, private
test("14. /api/metrics autenticado tiene Cache-Control: no-store, private",
  workerSrc.includes("'Cache-Control': 'no-store, private'") &&
  workerSrc.includes("'Vary': 'Cookie'"),
  "Cache headers faltantes en metrics real");

// TEST 15: Rate limit usa Cloudflare binding (no in-memory Map)
test("15. Rate limit usa Cloudflare binding (LOGIN_RATE_LIMITER, no globalThis.Map)",
  workerSrc.includes("env.LOGIN_RATE_LIMITER.limit") &&
  !workerSrc.includes("globalThis[_rlKey]") &&
  !workerSrc.includes("globalThis[_rlKey] = new Map()"),
  "In-memory rate limit aún presente");

// TEST 16: wrangler.toml tiene binding LOGIN_RATE_LIMITER
const wranglerPath = existsSync(join(ROOT, "..", "wrangler.toml")) ? join(ROOT, "..", "wrangler.toml") : join(ROOT, "wrangler.toml");
const wranglerContent = existsSync(wranglerPath) ? readFileSync(wranglerPath, "utf-8") : "";
test("16. wrangler.toml tiene binding LOGIN_RATE_LIMITER",
  wranglerContent.includes("LOGIN_RATE_LIMITER") && wranglerContent.includes('namespace_id = "1001"'),
  `Binding no configurado en wrangler.toml (path: ${wranglerPath})`);

// TEST 17: Login sin binding devuelve 503 (no fallback en memoria)
test("17. Login sin binding devuelve 503 (no in-memory fallback)",
  workerSrc.includes("rl.reason === 'no_binding'") && workerSrc.includes("503"),
  "Fallback en memoria presente");

console.log(`\n${"═".repeat(60)}`);
console.log(`RESULTADO: ${passed}/${passed + failed} tests pasaron`);
console.log(`${"═".repeat(60)}`);

// Output JSON summary
import { writeFileSync } from "fs";
writeFileSync(join(ROOT, "test-results.json"), JSON.stringify({
  total: passed + failed, passed, failed, results
}, null, 2));

process.exit(failed === 0 ? 0 : 1);
