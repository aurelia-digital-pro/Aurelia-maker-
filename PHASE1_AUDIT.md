# AURELIA Maker — Phase 1 Repository Truth Audit

**Repository:** `aurelia-digital-pro/Aurelia-maker-`  
**Branch:** `main`  
**Audit basis:** current checkout at commit `611d2e81efc26d4add02dd78cfa483b223de06fd`, with `origin/main` at the same SHA during this audit.

## Current repository state

The repository is on `main` and is synchronized with `origin/main` at the audit commit. The existing history contains the earlier measured audit and the cinematic factory implementation, followed by workflow and motion experiments. The current checkout contains the canonical `aurelia/` production implementation, the existing `aurelia-engine/` tree, the real-video acceptance scripts, provider abstractions, and the regression suite under `tests/`.

## Relevant implementation locations

| Concern | Actual path and symbol | Current behavior |
|---|---|---|
| Production workflow | `.github/workflows/production-e2e-test.yml`, job `production-test` | The job runs unit/smoke checks and a full Chat-to-FactoryRunner production test. At the audited commit it sets `AURELIA_FORCE_FALLBACK: "1"` at job scope. |
| Visual backend chain | `aurelia/visual_backend.py`, `generate_visual()` | The runtime probes Stable Diffusion, then calls the cloud API abstraction, then generates `pillow-fallback`. The audited implementation now skips the cloud branch when `AURELIA_FORCE_FALLBACK=1`; production mode enforcement is not yet present. |
| Cloud provider | `aurelia/visual_api.py`, `generate_via_api()` | Pollinations and configured cloud backends are attempted through an HTTP/image-decoding abstraction with status handling and provenance returned to `generate_visual()`. |
| Production orchestration | `aurelia/episode_engine.py`, `EpisodeProduction` | Plans scenes, creates per-shot visual assets, synthesizes narration, allocates shot durations, renders cinematic motion, applies transitions and finishing, mixes audio, builds subtitles, and invokes QC. |
| Factory boundary | `aurelia/factory_runner.py`, `FactoryRunner.run_episode_production()` / `execute()` | Creates a job, persists stage artifacts, runs the production stages, and fails the job when QC returns fatal checks. `handle_chat_production()` is the Chat entry path used by the CI E2E script. |
| Timing | `aurelia/shot_timer.py`, `allocate()`; `EpisodeProduction._apply_shot_timing()` | Allocates bounded shot durations from measured narration duration and shot semantic weights. The current media helper still contains a guarded retiming fallback for a short assembled timeline; production acceptance must reject that path when it represents global stretching. |
| Motion and VFX | `aurelia/visuals.py`, `CinematicVisualEngine.render_motion()` | Encodes FFmpeg zoom/pan/camera motion and visual filters. The current branch contains a temporal grain floor added during prior CI iteration; the new master prompt explicitly prohibits artificial grain/noise as a QC workaround, so this is a surgical repair target. |
| Media assembly | `aurelia/media.py`, `assemble_cinematic_clips()`, `mix_narration_and_music()`, `pad_video_to_duration()` | Assembles shots with transitions, mixes narration/music/sound/ambient layers, and avoids last-frame clone padding by retiming with a warning. |
| QC | `aurelia/qc_engine.py`, `run_qc()` | Performs stream/container checks, duration and narration checks, subtitle completeness, temporal/visual variation, full decode, and freeze detection. The visual variation fatal threshold is `0.005`; it must remain unchanged. |
| Fallback generation | `aurelia/ai_visual.py`, `generate_scene_image()`; `visual_backend.py`, `_generate_pillow()` | Provides deterministic development fallback imagery with scene/environment direction and provenance label `pillow-fallback`. It must remain available outside production mode. |
| Provenance | `visual_backend.generate_visual()` and `EpisodeProduction.generate_visual_assets()` | Records backend, fallback status, asset path/hash, prompt, seed, scene/shot indices, and render-motion metadata in visual manifests. Production proof must additionally prove zero fallback assets. |
| Existing tests | `tests/`, including provider, timing, continuity, visual signal, and transition tests | The local suite currently passes, but the new production-mode contract and real-provider requirement need explicit regression coverage. |

## Confirmed failure chain

The established CI failure is confirmed by the previous GitHub Actions logs and the current workflow configuration. The production-test job forces `AURELIA_FORCE_FALLBACK=1`, which leads to Pillow assets. The prior default Episode 0001 acceptance run generated 17 fallback images, measured approximately 29.792 seconds of visual material against approximately 107.482 seconds of narration, and entered a global timeline stretch. Final QC then measured `visual_variation = 0.0009`, below the unchanged fatal threshold `0.005`, and reported freeze intervals.

The repository-side cause is therefore not an absence of an MP4 or a missing unit test. It is that the job labelled production acceptance explicitly selects a development fallback and then lets a short visual timeline be reconciled to a much longer narration. The resulting output cannot prove a real visual provider or production provenance.

## Dependency relationships

```text
production-e2e-test.yml
  → Chat message
  → chat_entry.handle_chat_production()
  → FactoryRunner.execute()/run_episode_production()
  → EpisodeProduction.generate_visual_assets()
  → visual_backend.generate_visual()
  → SD or visual_api.generate_via_api() or Pillow fallback
  → EpisodeProduction.render_shots()
  → media.assemble_cinematic_clips()
  → audio mix / subtitles / master
  → qc_engine.run_qc()
  → delivery and proof artifact
```

`AURELIA_FORCE_FALLBACK` is currently used by local tests and, incorrectly for the new acceptance contract, by the CI production job. No single production boundary currently rejects the invalid combination of fallback mode and production mode because `AURELIA_PRODUCTION_MODE` is not yet enforced in the visual-generation boundary.

## Surgical repair required by the execution prompt

The correct repair is to preserve the existing architecture while changing the acceptance contract at the real production boundary:

1. Add one explicit production-mode contract that rejects `AURELIA_FORCE_FALLBACK=1` when `AURELIA_PRODUCTION_MODE=1`.
2. Make production acceptance set `AURELIA_PRODUCTION_MODE=1` and not force fallback.
3. Add a pre-generation real-provider availability check and fail fast with a clear error when no configured real provider can create and validate an image.
4. Keep Pillow available for unit, offline, and development paths, but prohibit it from being treated as a production result.
5. Preserve narration-driven bounded shot allocation and make global retiming a failure for production acceptance rather than a way to hide insufficient visual material.
6. Keep the `visual_variation >= 0.005` final gate and add an equivalent pre-master diagnostic gate without reducing the threshold.
7. Remove the prior artificial temporal grain/noise workaround and make fallback diversity come from meaningful scene/environment/shot composition and real provider assets in production.
8. Add tests for the production-mode contract, provider availability/provenance, Pillow non-production behavior, timing invariants, and static-video preflight.
9. Produce a real-provider acceptance run with fallback count zero, inspect the MP4 independently, and only then create `PRODUCTION_PROOF.md`.

This audit records the current state only. Production behavior changes belong to the subsequent repair phases.
