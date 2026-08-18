#!/usr/bin/env bash
# Chat-only production entry. The episode command and script come from Chat.
set -euo pipefail
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
python3 aurelia/generate.py chat
