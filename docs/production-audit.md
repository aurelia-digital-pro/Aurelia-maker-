# AURELIA Maker Production Audit

**Audit basis.** This audit reflects the checked-out repository at `/home/ubuntu/Aurelia-maker-`, branch `main`, and the executed acceptance run for Episode `0013`. It distinguishes code paths and files that were observed from claims that would require additional verification.

## Repository and execution identity

The repository remote is `https://github.com/aurelia-digital-pro/Aurelia-maker-.git`. The current branch is `main`. At audit start, the working tree contained uncommitted implementation changes and temporary verification files from the previous repair session. The latest checked-out remote commit is `5ba05350e91083df89e9edea264d8c5310a86bd5`. Temporary generated media is kept outside the repository and is not part of the implementation commit.

The primary user-facing entry point is `python -m aurelia.generate`. Both the `chat` and `produce` commands route through `handle_chat_production` and `FactoryRunner`; the repository acceptance command is:

```bash
PYTHONPATH=. python3 scripts/real_video_acceptance.py \
  --episode 0013 \
  --script scripts/episode-0013.txt \
  --output /tmp/aurelia-acceptance-fixed
```

## Verified canonical path

```text
Chat → FactoryRunner → production stages → EpisodeProduction
     → visual backend → shot renderer → edit/audio → color
     → subtitles → master → QC → delivery → FINAL MP4
```

`FactoryRunner.run_episode_production()` is the active chat/factory execution path. It instantiates `EpisodeProduction`, executes the ordered stage list, and blocks delivery when master validation or visual-manifest validation fails.

## Stage and artifact map

| Stage group | Responsible code | Current artifact | Downstream use | Audit status |
| --- | --- | --- | --- | --- |
| SCRIPT through PRE_PRODUCTION | `factory_runner.py`, `planner.py`, `scene_analyzer.py`, `shot_designer.py` | `factory/stage_artifacts/001_SCRIPT.json` through `008_PRE_PRODUCTION.json` | Each JSON result is passed to the next stage | Real planning logic with persisted stage evidence |
| VISUAL / ASSET | `episode_engine.py`, `visual_backend.py` | `visuals/scene_*_shot_*.png`, `visuals/visual_manifest.json` | Consumed by `render_shots()` | Real and verified |
| CAMERA / DEPTH / MOTION | `directing_engine.py`, `shot_designer.py`, `visuals.py` | `016_CAMERA.json`, `017_DEPTH.json`, `018_MOTION.json` plus shot MP4s | `render_shots()` consumes the plans and calls `render_motion()` | Real consumer path with persisted stage evidence |
| LIGHT / ATMOSPHERE / VFX | `factory_runner.py`, `episode_engine.py`, `visuals.py` | `019_LIGHT.json`, `020_ATMOSPHERE.json`, `021_VFX.json` plus shot MP4s | `render_motion()` applies lighting, blur, vignette, grain, and bloom in FFmpeg | Real pixel path with persisted stage evidence |
| NARRATION | `tts.py`, `episode_engine.py` | `audio/narration.wav` | Mixed into edit | Real and verified |
| MUSIC | `media.py`, `factory_runner.py` | `audio/ambient_music.wav` | Mixed into edit | Real and verified; procedural fallback is documented |
| DIALOGUE / SOUND / AUDIO | `factory_runner.py` | `023_DIALOGUE.json`, `024_SOUND.json`, `030_QC.json` | Stage state is persisted, but no independent foley/sound-design WAV is produced | Partial: metadata artifacts are real, sound design remains limited |
| EDIT | `episode_engine.py`, `media.py` | `edit/video_concat.mp4`, `edit/video_padded.mp4`, `edit/edit_mixed.mp4` | Color stage consumes mixed edit | Real artifact path; transitions are now rendered by the cinematic assembler |
| COLOR | `media.py` | `master/graded.mp4` | Subtitle stage consumes graded video | Real and verified |
| SUBTITLE | `media.py`, `episode_engine.py` | `episode-0013.srt`, `master/subtitled.mp4` | Master consumes subtitled video | Real and verified |
| MASTER | `media.py`, `factory_runner.py` | `delivery/episode-0013-youtube.mp4` and TikTok output when requested | QC and Delivery consume master | Real and verified |
| QC | `qc_engine.py`, `media.py` | QC result in execution/acceptance output | Blocks delivery on fatal failures | Real quality gate and verified |
| DELIVERY | `delivery.py`, `factory_runner.py` | `delivery/episode-0013-FINAL.mp4` and manifest | Final consumer/output | Real and verified |

## Evidence from the last end-to-end run

The repaired acceptance run used the chat/factory path and completed through `DELIVERY`. It produced exactly 31 JSON stage artifacts under `factory/stage_artifacts/`, one for every declared factory stage. The visual manifest recorded `cloud-api/pollinations` as the backend, with `total_fallbacks: 0` and `motion_renderer: CinematicVisualEngine`. The run produced narration, music, subtitles, graded video, subtitled video, master video, and the final delivery artifact. `scripts/repair_acceptance_smoke.py` and `scripts/cinematic_intelligence_check.py --script scripts/episode-0013.txt` both passed after repair.

The verified final artifact was:

```text
/tmp/factory/output/episode-0013/job-c129ad03e67344deb787605972f21b86/delivery/episode-0013-FINAL.mp4
```

`ffprobe` reported an H.264 video stream at `1920x1080` and `24 fps`, an AAC audio stream, MP4-compatible container metadata, duration `44.675` seconds, and size `7,460,078` bytes. The acceptance harness reported successful master checks, visual-manifest checks, and canonical-path verification.

## Confirmed gaps and limitations

The runner emits named stages for CAMERA, DEPTH, MOTION, LIGHT, ATMOSPHERE, VFX, DIALOGUE, SOUND, and AUDIO, but several of these stages currently return metadata or boolean flags rather than writing a separately verifiable artifact. The main cinematography parameters are nevertheless consumed later by `render_shots()`. The repair priority is therefore to persist stage artifacts and make the renderer consume the canonical persisted cinematography data, rather than creating a second factory or renderer.

The current cloud visual backend is available in the tested environment. Local Stable Diffusion is not installed (`torch`/`diffusers` unavailable), so the real cloud backend is the effective visual source in that environment. Pillow remains a last-resort visual fallback and must not be treated as equivalent to the cloud backend.

The current audio implementation produces narration and a procedural ambient music bed, with ducking applied during the narration/music mix. A separate foley/sound-design WAV is not currently produced; this is a documented limitation and is not described as completed.

## Completed repair and verification record

The implementation now persists all 31 factory stage results as JSON artifacts under `factory/stage_artifacts/`, records the directory and count in `production_manifest.json`, and passes the resulting state through the existing orchestrator. The camera, depth, motion, lighting, atmosphere, and VFX data are consumed by the existing shot renderer; the renderer applies the supported pixel operations in FFmpeg. The audio path preserves the existing TTS implementation and mixes narration with the generated ambient music bed using ducking. Fatal QC and visual-manifest checks remain active.

Verification executed after repair:

```bash
python3 -m py_compile aurelia/factory_runner.py aurelia/media.py aurelia/visuals.py aurelia/episode_engine.py scripts/repair_acceptance_smoke.py scripts/cinematic_intelligence_check.py
PYTHONPATH=. python3 scripts/repair_acceptance_smoke.py
PYTHONPATH=. python3 scripts/cinematic_intelligence_check.py --script scripts/episode-0013.txt
PYTHONPATH=. python3 scripts/real_video_acceptance.py --episode 0013 --script scripts/episode-0013.txt --output /tmp/aurelia-acceptance-audit
ffprobe -v error -show_entries format=filename,format_name,duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate -of json <FINAL_MP4>
```

The smoke test passed with two rendered shots, distinct motion intents, and a real `dissolve` transition through `assemble_cinematic_clips()`. The cinematic-intelligence regression test also passed. The end-to-end run completed all 31 stages and produced a valid final MP4. The remaining documented limitation is the absence of an independent foley/sound-design WAV artifact; the repository does not claim that capability as complete.


## Visual inspection notes

Representative frames extracted from the final MP4 at approximately 4.5 seconds and 40.2 seconds both contained non-black, non-solid cinematic imagery with visible subject detail, controlled dark edges, warm/cool contrast, and readable subtitle burn-in. The two frames show different AI-generated compositions over time. This confirms actual pixel output and subtitle inclusion, but a still-frame inspection cannot prove motion quality by itself; the end-to-end renderer smoke test and encoded shot path provide the reproducible motion evidence.


## Arabic final-frame inspection

The Arabic Episode 0001 run produced five representative frames across the duration. Early and late frames inspected from the encoded delivery showed real AI-generated subject imagery, visible dark-edge treatment and warm/cool grading, materially different compositions between scenes, and readable Arabic subtitle burn-in. The inspection confirms non-empty rendered pixels and subtitle inclusion; it does not replace motion metrics or full decode checks.


## Sound design and strengthened QC repair

The active FACTORY SOUND stage now creates `audio/sound_design.wav` with deterministic scene-boundary riser/noise cues using the Python standard library WAV writer. The active EDIT stage consumes this artifact alongside narration and music through FFmpeg `amix`; the production manifest records its path. The Episode 0001 verification produced a 48 kHz stereo PCM sound-design artifact of 107.48 seconds and a final AAC mix.

QC now adds hard full-stream FFmpeg decode validation, encoded-frame temporal variation sampling, audio/video duration relationship reporting, and required-artifact existence checks. Episode 0001 completed with `qc_passed=true`, zero fatal failures, zero warnings, and a 31-file stage-artifact directory. The acceptance harness still reports its legacy summary checks separately; the canonical Factory QC is the stronger gate.


## Next-stage transition improvement

The scene-boundary transition policy now combines the SceneAnalyzer transition hint with narrative beat, scene purpose, emotional register, and environment change. Hard cuts remain the default within scenes; at a semantic boundary, a climax with a world/environment change selects a motivated light transition, while resolution/conclusion and calm/wonder boundaries can select fade or dissolve. The canonical Arabic run for job `973e5b0ad1c14fe695a4efcc201d8784` reported `Applied 1 cinematic transitions across 6 shots`, proving that a non-cut transition reached the actual assembler rather than remaining only in metadata.

The resulting FINAL MP4 was accepted with duration `107.508s`, size `20,875,289` bytes, H.264 video at 1920x1080/24fps, AAC audio, and zero QC fatals or warnings. Representative beginning and ending frames were inspected: both contained non-blank generated imagery with changed framing/lighting and burned Arabic subtitles. The limitation remains that local Stable Diffusion is unavailable; Cloud/Pollinations supplied all six visual assets with zero Pillow fallbacks.


## Stereo final-mix correction

A direct ffprobe of the transition-enabled run exposed that the encoded AAC output was mono even though the authored sound-design source was stereo/48 kHz. The active mixer was corrected to apply `aformat=sample_rates=48000:channel_layouts=stereo` after `amix`, and the canonical Arabic E2E was rerun.

The corrected run is job `3367160fb27a4c7fac20771d444b08e0`. It applied one motivated cinematic transition across six shots, produced a valid accepted FINAL MP4, and passed all fatal and warning QC checks. Direct ffprobe now reports H.264 video at 1920x1080/24 fps and AAC audio at 48 kHz with two channels, with duration `107.520s` and size `21,520,905` bytes. The authored sound-design WAV is PCM stereo/48 kHz with duration `107.481813s` and is consumed by the active mixer.


## Visual-signal QC correction

The canonical run after the stereo-mix change exposed a false negative in `assets_have_visual_signal`: a valid low-chroma portrait had RGB channel-range `2.91` but luminance structure with mean standard deviation `46.22`. The QC gate was corrected without weakening blank-image protection: chromatic variation still passes through `channel_range`, while low-chroma or monochrome images must show meaningful luminance structure (`mean_stddev >= 6.0`). A flat or blank asset still fails both measurements.

The corrected canonical Arabic run is job `d5c70f76eb334789ae0b47b1390b3ddb`. It generated six Cloud/Pollinations assets with zero Pillow fallbacks, applied one motivated cinematic transition across six shots, produced an accepted FINAL MP4, and passed the strengthened QC gate with zero fatals and zero warnings. Direct ffprobe reports 1920x1080 H.264 video at 24 fps and AAC audio at 48 kHz stereo, duration `107.520s`, size `21,690,337` bytes. Representative early and late frames were inspected and showed non-blank rendered imagery, different framing/lighting, and Arabic subtitle burn-in.


## Subtitle completeness and latest visual verification

The subtitle producer now preserves full scene narration text by splitting long Arabic text into readable timed cues instead of truncating at 160 characters. The subtitle burn-in path now fails closed if FFmpeg cannot render subtitles, refusing to deliver an unsubtitled copy. Canonical QC now has a fatal `subtitle_completeness` check that parses cues and requires valid positive-duration cues covering the beginning through the end of the final video.

The latest canonical Arabic run is job `1394e028fa6f4277bcd3bd9da4b5aa83`, with `accepted: true`, `canonical_path_verified: true`, `legacy_produce_episode_used: false`, and empty fatal/warning lists. It applied one cinematic transition across six shots. The final MP4 is 107.520 seconds at 1920x1080; ffprobe reports H.264 video and AAC stereo audio at 48 kHz. The new `subtitle_completeness` check passed. Early and late decoded frames were inspected: both contained non-blank generated imagery, changed composition/lighting, and visible Arabic subtitle burn-in.
