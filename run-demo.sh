#!/usr/bin/env bash
# Quick run: generate a sample episode using the example script
export PYTHONPATH="$(pwd):$PYTHONPATH"
python3 aurelia/generate.py generate --script scripts/example.txt --episode 0012 --profile both
