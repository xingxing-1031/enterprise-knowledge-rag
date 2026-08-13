#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <git-ref>" >&2
  exit 2
fi

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env.vps}"
REFERENCE="$1"
SERVICE_TOKEN_FILE="${SERVICE_TOKEN_FILE:-}"
cd "$PROJECT_DIR"

cleanup() {
  if [[ -n "$SERVICE_TOKEN_FILE" ]]; then
    rm -f "$SERVICE_TOKEN_FILE"
  fi
}
trap cleanup EXIT

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing deployment environment: $ENV_FILE" >&2
  exit 1
fi

DIRTY_STATUS="$(git status --porcelain --untracked-files=all | grep -vE '^\?\? \.deployed-release$' || true)"
if [[ -n "$DIRTY_STATUS" ]]; then
  echo "refusing deployment because the server worktree has local changes" >&2
  printf '%s\n' "$DIRTY_STATUS" >&2
  exit 1
fi

git fetch --tags origin
TARGET_REFERENCE="$REFERENCE"
if git rev-parse --verify --quiet "origin/$REFERENCE" >/dev/null; then
  TARGET_REFERENCE="origin/$REFERENCE"
fi
git checkout --detach "$TARGET_REFERENCE"

set_env_value() {
  local key="$1"
  local value="$2"
  local temporary
  temporary="$(mktemp)"
  grep -v "^${key}=" "$ENV_FILE" > "$temporary" || true
  printf "%s='%s'\n" "$key" "$value" >> "$temporary"
  mv "$temporary" "$ENV_FILE"
}

if [[ ! -r "$SERVICE_TOKEN_FILE" ]]; then
  echo "missing internal service token file" >&2
  exit 1
fi
INTERNAL_SERVICE_TOKEN="$(<"$SERVICE_TOKEN_FILE")"
if [[ -z "$INTERNAL_SERVICE_TOKEN" ]]; then
  echo "internal service token must not be empty" >&2
  exit 1
fi
set_env_value INTERNAL_SERVICE_TOKEN "$INTERNAL_SERVICE_TOKEN"
unset INTERNAL_SERVICE_TOKEN

docker compose --env-file "$ENV_FILE" -p enterprise-knowledge-rag-vps \
  -f compose.vps.yaml --profile tools run --rm --build migrate
docker compose --env-file "$ENV_FILE" -p enterprise-knowledge-rag-vps \
  -f compose.vps.yaml --profile tools run --rm --build index
docker compose --env-file "$ENV_FILE" -p enterprise-knowledge-rag-vps \
  -f compose.vps.yaml --profile tools up -d --build api caddy

HTTP_PORT="$(grep -E '^HTTP_PORT=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- | tr -d "'\"")"
HTTP_PORT="${HTTP_PORT:-8010}"
curl --fail --silent --show-error --max-time 20 \
  "http://127.0.0.1:${HTTP_PORT}/ready" >/dev/null
git rev-parse HEAD > .deployed-release
echo "deployed=$(cat .deployed-release) port=${HTTP_PORT}"
