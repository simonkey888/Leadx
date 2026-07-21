import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

const baseURL = process.env.LEADX_BASE_URL;
if (!baseURL) throw new Error("LEADX_BASE_URL is required");
const smokeNonce = process.env.LEADX_SMOKE_NONCE || `${Date.now()}`;
const chromiumExecutable = process.env.LEADX_CHROMIUM_EXECUTABLE;
const screenshotDir = path.resolve(
  process.env.LEADX_SMOKE_SCREENSHOT_DIR || "../artifacts/production",
);

fs.mkdirSync(screenshotDir, { recursive: true });

test.use({
  browserName: "chromium",
  launchOptions: chromiumExecutable ? { executablePath: chromiumExecutable } : {},
});
test.setTimeout(60_000);

function log(stage, status, detail = "") {
  const suffix = detail ? ` detail=${JSON.stringify(detail)}` : "";
  console.log(`[leadx-smoke] ${new Date().toISOString()} ${status} stage=${JSON.stringify(stage)}${suffix}`);
}

async function phase(stage, action) {
  log(stage, "START");
  try {
    const result = await action();
    log(stage, "PASS");
    return result;
  } catch (error) {
    log(stage, "FAIL", error instanceof Error ? error.message : String(error));
    throw error;
  }
}

function uiURL(linea) {
  const url = new URL(baseURL);
  url.searchParams.set("linea", linea);
  url.searchParams.set("deploy_smoke", smokeNonce);
  return url.toString();
}

test.beforeEach(async ({ page }, testInfo) => {
  page.setDefaultTimeout(15_000);
  page.setDefaultNavigationTimeout(30_000);
  log(testInfo.title, "TEST_START");
});

test.afterEach(async ({}, testInfo) => {
  log(testInfo.title, testInfo.status === "passed" ? "TEST_PASS" : "TEST_END", testInfo.status);
});

for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
  test(`production anonymous ${name}`, async ({ page }) => {
    const pageErrors = [];
    const failedRequests = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("requestfailed", (request) => {
      const requestURL = new URL(request.url());
      const resourceType = request.resourceType();
      const relevantTypes = new Set(["document", "xhr", "fetch", "script", "stylesheet"]);
      if (requestURL.origin === new URL(baseURL).origin && relevantTypes.has(resourceType)) {
        failedRequests.push(`${request.method()} ${request.url()} ${request.failure()?.errorText || "unknown"}`);
      }
    });

    await phase(`${name}:viewport`, () => page.setViewportSize({ width, height }));
    await phase(`${name}:open-fotomultas`, async () => {
      await page.goto(uiURL("fotomultas"), { waitUntil: "domcontentloaded", timeout: 30_000 });
      await expect(page.getByRole("button", { name: "Fotomultas" })).toHaveAttribute("aria-pressed", "true");
    });
    await phase(`${name}:demo-contract`, async () => {
      await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
      await expect(page.getByText("Datos ficticios para explorar el CRM", { exact: false })).toBeVisible();
      const disabledWhatsApp = page.locator('button[title="WhatsApp deshabilitado en modo demo"]:visible').first();
      await expect(disabledWhatsApp).toBeVisible();
      await expect(disabledWhatsApp).toBeDisabled();
      await expect(page.locator('a[href^="https://wa.me/"]')).toHaveCount(0);
    });
    await phase(`${name}:switch-agro`, async () => {
      await page.getByRole("button", { name: "Repuestos agrícolas" }).click();
      await expect(page).toHaveURL(/linea=repuestos_agricolas/);
      await expect(page.getByRole("button", { name: "Repuestos agrícolas" })).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByText("Marca", { exact: true }).first()).toBeAttached();
      const text = await page.locator("body").innerText();
      expect(text).not.toMatch(/Company|Organization|Account/);
    });
    await phase(`${name}:open-detail`, async () => {
      const target = page.locator(width < 760 ? ".lead-card:visible" : ".lead-table tbody tr:visible").first();
      await expect(target).toBeVisible();
      await target.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByRole("button", { name: "Marcar como contactado" })).toBeDisabled();
    });
    await phase(`${name}:diagnostics`, async () => {
      const diagnostics = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        stored: localStorage.length + sessionStorage.length,
      }));
      expect(diagnostics.overflow).toBe(0);
      expect(diagnostics.stored).toBe(0);
      expect(pageErrors).toEqual([]);
      expect(failedRequests).toEqual([]);
    });
    await phase(`${name}:screenshot`, () => page.screenshot({
      path: path.join(screenshotDir, `${name}.png`),
      fullPage: true,
    }));
  });
}

test("production authenticated containment", async ({ page }) => {
  const password = process.env.LEADX_SMOKE_PASSWORD;
  if (!password) throw new Error("LEADX_SMOKE_PASSWORD is required");

  await phase("authenticated:login", async () => {
    const login = await page.request.post(
      `${baseURL}/api/auth/login?deploy_smoke=${encodeURIComponent(smokeNonce)}`,
      { data: { password } },
    );
    expect(login.status()).toBe(200);
  });

  let beforeBody;
  await phase("authenticated:session", async () => {
    const before = await page.request.get(
      `${baseURL}/api/auth/session?deploy_smoke=${encodeURIComponent(smokeNonce)}`,
    );
    beforeBody = await before.json();
    expect(beforeBody.authenticated).toBe(true);
  });

  await phase("authenticated:containment", async () => {
    const privateLeads = await page.request.get(
      `${baseURL}/api/leads?vertical=fotomultas&deploy_smoke=${encodeURIComponent(smokeNonce)}`,
    );
    expect(privateLeads.status()).toBe(200);
    const privateBody = await privateLeads.json();
    expect(privateBody.leads_all.every((lead) => lead.vertical === "fotomultas")).toBe(true);
  });

  await phase("authenticated:idle-session", async () => {
    const after = await page.request.get(
      `${baseURL}/api/auth/session?deploy_smoke=${encodeURIComponent(smokeNonce)}`,
    );
    const afterBody = await after.json();
    expect(afterBody.idleExpiresAt).toBe(beforeBody.idleExpiresAt);
  });

  await phase("authenticated:open-ui", async () => {
    await page.goto(uiURL("fotomultas"), { waitUntil: "domcontentloaded", timeout: 30_000 });
    await expect(page.getByText("Datos reales", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  });

  await phase("authenticated:logout", async () => {
    await page.getByRole("button", { name: "Salir" }).click();
    await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
    const ended = await page.request.get(
      `${baseURL}/api/auth/session?deploy_smoke=${encodeURIComponent(smokeNonce)}`,
    );
    expect((await ended.json()).authenticated).toBe(false);
  });
});
