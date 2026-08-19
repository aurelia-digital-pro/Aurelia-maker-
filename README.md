# AURELIA Maker — Free Local Video Engine (MVP)

This repository is an end-to-end, local-first MVP that converts an AURELIA script into cinematic documentary-style videos for YouTube (16:9) and TikTok (9:16). It is intentionally small, self-contained, and uses only free/open-source tools.

Quick goals achieved by this MVP:
- Chat-driven CLI + simple agent hooks (local LLM optional)
- Script → Scene planning (automatic)
- Local TTS (pyttsx3) → narration.wav
- Procedural cinematic visuals per scene (Pillow-generated starfields, gold accents, typography)
- Automatic editing and scene timing synced to narration
- Subtitles (SRT approximate timings)
- Background ambient music (procedural) + ducking
- Transitions and final concat via ffmpeg
- Outputs written to output/ as MP4 files for YouTube and TikTok

## Installation

### Prerequisites
- Python 3.10+
- FFmpeg (system binary)
- libespeak1 (for text-to-speech)

### Quick Setup

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y ffmpeg libespeak1 espeak

# Install Python dependencies
pip install -r requirements.txt
```

## Usage

### Generate Episode from Script

```bash
./run-demo.sh
```

Or manually:

```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
python3 aurelia/generate.py generate --script path/to/episode-script.txt --episode <EPISODE_ID> --profile both
```

`<EPISODE_ID>` and the corresponding script are explicit production inputs. There is no default episode.

### Output Files

Generated files are saved to `output/episode-{EPISODE_ID}/`:
- `episode-{EPISODE_ID}-youtube.mp4` — 1920x1080 with subtitles
- `episode-{EPISODE_ID}-tiktok.mp4` — 1920x1080 with subtitles
- `narration.wav` — Full narration audio
- `episode-{EPISODE_ID}.srt` — Subtitle file
- `visuals/` — Generated scene PNG backgrounds
- Individual scene MP4 files with zoom/pan effects

### Custom Script

Create your own episode script file and pass the matching episode id explicitly:

```bash
python3 aurelia/generate.py generate --script path/to/episode-script.txt --episode <EPISODE_ID> --profile both
```

### Chat Mode (Local Script Composition)

```bash
python3 aurelia/generate.py chat
```
