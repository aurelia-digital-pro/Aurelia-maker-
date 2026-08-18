# AURELIA Maker — Free Local Video Engine

This repository is an end-to-end, local-first production engine that converts an AURELIA script into cinematic documentary-style videos for YouTube (16:9) and TikTok (9:16). It uses free/open-source tools and a canonical Chat → Factory → FINAL MP4 path.

Production path:
- Chat request is the sole episode-content source
- Script → Scene planning → local TTS → procedural cinematic visuals
- FFmpeg editing → subtitles → color grade → master encode → QC → Delivery
- Every production job owns an isolated artifact directory and job-bound download
