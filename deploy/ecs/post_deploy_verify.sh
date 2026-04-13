#!/usr/bin/env bash
# Post-release gate: HTTP smoke + full_chain_consistency_audit (optional path).
# Env:
#   APP_ROOT, WEB_ROOT, ENV_FILE — passed to audit
#   HEALTH_URL, HEALTH_READY_URL — defaults 127.0.0.1:8010
#   AUDIT_SCRIPT — default /tmp/full_chain_consistency_audit.sh (uploaded by deploy)
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/clothing-assistant/clothing-assistant-main}"
WEB_ROOT="${WEB_ROOT:-/usr/share/nginx/html}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/backend/.env}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8010/health}"
HEALTH_READY_URL="${HEALTH_READY_URL:-http://127.0.0.1:8010/health/ready}"
ROOT_URL="${ROOT_URL:-http://127.0.0.1:8010/}"
AUDIT_SCRIPT="${AUDIT_SCRIPT:-/tmp/full_chain_consistency_audit.sh}"

echo "[post_deploy_verify] smoke: $HEALTH_URL"
if ! command -v curl >/dev/null 2>&1; then
  echo "[post_deploy_verify][ERROR] curl required" >&2
  exit 3
fi
curl -fsS "$HEALTH_URL" >/dev/null
echo "[post_deploy_verify] smoke: $HEALTH_READY_URL"
curl -fsS "$HEALTH_READY_URL" >/dev/null

echo "[post_deploy_verify] smoke: GET / (JSON)"
root_out="$(curl -fsS "$ROOT_URL" || true)"
if [[ -z "$root_out" ]] || ! echo "$root_out" | grep -q "Smart Outfit"; then
  echo "[post_deploy_verify][ERROR] root body missing expected app name" >&2
  exit 4
fi

if [[ ! -f "$AUDIT_SCRIPT" ]]; then
  echo "[post_deploy_verify][ERROR] audit script not found: $AUDIT_SCRIPT" >&2
  exit 5
fi

chmod +x "$AUDIT_SCRIPT" 2>/dev/null || true
echo "[post_deploy_verify] running audit: $AUDIT_SCRIPT"
APP_ROOT="$APP_ROOT" WEB_ROOT="$WEB_ROOT" ENV_FILE="$ENV_FILE" \
  HEALTH_URL="$HEALTH_URL" HEALTH_READY_URL="$HEALTH_READY_URL" \
  bash "$AUDIT_SCRIPT"
code=$?
if [[ "$code" -eq 2 ]]; then
  echo "[post_deploy_verify][ERROR] audit failed (failures)" >&2
  exit 2
fi
if [[ "$code" -eq 1 ]]; then
  echo "[post_deploy_verify][WARN] audit completed with warnings"
fi
echo "[post_deploy_verify] OK"
exit 0
