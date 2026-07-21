#!/bin/sh
set -eu

umask 077

STATE_DIR="${LEADX_STATE_DIR:-/state}"
REPO_ROOT="${LEADX_REPO_ROOT:-/app}"
INTERVAL_MINUTES="${LEADX_INTERVAL_MINUTES:-180}"
TIMEOUT_SECONDS="${LEADX_TIMEOUT_SECONDS:-260}"
MAX_HEALTH_AGE_MINUTES="${LEADX_MAX_HEALTH_AGE_MINUTES:-240}"

if [ "${LEADX_DISCOVERY_PUBLIC_NETWORK:-0}" != "1" ]; then
  echo '{"status":"BLOCKED","reason":"LEADX_DISCOVERY_PUBLIC_NETWORK_must_equal_1"}' >&2
  exit 78
fi

case "$STATE_DIR" in
  /*) ;;
  *) echo '{"status":"BLOCKED","reason":"LEADX_STATE_DIR_must_be_absolute"}' >&2; exit 78 ;;
esac

mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

CANDIDATES="$STATE_DIR/candidates-latest.json"
DECISIONS="$STATE_DIR/fotomultas-decisions.json"
VERIFICATIONS="$STATE_DIR/verifications.json"

set -- python -m labs.fotomultas_discovery.orchestrator \
  --repo-root "$REPO_ROOT" \
  --candidates-output "$CANDIDATES" \
  --decisions-output "$DECISIONS" \
  --verifications "$VERIFICATIONS" \
  --allow-public-network \
  --interval-minutes "$INTERVAL_MINUTES" \
  --timeout-seconds "$TIMEOUT_SECONDS"

if [ "${LEADX_RUN_ONCE:-0}" != "1" ]; then
  set -- "$@" --watch
fi

printf '%s\n' \
  "RUNTIME=fotomultas_discovery_lab" \
  "STATE_DIR=$STATE_DIR" \
  "RUN_ONCE=${LEADX_RUN_ONCE:-0}" \
  "INTERVAL_MINUTES=$INTERVAL_MINUTES" \
  "TIMEOUT_SECONDS=$TIMEOUT_SECONDS" \
  "MAX_HEALTH_AGE_MINUTES=$MAX_HEALTH_AGE_MINUTES" >&2

exec "$@"
