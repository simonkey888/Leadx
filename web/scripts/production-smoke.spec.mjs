import { test, expect } from "@playwright/test";

const baseURL = process.env.LEADX_BASE_URL;
if (!baseURL) throw new Error("LEADX_BASE_URL is required");

for (const [name, width, height] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
  test(`production anonymous ${name}`, async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.setViewportSize({ width, height });
    await page.goto(`${baseURL}/?linea=fotomultas`);
    await expect(page.getByRole("button", { name: "Fotomultas" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator('[title="Abrir WhatsApp"]:visible').first()).toBeVisible();
    await page.getByRole("button", { name: "Repuestos agrícolas" }).click();
    await expect(page).toHaveURL(/linea=repuestos_agricolas/);
    await expect(page.getByRole("button", { name: "Repuestos agrícolas" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Marca", { exact: true }).first()).toBeAttached();
    const text = await page.locator("body").innerText();
    expect(text).not.toMatch(/Company|Organization|Account/);
    const target = page.locator(width < 760 ? ".lead-card" : ".lead-table tbody tr").first();
    await target.click();
    await expect(page.getByRole("dialog")).toBeVisible();
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
  const login = await page.request.post(`${baseURL}/api/auth/login`, { data: { password } });
  expect(login.status()).toBe(200);
  const before = await page.request.get(`${baseURL}/api/auth/session`);
  const beforeBody = await before.json();
  expect(beforeBody.authenticated).toBe(true);
  const privateLeads = await page.request.get(`${baseURL}/api/leads?vertical=fotomultas`);
  expect(privateLeads.status()).toBe(200);
  const privateBody = await privateLeads.json();
  expect(privateBody.leads_all.every((lead) => lead.vertical === "fotomultas")).toBe(true);
  const after = await page.request.get(`${baseURL}/api/auth/session`);
  const afterBody = await after.json();
  expect(afterBody.idleExpiresAt).toBe(beforeBody.idleExpiresAt);
  await page.goto(`${baseURL}/?linea=fotomultas`);
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  await page.getByRole("button", { name: "Salir" }).click();
  await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  const ended = await page.request.get(`${baseURL}/api/auth/session`);
  expect((await ended.json()).authenticated).toBe(false);
});
