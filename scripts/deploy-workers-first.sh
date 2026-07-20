#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${LEADX_BASE_URL:-https://leadx.simondalmasso44.workers.dev}"
WORKER_NAME="${LEADX_WORKER_NAME:-leadx}"
WRANGLER_VERSION="${WRANGLER_VERSION:-4.111.0}"
EXPECTED_FOTOMULTAS_COUNT="${EXPECTED_FOTOMULTAS_COUNT:-9}"
EXPECTED_AGRO_COUNT="${EXPECTED_AGRO_COUNT:-40}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="${LEADX_DEPLOY_ARTIFACT_DIR:-$ROOT_DIR/artifacts/workers-first/$RUN_ID}"
BUNDLE_DIR="$ARTIFACT_DIR/bundle"
COOKIE_JAR="$ARTIFACT_DIR/session.cookies"

mkdir -p "$ARTIFACT_DIR" "$BUNDLE_DIR"
chmod 700 "$ARTIFACT_DIR"

log() { printf '[leadx-deploy] %s\n' "$*"; }
fail() { printf '[leadx-deploy] ERROR: %s\n' "$*" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

require_env_name() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "Missing required environment variable: $name"
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

  curl -fsS "$BASE_URL/api/health?deploy_smoke=$nonce" -o "$health"
  jq -e '.status == "ok" and .service == "leadx"' "$health" >/dev/null

  curl -fsS "$BASE_URL/api/auth/session?deploy_smoke=$nonce" -o "$session"
  jq -e '.authenticated == false and .mode == "demo"' "$session" >/dev/null

  curl -fsS -c "$COOKIE_JAR" \
    -H 'Content-Type: application/json' \
    --data-binary "$(jq -cn --arg password "$DASHBOARD_PASSWORD" '{password:$password}')" \
    "$BASE_URL/api/auth/login?deploy_smoke=$nonce" \
    -o "$login"
  jq -e '.ok == true' "$login" >/dev/null

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
  (
    cd web
    npm install --no-save --package-lock=false @playwright/test@1.51.1 >/dev/null
    npx playwright install --with-deps chromium >/dev/null
    npx playwright test scripts/production-smoke.spec.mjs --workers=1 \
      2>&1 | tee "$ARTIFACT_DIR/browser.log"
  )
}

for command in bash curl jq node npm sha256sum git; do
  require_command "$command"
done

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

SOURCE_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "The deployment source must be a Git working tree with a valid HEAD."
test -z "$(git status --porcelain)" || fail "Working tree is not clean. Commit or stash before deploying."

log "Installing exact frontend dependencies."
npm --prefix web ci

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
if ! production_smoke; then
  rollback_to_previous "post-deploy production smoke failed"
  fail "Production smoke failed; the previous version was restored."
fi

rm -f "$COOKIE_JAR" "$ARTIFACT_DIR/login.json" "$ARTIFACT_DIR/leads-"*.json
find "$ARTIFACT_DIR" -type f ! -name SHA256SUMS -print0 \
  | sort -z \
  | xargs -0 sha256sum > "$ARTIFACT_DIR/SHA256SUMS"

cat > "$ARTIFACT_DIR/summary.txt" <<SUMMARY
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

! grep -R -E -i \
  'authorization: bearer|set-cookie:|DASHBOARD_PASSWORD=|SESSION_SECRET=|INGEST_SECRET=|CLOUDFLARE_API_TOKEN=|whatsapp_publico|email_publico|contact_name' \
  "$ARTIFACT_DIR"

log "Deployment succeeded."
log "Cloudflare deployment ID: $NEW_DEPLOYMENT_ID"
log "Cloudflare version ID: $NEW_VERSION_ID"
log "Bundle SHA-256: $BUNDLE_SHA256"
log "Next mandatory step: reconcile this exact SOURCE_SHA in GitHub, then run the Workers-first reconciliation workflow."
