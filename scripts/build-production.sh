#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
exec pnpm --filter @workspace/api-server run build
