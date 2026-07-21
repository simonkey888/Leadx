import { spawn, spawnSync } from "node:child_process";
import process from "node:process";

const RUNNER_BLOCKED_EXIT = 86;
const mode = process.argv[2] || "--production";
const isPreflight = mode === "--preflight";
if (!isPreflight && mode !== "--production") {
  console.error(`[browser-runner] ERROR unknown mode: ${mode}`);
  process.exit(2);
}

function positiveInteger(name, fallback) {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number.parseInt(raw, 10);
  if (!Number.isFinite(value) || value <= 0) {
    console.error(`[browser-runner] ERROR ${name} must be a positive integer`);
    process.exit(2);
  }
  return value;
}

const testTimeoutMs = positiveInteger("LEADX_BROWSER_TEST_TIMEOUT_MS", 60_000);
const globalTimeoutMs = positiveInteger("LEADX_BROWSER_GLOBAL_TIMEOUT_MS", 240_000);
const hardTimeoutMs = positiveInteger(
  "LEADX_BROWSER_HARD_TIMEOUT_MS",
  isPreflight ? 45_000 : globalTimeoutMs + 30_000,
);
const heartbeatMs = positiveInteger("LEADX_BROWSER_HEARTBEAT_MS", 15_000);

let command;
let args;
const testOverride = process.env.LEADX_BROWSER_RUNNER_TEST_COMMAND_JSON;
if (testOverride) {
  let parsed;
  try {
    parsed = JSON.parse(testOverride);
  } catch {
    console.error("[browser-runner] ERROR LEADX_BROWSER_RUNNER_TEST_COMMAND_JSON is not valid JSON");
    process.exit(2);
  }
  if (!Array.isArray(parsed) || parsed.length < 1 || parsed.some((item) => typeof item !== "string")) {
    console.error("[browser-runner] ERROR test command must be a JSON string array");
    process.exit(2);
  }
  [command, ...args] = parsed;
} else if (isPreflight) {
  command = process.execPath;
  args = ["scripts/browser-runner-preflight.mjs"];
} else {
  command = process.platform === "win32" ? "npx.cmd" : "npx";
  args = [
    "playwright",
    "test",
    "scripts/production-smoke.spec.mjs",
    "--workers=1",
    "--reporter=line",
    `--timeout=${testTimeoutMs}`,
    `--global-timeout=${globalTimeoutMs}`,
  ];
}

const startedAt = Date.now();
let finished = false;
let timedOut = false;

function elapsedSeconds() {
  return Math.floor((Date.now() - startedAt) / 1000);
}

function killTree(child) {
  if (!child.pid) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], { stdio: "ignore" });
    return;
  }
  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    try {
      child.kill("SIGTERM");
    } catch {
      // Process already exited.
    }
  }
  setTimeout(() => {
    if (finished) return;
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      try {
        child.kill("SIGKILL");
      } catch {
        // Process already exited.
      }
    }
  }, 3_000).unref();
}

console.log(
  `[browser-runner] START mode=${isPreflight ? "preflight" : "production"} hard_timeout_ms=${hardTimeoutMs}`,
);

const child = spawn(command, args, {
  cwd: process.cwd(),
  env: process.env,
  stdio: "inherit",
  detached: process.platform !== "win32",
  shell: false,
});

const heartbeat = setInterval(() => {
  console.log(`[browser-runner] HEARTBEAT elapsed_seconds=${elapsedSeconds()}`);
}, heartbeatMs);
heartbeat.unref();

const hardTimeout = setTimeout(() => {
  if (finished) return;
  timedOut = true;
  clearInterval(heartbeat);
  console.error(
    `[browser-runner] BLOCKED hard_timeout elapsed_seconds=${elapsedSeconds()} mode=${isPreflight ? "preflight" : "production"}`,
  );
  killTree(child);
  setTimeout(() => {
    if (finished) return;
    console.error("[browser-runner] RESULT=BROWSER_RUNNER_BLOCKED forced_parent_exit=YES");
    process.exit(RUNNER_BLOCKED_EXIT);
  }, 5_000).unref();
}, hardTimeoutMs);
hardTimeout.unref();

child.once("error", (error) => {
  if (finished) return;
  finished = true;
  clearInterval(heartbeat);
  clearTimeout(hardTimeout);
  console.error(`[browser-runner] BLOCKED spawn_error=${error.message}`);
  process.exit(RUNNER_BLOCKED_EXIT);
});

child.once("exit", (code, signal) => {
  if (finished) return;
  finished = true;
  clearInterval(heartbeat);
  clearTimeout(hardTimeout);

  if (timedOut) {
    console.error(`[browser-runner] RESULT=BROWSER_RUNNER_BLOCKED elapsed_seconds=${elapsedSeconds()}`);
    process.exit(RUNNER_BLOCKED_EXIT);
  }

  if (code === 0) {
    console.log(`[browser-runner] PASS elapsed_seconds=${elapsedSeconds()}`);
    process.exit(0);
  }

  const detail = signal ? `signal=${signal}` : `exit_code=${code ?? "unknown"}`;
  if (isPreflight) {
    console.error(`[browser-runner] RESULT=BROWSER_RUNNER_BLOCKED ${detail}`);
    process.exit(RUNNER_BLOCKED_EXIT);
  }

  console.error(`[browser-runner] RESULT=BROWSER_SMOKE_FAILED ${detail}`);
  process.exit(code && code > 0 ? code : 1);
});
