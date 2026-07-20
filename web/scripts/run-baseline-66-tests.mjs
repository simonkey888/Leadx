import { readFile, writeFile, rm } from "node:fs/promises";

const sourceUrl = new URL("./baseline-66-tests.mjs", import.meta.url);
const original = await readFile(sourceUrl, "utf8");
const marker = `const healthResponse = (await call("/api/health", {}, anonymous)).response;
const health = await healthResponse.json();
test("health returns 200", healthResponse.status === 200 && health.status === "ok");
test("health schema is sanitized", JSON.stringify(Object.keys(health).sort()) === JSON.stringify(["checked_at", "service", "status", "version"]));
test("health skips KV", anonymous.calls.get === 0);`;
const replacement = `const healthResponse = (await call("/api/health", {}, anonymous)).response;
const health = await healthResponse.json();
test("health performs a real KV readiness read", healthResponse.status === 200 && health.status === "ok" && health.checks?.kv === "ok" && anonymous.calls.get === 1);
test("health schema is sanitized", JSON.stringify(Object.keys(health).sort()) === JSON.stringify(["checked_at", "checks", "service", "status", "version"]));
const missingHealthContext = environment({ LEADX_KV: { get: async () => null, put: async () => undefined } });
const missingHealthResponse = (await call("/api/health", {}, missingHealthContext)).response;
const brokenHealthContext = environment({ LEADX_KV: { get: async () => { throw new Error("synthetic health failure"); }, put: async () => undefined } });
const brokenHealthResponse = (await call("/api/health", {}, brokenHealthContext)).response;
test("health fails closed when KV data is missing or unreadable", missingHealthResponse.status === 503 && brokenHealthResponse.status === 503 && (await missingHealthResponse.json()).status === "degraded" && (await brokenHealthResponse.json()).checks?.kv === "fail");`;

const occurrences = original.split(marker).length - 1;
if (occurrences !== 1) throw new Error(`baseline_health_marker_count=${occurrences}`);

const generatedUrl = new URL(`./.baseline-66-generated-${crypto.randomUUID()}.mjs`, import.meta.url);
try {
  await writeFile(generatedUrl, original.replace(marker, replacement), { encoding: "utf8", flag: "wx" });
  await import(`${generatedUrl.href}?run=${Date.now()}`);
} finally {
  await rm(generatedUrl, { force: true });
}
