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
    await expect(page.getByRole("button", { name: label })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("html")).toHaveAttribute("data-linea", String(linea));
    if (Number(width) >= 760) await expect(page.getByText("Provincia", { exact: true }).first()).toBeVisible();
    if (detail) {
      await page.locator(Number(width) < 760 ? ".lead-card:visible" : ".lead-table tbody tr:visible").first().click();
      await expect(page.getByRole("dialog")).toBeVisible();
    }
    await expect(page.locator('a[title="Abrir WhatsApp"]:visible').first()).toBeVisible();
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
