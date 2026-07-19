import { test, expect } from "@playwright/test";

const SYNTHETIC_PASSWORD = "synthetic-controlled-password";
const PRIVATE_SENTINEL = "Lead privado sintético";

const viewports = [
  ["desktop-session", 1440, 900],
  ["mobile-session", 390, 844],
];

for (const [name, width, height] of viewports) {
  test(String(name), async ({ page }) => {
    let authenticated = false;
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

      if (url.pathname === "/api/auth/session") {
        return json(authenticated
          ? { authenticated: true, mode: "real", idleExpiresAt: Date.now() + 20 * 60_000, absoluteExpiresAt: Date.now() + 8 * 60 * 60_000 }
          : { authenticated: false, mode: "demo" });
      }
      if (url.pathname === "/api/auth/login" && request.method() === "POST") {
        const payload = request.postDataJSON();
        if (payload.password !== SYNTHETIC_PASSWORD) return json({ error: "Contraseña incorrecta" }, 401);
        authenticated = true;
        return json({ ok: true });
      }
      if (url.pathname === "/api/auth/logout" && request.method() === "POST") {
        authenticated = false;
        return json({ ok: true });
      }
      if (url.pathname === "/api/auth/activity" && request.method() === "POST") {
        return authenticated
          ? json({ authenticated: true, mode: "real", absoluteExpiresAt: Date.now() + 8 * 60 * 60_000 })
          : json({ error: "session_expired" }, 401);
      }
      if (url.pathname === "/api/leads") {
        if (!authenticated) return json({ error: "unauthorized" }, 401);
        const vertical = url.searchParams.get("vertical") || "fotomultas";
        return json({
          leads_all: [{
            id: `synthetic-private-${vertical}`,
            vertical,
            name: PRIVATE_SENTINEL,
            persona: PRIVATE_SENTINEL,
            province: "Provincia sintética",
            phone: "+54 9 342 555 9090",
            channel: "whatsapp",
            whatsapp_confirmed: true,
            assigned_to: "Operador sintético",
            status: "Contactado",
            priority: "Alta",
            created_at: "2026-07-19T12:00:00.000Z",
            contacted_at: "2026-07-19T12:30:00.000Z",
            notes: "Fixture privado controlado",
            amount: 123456,
            vertical_data: vertical === "fotomultas"
              ? { plate: "ZZ999ZZ", municipality: "Municipio sintético" }
              : { brand: "Marca sintética", machine_type: "Tractor", part_number: "SYN-001" },
          }],
          meta: { source: "synthetic-private", generated_at: "2026-07-19T12:35:00.000Z" },
        });
      }
      return json({ error: "not_found" }, 404);
    });

    await page.setViewportSize({ width: Number(width), height: Number(height) });
    await page.goto("http://127.0.0.1:4173/?linea=fotomultas");
    await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
    await expect(page.getByText("Datos ficticios para explorar el CRM", { exact: false })).toBeVisible();

    if (Number(width) < 760) await page.getByRole("button", { name: "Desbloquear datos reales" }).click();
    const passwordInput = page.getByLabel("Contraseña").last();
    await passwordInput.fill("wrong-synthetic-password");
    await page.getByRole("button", { name: Number(width) < 760 ? "Ingresar" : "Entrar" }).click();
    await expect(page.getByText("Contraseña incorrecta", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();

    await passwordInput.fill(SYNTHETIC_PASSWORD);
    await page.getByRole("button", { name: Number(width) < 760 ? "Ingresar" : "Entrar" }).click();
    const leadSurface = page.locator(Number(width) < 760 ? ".mobile-cards:visible" : ".lead-table:visible");
    await expect(page.getByText("Datos reales", { exact: true })).toBeVisible();
    await expect(leadSurface.getByText(PRIVATE_SENTINEL, { exact: true })).toBeVisible();
    await expect(leadSurface.getByText("CONTACTADO", { exact: true })).toBeVisible();
    await expect(page.locator('a[title="Abrir WhatsApp"]:visible').first()).toBeVisible();
    await expect(page.getByText("Datos ficticios para explorar el CRM", { exact: false })).toHaveCount(0);

    await page.reload();
    const reloadedLeadSurface = page.locator(Number(width) < 760 ? ".mobile-cards:visible" : ".lead-table:visible");
    await expect(page.getByText("Datos reales", { exact: true })).toBeVisible();
    await expect(reloadedLeadSurface.getByText(PRIVATE_SENTINEL, { exact: true })).toBeVisible();
    await page.screenshot({ path: `../artifacts/ui/${name}.png`, fullPage: true });

    await page.getByRole("button", { name: "Salir" }).click();
    await expect(page.getByText("Modo demo", { exact: true })).toBeVisible();
    await expect(page.getByText("Datos ficticios para explorar el CRM", { exact: false })).toBeVisible();
    await expect(page.getByText(PRIVATE_SENTINEL, { exact: true })).toHaveCount(0);
    await expect(page.locator('a[href^="https://wa.me/"]')).toHaveCount(0);

    const diagnostics = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      pageerror: document.documentElement.dataset.pageerror || "false",
      localStorageKeys: Object.keys(localStorage),
      sessionStorageKeys: Object.keys(sessionStorage),
    }));
    expect(diagnostics.overflow).toBe(0);
    expect(diagnostics.pageerror).toBe("false");
    expect(diagnostics.localStorageKeys).toEqual([]);
    expect(diagnostics.sessionStorageKeys).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
}
