# AURELIA Maker Capabilities

## Current Production Capability

AURELIA Maker can accept Arabic or English Chat/script input and produce a real multi-scene, multi-shot MP4 through a canonical factory path. The output can include narration, music, ambience, sound design, mixing, subtitles, color treatment, transitions, camera motion, atmosphere, VFX, mastering, and machine-checked delivery artifacts.

The factory is a serious **cinematic previsualization and narrated-film foundation**. It is not a finished Netflix production platform and must not be marketed as one without additional temporal video generation, identity conditioning, dialogue, editorial, and production infrastructure.

## Visual Backend Reality

The preferred tested remote backend is Pollinations through the configured cloud visual API. It produces real per-shot image assets and records `cloud-api/pollinations` provenance. Stable Diffusion is supported as an optional local backend when compatible models and dependencies are installed. Pillow is a deterministic fallback and is marked as `pillow-fallback`; it is not silently presented as AI imagery.

The current motion path is image-to-video. FFmpeg renders measurable pan/zoom/camera motion and applies depth, lighting, atmosphere, VFX, transitions, and finishing. It is **not** temporal text-to-video and does not synthesize true subject motion between frames. Character identity consistency is prompt-guided and series-aware, but not guaranteed like a dedicated identity-conditioned video model.

## Audio Reality

The audio path creates real 48 kHz stereo WAV artifacts. Narration uses the local priority chain available in the environment, including Piper/Kokoro when installed, espeak-ng, and pyttsx3 fallback. Music is a structured procedural stereo score. Ambient synthesis creates deterministic environmental beds, and sound-design layers are mixed with narration and music using gain control and ducking.

Typical local speech quality is intelligible and functional for documentaries, prototypes, and animatics. It is not equivalent to a professional human voice actor, studio Foley session, or final theatrical mix. Arabic quality depends on the installed voice backend and font/audio environment.

## Timing and Output Length

Output duration follows the actual narration and bounded shot timing allocation. The factory does not clone a final frame or add arbitrary silence to satisfy a numeric target. A practical 60–300 second episode therefore needs a script of roughly that natural spoken length. Shorter scripts produce shorter truthful films while remaining subject to configured acceptance gates.

Remote Pollinations image generation can be slow because each shot is generated separately. Local Pillow is fast but visually limited; local Stable Diffusion performance depends on installed model weights and hardware. A multi-scene remote-backed episode may take many minutes to complete.

## Series Support

`SeriesManager` persists series, season, episode, act, character, location, visual-language, voice-profile, and story-state records as JSON. `ContinuityContext` carries palette, environment, lighting, and character anchors into visual prompts. The system can therefore preserve a recorded series bible and verify sequel metadata, but it does not guarantee perfect visual identity continuity across independently generated images.

## Quality and Release Gates

Fatal QC checks cover container and stream integrity, H.264/AAC encoding, 1080p/24 fps output, complete decode, narration alignment and audibility, subtitle word coverage, temporal and visual variation, and freeze segments longer than 0.5 seconds. Direct `ffprobe`, full decode, `freezedetect`, loudness measurement, and representative-frame review are used for release evidence.

A passed QC gate confirms technical and structural validity of the actual MP4. It is not a subjective claim that every result is cinematographically finished or suitable for broadcast without human review.

## Reproducible Validation

The repository declares its Python dependencies in `requirements.txt`, including pytest. The maintained checks are:

```bash
python3 -m py_compile aurelia/*.py aurelia/providers/*.py
pytest -q tests/
PYTHONPATH=. python3 scripts/planner_multi_scene_smoke.py
PYTHONPATH=. python3 scripts/repair_acceptance_smoke.py
PYTHONPATH=. python3 scripts/sound_design_smoke.py
```

CI repeats the regression and media smoke checks. Real remote visual acceptance is environment-dependent and should be identified by its backend provenance and linked QC evidence.
