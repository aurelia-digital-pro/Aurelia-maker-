"""AURELIA — canonical episode production engine (Factory → FINAL MP4).

Architecture:
- PRIMARY visual path: visual_backend.generate_visual() — SD → Pillow fallback
- Every fallback is explicit in logs. No silent degradation.
- Shot-level visuals: one image per ShotSpec (2–5 per scene)
- Content-driven zoom/motion/transition from ShotDesigner
- SceneAnalyzer enriches planner output with beat/emotion/action context
- ProductionLogger records structured trace if injected via log= callable
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .directing_engine import DirectingEngine
from .media import (
    apply_color_grade,
    burn_subtitles,
    concat_clips,
    generate_ambient_music,
    master_encode,
    mix_narration_and_music,
    pad_video_to_duration,
    probe_duration,
    validate_master,
    validate_visual_manifest,
)
from .planner import plan_scenes
from .scene_analyzer import SceneAnalyzer
from .shot_designer import ShotDesigner, ShotSpec
from .tts import synthesize_script
from .visual_backend import generate_visual  # PRIMARY: SD → Pillow fallback

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
            for name in ("visuals", "shots", "audio", "edit", "master", "delivery", "factory")
        }
        for path in self.dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        self.director = DirectingEngine()
        self._analyzer = SceneAnalyzer()
        self._shot_designer = ShotDesigner()
        self._run_id = uuid.uuid4().hex[:16]
        if not self.title:
            self.title = self._extract_title(self.script_path.read_text(encoding="utf-8"))
        # Provenance path for visual manifest
        self.visual_manifest_path = self.dirs["visuals"] / "visual_manifest.json"
        # Total visual assets written (shots, not scenes) — set in generate_visual_assets
        self._total_visual_assets: int = 0

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
        dynamic_max = max(3, min(60, word_count // 50))
        raw = plan_scenes(script_text, min_scenes=3, max_scenes=dynamic_max)

        analyses = self._analyzer.analyze_sequence(raw)

        scenes: list[ScenePlan] = []
        for index, (raw_scene, analysis) in enumerate(zip(raw, analyses)):
            scene_id = f"episode-{self.episode_id}:scene-{index + 1:03d}"
            scene_words = len(raw_scene["text"].split())
            estimated_duration = max(_SCENE_DURATION_MIN, scene_words / 3.0)

            direction = self.director.direct(
                scene_id=scene_id,
                title=raw_scene["title"],
                text=raw_scene["text"],
                duration=estimated_duration,
                scene_index=index,
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
        """Generate one image per SHOT using visual_backend (SD → Pillow fallback).

        Every fallback is logged. No silent degradation.
        Sets self._total_visual_assets = total number of images generated.
        Returns dict: scene_index_str → list[Path]
        """
        self._emit("Generating visual assets — one image per shot via visual_backend...")
        scene_assets: dict[str, list[Path]] = {}
        manifest_scenes: list[dict[str, Any]] = []
        total_fallbacks = 0
        total_images = 0

        for scene in self.scenes:
            env = scene.direction.get("environment", "abstract")
            self._emit(f"  Scene {scene.index + 1} [{env}]: {scene.title[:50]}")
            shot_paths: list[Path] = []
            shots = scene.shots or []

            if not shots:
                # No shot plan — single image for scene
                path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}_shot_00.png"
                prov = generate_visual(
                    scene.index, scene.title, scene.text, path,
                    direction=scene.direction, width=512, height=512,
                    visual_note="", run_id=self._run_id,
                    logger=self._emit,
                )
                if prov["fallback"]:
                    total_fallbacks += 1
                    self._emit(
                        f"  [VISUAL][FALLBACK] Scene {scene.index+1} shot 0: "
                        f"{prov['fallback_reason']}"
                    )
                shot_paths.append(path)
                manifest_scenes.append(self._manifest_record(scene, 0, path, prov))
                total_images += 1
            else:
                for shot in shots:
                    shot_idx = shot["shot_index"]
                    path = self.dirs["visuals"] / (
                        f"scene_{scene.index + 1:02d}_shot_{shot_idx:02d}.png"
                    )
                    # Visual note = shot description + framing + motion_intent
                    visual_note = " ".join(filter(None, [
                        shot.get("description", ""),
                        shot.get("framing", ""),
                        shot.get("motion_intent", ""),
                    ]))
                    prov = generate_visual(
                        scene.index, scene.title, scene.text, path,
                        direction=scene.direction, width=512, height=512,
                        visual_note=visual_note, run_id=self._run_id,
                        logger=self._emit,
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
            f"Visual assets: {total_images} images, {total_fallbacks} Pillow fallbacks "
            f"({total_fallbacks/max(total_images,1)*100:.0f}%)"
        )

        manifest: dict[str, Any] = {
            "backend": "local-ai",
            "source": "chat",
            "run_id": self._run_id,
            "total_images": total_images,
            "total_fallbacks": total_fallbacks,
            "fallback_rate": round(total_fallbacks / max(total_images, 1), 3),
            "visual_processing": {"motion_renderer": "CinematicVisualEngine"},
            "scenes": manifest_scenes,
        }
        self.visual_manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self._emit(f"Visual manifest written: {self.visual_manifest_path}")
        return scene_assets

    @staticmethod
    def _manifest_record(
        scene: ScenePlan, shot_idx: int, path: Path, prov: dict[str, Any]
    ) -> dict[str, Any]:
        """Build one manifest entry for a generated visual."""
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "scene_index": scene.index,
            "shot_index":  shot_idx,
            "title":       scene.title,
            "asset":       str(path.resolve()),
            "asset_sha256": sha,
            "text_sha256": hashlib.md5(scene.text.encode()).hexdigest(),
            "backend":     prov.get("backend", "unknown"),
            "fallback":    prov.get("fallback", False),
            "fallback_reason": prov.get("fallback_reason", ""),
            "prompt":      prov.get("prompt", ""),
            "seed":        prov.get("seed", 0),
            "elapsed_s":   prov.get("elapsed_s", 0.0),
        }

    def synthesize_narration(self, script_text: str) -> Path:
        self._emit("Synthesizing narration (TTS)...")
        narration_path = self.dirs["audio"] / "narration.wav"
        language = self.language if self.language != "auto" else "en"
        synthesize_script(script_text, narration_path, language=language)
        if not narration_path.exists() or narration_path.stat().st_size < 100:
            raise RuntimeError("Narration synthesis failed — TTS produced no output")
        duration = probe_duration(narration_path)
        self._emit(f"Narration: {duration:.1f}s | language={language}")
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
            snippet = re.sub(r"\s+", " ", scene.text.strip())
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            lines.extend([str(cue_index), f"{fmt(cursor)} --> {fmt(end)}", snippet, ""])
            cue_index += 1
            cursor = end

        srt_path = self.root / f"episode-{self.episode_id}.srt"
        srt_path.write_text("\n".join(lines), encoding="utf-8")
        return srt_path

    def render_shots(
        self, scene_assets: dict[str, list[Path]]
    ) -> list[Path]:
        """Render one clip per shot image.

        Each shot uses its own ShotSpec parameters from ShotDesigner:
        framing, motion_intent, zoom range, depth_of_field.
        """
        from .visuals import CinematicVisualEngine
        self._emit("Rendering cinematic shots (content-driven motion per shot)...")
        engine = CinematicVisualEngine()
        all_clips: list[Path] = []

        for scene in self.scenes:
            direction = scene.direction
            lighting_plan = direction.get("lighting", {})
            environment = direction.get("environment", "abstract")

            if environment in _HIGH_SAT_ENVS:
                saturation = 1.12
            elif environment in _LOW_SAT_ENVS:
                saturation = 0.95
            else:
                saturation = 1.05

            key  = (lighting_plan.get("key")  or {})
            fill = (lighting_plan.get("fill") or {})
            brightness = 1.0 + min(float(key.get("intensity",  0.7)) * 0.04, 0.06)
            contrast   = 1.04 + min(float(fill.get("intensity", 0.2)) * 0.04, 0.03)
            atm = lighting_plan.get("atmosphere") or {}
            atm_haze = float(atm.get("haze", 0.0))
            atm_fog  = float(atm.get("fog",  0.0))

            assets = scene_assets.get(str(scene.index), [])
            shots  = scene.shots

            if not assets:
                self._emit(f"  [WARN] Scene {scene.index+1}: no assets, skipping")
                continue

            # If no shots planned, treat each asset as one implicit shot
            shot_iter: list[tuple[int, dict[str, Any]]] = []
            if shots:
                shot_iter = list(enumerate(shots))
            else:
                shot_iter = [(i, {}) for i in range(len(assets))]

            for i, shot_dict in shot_iter:
                asset = assets[min(i, len(assets) - 1)]
                out = self.dirs["shots"] / (
                    f"scene_{scene.index + 1:02d}_shot_{i:02d}.mp4"
                )

                motion   = shot_dict.get("motion_intent",  direction["camera"]["movement"])
                z_start  = float(shot_dict.get("zoom_start",  1.0))
                z_end    = float(shot_dict.get("zoom_end",    1.05))
                dof      = float(shot_dict.get("depth_of_field",
                                               direction.get("depth", {}).get("depth_of_field", 0.0)))
                duration = float(shot_dict.get("duration", scene.duration))

                engine.render_motion(
                    asset, out,
                    duration=duration,
                    camera={"movement": motion, "zoom_start": z_start, "zoom_end": z_end},
                    depth={"depth_of_field": dof},
                    lighting={"brightness": brightness, "contrast": contrast, "saturation": saturation},
                    atmosphere={"blur": atm_haze * 0.8},
                    vfx={"blur": atm_fog * 0.4},
                )
                all_clips.append(out)

        if not all_clips:
            raise RuntimeError("render_shots produced no clips")
        return all_clips

    def assemble_edit(
        self, clips: list[Path], narration_path: Path, music_path: Path | None
    ) -> Path:
        self._emit("Editing — concatenating shots and mixing audio...")
        video_only = self.dirs["edit"] / "video_concat.mp4"
        concat_clips(clips, video_only)
        target_duration = max(30.0, probe_duration(narration_path))
        padded_video = self.dirs["edit"] / "video_padded.mp4"
        pad_video_to_duration(video_only, padded_video, target_duration)
        mixed = self.dirs["edit"] / "edit_mixed.mp4"
        mix_narration_and_music(padded_video, narration_path, mixed, music_path)
        return mixed

    def finish(self, edit_path: Path, srt_path: Path) -> dict[str, Path]:
        """Grade → subtitle → master encode → QC → delivery alias."""
        from .qc_engine import run_qc

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

        # — QC with FATAL/WARNING distinction —
        planned_dur = max(5.0, sum(s.duration for s in self.scenes))
        qc = run_qc(
            video_path=final_alias,
            srt_path=srt_path,
            min_duration_s=max(5.0, planned_dur * 0.5),
            planned_duration_s=planned_dur,
            scene_count=len(self.scenes),
        )

        # validate_visual_manifest expects TOTAL ASSET COUNT (shots), not scene count
        # Use self._total_visual_assets set in generate_visual_assets
        total_assets = self._total_visual_assets or None  # None skips count check
        visual_qc = validate_visual_manifest(
            self.visual_manifest_path,
            expected_asset_count=total_assets,
        )
        qc["visual_content"] = visual_qc
        if qc["warnings"]:
            for w in qc["warnings"]:
                self._emit(f"[QC][WARNING] check={w['name']} msg={w['message']}")
        if qc["delivery_blocked"] or not visual_qc["passed"]:
            mp4_fatal_msgs = [f"{c['name']}: {c['message']}" for c in qc["fatals"]]
            visual_failed = visual_qc.get("failed_checks", [])
            visual_details = visual_qc.get("check_details", {})
            raise RuntimeError(
                f"QC FATAL —"
                f" mp4_fatals={mp4_fatal_msgs}"
                f" visual_qc_passed={visual_qc['passed']}"
                f" visual_failed_checks={visual_failed}"
                f" visual_details={visual_details}"
            )

        manifest = {
            "episode_id": self.episode_id,
            "title": self.title,
            "language": self.language,
            "run_id": self._run_id,
            "duration": probe_duration(final_alias),
            "planned_duration": planned_dur,
            "outputs": {key: str(path) for key, path in outputs.items()},
            "qc": qc,
            "visual_qc": visual_qc,
            "directing": [scene.direction for scene in self.scenes],
            "analyses": [scene.analysis for scene in self.scenes],
            "timestamp": time.time(),
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
        duration = max(
            probe_duration(narration),
            sum(scene.duration for scene in self.scenes) + 8.0,
        )
        music_path = self.dirs["audio"] / "ambient_music.wav"
        generate_ambient_music(duration + 4.0, music_path)
        clips = self.render_shots(scene_assets)
        edit = self.assemble_edit(clips, narration, music_path)
        outputs = self.finish(edit, srt)
        total_shots = sum(len(s.shots) for s in self.scenes)
        return {
            "episode_id": self.episode_id,
            "title": self.title,
            "language": self.language,
            "run_id": self._run_id,
            "final_mp4": str(outputs["final"]),
            "outputs": {k: str(v) for k, v in outputs.items()},
            "duration": probe_duration(outputs["final"]),
            "scenes": len(self.scenes),
            "total_shots": total_shots,
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
        profile=profile,
        language=language,
        max_duration=max_duration,
        log=log or (lambda _m: None),
    )
    return production.produce()


__all__ = ["EpisodeProduction", "produce_episode", "ScenePlan"]
