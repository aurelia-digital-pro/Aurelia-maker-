#!/usr/bin/env bash
set -e
echo "AURELIA Maker setup script — installing python deps and checking tools"
python3 -m venv .venv || python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# Check ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found in PATH. Please install ffmpeg (apt, brew, or from ffmpeg.org)"
  exit 1
fi
# Inform about optional components
echo "Optional: Install local LLM tools (ollama/llama.cpp) for advanced agent planning"
echo "Setup complete. Use 'python aurelia/generate.py --help'"
