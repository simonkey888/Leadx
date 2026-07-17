import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative, sep } from "node:path";

const repoRoot = join(process.cwd(), "..");
const excludedDirectories = new Set([".git", "node_modules", "dist", ".wrangler"]);
const textExtensions = new Set([
  "", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".toml", ".yml", ".yaml",
  ".json", ".md", ".html", ".css", ".txt", ".csv", ".xml", ".sh", ".bat", ".ps1",
]);
const allowedEmailDomains = new Set([
  "example.com", "example.invalid", "invalid", "leadx.test", "localhost", "users.noreply.github.com",
]);
const prohibitedDataRoots = ["data", `public${sep}data`, "upload", "download", "tool-results"];

function walk(directory) {
  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && excludedDirectories.has(entry.name)) continue;
    const absolute = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...walk(absolute));
    else files.push(absolute);
  }
  return files;
}

function isTextFile(path) {
  if (!textExtensions.has(extname(path).toLowerCase())) return false;
  if (statSync(path).size > 5 * 1024 * 1024) return false;
  const sample = readFileSync(path).subarray(0, 4096);
  return !sample.includes(0);
}

function isSyntheticPhone(value) {
  const digits = value.replace(/\D/g, "");
  return /^5490+$/.test(digits) || /^540+$/.test(digits);
}

function lineNumber(content, index) {
  return content.slice(0, index).split("\n").length;
}

const secretFindings = [];
const piiFindings = [];
const artifactFindings = [];
const files = walk(repoRoot);

for (const absolute of files) {
  const path = relative(repoRoot, absolute);
  if (prohibitedDataRoots.some((root) => path === root || path.startsWith(`${root}${sep}`))) {
    const filename = path.split(sep).at(-1) || "";
    const explicitlySafe = filename === ".gitkeep" || filename.endsWith(".schema.json") || filename.startsWith("sample_");
    if (!explicitlySafe) artifactFindings.push({ path, reason: "tracked runtime/data artifact" });
  }
  if (!isTextFile(absolute)) continue;
  const content = readFileSync(absolute, "utf8");

  const secretPatterns = [
    ["private key", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g],
    ["GitHub token", /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b/g],
    ["GitHub fine-grained token", /\bgithub_pat_[A-Za-z0-9_]{40,}\b/g],
    ["provider API token", /\b(?:sk|rk|pk)-(?:live|proj)?-?[A-Za-z0-9_-]{20,}\b/g],
    ["literal secret assignment", /\b(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|COOKIE)\b\s*[:=]\s*["'][^"'\n$<{]{8,}["']/gi],
    ["digit-join credential reconstruction", /\[\s*["']\d["'](?:\s*,\s*["']\d["']){2,}\s*\]\.join\s*\(/g],
  ];
  for (const [kind, pattern] of secretPatterns) {
    for (const match of content.matchAll(pattern)) {
      secretFindings.push({ path, line: lineNumber(content, match.index || 0), kind });
    }
  }
  if (/^\.env(?:\.|$)/.test(path.split(sep).at(-1) || "") && !path.endsWith(".env.example")) {
    secretFindings.push({ path, line: 1, kind: "tracked environment file" });
  }

  const emailPattern = /\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b/gi;
  for (const match of content.matchAll(emailPattern)) {
    const domain = match[1].toLowerCase();
    if (!allowedEmailDomains.has(domain)) piiFindings.push({ path, line: lineNumber(content, match.index || 0), kind: "email address" });
  }

  const phonePattern = /(?:\+?54\s*9?\s*)?(?:11|2\d{2}|3\d{2})[\s().-]*\d{3,4}[\s.-]*\d{4}\b/g;
  for (const match of content.matchAll(phonePattern)) {
    if (!isSyntheticPhone(match[0])) piiFindings.push({ path, line: lineNumber(content, match.index || 0), kind: "Argentine phone number" });
  }

  const isDataArtifact = prohibitedDataRoots.some((root) => path === root || path.startsWith(`${root}${sep}`)) || [".json", ".csv", ".txt", ".log"].includes(extname(path).toLowerCase());
  if (isDataArtifact) {
    const personalUrlPattern = /https?:\/\/(?:wa\.me|m\.me|(?:www\.)?instagram\.com|(?:www\.)?(?:facebook|x|twitter)\.com)\/[A-Za-z0-9._-]+/gi;
    for (const match of content.matchAll(personalUrlPattern)) {
      piiFindings.push({ path, line: lineNumber(content, match.index || 0), kind: "personal contact/profile URL" });
    }
  }
}

console.log(`SECRET_SCAN=${secretFindings.length === 0 ? "PASS" : "FAIL"}`);
console.log(`PII_SCAN=${piiFindings.length === 0 && artifactFindings.length === 0 ? "PASS" : "FAIL"}`);
console.log(`FILES_SCANNED=${files.length}`);

for (const finding of secretFindings) console.error(`SECRET ${finding.path}:${finding.line} ${finding.kind}`);
for (const finding of piiFindings) console.error(`PII ${finding.path}:${finding.line} ${finding.kind}`);
for (const finding of artifactFindings) console.error(`ARTIFACT ${finding.path} ${finding.reason}`);

if (secretFindings.length || piiFindings.length || artifactFindings.length) process.exitCode = 1;
