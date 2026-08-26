#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export AURELIA_PRODUCTION_MODE="${AURELIA_PRODUCTION_MODE:-1}"
export AURELIA_FORCE_FALLBACK="${AURELIA_FORCE_FALLBACK:-0}"
export AURELIA_ALLOW_DEGRADED_TTS="${AURELIA_ALLOW_DEGRADED_TTS:-0}"

PORT="${PORT:-8765}"
exec python3 -m aurelia.generate serve --host "${AURELIA_BIND_HOST:-0.0.0.0}" --port "$PORT"
