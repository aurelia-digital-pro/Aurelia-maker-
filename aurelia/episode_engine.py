"""AURELIA Maker — canonical episode production engine (Factory → FINAL MP4).

Key fixes in this revision:
- max_duration is now DYNAMIC — defaults to 3600 s (1 hour), scales to content
- scene_index is now passed to DirectingEngine.direct() for movement variety
- environment saturation is now derived from environment type, not a fixed list
- language is auto-detected from script if not explicitly set
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .ai_visual import generate_scene_image
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
from .tts import synthesize_script

LogFn = Callable[[str], None]

# Default scene duration in seconds
_SCENE_DURATION_DEFAULT = 18.0
# Minimum per-scene duration even after scaling
_SCENE_DURATION_MIN = 6.0
# When no max_duration supplied, we use this large value (1 hour)
_MAX_DURATION_UNLIMITED = 3600.0

# Environments that look best with slightly boosted saturation
_HIGH_SAT_ENVS = {"space", "ocean", "fantasy", "fire", "dream", "machine"}
# Environments that look best with slightly reduced saturation (moody)
_LOW_SAT_ENVS = {"ancient", "battle", "industry"}


@dataclass
class ScenePlan:
    index: int
    title: str
    text: str
    duration: float = _SCENE_DURATION_DEFAULT
    movement: str = "push_in"
    direction: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeProduction:
    episode_id: str
    root: Path
    script_path: Path
    profile: str = "youtube"
    language: str = "auto"        # "ar", "en", or "auto" — auto-detected from script
    max_duration: float = _MAX_DURATION_UNLIMITED  # no hard cap by default
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
        if not self.title:
            self.title = self._extract_title(self.script_path.read_text(encoding="utf-8"))

    @staticmethod
    def _extract_title(request_text: str) -> str:
        for line in request_text.splitlines():
            m = re.match(
                r'^\s*(?:title|العنوان|عنوان)\s*[:=]\s*(.+?)\s*$',
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
                r'^\s*(?:title|العنوان|عنوان|language|lang|اللغة|لغة)\s*[:=]\s*.+?\s*$',
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
        # Auto-detect language if not explicitly set
        if self.language == "auto":
            self.language = self._detect_language(request_text)
            self._emit(f"Language auto-detected: {self.language}")
        return body

    def build_scene_plan(self, script_text: str) -> list[ScenePlan]:
        # Dynamically compute max_scenes from content length
        word_count = len(script_text.split())
        dynamic_max = max(3, min(60, word_count // 50))  # ~50 words per scene
        raw = plan_scenes(script_text, min_scenes=3, max_scenes=dynamic_max)

        scenes: list[ScenePlan] = []
        for index, scene in enumerate(raw):
            scene_id = f"episode-{self.episode_id}:scene-{index + 1:03d}"
            # Estimate scene duration from text length (~3 words/second narration pace)
            scene_words = len(scene["text"].split())
            estimated_duration = max(_SCENE_DURATION_MIN, scene_words / 3.0)
            direction = self.director.direct(
                scene_id=scene_id,
                title=scene["title"],
                text=scene["text"],
                duration=estimated_duration,
                scene_index=index,  # enables movement variety
            )
            scenes.append(ScenePlan(
                index=index,
                title=scene["title"],
                text=scene["text"],
                duration=estimated_duration,
                movement=direction["camera"]["movement"],
                direction=direction,
            ))

        if not scenes:
            raise ValueError("No scenes could be planned from the supplied script")

        # Only scale if we genuinely exceed max_duration (no scaling for unlimited)
        total = sum(s.duration for s in scenes) + 8.0
        if total > self.max_duration:
            scale = (self.max_duration - 8.0) / max(sum(s.duration for s in scenes), 1.0)
            for scene in scenes:
                scene.duration = max(_SCENE_DURATION_MIN, round(scene.duration * scale, 1))
                scene.direction["motion"]["duration"] = scene.duration

        self.scenes = scenes
        total_planned = sum(s.duration for s in scenes)
        self._emit(
            f"Scene plan: {len(scenes)} scenes, "
            f"estimated duration {total_planned:.0f}s ({total_planned / 60:.1f} min)"
        )
        return scenes

    def generate_visual_assets(self) -> list[Path]:
        self._emit("Generating visual assets (local AI / cinematic procedural)...")
        assets: list[Path] = []
        for scene in self.scenes:
            path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}.png"
            env = scene.direction.get("environment", "abstract")
            self._emit(f"  Scene {scene.index + 1}: [{env}] {scene.title[:50]}")
            generate_scene_image(
                scene.index, scene.title, scene.text, path,
                direction=scene.direction, width=512, height=512,
            )
            assets.append(path)

        if not assets or not all(
            p.exists() and p.stat().st_size > 1000 for p in assets
        ):
            raise RuntimeError("Visual generation produced no valid scene assets")

        script_text_for_manifest = self.script_path.read_text(encoding="utf-8").strip()
        self.visual_manifest_path = self.root / "visual_manifest.json"
        self.visual_manifest_path.write_text(
            json.dumps({
                "backend": "local-ai",
                "source": "chat",
                "episode_id": self.episode_id,
                "title": self.title,
                "source_text_sha256": hashlib.sha256(
                    script_text_for_manifest.encode("utf-8")
                ).hexdigest(),
                "scenes": [
                    {
                        "index": scene.index,
                        "title": scene.title,
                        "environment": scene.direction.get("environment", "abstract"),
                        "text_sha256": hashlib.sha256(scene.text.encode("utf-8")).hexdigest(),
                        "asset": str(asset),
                        "asset_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        "direction": scene.direction,
                    }
                    for scene, asset in zip(self.scenes, assets)
                ],
                "visual_processing": {
                    "backend": "local-ai",
                    "motion_renderer": "CinematicVisualEngine",
                    "image_enhancement": "Pillow color and resize processing",
                },
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return assets

    def synthesize_narration(self, script_text: str) -> Path:
        self._emit(f"Synthesizing narration (language={self.language})...")
        narration_path = self.dirs["audio"] / "narration.wav"
        synthesize_script(script_text, narration_path)
        if not narration_path.exists() or narration_path.stat().st_size < 1000:
            raise RuntimeError("Narration synthesis failed")
        narration_duration = probe_duration(narration_path)
        self._emit(
            f"Narration ready: {narration_path.stat().st_size} bytes, "
            f"{narration_duration:.1f}s"
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
            snippet = re.sub(r"\s+", " ", scene.text.strip())
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            lines.extend([str(cue_index), f"{fmt(cursor)} --> {fmt(end)}", snippet, ""])
            cue_index += 1
            cursor = end

        srt_path = self.root / f"episode-{self.episode_id}.srt"
        srt_path.write_text("\n".join(lines), encoding="utf-8")
        return srt_path

    def render_shots(self, assets: list[Path]) -> list[Path]:
        from .visuals import CinematicVisualEngine
        self._emit("Rendering cinematic shots with content-driven camera motion...")
        engine = CinematicVisualEngine()
        clips: list[Path] = []
        if len(assets) != len(self.scenes):
            raise RuntimeError("Every planned scene must have exactly one visual asset")
        for scene, asset in zip(self.scenes, assets):
            out = self.dirs["shots"] / f"scene_{scene.index + 1:02d}.mp4"
            direction = scene.direction
            camera_plan = direction["camera"]
            motion_plan = direction["motion"]
            lighting_plan = direction["lighting"]
            depth_plan = direction["depth"]
            environment = direction.get("environment", "abstract")

            zoom_start = float(motion_plan.get("start", {}).get("zoom", 1.0))
            zoom_end = float(motion_plan.get("end", {}).get("zoom", 1.08))
            key = lighting_plan.get("key") or {}
            fill = lighting_plan.get("fill") or {}
            brightness = 1.0 + min(float(key.get("intensity", 0.7)) * 0.04, 0.06)
            contrast = 1.04 + min(float(fill.get("intensity", 0.2)) * 0.04, 0.03)

            # Saturation derived from environment type
            if environment in _HIGH_SAT_ENVS:
                saturation = 1.12
            elif environment in _LOW_SAT_ENVS:
                saturation = 0.95
            else:
                saturation = 1.05

            engine.render_motion(
                asset, out,
                duration=scene.duration,
                camera={
                    "movement": camera_plan["movement"],
                    "zoom_start": zoom_start,
                    "zoom_end": zoom_end,
                },
                depth={"depth_of_field": float(depth_plan.get("depth_of_field", 0.0))},
                lighting={
                    "brightness": brightness,
                    "contrast": contrast,
                    "saturation": saturation,
                },
                atmosphere={
                    "blur": float(
                        (lighting_plan.get("atmosphere") or {}).get("haze", 0.0)
                    ) * 0.8
                },
                vfx={
                    "blur": float(
                        (lighting_plan.get("atmosphere") or {}).get("fog", 0.0)
                    ) * 0.4
                },
            )
            clips.append(out)
        return clips

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

        qc = validate_master(final_alias, min_duration=5.0)  # reduced minimum for short episodes
        visual_qc = validate_visual_manifest(self.visual_manifest_path, len(self.scenes))
        qc["visual_content"] = visual_qc
        qc["passed"] = qc["passed"] and visual_qc["passed"]
        if not qc["passed"]:
            raise RuntimeError(f"QC failed: {qc}")

        manifest = {
            "episode_id": self.episode_id,
            "title": self.title,
            "language": self.language,
            "duration": probe_duration(final_alias),
            "outputs": {key: str(path) for key, path in outputs.items()},
            "qc": qc,
            "directing": [scene.direction for scene in self.scenes],
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
        assets = self.generate_visual_assets()
        narration = self.synthesize_narration(script_text)
        srt = self.build_subtitles(narration)
        duration = max(
            probe_duration(narration),
            sum(scene.duration for scene in self.scenes) + 8.0,
        )
        music_path = self.dirs["audio"] / "ambient_music.wav"
        generate_ambient_music(duration + 4.0, music_path)
        clips = self.render_shots(assets)
        edit = self.assemble_edit(clips, narration, music_path)
        outputs = self.finish(edit, srt)
        return {
            "episode_id": self.episode_id,
            "title": self.title,
            "language": self.language,
            "final_mp4": str(outputs["final"]),
            "outputs": {k: str(v) for k, v in outputs.items()},
            "duration": probe_duration(outputs["final"]),
            "scenes": len(self.scenes),
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
