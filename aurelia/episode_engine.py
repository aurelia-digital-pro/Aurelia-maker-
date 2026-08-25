"""AURELIA — canonical episode production engine (Factory → FINAL MP4).

Architecture:
- PRIMARY visual chain: SD (local) → Cloud API (Pollinations FLUX free) → Pillow
- Checkpoint/resume: VisualCheckpoint saves each completed shot to disk.
  Interrupted productions resume from last successful shot, not from zero.
- Shot-level visuals: one image per ShotSpec (2–5 per scene)
- Content-driven zoom/motion/transition from ShotDesigner
- SceneAnalyzer enriches planner output with beat/emotion/action context
- ProductionLogger records structured trace if injected via log= callable
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .ambient_synth import synthesize_ambient
from .continuity import ContinuityContext
from .directing_engine import DirectingEngine
from .media import (
    apply_color_grade,
    burn_subtitles,
    concat_clips,
    generate_ambient_music,
    generate_sound_design,
    master_encode,
    mix_narration_and_music,
    pad_video_to_duration,
    assemble_cinematic_clips,
    probe_duration,
    validate_master,
    validate_visual_manifest,
)
from .planner import plan_scenes
from .music_engine import generate_cinematic_music
from .providers.audio import EdgeTTSProvider
from .providers.ambient import SynthAmbientProvider
from .providers.music import CinematicMusicProvider
from .scene_analyzer import SceneAnalyzer
from .shot_designer import ShotDesigner, ShotSpec
from .shot_timer import allocate as allocate_shot_durations
from .transitions import select_transition
from .tts import synthesize_script
from .visual_backend import (
    assert_production_visual_provider,
    generate_visual,
)  # PRIMARY: SD → Cloud API → Pillow
from .visual_checkpoint import VisualCheckpoint

LogFn = Callable[[str], None]

_SCENE_DURATION_DEFAULT = 18.0
_SCENE_DURATION_MIN = 6.0
_MAX_DURATION_UNLIMITED = 3600.0

_HIGH_SAT_ENVS = {"space", "ocean", "fantasy", "fire", "dream", "machine"}
_LOW_SAT_ENVS  = {"ancient", "battle", "industry"}


@dataclass
class ScenePlan:
    index: int
    title: str
    text: str
    duration: float = _SCENE_DURATION_DEFAULT
    movement: str = "push_in"
    direction: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    shots: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EpisodeProduction:
    episode_id: str
    root: Path
    script_path: Path
    profile: str = "youtube"
    language: str = "auto"
    max_duration: float = _MAX_DURATION_UNLIMITED
    title: str = ""
    scenes: list[ScenePlan] = field(default_factory=list)
    log: LogFn = field(default=lambda _msg: None)

    def __post_init__(self) -> None:
        self.episode_id = (
            self.episode_id.zfill(4) if self.episode_id.isdigit() else self.episode_id
        )
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.dirs = {
            name: self.root / name
            for name in ("visuals", "depth", "shots", "audio", "edit", "master", "delivery", "factory")
        }
        for path in self.dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        self.director = DirectingEngine()
        self._analyzer = SceneAnalyzer()
        self._shot_designer = ShotDesigner()
        self._run_id = uuid.uuid4().hex[:16]
        if not self.title:
            self.title = self._extract_title(self.script_path.read_text(encoding="utf-8"))
        self.visual_manifest_path = self.dirs["visuals"] / "visual_manifest.json"
        # Total visual assets generated (shots, not scenes)
        self._total_visual_assets: int = 0
        # Provider-aware narration evidence propagated into the final manifest.
        self.audio_provenance: dict[str, Any] = {}
        self.music_provenance: dict[str, Any] = {}
        self.ambient_provenance: dict[str, Any] = {}
        self.cinematic_treatments: list[dict[str, Any]] = []

    @staticmethod
    def _extract_title(request_text: str) -> str:
        for line in request_text.splitlines():
            m = re.match(
                r'^\s*(?:title|\u0627\u0644\u0639\u0646\u0648\u0627\u0646|\u0639\u0646\u0648\u0627\u0646)\s*[:=]\s*(.+?)\s*$',
                line, re.IGNORECASE,
            )
            if m:
                return m.group(1).strip()
        heading = next(
            (m.group(1).strip()
             for m in re.finditer(r'^\s*#+\s+(.+?)\s*$', request_text, re.MULTILINE)),
            "",
        )
        if heading:
            return heading
        for line in request_text.splitlines():
            stripped = line.strip()
            if stripped and len(stripped) > 3:
                return stripped[:80]
        raise ValueError("Production request contains no real title")

    @staticmethod
    def _extract_script_body(request_text: str) -> str:
        lines = []
        for line in request_text.splitlines():
            if re.match(
                r'^\s*(?:title|\u0627\u0644\u0639\u0646\u0648\u0627\u0646|\u0639\u0646\u0648\u0627\u0646|language|lang|\u0627\u0644\u0644\u063a\u0629|\u0644\u063a\u0629)\s*[:=]\s*.+?\s*$',
                line, re.IGNORECASE,
            ):
                continue
            lines.append(line)
        body = "\n".join(lines).strip()
        if not body:
            raise ValueError("Production request contains no episode script content")
        return body

    @staticmethod
    def _detect_language(text: str) -> str:
        ar_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        return "ar" if ar_chars > len(text) * 0.15 else "en"

    def _emit(self, message: str) -> None:
        self.log(message)

    def load_script(self) -> str:
        request_text = self.script_path.read_text(encoding="utf-8").strip()
        if not request_text:
            raise ValueError(f"Empty script: {self.script_path}")
        body = self._extract_script_body(request_text)
        if self.language == "auto":
            self.language = self._detect_language(request_text)
            self._emit(f"Language auto-detected: {self.language}")
        return body

    def build_scene_plan(self, script_text: str) -> list[ScenePlan]:
        """PRIMARY: planner segments → SceneAnalyzer enriches → ShotDesigner assigns shots."""
        word_count = len(script_text.split())
        # Scale the scene ceiling with narrative length; approximately one
        # scene per 25 words keeps long films paced without hardcoding counts.
        dynamic_max = max(5 if word_count >= 80 else 3, min(60, (word_count + 19) // 20))
        raw = plan_scenes(script_text, min_scenes=3, max_scenes=dynamic_max)
        analyses = self._analyzer.analyze_sequence(raw)
        scenes: list[ScenePlan] = []
        for index, (raw_scene, analysis) in enumerate(zip(raw, analyses)):
            scene_id = f"episode-{self.episode_id}:scene-{index + 1:03d}"
            scene_words = len(raw_scene["text"].split())
            estimated_duration = max(_SCENE_DURATION_MIN, scene_words / 3.0)
            direction = self.director.direct(
                scene_id=scene_id, title=raw_scene["title"],
                text=raw_scene["text"], duration=estimated_duration,
                scene_index=index, scene_analysis=analysis.to_dict(),
            )
            shot_specs = self._shot_designer.design(analysis, estimated_duration)
            shot_summary = ", ".join(
                f"{s.framing}+{s.motion_intent}" for s in shot_specs
            )
            self._emit(
                f"  Scene {index+1} [{analysis.narrative_beat}/{analysis.emotional_register}]: "
                f"{len(shot_specs)} shots — {shot_summary}"
            )
            scenes.append(ScenePlan(
                index=index,
                title=raw_scene["title"],
                text=raw_scene["text"],
                duration=estimated_duration,
                movement=direction["camera"]["movement"],
                direction=direction,
                analysis=analysis.to_dict(),
                shots=[s.to_dict() for s in shot_specs],
            ))
        if not scenes:
            raise ValueError("No scenes could be planned from the supplied script")
        total = sum(s.duration for s in scenes) + 8.0
        if total > self.max_duration:
            scale = (self.max_duration - 8.0) / max(sum(s.duration for s in scenes), 1.0)
            for scene in scenes:
                scene.duration = max(_SCENE_DURATION_MIN, round(scene.duration * scale, 1))
                scene.direction["motion"]["duration"] = scene.duration
        self.scenes = scenes
        total_planned = sum(s.duration for s in scenes)
        total_shots = sum(len(s.shots) for s in scenes)
        self._emit(
            f"Scene plan: {len(scenes)} scenes, {total_shots} total shots, "
            f"estimated {total_planned:.0f}s ({total_planned / 60:.1f} min)"
        )
        return scenes

    def generate_visual_assets(self) -> dict[str, list[Path]]:
        """Generate one image per SHOT.

        Chain: SD (local) → Cloud API (Pollinations FLUX free) → Pillow.
        Checkpoint/resume: already-generated shots are loaded from disk,
        not regenerated. Safe to restart interrupted long-episode productions.
        """
        provider = assert_production_visual_provider(logger=self._emit)
        if provider != "development":
            self._emit(f"[PRODUCTION] Real visual provider preflight passed: {provider}")
        self._emit("Generating visual assets — SD → Cloud API → Pillow per shot...")
        scene_assets: dict[str, list[Path]] = {}
        manifest_scenes: list[dict[str, Any]] = []
        total_fallbacks = 0
        total_images = 0
        total_resumed = 0
        continuity_anchors: dict[str, str] = {}

        # One checkpoint file per production root — persists across restarts
        checkpoint = VisualCheckpoint(
            self.dirs["visuals"] / "generation_checkpoint.json"
        )
        if checkpoint.completed_count() > 0:
            self._emit(
                f"  [RESUME] Checkpoint: {checkpoint.completed_count()} shots already done"
            )

        for scene in self.scenes:
            env = scene.direction.get("environment", "abstract")
            analysis_data = scene.analysis or {}
            lighting_key = str(((scene.direction.get("lighting") or {}).get("key") or {}).get("color", "neutral"))
            palette = list(scene.direction.get("visual_palette") or [str(env), lighting_key, "cinematic shadow"])
            subject = str(analysis_data.get("primary_subject", "")).strip()
            continuity_tags = set(analysis_data.get("continuity_tags", []) or [])
            if subject and (env == "human" or "character_continuity" in continuity_tags):
                continuity_anchors.setdefault(
                    subject,
                    f"recurring subject associated with {env} environment",
                )
            context = ContinuityContext(
                palette=palette,
                environment_description=str(scene.direction.get("environment_description") or f"{env} cinematic environment"),
                lighting_key=lighting_key,
                character_anchors=continuity_anchors,
            )
            scene.direction["visual_palette"] = palette
            scene.direction["continuity"] = context.to_dict()
            self._emit(f"  Scene {scene.index + 1} [{env}]: {scene.title[:50]}")
            shot_paths: list[Path] = []
            shots = scene.shots or []

            if not shots:
                shot_idx = 0
                path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}_shot_00.png"
                if checkpoint.is_done(scene.index, shot_idx, path):
                    prov = checkpoint.get_provenance(scene.index, shot_idx)
                    self._emit(
                        f"  [RESUME] Scene {scene.index+1} shot 0: "
                        f"cached ({prov.get('backend', '?')})"
                    )
                    total_resumed += 1
                else:
                    prov = generate_visual(
                        scene.index, scene.title, scene.text, path,
                        direction=scene.direction, width=512, height=512,
                        visual_note="", run_id=self._run_id, logger=self._emit,
                    )
                    checkpoint.mark_done(
                        scene.index, shot_idx, path, prov.get("backend", ""), prov
                    )
                    if prov["fallback"]:
                        total_fallbacks += 1
                        self._emit(
                            f"  [VISUAL][FALLBACK] Scene {scene.index+1} shot 0: "
                            f"{prov['fallback_reason']}"
                        )
                shot_paths.append(path)
                manifest_scenes.append(self._manifest_record(scene, shot_idx, path, prov))
                total_images += 1
            else:
                for shot in shots:
                    shot_idx = shot["shot_index"]
                    path = self.dirs["visuals"] / (
                        f"scene_{scene.index + 1:02d}_shot_{shot_idx:02d}.png"
                    )
                    analysis_data = scene.analysis or {}
                    visual_note = " ".join(filter(None, [
                        shot.get("description", ""),
                        f"subject {analysis_data.get('primary_subject', '')}",
                        f"objective {analysis_data.get('visual_objective', '')}",
                        f"purpose {shot.get('narrative_purpose', analysis_data.get('scene_purpose', ''))}",
                        shot.get("framing", ""),
                        shot.get("motion_intent", ""),
                    ]))
                    # Preserve scene continuity while making shot grammar real:
                    # the visual backend receives structured per-shot camera,
                    # lens, motion, and depth values instead of only a trailing
                    # note that could be ignored by the image model.
                    shot_direction = deepcopy(scene.direction)
                    shot_camera = shot_direction.setdefault("camera", {})
                    shot_motion = shot_direction.setdefault("motion", {})
                    shot_depth = shot_direction.setdefault("depth", {})
                    framing = str(shot.get("framing", "cinematic"))
                    lens_by_framing = {
                        "extreme_wide": 18.0,
                        "wide": 24.0,
                        "medium": 50.0,
                        "over_shoulder": 50.0,
                        "close_up": 85.0,
                        "extreme_close_up": 100.0,
                    }
                    shot_camera["framing"] = framing
                    shot_camera["lens_mm"] = lens_by_framing.get(framing, shot_camera.get("lens_mm", 35.0))
                    shot_camera["movement"] = shot.get("motion_intent", shot_camera.get("movement", "static"))
                    shot_motion["type"] = shot.get("motion_intent", shot_motion.get("type", "static"))
                    shot_motion["magnitude"] = shot.get("motion_magnitude", shot_motion.get("magnitude", 0.0))
                    shot_depth["depth_of_field"] = shot.get("depth_of_field", shot_depth.get("depth_of_field", 0.0))
                    shot_direction["shot_function"] = shot.get("shot_function", "coverage")
                    shot_direction["cinematic_treatment"] = shot.get("cinematic_treatment", "depth_push")
                    shot_direction["focus_behavior"] = shot.get("focus_behavior", "deep_focus")
                    shot_direction["atmosphere_mode"] = shot.get("atmosphere_mode", "none")
                    shot_direction["shot_visual_note"] = visual_note
                    shot_direction["subject_detail"] = str(analysis_data.get("primary_subject", ""))
                    shot_direction["continuity"] = context.to_dict()

                    if checkpoint.is_done(scene.index, shot_idx, path):
                        prov = checkpoint.get_provenance(scene.index, shot_idx)
                        self._emit(
                            f"  [RESUME] Scene {scene.index+1} shot {shot_idx}: "
                            f"cached ({prov.get('backend', '?')})"
                        )
                        total_resumed += 1
                    else:
                        prov = generate_visual(
                            scene.index, scene.title, scene.text, path,
                            direction=shot_direction, width=512, height=512,
                            visual_note=visual_note, run_id=self._run_id,
                            logger=self._emit,
                        )
                        checkpoint.mark_done(
                            scene.index, shot_idx, path, prov.get("backend", ""), prov
                        )
                        if prov["fallback"]:
                            total_fallbacks += 1
                            self._emit(
                                f"  [VISUAL][FALLBACK] Scene {scene.index+1} "
                                f"shot {shot_idx}: {prov['fallback_reason']}"
                            )

                    shot_paths.append(path)
                    manifest_scenes.append(
                        self._manifest_record(scene, shot_idx, path, prov)
                    )
                    total_images += 1

            scene_assets[str(scene.index)] = shot_paths

        self._total_visual_assets = total_images
        self._emit(
            f"Visual assets: {total_images} images"
            f" ({total_resumed} resumed, {total_fallbacks} Pillow fallbacks,"
            f" {total_images - total_resumed - total_fallbacks} new via SD/API)"
        )

        # Derive the top-level backend label from what actually ran, instead of
        # hardcoding "local-ai" — per-scene provenance already records the real
        # backend (e.g. "stable-diffusion", "cloud-api/pollinations",
        # "pillow-fallback") and must not be overwritten with a false claim.
        backends_used = sorted({
            str(record.get("backend", "unknown")) for record in manifest_scenes
        }) or ["unknown"]
        manifest: dict[str, Any] = {
            "backend": backends_used[0] if len(backends_used) == 1 else "mixed",
            "backends_used": backends_used,
            "source":   "chat",
            "run_id":   self._run_id,
            "total_images":    total_images,
            "total_fallbacks": total_fallbacks,
            "total_resumed":   total_resumed,
            "fallback_rate":   round(total_fallbacks / max(total_images, 1), 3),
            "visual_processing": {"motion_renderer": "CinematicVisualEngine"},
            "scenes": manifest_scenes,
        }
        self.visual_manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._emit(f"Visual manifest: {self.visual_manifest_path}")
        return scene_assets

    @staticmethod
    def _manifest_record(
        scene: ScenePlan, shot_idx: int, path: Path, prov: dict[str, Any]
    ) -> dict[str, Any]:
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "scene_index": scene.index,
            "shot_index":  shot_idx,
            "title":       scene.title,
            "asset":       str(path.resolve()),
            "asset_sha256": sha,
            "text_sha256":  hashlib.sha256(scene.text.encode()).hexdigest(),
            "backend":      prov.get("backend", "unknown"),
            "fallback":     prov.get("fallback", False),
            "fallback_reason": prov.get("fallback_reason", ""),
            "prompt":       prov.get("prompt", ""),
            "seed":         prov.get("seed", 0),
            "elapsed_s":    prov.get("elapsed_s", 0.0),
        }

    def synthesize_narration(self, script_text: str) -> Path:
        """Synthesize narration. TTS auto-detects language from text content."""
        self._emit(f"Synthesizing narration (TTS, language={self.language})...")
        narration_path = self.dirs["audio"] / "narration.wav"
        provider = EdgeTTSProvider()
        provider.generate(script_text, narration_path, language=self.language)
        if not narration_path.exists() or narration_path.stat().st_size < 100:
            raise RuntimeError("Narration synthesis failed — TTS produced no output")
        duration = probe_duration(narration_path)
        self.audio_provenance = dict(provider.provenance)
        if not self.audio_provenance or self.audio_provenance.get("fallback"):
            raise RuntimeError("Production narration must expose a non-degraded provider provenance")
        self._emit(
            f"Narration: {duration:.1f}s | provider={self.audio_provenance.get('provider')} "
            f"voice={self.audio_provenance.get('voice')} | language={self.language}"
        )
        return narration_path

    def build_subtitles(self, narration_path: Path) -> Path:
        self._emit("Building subtitle track...")
        total_duration = probe_duration(narration_path)
        if total_duration <= 0:
            total_duration = sum(scene.duration for scene in self.scenes) + 8.0
        per_scene = total_duration / max(len(self.scenes), 1)

        def fmt(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds - int(seconds)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines: list[str] = []
        cue_index = 1
        cursor = 0.0
        for scene in self.scenes:
            end = cursor + per_scene
            full_text = re.sub(r"\s+", " ", scene.text.strip())
            if not full_text:
                cursor = end
                continue

            # Preserve every narrated word. Long scene text is split into
            # readable timed cues instead of being truncated with an ellipsis.
            words = full_text.split()
            chunks: list[str] = []
            current: list[str] = []
            # Keep cues readable on a 16:9 frame. The burn-in style also has
            # explicit safe-area margins, so this bound prevents long Arabic
            # cues from becoming a four-line block over the subject.
            for word in words:
                candidate = " ".join([*current, word])
                if current and len(candidate) > 76:
                    chunks.append(" ".join(current))
                    current = [word]
                else:
                    current.append(word)
            if current:
                chunks.append(" ".join(current))

            def wrap_display_text(chunk: str, max_chars: int = 42) -> str:
                display_lines: list[str] = []
                line_words: list[str] = []
                for word in chunk.split():
                    candidate = " ".join([*line_words, word])
                    if line_words and len(candidate) > max_chars:
                        display_lines.append(" ".join(line_words))
                        line_words = [word]
                    else:
                        line_words.append(word)
                if line_words:
                    display_lines.append(" ".join(line_words))
                return "\n".join(display_lines[:2])

            total_chars = max(sum(len(chunk) for chunk in chunks), 1)
            cue_cursor = cursor
            for chunk_index, chunk in enumerate(chunks):
                if chunk_index == len(chunks) - 1:
                    cue_end = end
                else:
                    cue_end = cue_cursor + per_scene * len(chunk) / total_chars
                lines.extend([
                    str(cue_index),
                    f"{fmt(cue_cursor)} --> {fmt(cue_end)}",
                    wrap_display_text(chunk),
                    "",
                ])
                cue_index += 1
                cue_cursor = cue_end
            cursor = end

        srt_path = self.root / f"episode-{self.episode_id}.srt"
        srt_path.write_text("\n".join(lines), encoding="utf-8")
        return srt_path

    def _apply_shot_timing(self, narration_duration: float) -> None:
        """Allocate the real narration length across every planned shot."""
        flattened: list[dict[str, Any]] = [shot for scene in self.scenes for shot in scene.shots]
        if not flattened:
            return
        durations = allocate_shot_durations(flattened, narration_duration)
        cursor = 0
        for scene in self.scenes:
            scene_total = 0.0
            for shot in scene.shots:
                shot["duration"] = durations[cursor]
                scene_total += durations[cursor]
                cursor += 1
            if scene.shots:
                scene.duration = scene_total
        self._emit(
            f"Shot timing allocated across {len(flattened)} shots: "
            f"{sum(durations):.2f}s narration coverage"
        )

    def render_shots(
        self, scene_assets: dict[str, list[Path]]
    ) -> list[Path]:
        """Render one clip per shot image with content-driven cinematic motion."""
        from .visuals import CinematicVisualEngine
        self._emit("Rendering cinematic shots (content-driven motion per shot)...")
        engine = CinematicVisualEngine()
        all_clips: list[Path] = []
        boundary_transitions: list[str] = []
        rendered_treatments: list[dict[str, Any]] = []

        for scene in self.scenes:
            direction     = scene.direction
            lighting_plan = direction.get("lighting", {})
            environment   = direction.get("environment", "abstract")

            analysis_data = scene.analysis or {}
            emotion = str(analysis_data.get("emotional_register", "neutral"))
            if environment in _HIGH_SAT_ENVS:
                saturation = 1.10
            elif environment in _LOW_SAT_ENVS:
                saturation = 0.98
            else:
                saturation = 1.03
            saturation += {
                "joyful": 0.10,
                "awe": 0.07,
                "wonder": 0.05,
                "tense": 0.02,
                "dread": -0.10,
                "melancholic": -0.14,
                "calm": -0.02,
            }.get(emotion, 0.0)
            saturation = min(1.22, max(0.78, saturation))

            key  = (lighting_plan.get("key")  or {})
            fill = (lighting_plan.get("fill") or {})
            brightness = 1.0 + min(float(key.get("intensity", 0.7)) * 0.04, 0.06)
            brightness += {"joyful": 0.025, "awe": 0.015, "dread": -0.025, "melancholic": -0.02}.get(emotion, 0.0)
            contrast = 1.04 + min(float(fill.get("intensity", 0.2)) * 0.04, 0.03)
            contrast += {"tense": 0.05, "dread": 0.06, "melancholic": 0.01, "calm": -0.02}.get(emotion, 0.0)
            atm = lighting_plan.get("atmosphere") or {}
            atm_haze = float(atm.get("haze", 0.0))
            atm_fog  = float(atm.get("fog",  0.0))

            assets = scene_assets.get(str(scene.index), [])
            shots  = scene.shots

            if not assets:
                self._emit(f"  [WARN] Scene {scene.index+1}: no assets, skipping")
                continue

            shot_iter: list[tuple[int, dict[str, Any]]] = []
            if shots:
                shot_iter = list(enumerate(shots))
            else:
                shot_iter = [(i, {}) for i in range(len(assets))]

            previous_shot: dict[str, Any] | None = None
            for i, shot_dict in shot_iter:
                asset    = assets[min(i, len(assets) - 1)]
                out      = self.dirs["shots"] / (
                    f"scene_{scene.index + 1:02d}_shot_{i:02d}.mp4"
                )
                motion   = shot_dict.get("motion_intent",  direction["camera"]["movement"])
                z_start  = float(shot_dict.get("zoom_start",  1.0))
                z_end    = float(shot_dict.get("zoom_end",    1.05))
                dof      = float(shot_dict.get("depth_of_field",
                                direction.get("depth", {}).get("depth_of_field", 0.0)))
                duration = float(shot_dict.get("duration", scene.duration))
                treatment = str(shot_dict.get("cinematic_treatment", "depth_push"))
                depth_mode = str(shot_dict.get("depth_mode", "none"))
                depth_artifact = self.dirs["depth"] / (
                    f"scene_{scene.index + 1:02d}_shot_{i:02d}_depth.png"
                )
                parallax_strength = {
                    "layered_reveal": 0.14,
                    "subject_follow": 0.10,
                    "depth_push": 0.08,
                    "atmospheric_drift": 0.05,
                }.get(treatment, 0.06)
                rendered_treatments.append({
                    "scene_index": scene.index,
                    "shot_index": i,
                    "treatment": treatment,
                    "depth_mode": depth_mode,
                    "focus_behavior": shot_dict.get("focus_behavior", "deep_focus"),
                    "atmosphere_mode": shot_dict.get("atmosphere_mode", "none"),
                    "environment": environment,
                    "emotion": emotion,
                    "visual_palette": list(direction.get("visual_palette") or []),
                    "depth_artifact": str(depth_artifact),
                    "parallax_strength": parallax_strength,
                })
                engine.render_motion(
                    asset, out,
                    duration=duration,
                    camera={"movement": motion, "zoom_start": z_start, "zoom_end": z_end},
                    depth={"depth_of_field": dof, "mode": depth_mode,
                           "parallax_strength": parallax_strength,
                           "artifact_path": str(depth_artifact)},
                    lighting={"brightness": brightness, "contrast": contrast,
                               "saturation": saturation},
                    atmosphere={"blur": atm_haze * 0.8, "haze": atm_haze, "fog": atm_fog},
                    vfx={
                        "blur": atm_fog * 0.4,
                        "grain": 0.025 if environment not in {"dream", "fantasy"} else 0.015,
                        "vignette": 0.22 if environment not in {"ocean", "space"} else 0.14,
                        "bloom": 0.10 if float(key.get("intensity", 0.7)) > 0.75 else 0.06,
                    },
                )
                if all_clips:
                    scene_change = i == 0 and scene.index > 0
                    transition_spec = select_transition(
                        previous_shot, shot_dict, scene_change=scene_change
                    )
                    transition = transition_spec.kind.value
                    if transition == "hard_cut":
                        transition = "cut"
                    # SceneAnalyzer is authoritative for semantic boundaries. If
                    # its hint is a cut, preserve hard cuts inside a scene but
                    # allow a motivated scene-level xfade when the narrative
                    # context calls for a reveal, resolution, or a climax with
                    # a world/environment change.
                    if i == 0 and scene.index > 0:
                        analysis = scene.analysis or {}
                        previous = self.scenes[scene.index - 1]
                        previous_env = (previous.direction or {}).get("environment")
                        current_env = direction.get("environment")
                        beat = str(analysis.get("narrative_beat", ""))
                        purpose = str(analysis.get("scene_purpose", ""))
                        emotion = str(analysis.get("emotional_register", ""))
                        if transition in {"cut", "none", ""}:
                            if beat == "climax" and previous_env != current_env:
                                transition = "light"
                            elif purpose == "conclude" or beat in {"resolution", "transition"}:
                                transition = "fade"
                            elif emotion in {"calm", "melancholic", "wonder"}:
                                transition = "dissolve"
                    boundary_transitions.append(transition)
                all_clips.append(out)
                previous_shot = shot_dict

        if not all_clips:
            raise RuntimeError("render_shots produced no clips")
        self._shot_transitions = boundary_transitions
        self.cinematic_treatments = rendered_treatments
        if self.visual_manifest_path.is_file():
            try:
                manifest = json.loads(self.visual_manifest_path.read_text(encoding="utf-8"))
                for record in manifest.get("scenes", []):
                    record["rendered_motion"] = True
                manifest.setdefault("visual_processing", {})["rendered_motion"] = True
                manifest["cinematic_treatments"] = rendered_treatments
                self.visual_manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
        self._emit(
            f"  Applied {sum(t not in {'cut', 'none', ''} for t in boundary_transitions)} "
            f"cinematic transitions across {len(all_clips)} shots"
        )
        return all_clips

    def assemble_edit(
        self, clips: list[Path], narration_path: Path, music_path: Path | None,
        sound_design_path: Path | None = None, ambient_path: Path | None = None,
    ) -> Path:
        self._emit("Editing — concatenating shots and mixing audio...")
        video_only = self.dirs["edit"] / "video_concat.mp4"
        transitions = getattr(self, "_shot_transitions", None) or ["cut"] * max(0, len(clips) - 1)
        assemble_cinematic_clips(clips, transitions, video_only)
        target_duration = max(30.0, probe_duration(narration_path))
        padded_video = self.dirs["edit"] / "video_padded.mp4"
        pad_video_to_duration(video_only, padded_video, target_duration)
        mixed = self.dirs["edit"] / "edit_mixed.mp4"
        mix_narration_and_music(
            padded_video, narration_path, mixed, music_path, sound_design_path, ambient_path
        )
        return mixed

    def finish(
        self, edit_path: Path, srt_path: Path, narration_path: Path | None = None,
    ) -> dict[str, Path]:
        """Grade → subtitle → master encode → QC → delivery alias."""
        from .qc_engine import run_qc, visual_variation_preflight

        preflight = visual_variation_preflight(edit_path, threshold=0.005)
        self._emit(
            f"[PREFLIGHT] stage=EDIT path={edit_path} "
            f"minimum_diff={preflight.get('minimum_diff', 0.0):.4f} "
            f"threshold={preflight.get('threshold', 0.005):.3f} "
            f"passed={preflight.get('passed', False)}"
        )
        if not preflight.get("passed", False):
            raise RuntimeError(
                "PREFLIGHT FATAL: stage=EDIT "
                f"minimum_diff={preflight.get('minimum_diff', 0.0):.4f} "
                "threshold=0.005 "
                f"video_path={edit_path} "
                "likely insufficient real scene motion or provider variation"
            )

        self._emit("Color grading...")
        graded = self.dirs["master"] / "graded.mp4"
        apply_color_grade(edit_path, graded)

        self._emit("Burning subtitles...")
        subtitled = self.dirs["master"] / "subtitled.mp4"
        burn_subtitles(graded, srt_path, subtitled)

        self._emit("Mastering final encode...")
        final_youtube = self.dirs["delivery"] / f"episode-{self.episode_id}-youtube.mp4"
        master_encode(subtitled, final_youtube, profile="youtube")
        outputs: dict[str, Path] = {"youtube": final_youtube}

        if self.profile in {"tiktok", "both"}:
            final_tiktok = self.dirs["delivery"] / f"episode-{self.episode_id}-tiktok.mp4"
            master_encode(subtitled, final_tiktok, profile="tiktok")
            outputs["tiktok"] = final_tiktok

        final_alias = self.dirs["delivery"] / f"episode-{self.episode_id}-FINAL.mp4"
        final_alias.write_bytes(final_youtube.read_bytes())
        outputs["final"] = final_alias

        # Reconcile the pre-production scene-duration estimate with the real
        # narration length once it is known — the scene plan is only an
        # early estimate made before TTS runs, so it can be far shorter than
        # the actual spoken content. Comparing final duration against the
        # raw estimate alone produces a false "duration mismatch" against a
        # video whose length is actually correct.
        planned_dur = max(5.0, sum(s.duration for s in self.scenes))
        if narration_path is not None:
            try:
                planned_dur = max(planned_dur, probe_duration(narration_path))
            except Exception:
                pass
        qc = run_qc(
            video_path=final_alias, srt_path=srt_path,
            min_duration_s=max(5.0, planned_dur * 0.5),
            planned_duration_s=planned_dur,
            scene_count=len(self.scenes),
            narration_path=narration_path,
            expected_text_path=self.script_path,
            require_audio_quality=True,
        )

        total_assets = self._total_visual_assets or None
        visual_qc = validate_visual_manifest(
            self.visual_manifest_path, expected_asset_count=total_assets,
        )
        qc["visual_content"] = visual_qc
        if qc["warnings"]:
            for w in qc["warnings"]:
                self._emit(f"[QC][WARNING] check={w['name']} msg={w['message']}")
        if qc["delivery_blocked"] or not visual_qc["passed"]:
            mp4_fatal_msgs  = [f"{c['name']}: {c['message']}" for c in qc["fatals"]]
            visual_failed   = visual_qc.get("failed_checks", [])
            visual_details  = visual_qc.get("check_details", {})
            raise RuntimeError(
                f"QC FATAL —"
                f" mp4_fatals={mp4_fatal_msgs}"
                f" visual_qc_passed={visual_qc['passed']}"
                f" visual_failed_checks={visual_failed}"
                f" visual_details={visual_details}"
            )

        manifest = {
            "episode_id":       self.episode_id,
            "title":            self.title,
            "language":         self.language,
            "run_id":           self._run_id,
            "duration":         probe_duration(final_alias),
            "planned_duration": planned_dur,
            "outputs":          {key: str(path) for key, path in outputs.items()},
            "qc":               qc,
            "visual_qc":        visual_qc,
            "audio_quality":    dict(qc.get("audio_quality", {})),
            "subtitle_path":    str(srt_path),
            "audio_provenance": dict(self.audio_provenance),
            "music_provenance": dict(self.music_provenance),
            "ambient_provenance": dict(self.ambient_provenance),
            "cinematic_treatments": list(self.cinematic_treatments),
            "directing":        [scene.direction for scene in self.scenes],
            "analyses":         [scene.analysis  for scene in self.scenes],
            "timestamp":        time.time(),
        }
        (self.root / "production_manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        final_duration = probe_duration(final_alias)
        self._emit(
            f"FINAL MP4 ready: {final_alias} "
            f"({final_duration:.1f}s / {final_duration / 60:.1f} min)"
        )
        return outputs

    def produce(self) -> dict[str, Any]:
        """Single-call production: script → FINAL MP4."""
        self._emit(f"Starting AURELIA production — Episode {self.episode_id}")
        script_text = self.load_script()
        self._emit(f"Title: {self.title} | Language: {self.language}")
        self.build_scene_plan(script_text)
        scene_assets = self.generate_visual_assets()
        narration = self.synthesize_narration(script_text)
        srt = self.build_subtitles(narration)
        self._apply_shot_timing(probe_duration(narration))
        duration = max(
            probe_duration(narration),
            sum(scene.duration for scene in self.scenes) + 8.0,
        )
        emotional_arc = [str((scene.analysis or {}).get("emotional_register", "neutral")) for scene in self.scenes]
        music_path = self.dirs["audio"] / "cinematic_music.wav"
        music_provider = CinematicMusicProvider()
        music_provider.generate(duration + 4.0, music_path, emotional_arc=emotional_arc)
        self.music_provenance = {
            "provider": music_provider.name,
            "engine": "generate_cinematic_music",
            "artifact": str(music_path),
            "duration_s": duration + 4.0,
            "emotional_arc": emotional_arc,
            "fallback": False,
            "fallback_reason": "",
        }
        ambient_path = self.dirs["audio"] / "ambient_bed.wav"
        ambient_segments: list[Path] = []
        ambient_provider = SynthAmbientProvider()
        ambient_environments: list[str] = []
        for scene in self.scenes:
            environment = str((scene.direction or {}).get("environment", "abstract"))
            ambient_environments.append(environment)
            segment_path = self.dirs["audio"] / f"ambient_scene_{scene.index + 1:02d}.wav"
            ambient_provider.generate(
                environment, max(2.0, scene.duration + 0.25), segment_path,
                seed=scene.index,
            )
            ambient_segments.append(segment_path)
        try:
            from pydub import AudioSegment
            combined = AudioSegment.empty()
            for segment in ambient_segments:
                combined += AudioSegment.from_wav(segment)
            combined.export(ambient_path, format="wav")
        except Exception as exc:
            raise RuntimeError(f"Ambient bed assembly failed: {exc}") from exc
        self.ambient_provenance = {
            "provider": ambient_provider.name,
            "engine": "synthesize_ambient",
            "artifact": str(ambient_path),
            "environments": ambient_environments,
            "duration_s": probe_duration(ambient_path),
            "fallback": False,
            "fallback_reason": "",
        }
        sound_design_path = self.dirs["audio"] / "sound_design.wav"
        scene_boundaries = []
        cursor = 0.0
        for scene in self.scenes[:-1]:
            cursor += scene.duration
            scene_boundaries.append(cursor)
        generate_sound_design(duration, scene_boundaries, sound_design_path)
        clips  = self.render_shots(scene_assets)
        edit   = self.assemble_edit(clips, narration, music_path, sound_design_path, ambient_path)
        outputs = self.finish(edit, srt, narration_path=narration)
        total_shots = sum(len(s.shots) for s in self.scenes)
        return {
            "episode_id":  self.episode_id,
            "title":       self.title,
            "language":    self.language,
            "run_id":      self._run_id,
            "final_mp4":   str(outputs["final"]),
            "outputs":     {k: str(v) for k, v in outputs.items()},
            "duration":    probe_duration(outputs["final"]),
            "scenes":      len(self.scenes),
            "total_shots": total_shots,
            "audio_provenance": dict(self.audio_provenance),
            "music_provenance": dict(self.music_provenance),
            "ambient_provenance": dict(self.ambient_provenance),
        }


def produce_episode(
    episode_id: str,
    script_path: str | Path,
    output_root: str | Path,
    profile: str = "both",
    language: str = "auto",
    log: LogFn | None = None,
    max_duration: float = _MAX_DURATION_UNLIMITED,
) -> dict[str, Any]:
    production = EpisodeProduction(
        episode_id=episode_id,
        root=(
            Path(output_root)
            / f"episode-{episode_id.zfill(4) if episode_id.isdigit() else episode_id}"
        ),
        script_path=Path(script_path),
        profile=profile, language=language,
        max_duration=max_duration,
        log=log or (lambda _m: None),
    )
    return production.produce()


__all__ = ["EpisodeProduction", "produce_episode", "ScenePlan"]
