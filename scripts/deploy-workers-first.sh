#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${LEADX_BASE_URL:-https://leadx.simondalmasso44.workers.dev}"
WORKER_NAME="${LEADX_WORKER_NAME:-leadx}"
WRANGLER_VERSION="${WRANGLER_VERSION:-4.111.0}"
EXPECTED_FOTOMULTAS_COUNT="${EXPECTED_FOTOMULTAS_COUNT:-9}"
EXPECTED_AGRO_COUNT="${EXPECTED_AGRO_COUNT:-40}"
BROWSER_PREFLIGHT_ONLY="${LEADX_BROWSER_PREFLIGHT_ONLY:-0}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="${LEADX_DEPLOY_ARTIFACT_DIR:-$ROOT_DIR/artifacts/workers-first/$RUN_ID}"
BUNDLE_DIR="$ARTIFACT_DIR/bundle"
COOKIE_JAR="$ARTIFACT_DIR/session.cookies"

log() { printf '[leadx-deploy] %s\n' "$*"; }
fail() { printf '[leadx-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

require_env_name() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "Missing required environment variable: $name"
}

normalize_browser_path() {
  local candidate="$1"
  if command -v cygpath >/dev/null 2>&1 && [[ "$candidate" == /* ]]; then
    cygpath -w "$candidate"
  else
    printf '%s\n' "$candidate"
  fi
}

resolve_chromium_executable() {
  local candidate=""

  if [[ -n "${LEADX_CHROMIUM_EXECUTABLE:-}" ]]; then
    printf '%s\n' "$LEADX_CHROMIUM_EXECUTABLE"
    return 0
  fi

  for browser_command in chromium chromium-browser google-chrome-stable google-chrome chrome msedge; do
    candidate="$(command -v "$browser_command" 2>/dev/null || true)"
    if [[ -n "$candidate" ]]; then
      normalize_browser_path "$candidate"
      return 0
    fi
  done

  if command -v where.exe >/dev/null 2>&1; then
    for browser_binary in chromium.exe chrome.exe msedge.exe; do
      candidate="$(where.exe "$browser_binary" 2>/dev/null | tr -d '\r' | head -n 1 || true)"
      if [[ -n "$candidate" ]]; then
        printf '%s\n' "$candidate"
        return 0
      fi
    done
  fi

  for candidate in \
    "/c/Program Files/Google/Chrome/Application/chrome.exe" \
    "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
    "/c/Program Files/Microsoft/Edge/Application/msedge.exe" \
    "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"; do
    if [[ -f "$candidate" ]]; then
      normalize_browser_path "$candidate"
      return 0
    fi
  done

  return 1
}

deployments_jq='
  def deployments:
    if (.result | type) == "array" then
      .result
    elif (.result | type) == "object"
         and (.result.deployments | type) == "array" then
      .result.deployments
    else
      error("Unexpected Cloudflare deployments response schema")
    end;
'

cloudflare_deployments() {
  local destination="$1"
  curl -fsS \
    -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/deployments" \
    > "$destination"
  jq -e "${deployments_jq} .success == true and (deployments | length) > 0" "$destination" >/dev/null
}

active_deployment_id() {
  jq -r "${deployments_jq} deployments[0].id // empty" "$1"
}

active_version_id() {
  jq -r "${deployments_jq} deployments[0].versions[]? | select(.percentage == 100) | .version_id" "$1" | head -n 1
}

active_version_count() {
  jq -r "${deployments_jq} deployments[0].versions | length" "$1"
}

active_traffic_percentage() {
  jq -r "${deployments_jq} deployments[0].versions[0].percentage // empty" "$1"
}

run_browser_stage() {
  local mode="$1"
  local output_file="$2"
  local stage_status

  (
    cd web
    node scripts/run-browser-smoke.mjs "$mode"
  ) 2>&1 | tee "$output_file"
  stage_status="${PIPESTATUS[0]}"
  return "$stage_status"
}

prepare_browser_runner() {
  log "Installing Playwright test package without downloading a browser."
  npm --prefix web install --no-save --package-lock=false @playwright/test@1.51.1 >/dev/null

  LEADX_CHROMIUM_EXECUTABLE="$(resolve_chromium_executable || true)"
  [[ -n "$LEADX_CHROMIUM_EXECUTABLE" ]] \
    || fail "BROWSER_RUNNER_BLOCKED: no installed Chromium, Chrome, or Edge executable was found."
  export LEADX_CHROMIUM_EXECUTABLE

  log "Validating the installed browser before any Cloudflare deployment."
  if run_browser_stage --preflight "$ARTIFACT_DIR/browser-preflight.log"; then
    printf 'BROWSER_RUNNER_PREFLIGHT=PASS\n' >> "$ARTIFACT_DIR/summary.txt"
    log "Browser runner preflight passed."
  else
    local preflight_status=$?
    printf 'BROWSER_RUNNER_PREFLIGHT=BLOCKED\n' >> "$ARTIFACT_DIR/summary.txt"
    fail "BROWSER_RUNNER_BLOCKED: preflight exited with status ${preflight_status}; no deploy was attempted."
  fi
}

rollback_to_previous() {
  local reason="$1"
  [[ -n "${PREVIOUS_VERSION_ID:-}" ]] || {
    log "Rollback impossible: previous version was not captured."
    return 1
  }

  log "Rolling back to previous version ${PREVIOUS_VERSION_ID}."
  npx --yes "wrangler@${WRANGLER_VERSION}" rollback "$PREVIOUS_VERSION_ID" \
    --message "LeadX automatic rollback: ${reason}"

  local rollback_json="$ARTIFACT_DIR/rollback-deployments.json"
  local restored=""
  for _ in $(seq 1 60); do
    cloudflare_deployments "$rollback_json"
    restored="$(active_version_id "$rollback_json")"
    [[ "$restored" == "$PREVIOUS_VERSION_ID" ]] && break
    sleep 2
  done

  [[ "$restored" == "$PREVIOUS_VERSION_ID" ]] || fail "Rollback did not restore the previous version."
  curl -fsS "$BASE_URL/api/health?rollback_smoke=$(date +%s%N)" \
    | jq -e '.status == "ok" and .service == "leadx"' >/dev/null
  printf 'ROLLBACK_STATE=completed\n' >> "$ARTIFACT_DIR/summary.txt"
  log "Rollback completed and health-checked."
}

production_smoke() {
  local nonce="workers-first-${RUN_ID}-$(date +%s%N)"
  local health="$ARTIFACT_DIR/health.json"
  local session="$ARTIFACT_DIR/session-anonymous.json"
  local login="$ARTIFACT_DIR/login.json"
  local agro="$ARTIFACT_DIR/leads-repuestos_agricolas.json"
  local fines="$ARTIFACT_DIR/leads-fotomultas.json"

  log "HTTP smoke: health."
  curl -fsS "$BASE_URL/api/health?deploy_smoke=$nonce" -o "$health"
  jq -e '.status == "ok" and .service == "leadx"' "$health" >/dev/null

  log "HTTP smoke: anonymous session."
  curl -fsS "$BASE_URL/api/auth/session?deploy_smoke=$nonce" -o "$session"
  jq -e '.authenticated == false and .mode == "demo"' "$session" >/dev/null

  log "HTTP smoke: authenticated login."
  curl -fsS -c "$COOKIE_JAR" \
    -H 'Content-Type: application/json' \
    --data-binary "$(jq -cn --arg password "$DASHBOARD_PASSWORD" '{password:$password}')" \
    "$BASE_URL/api/auth/login?deploy_smoke=$nonce" \
    -o "$login"
  jq -e '.ok == true' "$login" >/dev/null

  log "HTTP smoke: vertical readback."
  curl -fsS -b "$COOKIE_JAR" \
    "$BASE_URL/api/leads?vertical=repuestos_agricolas&deploy_smoke=$nonce" \
    -o "$agro"
  curl -fsS -b "$COOKIE_JAR" \
    "$BASE_URL/api/leads?vertical=fotomultas&deploy_smoke=$nonce" \
    -o "$fines"

  jq -e --argjson expected "$EXPECTED_AGRO_COUNT" \
    '(.meta.source != "demo") and (.leads_all | length == $expected) and all(.leads_all[]; .vertical == "repuestos_agricolas")' \
    "$agro" >/dev/null
  jq -e --argjson expected "$EXPECTED_FOTOMULTAS_COUNT" \
    '(.meta.source != "demo") and (.leads_all | length == $expected) and all(.leads_all[]; .vertical == "fotomultas")' \
    "$fines" >/dev/null

  local agro_unique fines_unique
  agro_unique="$(jq '[.leads_all[].id] | unique | length' "$agro")"
  fines_unique="$(jq '[.leads_all[].id] | unique | length' "$fines")"
  [[ "$agro_unique" == "$EXPECTED_AGRO_COUNT" ]] || return 1
  [[ "$fines_unique" == "$EXPECTED_FOTOMULTAS_COUNT" ]] || return 1

  log "HTTP smoke: logout."
  curl -fsS -b "$COOKIE_JAR" -c "$COOKIE_JAR" -X POST \
    "$BASE_URL/api/auth/logout?deploy_smoke=$nonce" \
    -o "$ARTIFACT_DIR/logout.json"
  curl -fsS -b "$COOKIE_JAR" \
    "$BASE_URL/api/auth/session?deploy_smoke=$nonce" \
    -o "$ARTIFACT_DIR/session-ended.json"
  jq -e '.authenticated == false and .mode == "demo"' "$ARTIFACT_DIR/session-ended.json" >/dev/null

  export LEADX_BASE_URL="$BASE_URL"
  export LEADX_SMOKE_PASSWORD="$DASHBOARD_PASSWORD"
  export LEADX_SMOKE_NONCE="$nonce"
  export LEADX_SMOKE_SCREENSHOT_DIR="$ARTIFACT_DIR/screenshots"

  log "Browser smoke: starting controlled Playwright runner."
  run_browser_stage --production "$ARTIFACT_DIR/browser.log"
}

for command in bash curl jq node npm sha256sum git; do
  require_command "$command"
done

SOURCE_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "The deployment source must be a Git working tree with a valid HEAD."
test -z "$(git status --porcelain)" || fail "Working tree is not clean. Commit or stash before deploying."

mkdir -p "$ARTIFACT_DIR" "$BUNDLE_DIR"
chmod 700 "$ARTIFACT_DIR"
: > "$ARTIFACT_DIR/summary.txt"

log "Installing exact frontend dependencies."
npm --prefix web ci
prepare_browser_runner

if [[ "$BROWSER_PREFLIGHT_ONLY" == "1" ]]; then
  cat >> "$ARTIFACT_DIR/summary.txt" <<SUMMARY
DEPLOY_SOURCE=browser-preflight-only
SOURCE_SHA=$SOURCE_SHA
DEPLOY_ATTEMPTED=NO
PRODUCTION_CHANGED=NO
ROLLBACK_EXECUTED=NO
SUMMARY
  find "$ARTIFACT_DIR" -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum > "$ARTIFACT_DIR/SHA256SUMS"
  log "Browser runner validation completed without deploying."
  exit 0
fi

# Secret names only. Values are never printed.
# GitHub repository secrets:
#   CLOUDFLARE_ACCOUNT_ID
#   CLOUDFLARE_API_TOKEN
#   DASHBOARD_PASSWORD
#   INGEST_SECRET
#   SESSION_SECRET
# Names matched between GitHub and the Cloudflare deployment environment:
#   CLOUDFLARE_ACCOUNT_ID
#   CLOUDFLARE_API_TOKEN
#   DASHBOARD_PASSWORD
for name in CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN DASHBOARD_PASSWORD; do
  require_env_name "$name"
done

log "Running build, tests and typecheck."
npm --prefix web run build
npm --prefix web test
npm --prefix web run typecheck

log "Checking Cloudflare authentication and runtime secret names."
npx --yes "wrangler@${WRANGLER_VERSION}" whoami >/dev/null
runtime_secret_names="$(npx --yes "wrangler@${WRANGLER_VERSION}" secret list --format json | jq -r '.[].name')"
for name in DASHBOARD_PASSWORD SESSION_SECRET INGEST_SECRET; do
  grep -Fxq "$name" <<<"$runtime_secret_names" || fail "Missing Cloudflare Worker runtime secret: $name"
done

log "Capturing the active deployment before changes."
cloudflare_deployments "$ARTIFACT_DIR/previous-deployments.json"
PREVIOUS_DEPLOYMENT_ID="$(active_deployment_id "$ARTIFACT_DIR/previous-deployments.json")"
PREVIOUS_VERSION_ID="$(active_version_id "$ARTIFACT_DIR/previous-deployments.json")"
[[ -n "$PREVIOUS_DEPLOYMENT_ID" && -n "$PREVIOUS_VERSION_ID" ]] \
  || fail "Could not capture the previous deployment/version."

log "Building the exact Wrangler bundle without deploying."
npx --yes "wrangler@${WRANGLER_VERSION}" deploy --dry-run --outdir "$BUNDLE_DIR" \
  2>&1 | tee "$ARTIFACT_DIR/dry-run.log"
BUNDLE_SHA256="$(
  find "$BUNDLE_DIR" -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    | sha256sum \
    | awk '{print $1}'
)"
[[ "$BUNDLE_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "Could not calculate the deployment bundle hash."

log "Deploying exactly once to Cloudflare Workers."
DEPLOY_OUTPUT="$ARTIFACT_DIR/deploy.log"
npx --yes "wrangler@${WRANGLER_VERSION}" deploy 2>&1 | tee "$DEPLOY_OUTPUT"
NEW_VERSION_ID="$(grep -oE 'Current Version ID: [a-f0-9-]+' "$DEPLOY_OUTPUT" | awk '{print $4}' | tail -n 1)"
if [[ -z "$NEW_VERSION_ID" ]]; then
  NEW_VERSION_ID="$(npx --yes "wrangler@${WRANGLER_VERSION}" versions list --json | jq -r '.[0].id // .[0].version_id // empty')"
fi
[[ -n "$NEW_VERSION_ID" ]] || {
  rollback_to_previous "new version ID could not be resolved"
  fail "Deploy output did not provide a version ID."
}

log "Waiting for the new version to become the only active version at 100% traffic."
NEW_DEPLOYMENT_ID=""
propagated=false
for _ in $(seq 1 90); do
  cloudflare_deployments "$ARTIFACT_DIR/current-deployments.json"
  current_version="$(active_version_id "$ARTIFACT_DIR/current-deployments.json")"
  current_count="$(active_version_count "$ARTIFACT_DIR/current-deployments.json")"
  current_percentage="$(active_traffic_percentage "$ARTIFACT_DIR/current-deployments.json")"
  if [[ "$current_version" == "$NEW_VERSION_ID" && "$current_count" == "1" && "$current_percentage" == "100" ]]; then
    NEW_DEPLOYMENT_ID="$(active_deployment_id "$ARTIFACT_DIR/current-deployments.json")"
    propagated=true
    break
  fi
  sleep 2
done

if [[ "$propagated" != true || -z "$NEW_DEPLOYMENT_ID" ]]; then
  rollback_to_previous "new deployment did not reach 100 percent traffic"
  fail "New deployment did not propagate correctly."
fi

log "Running authenticated HTTP and browser production smokes."
if production_smoke; then
  log "Production smoke passed."
else
  smoke_status=$?
  if [[ "$smoke_status" == "86" ]]; then
    printf 'BROWSER_RUNNER=BLOCKED\n' >> "$ARTIFACT_DIR/summary.txt"
    rollback_to_previous "browser runner blocked during post-deploy smoke"
    fail "BROWSER_RUNNER_BLOCKED; the previous version was restored."
  fi
  printf 'BROWSER_SMOKE=FAILED\n' >> "$ARTIFACT_DIR/summary.txt"
  rollback_to_previous "post-deploy production smoke failed"
  fail "Production smoke failed; the previous version was restored."
fi

rm -f "$COOKIE_JAR" "$ARTIFACT_DIR/login.json" "$ARTIFACT_DIR/leads-"*.json

cat >> "$ARTIFACT_DIR/summary.txt" <<SUMMARY
DEPLOY_SOURCE=cloudflare-workers-first
SOURCE_SHA=$SOURCE_SHA
BUNDLE_SHA256=$BUNDLE_SHA256
PREVIOUS_DEPLOYMENT_ID=$PREVIOUS_DEPLOYMENT_ID
PREVIOUS_VERSION_ID=$PREVIOUS_VERSION_ID
NEW_DEPLOYMENT_ID=$NEW_DEPLOYMENT_ID
NEW_VERSION_ID=$NEW_VERSION_ID
TRAFFIC_ACTIVE=100
HEALTH=PASS
AUTHENTICATED_READBACK=PASS
FOTOMULTAS_REAL_COUNT=$EXPECTED_FOTOMULTAS_COUNT
REPUESTOS_AGRICOLAS_REAL_COUNT=$EXPECTED_AGRO_COUNT
BROWSER_SMOKE=PASS
ROLLBACK_EXECUTED=NO
GITHUB_RECONCILIATION_REQUIRED=YES
SUMMARY

find "$ARTIFACT_DIR" -type f ! -name SHA256SUMS -print0 \
  | sort -z \
  | xargs -0 sha256sum > "$ARTIFACT_DIR/SHA256SUMS"

# Hard fail if evidence contains secret values or private lead records.
! grep -R -E -i \
  'authorization: bearer|set-cookie:|DASHBOARD_PASSWORD=|SESSION_SECRET=|INGEST_SECRET=|CLOUDFLARE_API_TOKEN=|whatsapp_publico|email_publico|contact_name' \
  "$ARTIFACT_DIR"

log "Deployment succeeded."
log "Cloudflare deployment ID: $NEW_DEPLOYMENT_ID"
log "Cloudflare version ID: $NEW_VERSION_ID"
log "Bundle SHA-256: $BUNDLE_SHA256"
log "Next mandatory step: reconcile this exact SOURCE_SHA in GitHub, then run the Workers-first reconciliation workflow."
