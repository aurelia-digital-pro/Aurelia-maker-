#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export AURELIA_PRODUCTION_MODE="${AURELIA_PRODUCTION_MODE:-1}"
export AURELIA_FORCE_FALLBACK="${AURELIA_FORCE_FALLBACK:-0}"
export AURELIA_ALLOW_DEGRADED_TTS="${AURELIA_ALLOW_DEGRADED_TTS:-0}"
export AURELIA_CANONICAL_API_URL="${AURELIA_CANONICAL_API_URL:-http://127.0.0.1:8765}"

canonical_port="${AURELIA_CANONICAL_API_PORT:-8765}"
canonical_host="${AURELIA_CANONICAL_API_HOST:-127.0.0.1}"
api_port="${PORT:-8080}"

python3 -m aurelia.generate serve \
  --host "$canonical_host" \
  --port "$canonical_port" \
  >"${AURELIA_CANONICAL_LOG:-/tmp/aurelia-canonical-api.log}" 2>&1 &
canonical_pid=$!

cleanup() {
  kill "$canonical_pid" 2>/dev/null || true
  wait "$canonical_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fsS --max-time 1 "${AURELIA_CANONICAL_API_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$canonical_pid" 2>/dev/null; then
    cat "${AURELIA_CANONICAL_LOG:-/tmp/aurelia-canonical-api.log}" >&2 || true
    exit 1
  fi
  sleep 1
done

if [[ -f artifacts/api-server/dist/index.mjs ]]; then
  exec env PORT="$api_port" AURELIA_CANONICAL_API_URL="$AURELIA_CANONICAL_API_URL" \
    node --enable-source-maps artifacts/api-server/dist/index.mjs
fi

exec env PORT="$api_port" AURELIA_CANONICAL_API_URL="$AURELIA_CANONICAL_API_URL" \
  pnpm --filter @workspace/api-server run dev
