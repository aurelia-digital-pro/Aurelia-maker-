# AURELIA Maker — Factory Status

## Status

Factory Architecture: COMPLETE
Production Architecture: COMPLETE
Real Video Pipeline Integration: COMPLETE
Web Interface + Chat: COMPLETE
Episode 0013: READY FOR PRODUCTION

## Canonical Path

```
Chat / CLI
  → FactoryRunner
  → Factory metadata stages (SCRIPT → PRE_PRODUCTION)
  → EpisodeEngine (SEQUENCE → DELIVERY)
  → FINAL MP4
```

Legacy MVP renderer: DISABLED

## Usage

```bash
pip install -r requirements.txt
python -m aurelia.generate serve
# Open http://127.0.0.1:8765
# Chat: Create Episode 0013
```

Or CLI:

```bash
python -m aurelia.generate generate --episode 0013 --profile both
```
