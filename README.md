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

This is an MVP focused on local execution, maximum automation, and no paid APIs.

See README for usage and installation.
