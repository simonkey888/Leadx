import { test, expect } from "@playwright/test";

const baseURL = process.env.LEADX_BASE_URL;
if (!baseURL) throw new Error("LEADX_BASE_URL is required");
const smokeNonce = process.env.LEADX_SMOKE_NONCE || `${Date.now()}`;

function uiURL(linea) {
  const url = new URL(baseURL);
  url.searchParams.set("linea", linea);
  url.searchParams.set("deploy_smoke", smokeNonce);
  return url.toString();
}

for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
  test(`production anonymous ${name}`, async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.setViewportSize({ width, height });
    await page.goto(uiURL("fotomultas"), { waitUntil: "networkidle" });
    await expect(page.getByRole("button", { name: "Fotomultas" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
    await expect(page.getByText("Datos ficticios para explorar el CRM", { exact: false })).toBeVisible();
    const disabledWhatsApp = page.locator('button[title="WhatsApp deshabilitado en modo demo"]:visible').first();
    await expect(disabledWhatsApp).toBeVisible();
    await expect(disabledWhatsApp).toBeDisabled();
    await expect(page.locator('a[href^="https://wa.me/"]')).toHaveCount(0);
    await page.getByRole("button", { name: "Repuestos agrícolas" }).click();
    await expect(page).toHaveURL(/linea=repuestos_agricolas/);
    await expect(page.getByRole("button", { name: "Repuestos agrícolas" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Marca", { exact: true }).first()).toBeAttached();
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/Company|Organization|Account/);
    const target = page.locator(width < 760 ? ".lead-card:visible" : ".lead-table tbody tr:visible").first();
    await expect(target).toBeVisible();
    await target.click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("button", { name: "Marcar como contactado" })).toBeDisabled();
    const diagnostics = await page.evaluate(() => ({ overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, stored: localStorage.length + sessionStorage.length }));
    expect(diagnostics.overflow).toBe(0);
    expect(diagnostics.stored).toBe(0);
    expect(pageErrors).toEqual([]);
    await page.screenshot({ path: `../artifacts/production/${name}.png`, fullPage: true });
  });
}

test("production authenticated containment", async ({ page }) => {
  const password = process.env.LEADX_SMOKE_PASSWORD;
  if (!password) throw new Error("LEADX_SMOKE_PASSWORD is required");
  const login = await page.request.post(`${baseURL}/api/auth/login?deploy_smoke=${encodeURIComponent(smokeNonce)}`, { data: { password } });
  expect(login.status()).toBe(200);
  const before = await page.request.get(`${baseURL}/api/auth/session?deploy_smoke=${encodeURIComponent(smokeNonce)}`);
  const beforeBody = await before.json();
  expect(beforeBody.authenticated).toBe(true);
  const privateLeads = await page.request.get(`${baseURL}/api/leads?vertical=fotomultas&deploy_smoke=${encodeURIComponent(smokeNonce)}`);
  expect(privateLeads.status()).toBe(200);
  const privateBody = await privateLeads.json();
  expect(privateBody.leads_all.every((lead) => lead.vertical === "fotomultas")).toBe(true);
  const after = await page.request.get(`${baseURL}/api/auth/session?deploy_smoke=${encodeURIComponent(smokeNonce)}`);
  const afterBody = await after.json();
  expect(afterBody.idleExpiresAt).toBe(beforeBody.idleExpiresAt);
  await page.goto(uiURL("fotomultas"), { waitUntil: "networkidle" });
  await expect(page.getByText("Datos reales", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  await page.getByRole("button", { name: "Salir" }).click();
  await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  const ended = await page.request.get(`${baseURL}/api/auth/session?deploy_smoke=${encodeURIComponent(smokeNonce)}`);
  expect((await ended.json()).authenticated).toBe(false);
});
