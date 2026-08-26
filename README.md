# AURELIA Maker

**A local-first cinematic film and series factory for turning a Chat request or script into a structured, narrated, subtitled MP4.** It is designed as a production foundation and previsualization system that can be extended toward long-form film and episodic workflows. It does not claim to be Netflix-grade or to provide a fully generative-video model.

## 1. What AURELIA Maker Produces

AURELIA accepts Arabic or English narrative input and builds a multi-scene, multi-shot production. The canonical path creates real visual files, narration, music, ambience, sound design, subtitles, edited motion, color treatment, a mastered H.264/AAC MP4, and machine-checkable QC evidence.

The system is intentionally **script-duration driven**. It does not clone frames, append artificial silence, or weaken QC merely to reach a target duration. For a 60–300 second episode, provide a script whose natural narration is approximately that long; short scripts will produce shorter, honest outputs.

## 2. Honest Capability Boundary

The current visual system is an **image-to-video pipeline**: an image provider creates a shot image and FFmpeg applies measurable camera motion, depth treatment, atmosphere, VFX, transitions, and timing. It is not a temporal generative-video or text-to-video subject-motion model. Characters and locations can be guided by structured prompts and series continuity context, but identity consistency is not guaranteed at the level of a dedicated character-conditioning model.

The result is suitable for cinematic prototypes, narrated documentaries, visual essays, trailers, animatics, and a foundation for a larger film factory. It should not be described as a finished Netflix production system without adding a temporal video model, stronger identity conditioning, professional dialogue recording, and editorial review.

## 3. Quick Start

```bash
sudo apt-get update -y
sudo apt-get install -y ffmpeg espeak-ng fonts-dejavu fontconfig
python3 -m pip install -r requirements.txt

# Interactive web interface
PYTHONPATH=. python3 -m aurelia.generate serve
# Open http://127.0.0.1:8765
```

The authoritative production environment is Python 3.12+, the dependencies in `requirements.txt`, the `edge-tts` executable, FFmpeg with `ffprobe`, Pillow, NumPy, pydub, and a font configuration that can render Arabic subtitles. In production mode, Edge Neural TTS is mandatory; local `espeak-ng` is only an explicitly degraded non-production adapter.

## 4. Chat and Script Inputs

Chat requests may contain a synthetic production command followed by user-authored metadata and story text. The Chat entry point removes only its synthetic command and preserves the actual body for provenance hashing. Titles and language can be supplied explicitly.

```text
Create Episode 0088
Title: The First Signal
Language: en

At the edge of the relay station, Mira hears a signal that should not exist.
The storm moves across the ridge while the instruments wake one by one.
```

A script file can be produced directly with the CLI:

```bash
PYTHONPATH=. python3 -m aurelia.generate produce \
  --script scripts/episode-0001-arabic-test.txt
```

## 5. End-to-End Factory Architecture

The production path is:

```text
Chat / CLI
  → Chat normalization and provenance binding
  → FactoryRunner job and stage artifacts
  → planning, story analysis, world, character, and series context
  → scene and shot grammar
  → visual provider and per-shot visual manifest
  → camera, depth, motion, lighting, atmosphere, and VFX rendering
  → canonical Edge Neural narration/TTS, music, ambience, and sound design
  → edit, transitions, color, subtitles, mastering
  → QC and delivery
```

`FactoryRunner` is the canonical job boundary. `EpisodeProduction` performs the media work, while the stage contract and production logger preserve inspectable artifacts rather than reporting metadata-only success.

## 6. Production Stages

The factory exposes the following stage vocabulary:

| Group | Stages |
|---|---|
| Story | SCRIPT, DEVELOPMENT, STORY, WORLD, CHARACTER, SERIES_BIBLE, RESEARCH |
| Planning | PRE_PRODUCTION, SEQUENCE, SCENE, SHOT, STORYBOARD, ANIMATIC |
| Visuals | VISUAL, ASSET, CAMERA, DEPTH, MOTION, LIGHT, ATMOSPHERE, VFX |
| Audio | NARRATION, DIALOGUE, SOUND, MUSIC |
| Finishing | EDIT, COLOR, SUBTITLE, MASTER, QC, DELIVERY |

Scene and shot counts are derived from narrative content. The planner balances sentence units into multiple scenes, and the shot designer assigns framing, movement, lens, depth, and shot function instead of using one hard-coded template.

## 7. Visual Providers and Motion Rendering

Visual provider abstractions live under `aurelia/providers/`. The available paths are listed below.

| Provider | Role | Output behavior |
|---|---|---|
| Pollinations / cloud API | Preferred remote visual source when enabled | Real image files with `cloud-api/pollinations` provenance |
| Stable Diffusion | Optional local image source | Used when a compatible local model is installed |
| Pillow | Deterministic fallback | Synthetic title/scene art; explicitly marked as fallback |

After image generation, `CinematicVisualEngine` renders each shot as a real video stream. Near-static instructions receive a minimum measurable zoom travel, and the manifest records rendered-motion provenance. The final edit applies crossfades, dissolves, wipes, cuts, or fades according to shot and scene boundaries. Grain, vignette, bloom, lighting adjustments, and atmosphere are applied through the FFmpeg media path, not stored only as metadata.

## 8. Audio, Narration, Music, and Mixing

Narration uses the canonical provider-aware `EdgeTTSProvider`: Arabic selects `ar-SA-HamedNeural`, English selects the configured English Edge voice, and the resulting WAV is probed before the pipeline advances. In production mode, provider failure is preserved as a failure; espeak-ng is available only through an explicit degraded non-production path. Arabic and English are detected from the text, and dialogue-prefixed lines can be split into speaker segments.

Music is a structured 48 kHz stereo score with intro, build, climax, and resolution layers. Ambient synthesis provides deterministic environmental beds such as forest, mountain, desert, machine, ocean, city, space, and ancient profiles. Sound-design layers and narration are mixed with FFmpeg/pydub gain control and ducking so the final MP4 contains real narration, music, ambience, and effects streams in the final mix.

## 9. Subtitles and Language Support

Subtitles are generated from the actual narration/script timing and burned into the video with FFmpeg ASS rendering. Arabic RTL shaping is supported through `arabic-reshaper`, `python-bidi`, and installed fonts. QC checks subtitle presence, timing bounds, and word coverage against the source narration rather than accepting an empty or unrelated subtitle file.

## 10. Timing, Transitions, and Continuity

Narration-aware shot timing allocates each scene's available duration across semantic shot weights while respecting bounded minimum and maximum shot lengths. This keeps the video aligned with the real narration and avoids clone-padding a last frame.

Typed transition specifications in `aurelia/transitions.py` select scene-boundary dissolves and content-aware cuts, then the edit stage applies the transition to actual clips. `ContinuityContext` carries palette, environment, lighting, and character anchors into shot prompts. The separate `SeriesManager` persists series, season, episode, character, location, visual-language, and story-state records as JSON for sequel production.

## 11. Quality Control and Acceptance

`aurelia/qc_engine.py` and the real-video acceptance harness check the delivered MP4 itself. Fatal checks include file and stream integrity, H.264 video, AAC audio, 1080p resolution, 24 fps, complete decode, narration duration alignment, subtitle completeness, temporal variation, visual variation, and freeze segments longer than 0.5 seconds. Direct `ffprobe`, full decode, `freezedetect`, loudness, and representative-frame inspection remain part of release verification.

QC is not bypassed for short scripts. A successful acceptance report means the produced artifact satisfies the configured technical gate; it does not mean that still-image motion has become temporal generative video.

## 12. Local Production and CI Commands

Useful local checks are:

```bash
python3 -m py_compile aurelia/*.py aurelia/providers/*.py
pytest -q tests/
PYTHONPATH=. python3 scripts/planner_multi_scene_smoke.py
PYTHONPATH=. python3 scripts/repair_acceptance_smoke.py
PYTHONPATH=. python3 scripts/sound_design_smoke.py
```

The GitHub Actions workflow installs `requirements.txt`, Python 3.12, FFmpeg, espeak-ng for non-production utilities, and Arabic fonts, then runs the repository suite and canonical Chat-to-Factory acceptance path. Production acceptance requires a real visual provider and canonical Edge TTS; Pillow and local degraded audio are never accepted as production results.

## 13. Output Layout and Provenance

A factory job writes inspectable files beneath its job directory. The exact paths may be configured by the runner, but the canonical shape is:

```text
output/episode-XXXX/job-<uuid>/
  factory/stage_artifacts/
  visuals/                  # per-shot source images and visual manifest
  shots/                    # rendered cinematic shot clips
  audio/                    # narration, music, ambience, sound design, mix
  edit/ color/ master/
  subtitles/                # SRT/ASS artifacts
  production_manifest.json
  qc.json
  delivery/episode-XXXX-FINAL.mp4
```

Manifests record source hashes, backend provenance, asset hashes, shot direction, transition choices, and rendered-motion signals. Generated MP4s, run directories, secrets, and temporary evidence are intentionally excluded from source control.

## 14. Series Roadmap and Contribution Boundary

AURELIA is ready for iterative film and series development: add longer scripts, register recurring characters and locations with `SeriesManager`, preserve a visual language, and review each delivered episode. The current roadmap should prioritize temporal generative-video backends, stronger character identity conditioning, richer dialogue and lip-sync, professional Foley and voice options, and human editorial review.

Contributions should preserve the real-artifact rule: every claimed capability must affect the final pixels or audio, every backend fallback must be disclosed in provenance, and no test should replace a media gate with fabricated frames or weakened thresholds.

## License

See [LICENSE](LICENSE).
