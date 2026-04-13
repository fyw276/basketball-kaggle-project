#!/usr/bin/env bash
set -euo pipefail

# Linux-side full-chain consistency audit for ECS host.
# Usage:
#   bash scripts/full_chain_consistency_audit.sh
# Optional env:
#   APP_ROOT=/opt/clothing-assistant/clothing-assistant-main
#   WEB_ROOT=/usr/share/nginx/html
#   ENV_FILE=/opt/clothing-assistant/clothing-assistant-main/backend/.env
#   HEALTH_URL=http://127.0.0.1:8010/health

APP_ROOT="${APP_ROOT:-/opt/clothing-assistant/clothing-assistant-main}"
WEB_ROOT="${WEB_ROOT:-/usr/share/nginx/html}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/backend/.env}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8010/health}"

fail=0
warn=0

say() {
  local status="$1"
  local name="$2"
  local detail="$3"
  printf '[%s] %s :: %s\n' "$status" "$name" "$detail"
}

ok() { say "OK" "$1" "$2"; }
ng() { say "FAIL" "$1" "$2"; fail=$((fail+1)); }
wn() { say "WARN" "$1" "$2"; warn=$((warn+1)); }

if [[ -d "$APP_ROOT/.git" ]]; then
  if c=$(git -C "$APP_ROOT" rev-parse HEAD 2>/dev/null); then
    ok "code.remote.commit" "$c"
  else
    ng "code.remote.commit" "cannot read git commit"
  fi
else
  wn "code.remote.commit" "no .git under $APP_ROOT"
fi

if [[ -f "$WEB_ROOT/index.html" ]]; then
  h=$(sha256sum "$WEB_ROOT/index.html" | awk '{print $1}')
  ok "frontend.remote.index" "sha256=$h"
else
  ng "frontend.remote.index" "missing $WEB_ROOT/index.html"
fi

if [[ -f "$APP_ROOT/backend/.env.example" ]]; then
  local_keys=$(grep -v '^#' "$APP_ROOT/backend/.env.example" | grep '=' | cut -d= -f1 | sort -u || true)
  lc=$(printf '%s\n' "$local_keys" | sed '/^$/d' | wc -l | tr -d ' ')
  ok "backend.remote.env.example.keys" "count=$lc"
else
  wn "backend.remote.env.example.keys" "missing $APP_ROOT/backend/.env.example"
  local_keys=""
fi

if [[ -f "$ENV_FILE" ]]; then
  remote_keys=$(grep -v '^#' "$ENV_FILE" | grep '=' | cut -d= -f1 | sort -u || true)
  rc=$(printf '%s\n' "$remote_keys" | sed '/^$/d' | wc -l | tr -d ' ')
  ok "backend.remote.env.keys" "count=$rc"

  if [[ -n "$local_keys" ]]; then
    missing=$(comm -23 <(printf '%s\n' "$local_keys" | sed '/^$/d') <(printf '%s\n' "$remote_keys" | sed '/^$/d') || true)
    if [[ -n "${missing// /}" ]]; then
      ng "backend.remote.env.coverage" "missing keys: $(echo "$missing" | tr '\n' ',' | sed 's/,$//')"
    else
      ok "backend.remote.env.coverage" "remote covers .env.example keys"
    fi
  fi
else
  ng "backend.remote.env.keys" "missing $ENV_FILE"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-active --quiet nginx; then
    ok "network.nginx" "active"
  else
    ng "network.nginx" "inactive"
  fi
else
  wn "network.nginx" "systemctl not found"
fi

if command -v curl >/dev/null 2>&1; then
  if out=$(curl -fsS "$HEALTH_URL" 2>/dev/null); then
    ok "backend.remote.health" "$out"
  else
    ng "backend.remote.health" "health check failed: $HEALTH_URL"
  fi
else
  wn "backend.remote.health" "curl not found"
fi

echo "Summary: fail=$fail warn=$warn"
if [[ "$fail" -gt 0 ]]; then
  exit 2
fi
if [[ "$warn" -gt 0 ]]; then
  exit 1
fi
exit 0
