#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PAYLOAD_FILE="${1:-}"
MAX_PAYLOAD_BYTES=$((2 * 1024 * 1024))
MAX_LEADS=500

fail() {
  printf 'ERROR=%s\n' "$1" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "missing_command:$1"
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

for command_name in jq awk wc sort git; do
  need "$command_name"
done
if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
  fail 'missing_command:sha256sum_or_shasum'
fi

[[ -n "$PAYLOAD_FILE" ]] || fail 'usage:validate-lead-import-payload.sh_/absolute/path/private-payload.json'
[[ -f "$PAYLOAD_FILE" ]] || fail 'payload_not_regular_file'
[[ ! -L "$PAYLOAD_FILE" ]] || fail 'payload_symlink_forbidden'
[[ -r "$PAYLOAD_FILE" ]] || fail 'payload_not_readable'

PAYLOAD_DIR="$(cd "$(dirname "$PAYLOAD_FILE")" && pwd -P)"
PAYLOAD_ABS="$PAYLOAD_DIR/$(basename "$PAYLOAD_FILE")"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "$REPO_ROOT" && ( "$PAYLOAD_ABS" == "$REPO_ROOT" || "$PAYLOAD_ABS" == "$REPO_ROOT"/* ) ]]; then
  fail 'private_payload_must_be_outside_git_repository'
fi

PAYLOAD_BYTES="$(wc -c < "$PAYLOAD_ABS" | tr -d '[:space:]')"
[[ "$PAYLOAD_BYTES" =~ ^[0-9]+$ ]] || fail 'payload_size_unreadable'
(( PAYLOAD_BYTES > 0 && PAYLOAD_BYTES <= MAX_PAYLOAD_BYTES )) || fail "payload_size_invalid:$PAYLOAD_BYTES"
jq -e . "$PAYLOAD_ABS" >/dev/null || fail 'payload_invalid_json'

TARGET_VERTICAL="$(jq -r '.vertical // empty' "$PAYLOAD_ABS")"
jq -e --arg vertical "$TARGET_VERTICAL" '
  type == "object"
  and .mode == "upsert_vertical"
  and (.vertical == "fotomultas" or .vertical == "repuestos_agricolas")
  and (.leads_all | type == "array")
  and (.leads_all | length > 0 and length <= 500)
  and ([.leads_all[] | (.id | type == "string" and length > 0)] | all)
  and ([.leads_all[] | .vertical == $vertical] | all)
  and ([.leads_all[] | (._isDemo // false) == false] | all)
' "$PAYLOAD_ABS" >/dev/null || fail 'payload_contract_invalid'

PAYLOAD_COUNT="$(jq '.leads_all | length' "$PAYLOAD_ABS")"
(( PAYLOAD_COUNT <= MAX_LEADS )) || fail 'payload_lead_limit_exceeded'
PAYLOAD_UNIQUE_COUNT="$(jq '[.leads_all[].id] | unique | length' "$PAYLOAD_ABS")"
[[ "$PAYLOAD_COUNT" == "$PAYLOAD_UNIQUE_COUNT" ]] || fail 'payload_duplicate_ids'

TMP_IDS="$(mktemp "${TMPDIR:-/tmp}/leadx-import-ids.XXXXXX")"
trap 'rm -f "$TMP_IDS"' EXIT
jq -r '.leads_all[].id' "$PAYLOAD_ABS" | LC_ALL=C sort -u > "$TMP_IDS"

printf '%s\n' \
  'PAYLOAD_VALIDATION=PASS' \
  "TARGET_VERTICAL=$TARGET_VERTICAL" \
  "PAYLOAD_BYTES=$PAYLOAD_BYTES" \
  "PAYLOAD_COUNT=$PAYLOAD_COUNT" \
  "PAYLOAD_SHA256=$(sha256_file "$PAYLOAD_ABS")" \
  "PAYLOAD_ID_SET_SHA256=$(sha256_file "$TMP_IDS")" \
  'UNIQUE_IDS=PASS' \
  'VERTICAL_CONTAINMENT=PASS' \
  'PRIVATE_PAYLOAD_PUBLISHED=NO' \
  'PERMANENT_PRIVATE_ARTIFACTS_CREATED=NO'
