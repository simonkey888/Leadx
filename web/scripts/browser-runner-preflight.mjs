import fs from "node:fs";
import { chromium } from "@playwright/test";

const executablePath = process.env.LEADX_CHROMIUM_EXECUTABLE;
if (!executablePath) {
  throw new Error("LEADX_CHROMIUM_EXECUTABLE is required");
}
if (!fs.existsSync(executablePath)) {
  throw new Error(`Configured Chromium executable does not exist: ${executablePath}`);
}

console.log(`[browser-preflight] START executable=${executablePath}`);
const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: ["--disable-gpu", "--no-first-run", "--no-default-browser-check"],
  timeout: 30_000,
});

try {
  console.log("[browser-preflight] BROWSER_LAUNCHED");
  const page = await browser.newPage();
  page.setDefaultTimeout(10_000);
  page.setDefaultNavigationTimeout(10_000);
  await page.goto("data:text/html,<title>LeadX runner preflight</title><main>ok</main>", {
    waitUntil: "domcontentloaded",
    timeout: 10_000,
  });
  const text = await page.locator("main").innerText();
  if (text !== "ok") throw new Error("Preflight page did not render expected content");
  console.log("[browser-preflight] PAGE_RENDER=PASS");
} finally {
  await browser.close();
}

console.log("[browser-preflight] PASS");
