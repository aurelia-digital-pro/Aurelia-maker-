# AURELIA Maker

**Free, local, open-source cinematic video factory.**

`Chat Prompt → AURELIA → Script Intelligence → Cinematic Direction → Scene Visuals → Arabic/English Narration → Music → Subtitles → Color Grade → Final MP4`

---

## Quick Start

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update -y
sudo apt-get install -y ffmpeg espeak-ng fonts-dejavu fontconfig

# Install Python dependencies
pip install -r requirements.txt

# Launch web interface
python -m aurelia.generate serve
# Open: http://127.0.0.1:8765
```

---

## Chat Usage (Arabic + English)

### Arabic Command

```
أنشئ فيلمًا وثائقيًا سينمائيًا بالعربية عن الذكاء الاصطناعي
العنوان: عقول خفية
اللغة: ar

في قلب الكون الرقمي...
```

### English Command

```
Create Episode 0001
Title: Hidden Minds
Language: en

In the heart of the digital cosmos...
```

---

## CLI Usage

```bash
# Web interface
python -m aurelia.generate serve

# Interactive chat
python -m aurelia.generate chat

# Produce from script file
python -m aurelia.generate produce --script scripts/episode-0001-arabic-test.txt

# Quick demo
bash run-demo.sh ar    # Arabic
bash run-demo.sh en    # English
```

---

## Architecture

```
Chat / CLI
  → chat_entry.py    (Arabic + English parsing)
  → factory_runner.py (31-stage production pipeline)
  → episode_engine.py (scene plan → visuals → audio → edit)
  → FINAL MP4
```

### Production Stages (31)

`SCRIPT → DEVELOPMENT → STORY → WORLD → CHARACTER → SERIES_BIBLE → RESEARCH → PRE_PRODUCTION → SEQUENCE → SCENE → SHOT → STORYBOARD → ANIMATIC → VISUAL → ASSET → CAMERA → DEPTH → MOTION → LIGHT → ATMOSPHERE → VFX → NARRATION → DIALOGUE → SOUND → MUSIC → AUDIO → EDIT → COLOR → SUBTITLE → MASTER → QC → DELIVERY`

---

## Stack (100% Free / Open Source)

| Component | Tool | Notes |
|-----------|------|-------|
| Visual generation | Stable Diffusion v1.5 | Optional; falls back to Pillow |
| Narration (EN) | espeak-ng en-us+f3 | Offline, no API |
| Narration (AR) | espeak-ng ar | Offline, supports Arabic |
| Motion / Assembly | FFmpeg | libx264 |
| Music | pydub pentatonic synthesis | Procedural |
| Subtitles | FFmpeg ASS burn-in | Arabic RTL supported |
| Color grade | FFmpeg eq filter | |
| Web server | FastAPI + uvicorn | |

### Optional: Higher-Quality Visuals

```bash
pip install -r requirements-ai.txt  # torch + diffusers
```

Stable Diffusion runs automatically if installed.

---

## Outputs

```
output/
  episode-XXXX/
    job-<uuid>/
      delivery/
        episode-XXXX-youtube.mp4   (1920×1080)
        episode-XXXX-tiktok.mp4    (1080×1920)
        episode-XXXX-FINAL.mp4
      production_manifest.json
      episode-XXXX.srt
      visual_manifest.json
      visuals/ shots/ audio/ edit/ master/
```

---

## System Requirements

- Python 3.10+
- FFmpeg (system binary)
- espeak-ng (for TTS)
- 1 GB disk space per episode
- GPU optional (Stable Diffusion is faster with GPU)
