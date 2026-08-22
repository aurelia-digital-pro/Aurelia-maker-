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
