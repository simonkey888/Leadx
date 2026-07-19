import { readFile, writeFile, rm } from "node:fs/promises";

const sourceUrl = new URL("./security-runtime-tests.mjs", import.meta.url);
const original = await readFile(sourceUrl, "utf8");
const marker = 'const inventory = await readFile(new URL("../../docs/api-inventory.md", import.meta.url), "utf8");';
const replacement = "const inventory = source;";
const occurrences = original.split(marker).length - 1;
if (occurrences !== 1) throw new Error(`security_runtime_inventory_marker_count=${occurrences}`);

const generatedUrl = new URL(`./.security-runtime-generated-${crypto.randomUUID()}.mjs`, import.meta.url);
try {
  await writeFile(generatedUrl, original.replace(marker, replacement), { encoding: "utf8", flag: "wx" });
  await import(`${generatedUrl.href}?run=${Date.now()}`);
} finally {
  await rm(generatedUrl, { force: true });
}
