"""AURELIA Maker — canonical episode production engine (Factory → FINAL MP4)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .ai_visual import generate_scene_image, generate_title_card
from .directing_engine import DirectingEngine
from .media import (
    apply_color_grade,
    burn_subtitles,
    concat_clips,
    generate_ambient_music,
    master_encode,
    mix_narration_and_music,
    probe_duration,
    validate_master,
)
from .planner import plan_scenes
from .tts import synthesize_script


LogFn = Callable[[str], None]


@dataclass
class ScenePlan:
    index: int
    title: str
    text: str
    duration: float = 18.0
    movement: str = "push_in"
    direction: dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeProduction:
    episode_id: str
    root: Path
    script_path: Path
    profile: str = "youtube"
    max_duration: float = 180.0
    scenes: list[ScenePlan] = field(default_factory=list)
    log: LogFn = field(default=lambda _msg: None)

    def __post_init__(self) -> None:
        self.episode_id = self.episode_id.zfill(4) if self.episode_id.isdigit() else self.episode_id
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.dirs = {
            "visuals": self.root / "visuals",
            "shots": self.root / "shots",
            "audio": self.root / "audio",
            "edit": self.root / "edit",
            "master": self.root / "master",
            "delivery": self.root / "delivery",
            "factory": self.root / "factory",
        }
        for path in self.dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        self.director = DirectingEngine()

    def _emit(self, message: str) -> None:
        self.log(message)

    def load_script(self) -> str:
        text = self.script_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ValueError(f"Empty script: {self.script_path}")
        return text

    def build_scene_plan(self, script_text: str) -> list[ScenePlan]:
        raw = plan_scenes(script_text)
        scenes: list[ScenePlan] = []

        for index, scene in enumerate(raw):
            scene_id = f"episode-{self.episode_id}:scene-{index + 1:03d}"
            direction = self.director.direct(
                scene_id=scene_id,
                title=scene["title"],
                text=scene["text"],
                duration=18.0,
            )
            scenes.append(
                ScenePlan(
                    index=index,
                    title=scene["title"],
                    text=scene["text"],
                    duration=18.0,
                    movement=direction["camera"]["movement"],
                    direction=direction,
                )
            )

        if not scenes:
            raise ValueError("No scenes could be planned from the supplied script")

        total = sum(scene.duration for scene in scenes) + 8.0
        if total > self.max_duration:
            scale = (self.max_duration - 8.0) / sum(scene.duration for scene in scenes)
            for scene in scenes:
                scene.duration = max(8.0, round(scene.duration * scale, 1))
                scene.direction["motion"]["duration"] = scene.duration

        self.scenes = scenes
        return scenes

    def generate_visual_assets(self) -> list[Path]:
        self._emit("Generating cinematic visual assets...")
        assets: list[Path] = []

        title_path = self.dirs["visuals"] / "00_title.png"
        generate_title_card(
            "AURELIA MAKER",
            f"Episode {self.episode_id} — Cinematic Production Factory",
            title_path,
        )
        assets.append(title_path)

        for scene in self.scenes:
            path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}.png"
            generate_scene_image(scene.index, scene.title, scene.text, path)
            assets.append(path)

        return assets

    def synthesize_narration(self, script_text: str) -> Path:
        self._emit("Synthesizing narration (TTS)...")
        narration_path = self.dirs["audio"] / "narration.wav"
        synthesize_script(script_text, narration_path)
        if not narration_path.exists() or narration_path.stat().st_size < 100:
            raise RuntimeError("Narration synthesis failed")
        return narration_path

    def build_subtitles(self, narration_path: Path) -> Path:
        self._emit("Building subtitle track...")
        total_duration = probe_duration(narration_path)
        if total_duration <= 0:
            total_duration = sum(scene.duration for scene in self.scenes) + 8.0

        intro_duration = 8.0
        body_duration = max(total_duration - intro_duration, 1.0)
        per_scene = body_duration / max(len(self.scenes), 1)

        lines: list[str] = []
        cue_index = 1
        cursor = 0.0

        def fmt(seconds: float) -> str:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            ms = int((seconds - int(seconds)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        intro_text = f"AURELIA MAKER — Episode {self.episode_id}"
        lines.extend([str(cue_index), f"{fmt(cursor)} --> {fmt(cursor + intro_duration)}", intro_text, ""])
        cue_index += 1
        cursor += intro_duration

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

        title_clip = self.dirs["shots"] / "00_title.mp4"
        engine.render_motion(
            assets[0], title_clip, duration=8.0,
            camera={"movement": "push_in", "zoom_start": 1.0, "zoom_end": 1.12},
            lighting={"brightness": 1.05, "contrast": 1.08, "saturation": 1.1},
        )
        clips.append(title_clip)

        for scene, asset in zip(self.scenes, assets[1:]):
            out = self.dirs["shots"] / f"scene_{scene.index + 1:02d}.mp4"
            direction = scene.direction
            camera_plan = direction["camera"]
            motion_plan = direction["motion"]
            lighting_plan = direction["lighting"]
            depth_plan = direction["depth"]

            zoom_start = float(motion_plan.get("start", {}).get("zoom", 1.0))
            zoom_end = float(motion_plan.get("end", {}).get("zoom", 1.08))
            key = lighting_plan.get("key") or {}
            fill = lighting_plan.get("fill") or {}
            brightness = 1.0 + min(float(key.get("intensity", 0.7)) * 0.04, 0.06)
            contrast = 1.04 + min(float(fill.get("intensity", 0.2)) * 0.04, 0.03)
            saturation = 1.08 if direction["environment"] in {"space", "abstract"} else 1.04

            engine.render_motion(
                asset,
                out,
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
                    "blur": float((lighting_plan.get("atmosphere") or {}).get("haze", 0.0)) * 0.8,
                },
                vfx={
                    "blur": float((lighting_plan.get("atmosphere") or {}).get("fog", 0.0)) * 0.4,
                },
            )
            clips.append(out)

        return clips

    def assemble_edit(self, clips: list[Path], narration_path: Path, music_path: Path) -> Path:
        self._emit("Editing — concatenating shots and mixing audio...")
        video_only = self.dirs["edit"] / "video_concat.mp4"
        concat_clips(clips, video_only)
        mixed = self.dirs["edit"] / "edit_mixed.mp4"
        mix_narration_and_music(video_only, narration_path, mixed, music_path)
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
        outputs = {"youtube": final_youtube}

        if self.profile in {"tiktok", "both"}:
            final_tiktok = self.dirs["delivery"] / f"episode-{self.episode_id}-tiktok.mp4"
            master_encode(subtitled, final_tiktok, profile="tiktok")
            outputs["tiktok"] = final_tiktok

        final_alias = self.dirs["delivery"] / f"episode-{self.episode_id}-FINAL.mp4"
        final_alias.write_bytes(final_youtube.read_bytes())
        outputs["final"] = final_alias

        qc = validate_master(final_alias, min_duration=30.0)
        if not qc["passed"]:
            raise RuntimeError(f"QC failed: {qc}")

        manifest = {
            "episode_id": self.episode_id,
            "duration": probe_duration(final_alias),
            "outputs": {key: str(path) for key, path in outputs.items()},
            "qc": qc,
            "directing": [scene.direction for scene in self.scenes],
            "timestamp": time.time(),
        }
        (self.root / "production_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        self._emit(f"FINAL MP4 ready: {final_alias}")
        return outputs

    def produce(self) -> dict[str, Any]:
        self._emit(f"Starting Factory production — Episode {self.episode_id}")
        script_text = self.load_script()
        self.build_scene_plan(script_text)
        assets = self.generate_visual_assets()
        narration = self.synthesize_narration(script_text)
        srt = self.build_subtitles(narration)
        duration = max(probe_duration(narration), sum(s.duration for s in self.scenes) + 8.0)
        music_path = self.dirs["audio"] / "ambient_music.wav"
        generate_ambient_music(duration + 4.0, music_path)
        clips = self.render_shots(assets)
        edit = self.assemble_edit(clips, narration, music_path)
        outputs = self.finish(edit, srt)
        return {
            "episode_id": self.episode_id,
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
    log: LogFn | None = None,
) -> dict[str, Any]:
    production = EpisodeProduction(
        episode_id=episode_id,
        root=Path(output_root) / f"episode-{episode_id.zfill(4) if episode_id.isdigit() else episode_id}",
        script_path=Path(script_path),
        profile=profile,
        log=log or (lambda _m: None),
    )
    return production.produce()


__all__ = ["EpisodeProduction", "produce_episode", "ScenePlan"]
