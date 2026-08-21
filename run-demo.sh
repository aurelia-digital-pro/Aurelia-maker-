#!/usr/bin/env bash
# AURELIA Maker — Quick local test script
# Usage: bash run-demo.sh [ar|en] [episode_id]

set -euo pipefail

LANG_ARG="${1:-ar}"
EPISODE="${2:-0001}"

echo "◈ AURELIA Maker — Local Production Test"
echo "Language : ${LANG_ARG}"
echo "Episode  : ${EPISODE}"
echo ""

# Verify dependencies
if ! command -v ffmpeg &> /dev/null; then
  echo "[ERROR] FFmpeg not found. Install: sudo apt-get install -y ffmpeg"
  exit 1
fi

if ! command -v espeak-ng &> /dev/null && ! command -v espeak &> /dev/null; then
  echo "[WARN] espeak-ng not found. Install: sudo apt-get install -y espeak-ng"
fi

# Install requirements if needed
pip install -q -r requirements.txt

# Determine script to use
if [ "${LANG_ARG}" = "ar" ]; then
  SCRIPT="scripts/episode-0001-arabic-test.txt"
else
  SCRIPT="scripts/episode-0002-english-test.txt"
fi

if [ ! -f "${SCRIPT}" ]; then
  echo "[ERROR] Script not found: ${SCRIPT}"
  exit 1
fi

echo "Script   : ${SCRIPT}"
echo ""

# Run production
python -m aurelia.generate produce \
  --script "${SCRIPT}" \
  --episode "${EPISODE}" \
  --profile both
