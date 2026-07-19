import { test, expect } from "@playwright/test";

const cases = [
  ["desktop-fotomultas", 1440, 900, "fotomultas", false],
  ["desktop-repuestos", 1440, 900, "repuestos_agricolas", false],
  ["desktop-drawer", 1440, 900, "fotomultas", true],
  ["desktop-whatsapp", 1440, 900, "repuestos_agricolas", true],
  ["mobile-fotomultas", 390, 844, "fotomultas", false],
  ["mobile-repuestos", 390, 844, "repuestos_agricolas", false],
  ["mobile-sheet", 390, 844, "fotomultas", true],
  ["mobile-whatsapp", 390, 844, "repuestos_agricolas", true],
];

for (const [name, width, height, linea, detail] of cases) {
  test(String(name), async ({ page }) => {
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.setViewportSize({ width: Number(width), height: Number(height) });
    await page.goto(`http://127.0.0.1:4173/?linea=${linea}`);
    const label = linea === "fotomultas" ? "Fotomultas" : "Repuestos agrícolas";
    const leadSurface = page.locator(Number(width) < 760 ? ".mobile-cards:visible" : ".lead-table:visible");
    await expect(page.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveAttribute("data-linea", String(linea));
    await expect(page.getByText("Datos ficticios para explorar el CRM", { exact: false })).toBeVisible();
    await expect(leadSurface.getByText("CONTACTADO", { exact: true }).first()).toBeVisible();
    await expect(leadSurface.getByText("NO CONTACTADO", { exact: true }).first()).toBeVisible();
    if (Number(width) >= 760) await expect(leadSurface.locator("th", { hasText: "Provincia" })).toBeVisible();
    if (detail) {
      await page.locator(Number(width) < 760 ? ".lead-card:visible" : ".lead-table tbody tr:visible").first().click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByRole("button", { name: "Marcar como contactado" })).toBeDisabled();
    }
    const demoWhatsApp = page.locator('button[title="WhatsApp deshabilitado en modo demo"]:visible').first();
    await expect(demoWhatsApp).toBeVisible();
    await expect(demoWhatsApp).toBeDisabled();
    await expect(page.locator('a[href^="https://wa.me/"]')).toHaveCount(0);
    const diagnostics = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      pageerror: document.documentElement.dataset.pageerror || "false",
      linea: document.documentElement.dataset.linea,
    }));
    expect(diagnostics.overflow).toBe(0);
    expect(diagnostics.pageerror).toBe("false");
    expect(diagnostics.linea).toBe(linea);
    expect(pageErrors).toEqual([]);
    await page.screenshot({ path: `../artifacts/ui/${name}.png`, fullPage: true });
  });
}
