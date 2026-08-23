# AURELIA Maker — Phase 1 Repository Truth Audit

**Audit date:** 2026-08-23
**Repository:** `aurelia-digital-pro/Aurelia-maker-`
**Branch:** `main`
**Audit source:** fresh clone of `origin/main` at commit `044ae2477b48002e604d1403e4dc42b921fcd542`

## Execution

The repository was freshly cloned and all 66 Python files under `aurelia/` were read into an audit snapshot and parsed successfully with Python AST validation. Episode 0002 was run through the canonical acceptance path:

> Chat → FactoryRunner → production stages → visuals → camera/motion → offline TTS → music → subtitles → color → master → QC → Delivery

The original acceptance filename `episode-0002-english-test.txt` did not satisfy the harness’s explicit naming rule, so it was copied only inside the temporary fresh clone to `episode-0002.txt`; no source project file was changed for this correction.

## Measured output

| Measurement | Result |
|---|---|
| Job ID | `5e1426dfc53749b9902d5b659c93b1d2` |
| FINAL MP4 | `/tmp/Aurelia-maker-fresh/runs/audit/episode-0002-final.mp4` |
| SHA-256 | `631ab0784a44116ea34fd17115891ebe34ebdfd8837065da47c5b5b0a87fbb27` |
| Size | 27,157,657 bytes |
| Duration | 74.225 seconds |
| Video | H.264, 1920×1080, 24 fps, progressive |
| Audio | AAC-LC, 48,000 Hz, stereo |
| Full decode | PASS |
| Visual backend | Pollinations cloud API; 9 images, 0 Pillow fallbacks |
| Planned scenes / shots | 3 / 9 |
| Acceptance harness | PASS; no fatal QC checks |

## Freeze detection

A direct FFmpeg `freezedetect=n=-60dB:d=0.5` scan found repeated freeze segments, including intervals longer than the required production threshold:

| Start | End | Duration |
|---:|---:|---:|
| 14.500s | 15.208s | 0.708s |
| 15.208s | 16.208s | 1.000s |
| 17.000s | 17.583s | 0.583s |
| 53.708s | 56.000s | 2.292s |
| 56.000s | 57.083s | 1.083s |
| 57.083s | 62.417s | 5.333s |
| 62.417s | 64.375s | 1.958s |
| 64.375s | 66.417s | 2.042s |
| 66.417s | 71.958s | 5.542s |

The freeze scan therefore **fails the stricter Phase 1 cinematic criterion** despite the existing acceptance harness passing its current checks. This confirms the prompt’s stated technical risk: some shot paths still expose cloned/static frames during duration fitting or concatenation.

## Initial audit conclusions

The core factory path is real and operational: it creates a valid 1080p MP4 with H.264 video, stereo AAC audio, generated visuals, narration, subtitles, master encoding, and delivery. The primary measured blocker is excessive freeze-frame exposure in the final stream. The next phase must remove silent clone-padding from shot rendering, force nonzero motion for static shots, and re-run the production plus direct freezedetect before proceeding.

The audit also confirms that the current acceptance script’s `min_duration_s=30` gate is weaker than the Phase 1 documentary requirement for a standard script, and that the current pipeline’s three-scene/9-shot result is below the later Phase 8 target of at least five scenes and 12 shots for the specified long film.
