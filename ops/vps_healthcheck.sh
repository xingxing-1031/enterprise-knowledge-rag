#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.vps}"
LOG_DIR="${LOG_DIR:-$PROJECT_DIR/logs}"
mkdir -p "$LOG_DIR"

HTTP_PORT="$(grep -E '^HTTP_PORT=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d "'\"")"
HTTP_PORT="${HTTP_PORT:-8010}"
status="ok"
detail="ready"
if ! curl --fail --silent --show-error --max-time 10 \
  "http://127.0.0.1:${HTTP_PORT}/ready" >/dev/null; then
  status="failed"
  detail="ready_endpoint_unavailable"
fi

disk_used="$(df -P "$PROJECT_DIR" | awk 'NR==2 {gsub(/%/, "", $5); print $5}')"
if [[ "$disk_used" -ge 85 ]]; then
  status="failed"
  detail="disk_usage_${disk_used}_percent"
fi

timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '{"timestamp":"%s","event":"enterprise_rag_healthcheck","status":"%s","detail":"%s","disk_used_percent":%s}\n' \
  "$timestamp" "$status" "$detail" "$disk_used" >> "$LOG_DIR/healthcheck.jsonl"

[[ "$status" == "ok" ]]
