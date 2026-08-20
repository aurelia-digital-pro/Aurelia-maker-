"""AURELIA Maker — canonical episode production engine (Factory → FINAL MP4).

This module now uses the canonical visual provider (aurelia.providers_visual)
for all production visual assets. The legacy procedural asset_generator has
been isolated and MUST NOT be invoked by canonical production.

Production is fail-closed: any failure in AI visual generation, TTS, or media
assembly raises an exception and stops the job.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .providers_visual import generate_scene_image_with_provenance
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
    title: str = ""
    scenes: list[ScenePlan] = field(default_factory=list)
    log: LogFn = field(default=lambda _msg: None)

    def __post_init__(self) -> None:
        self.episode_id = self.episode_id.zfill(4) if self.episode_id.isdigit() else self.episode_id
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.dirs = {name: self.root / name for name in ("visuals", "shots", "audio", "edit", "master", "delivery", "factory")}
        for path in self.dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        self.director = DirectingEngine()
        if not self.title:
            self.title = self._extract_title(self.script_path.read_text(encoding="utf-8"))

    @staticmethod
    def _extract_title(request_text: str) -> str:
        for line in request_text.splitlines():
            match = re.match(r"^\s*(?:title|العنوان)\s*[:=]\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        heading = next((m.group(1).strip() for m in re.finditer(r"^\s*#\s+(.+?)\s*$", request_text, re.MULTILINE)), "")
        if heading:
            return heading
        raise ValueError("Production request contains no real title")

    @staticmethod
    def _extract_script_body(request_text: str) -> str:
        lines = []
        for line in request_text.splitlines():
            if re.match(r"^\s*(?:title|العنوان|language|lang|اللغة)\s*[:=]\s*.+?\s*$", line, re.IGNORECASE):
                continue
            lines.append(line)
        body = "\n".join(lines).strip()
        if not body:
            raise ValueError("Production request contains no episode script content")
        return body

    def _emit(self, message: str) -> None:
        self.log(message)

    def load_script(self) -> str:
        request_text = self.script_path.read_text(encoding="utf-8").strip()
        if not request_text:
            raise ValueError(f"Empty script: {self.script_path}")
        return self._extract_script_body(request_text)

    def build_scene_plan(self, script_text: str) -> list[ScenePlan]:
        raw = plan_scenes(script_text)
        scenes: list[ScenePlan] = []
        for index, scene in enumerate(raw):
            scene_id = f"episode-{self.episode_id}:scene-{index + 1:03d}"
            # Director returns a dict containing camera/motion/depth/lighting etc.
            direction = self.director.direct(scene_id=scene_id, title=scene["title"], text=scene["text"], duration=18.0)
            duration = float(direction.get("motion", {}).get("duration") or 18.0)
            scenes.append(ScenePlan(index=index, title=scene["title"], text=scene["text"], duration=duration, movement=direction.get("camera", {}).get("movement", "push_in"), direction=direction))
        if not scenes:
            raise ValueError("No scenes could be planned from the supplied script")
        total = sum(scene.duration for scene in scenes) + 8.0
        if total > self.max_duration:
            scale = (self.max_duration - 8.0) / sum(scene.duration for scene in scenes)
            for scene in scenes:
                scene.duration = max(5.0, round(scene.duration * scale, 1))
                if "motion" in scene.direction:
                    scene.direction["motion"]["duration"] = scene.duration
        self.scenes = scenes
        return scenes

    def generate_visual_assets(self) -> list[Path]:
        """Generate AI visuals for title + scenes using the canonical visual provider.

        This function is fail-closed: any provider error must raise and stop production.
        It records provenance and writes a per-run production_manifest.json entry for visuals.
        """
        self._emit("Generating cinematic visual assets (AI backend)...")
        assets: list[Path] = []
        provenance: list[dict[str, Any]] = []

        # Title card via AI provider (scene_index = -1)
        title_path = self.dirs["visuals"] / "00_title.png"
        out, prov = generate_scene_image_with_provenance(-1, f"TITLE: {self.title}", self.title, title_path, direction={"type": "title_card"})
        assets.append(out)
        provenance.append(prov)

        # Scenes
        for scene in self.scenes:
            path = self.dirs["visuals"] / f"scene_{scene.index + 1:02d}.png"
            out, prov = generate_scene_image_with_provenance(scene.index, scene.title, scene.text, path, direction=scene.direction)
            assets.append(out)
            provenance.append(prov)

        # Validate assets
        for p in assets:
            if not p.exists() or p.stat().st_size == 0:
                raise RuntimeError(f"Visual generation produced invalid asset: {p}")

        # write visuals manifest
        visuals_entry = {"generated_at": time.time(), "assets": provenance}
        (self.root / "visuals_provenance.json").write_text(json.dumps(visuals_entry, indent=2, ensure_ascii=False), encoding="utf-8")
        return assets

    def synthesize_narration(self, script_text: str) -> Path:
        self._emit("Synthesizing narration (configured TTS)...")
        narration_path = self.dirs["audio"] / "narration.wav"
        synthesize_script(script_text, narration_path)
        if not narration_path.exists() or narration_path.stat().st_size < 1000:
            raise RuntimeError("Narration synthesis failed")
        self._emit(f"Narration generated: {narration_path} ({narration_path.stat().st_size} bytes)")
        return narration_path

    def build_subtitles(self, narration_path: Path) -> Path:
        self._emit("Building subtitle track from narration timing...")
        total_duration = probe_duration(narration_path)
        if total_duration <= 0:
            total_duration = sum(scene.duration for scene in self.scenes) + 8.0
        # Use scene durations to place cues deterministically
        intro_duration = 8.0
        body_duration = max(total_duration - intro_duration, 1.0)
        per_scene = body_duration / max(len(self.scenes), 1)
        lines: list[str] = []
        cue_index = 1
        cursor = 0.0

        def fmt(seconds: float) -> str:
            h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60); ms = int((seconds - int(seconds)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        lines.extend([str(cue_index), f"{fmt(cursor)} --> {fmt(cursor + intro_duration)}", self.title, ""])
        cue_index += 1; cursor += intro_duration
        for scene in self.scenes:
            end = cursor + per_scene
            snippet = re.sub(r"\s+", " ", scene.text.strip())
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            lines.extend([str(cue_index), f"{fmt(cursor)} --> {fmt(end)}", snippet, ""])
            cue_index += 1; cursor = end
        srt_path = self.root / f"episode-{self.episode_id}.srt"
        srt_path.write_text("\n".join(lines), encoding="utf-8")
        return srt_path

    def render_shots(self, assets: list[Path]) -> list[Path]:
        from .visuals import CinematicVisualEngine
        self._emit("Rendering cinematic shots with content-driven camera motion...")
        engine = CinematicVisualEngine()
        clips: list[Path] = []
        # title shot
        title_clip = self.dirs["shots"] / "00_title.mp4"
        engine.render_motion(assets[0], title_clip, duration=8.0, camera={"movement": "push_in", "zoom_start": 1.0, "zoom_end": 1.12}, lighting={"brightness": 1.05, "contrast": 1.08, "saturation": 1.02}, atmosphere={}, vfx={})
        clips.append(title_clip)
        # scene shots
        for scene, asset in zip(self.scenes, assets[1:]):
            out = self.dirs["shots"] / f"scene_{scene.index + 1:02d}.mp4"
            direction = scene.direction
            camera_plan = direction.get("camera", {})
            motion_plan = direction.get("motion", {})
            lighting_plan = direction.get("lighting", {})
            depth_plan = direction.get("depth", {})
            zoom_start = float(motion_plan.get("start", {}).get("zoom", 1.0))
            zoom_end = float(motion_plan.get("end", {}).get("zoom", zoom_start + 0.08))
            engine.render_motion(asset, out, duration=scene.duration, camera={"movement": camera_plan.get("movement", "push_in"), "zoom_start": zoom_start, "zoom_end": zoom_end}, depth=depth_plan, lighting=lighting_plan, atmosphere=lighting_plan.get("atmosphere", {}), vfx={})
            clips.append(out)
        return clips

    def assemble_edit(self, clips: list[Path], narration_path: Path, music_path: Path) -> Path:
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
            "title": self.title,
            "duration": probe_duration(final_alias),
            "outputs": {key: str(path) for key, path in outputs.items()},
            "qc": qc,
            "directing": [s.direction for s in self.scenes],
        }
        (self.root / "production_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        self._emit(f"FINAL MP4 ready: {final_alias}")
        return outputs

    def produce(self) -> dict[str, Any]:
        self._emit(f"Starting Factory production — Episode {self.episode_id}: {self.title}")
        script_text = self.load_script()
        self.build_scene_plan(script_text)
        assets = self.generate_visual_assets()
        narration = self.synthesize_narration(script_text)
        srt = self.build_subtitles(narration)
        clips = self.render_shots(assets)
        music = generate_ambient_music(max(10.0, sum(s.duration for s in self.scenes)), self.dirs["audio"] / "music.wav")
        edit = self.assemble_edit(clips, narration, music)
        outputs = self.finish(edit, srt)
        return {"episode_id": self.episode_id, "title": self.title, "final_mp4": str(outputs["final"]), "outputs": {k: str(v) for k, v in outputs.items()}, "duration": probe_duration(outputs["final"])}


def produce_episode(episode_id: str, script_path: str | Path, output_root: str | Path, profile: str = "both", log: LogFn | None = None) -> dict[str, Any]:
    production = EpisodeProduction(episode_id=episode_id, root=Path(output_root) / f"episode-{episode_id.zfill(4) if episode_id.isdigit() else episode_id}", script_path=Path(script_path), profile=profile, log=(log or (lambda _m: None)))
    return production.produce()


__all__ = ["EpisodeProduction", "produce_episode", "ScenePlan"]
