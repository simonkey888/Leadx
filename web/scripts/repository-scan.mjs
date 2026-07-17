import { createHash, randomBytes } from "node:crypto";
import { mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, extname, join, relative, sep } from "node:path";
import { execFileSync } from "node:child_process";

const repoRoot = join(process.cwd(), "..");
const artifactDir = join(repoRoot, "artifacts", "security");
mkdirSync(artifactDir, { recursive: true });

const textExtensions = new Set([
  "", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".toml", ".yml", ".yaml",
  ".json", ".md", ".html", ".css", ".txt", ".csv", ".xml", ".sh", ".bat", ".ps1",
]);
const allowedEmailDomains = new Set([
  "example.com", "example.invalid", "invalid", "leadx.test", "leadx.invalid", "localhost", "users.noreply.github.com",
]);
const salt = randomBytes(32);

function git(args, options = {}) {
  return execFileSync("git", args, { cwd: repoRoot, encoding: options.encoding ?? "utf8", maxBuffer: 128 * 1024 * 1024 });
}

function fingerprint(value) {
  return createHash("sha256").update(salt).update("\0").update(value).digest("hex").slice(0, 20);
}

function lineNumber(content, index) {
  return content.slice(0, index).split("\n").length;
}

function isTextFile(path) {
  if (!textExtensions.has(extname(path).toLowerCase())) return false;
  const absolute = join(repoRoot, path);
  if (statSync(absolute).size > 5 * 1024 * 1024) return false;
  const sample = readFileSync(absolute).subarray(0, 4096);
  return !sample.includes(0);
}

function syntheticPhone(value) {
  const digits = value.replace(/\D/g, "");
  return /^5490+$/.test(digits) || /^540+$/.test(digits) || /^54911(?:0{8})$/.test(digits);
}

function sourceLike(path) {
  return [".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".sh", ".ps1"].includes(extname(path).toLowerCase());
}

const secretRules = [
  ["PRIVATE_KEY", /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/g],
  ["GITHUB_TOKEN", /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b/g],
  ["GITHUB_FINE_GRAINED_TOKEN", /\bgithub_pat_[A-Za-z0-9_]{40,}\b/g],
  ["PROVIDER_API_TOKEN", /\b(?:sk|rk|pk)-(?:live|proj)?-?[A-Za-z0-9_-]{20,}\b/g],
  ["CLOUDFLARE_TOKEN_ASSIGNMENT", /\b(?:CLOUDFLARE_API_TOKEN|API_TOKEN)\b\s*[:=]\s*["'][A-Za-z0-9_-]{20,}["']/gi],
  ["LITERAL_SECRET_ASSIGNMENT", /\b(?:SECRET|TOKEN|PASSWORD|API_KEY|PRIVATE_KEY|COOKIE)\b\s*[:=]\s*["'][^"'\n$<{]{8,}["']/gi],
  ["DIGIT_JOIN_CREDENTIAL", /\[\s*["']\d["'](?:\s*,\s*["']\d["']){2,}\s*\]\.join\s*\(/g],
];

const currentSecretFindings = [];
const currentPiiFindings = [];
const currentFalsePositives = [];
const tracked = git(["ls-files", "-z"], { encoding: "buffer" }).toString("utf8").split("\0").filter(Boolean);

for (const path of tracked) {
  if (!isTextFile(path)) continue;
  const content = readFileSync(join(repoRoot, path), "utf8");

  for (const [rule, pattern] of secretRules) {
    pattern.lastIndex = 0;
    for (const match of content.matchAll(pattern)) {
      const value = match[0];
      const index = match.index || 0;
      const context = content.slice(Math.max(0, index - 80), index + value.length + 80);
      if (sourceLike(path) && /(?:RegExp|matchAll|secretRules|pattern|fixture|synthetic)/i.test(context)) {
        currentFalsePositives.push({ rule, path, line: lineNumber(content, index), classification: "SOURCE_PATTERN" });
        continue;
      }
      currentSecretFindings.push({ rule, path, line: lineNumber(content, index), fingerprint: fingerprint(value) });
    }
  }

  const filename = path.split(sep).at(-1) || "";
  if (/^\.env(?:\.|$)/.test(filename) && !filename.endsWith(".env.example")) {
    currentSecretFindings.push({ rule: "TRACKED_ENV_FILE", path, line: 1, fingerprint: fingerprint(path) });
  }

  const emailPattern = /\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b/gi;
  for (const match of content.matchAll(emailPattern)) {
    const domain = match[1].toLowerCase();
    if (allowedEmailDomains.has(domain)) continue;
    const index = match.index || 0;
    const context = content.slice(Math.max(0, index - 60), index + match[0].length + 60);
    if (sourceLike(path) && !/(?:email|correo|contact|fixture|lead)/i.test(context)) {
      currentFalsePositives.push({ rule: "EMAIL_ADDRESS", path, line: lineNumber(content, index), classification: "SOURCE_PATTERN" });
      continue;
    }
    currentPiiFindings.push({ rule: "EMAIL_ADDRESS", path, line: lineNumber(content, index), fingerprint: fingerprint(match[0].toLowerCase()) });
  }

  const phonePattern = /(?:\+?54\s*9?\s*)?(?:11|2\d{2}|3\d{2})[\s().-]*\d{3,4}[\s.-]*\d{4}\b/g;
  for (const match of content.matchAll(phonePattern)) {
    if (syntheticPhone(match[0])) continue;
    const index = match.index || 0;
    const context = content.slice(Math.max(0, index - 60), index + match[0].length + 60);
    if (sourceLike(path) && !/(?:phone|tel[eé]fono|whatsapp|contact|fixture|lead|wa\.me)/i.test(context)) continue;
    currentPiiFindings.push({ rule: "ARGENTINE_PHONE", path, line: lineNumber(content, index), fingerprint: fingerprint(match[0].replace(/\D/g, "")) });
  }

  const personalUrlPattern = /https?:\/\/(?:wa\.me|m\.me|(?:www\.)?instagram\.com|(?:www\.)?(?:facebook|x|twitter)\.com)\/[A-Za-z0-9._-]+/gi;
  for (const match of content.matchAll(personalUrlPattern)) {
    const index = match.index || 0;
    if (sourceLike(path) && /(?:RegExp|pattern|fixture|synthetic)/i.test(content.slice(Math.max(0, index - 60), index + match[0].length + 60))) continue;
    currentPiiFindings.push({ rule: "PERSONAL_PROFILE_URL", path, line: lineNumber(content, index), fingerprint: fingerprint(match[0].toLowerCase()) });
  }
}

let historySecretCount = 0;
let historyPiiCount = 0;
const historyFingerprints = new Set();
try {
  const history = git(["log", "--all", "--format=commit:%H", "-p", "--no-ext-diff", "--no-textconv"]);
  for (const [rule, pattern] of secretRules) {
    pattern.lastIndex = 0;
    for (const match of history.matchAll(pattern)) {
      historySecretCount += 1;
      historyFingerprints.add(`${rule}:${fingerprint(match[0])}`);
    }
  }
  for (const match of history.matchAll(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi)) {
    const domain = match[0].split("@").at(-1).toLowerCase();
    if (!allowedEmailDomains.has(domain)) {
      historyPiiCount += 1;
      historyFingerprints.add(`EMAIL_ADDRESS:${fingerprint(match[0].toLowerCase())}`);
    }
  }
  for (const match of history.matchAll(/(?:\+?54\s*9?\s*)?(?:11|2\d{2}|3\d{2})[\s().-]*\d{3,4}[\s.-]*\d{4}\b/g)) {
    if (!syntheticPhone(match[0])) {
      historyPiiCount += 1;
      historyFingerprints.add(`ARGENTINE_PHONE:${fingerprint(match[0].replace(/\D/g, ""))}`);
    }
  }
} catch {
  historySecretCount = -1;
  historyPiiCount = -1;
}

const currentReport = {
  schema: "leadx-current-tree-scan-v1",
  files_scanned: tracked.length,
  secret_status: currentSecretFindings.length === 0 ? "PASS" : "FAIL",
  pii_status: currentPiiFindings.length === 0 ? "PASS" : "FAIL",
  secret_findings: currentSecretFindings,
  pii_findings: currentPiiFindings,
  false_positive_count: currentFalsePositives.length,
  false_positives: currentFalsePositives,
};
const historyReport = {
  schema: "leadx-history-audit-v1",
  secret_status: historySecretCount === 0 ? "PASS" : historySecretCount > 0 ? "FAIL" : "INDETERMINATE",
  pii_status: historyPiiCount === 0 ? "PASS" : historyPiiCount > 0 ? "FAIL" : "INDETERMINATE",
  secret_finding_count: historySecretCount,
  pii_finding_count: historyPiiCount,
  redacted_fingerprints: [...historyFingerprints].sort(),
  remediation_required: historySecretCount > 0 || historyPiiCount > 0,
  values_redacted: true,
};
writeFileSync(join(artifactDir, "current-tree-scan.json"), `${JSON.stringify(currentReport, null, 2)}\n`);
writeFileSync(join(artifactDir, "history-audit-redacted.json"), `${JSON.stringify(historyReport, null, 2)}\n`);
writeFileSync(join(artifactDir, "scan-summary.txt"), [
  `CURRENT_TREE_SECRET_SCAN=${currentReport.secret_status}`,
  `CURRENT_TREE_PII_SCAN=${currentReport.pii_status}`,
  `CURRENT_TREE_FALSE_POSITIVES=${currentFalsePositives.length}`,
  `GIT_HISTORY_SECRET_SCAN=${historyReport.secret_status}`,
  `GIT_HISTORY_PII_SCAN=${historyReport.pii_status}`,
  `HISTORY_REMEDIATION_REQUIRED=${historyReport.remediation_required ? "yes" : "no"}`,
  "HISTORY_VALUES_REDACTED=yes",
].join("\n") + "\n");

console.log(`CURRENT_TREE_SECRET_SCAN=${currentReport.secret_status}`);
console.log(`CURRENT_TREE_PII_SCAN=${currentReport.pii_status}`);
console.log(`CURRENT_TREE_FALSE_POSITIVES=${currentFalsePositives.length}`);
console.log(`GIT_HISTORY_SECRET_SCAN=${historyReport.secret_status}`);
console.log(`GIT_HISTORY_PII_SCAN=${historyReport.pii_status}`);
console.log(`HISTORY_REMEDIATION_REQUIRED=${historyReport.remediation_required ? "yes" : "no"}`);
console.log("HISTORY_VALUES_REDACTED=yes");

if (currentSecretFindings.length || currentPiiFindings.length) process.exitCode = 1;
