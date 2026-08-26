#!/usr/bin/env bash
set -euo pipefail

# Keep local/Replit Python runtime identical to CI and the canonical engine.
python3 -m pip install --quiet -r requirements.txt
pnpm install --frozen-lockfile
pnpm --filter db push
