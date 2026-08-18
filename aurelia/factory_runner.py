"""AURELIA Maker — single production path from Chat request to FINAL MP4."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .episode_engine import EpisodeProduction
from .production_contract import PRODUCTION_STAGES
from .production_pipeline import build_production_pipeline


@dataclass
class ProductionJob:
    job_id: str
    episode_id: str
    status: str = "QUEUED"
    stage: str = ""
    progress: float = 0.0
    final_mp4: str = ""
    error: str = ""
    logs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class FactoryRunner:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.output = self.root / "output"
        self.output.mkdir(exist_ok=True)
        self.scripts = self.root / "scripts"
        self.scripts.mkdir(exist_ok=True)
        self.jobs: dict[str, ProductionJob] = {}
        self._lock = threading.Lock()

    def _log(self, job: ProductionJob, message: str) -> None:
        line = message.strip()
        with self._lock:
            job.logs.append(line)
        print(line, flush=True)

    def _set_stage(self, job: ProductionJob, stage: str, progress: float) -> None:
        with self._lock:
            job.stage = stage
            job.progress = max(0.0, min(100.0, progress))

    def resolve_episode_id(self, text: str) -> str | None:
        for pattern in (
            r"(?:create|produce|make|generate|build)\s+episode\s+(\d{1,4})",
            r"episode\s+(\d{1,4})",
            r"\b(\d{4})\b",
        ):
            match = re.search(pattern, text.lower())
            if match:
                return match.group(1).zfill(4)
        return None

    def default_script_path(self, episode_id: str) -> Path:
        return self.scripts / f"episode-{episode_id}.txt"

    def ensure_episode_script(self, episode_id: str) -> Path:
        path = self.default_script_path(episode_id)
        if not path.exists():
            raise FileNotFoundError(f"No script supplied for Episode {episode_id}: {path}")
        return path

    def create_job(self, episode_id: str, profile: str = "both", script_path: Path | None = None) -> ProductionJob:
        episode_id = episode_id.zfill(4) if episode_id.isdigit() else episode_id
        job = ProductionJob(job_id=str(uuid.uuid4())[:8], episode_id=episode_id, metadata={"profile": profile})
        if script_path is not None:
            job.metadata["script"] = str(script_path)
        with self._lock:
            self.jobs[job.job_id] = job
        return job

    @staticmethod
    def _extract_metadata(script_text: str) -> tuple[str, str]:
        title = ""
        language = ""
        for line in script_text.splitlines():
            match = re.match(r"^\s*(?:title|العنوان)\s*[:=]\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                continue
            match = re.match(r"^\s*(?:language|lang|اللغة)\s*[:=]\s*(.+?)\s*$", line, re.IGNORECASE)
            if match:
                language = match.group(1).strip()
        if not title:
            heading = next((m.group(1).strip() for m in re.finditer(r"^\s*#\s+(.+?)\s*$", script_text, re.MULTILINE)), "")
            title = heading
        if not title:
            raise ValueError("Production request must contain a real title (Title: ... or a Markdown heading)")
        if not language:
            raise ValueError("Production request must contain the requested language (Language: ...)")
        return title, language

    def run_episode_production(self, job: ProductionJob, script_path: Path, profile: str = "both") -> dict[str, Any]:
        script_text = script_path.read_text(encoding="utf-8").strip()
        if not script_text:
            raise ValueError(f"Empty production request: {script_path}")
        title, language = self._extract_metadata(script_text)

        production_root = self.output / f"episode-{job.episode_id}"
        pipeline = build_production_pipeline(production_root / "factory")
        run = pipeline.orchestrator.create_run(
            project=f"episode-{job.episode_id}",
            metadata={"mode": "production", "source": "chat", "episode_id": job.episode_id, "title": title, "language": language, "profile": profile},
        )
        job.metadata.update({"run_id": run.id, "title": title, "language": language})

        production = EpisodeProduction(
            episode_id=job.episode_id,
            root=production_root,
            script_path=script_path,
            profile=profile,
            log=lambda message: self._log(job, f"[FACTORY] {message}"),
        )
        state: dict[str, Any] = {
            "script": str(script_path.resolve()), "text": script_text, "episode": job.episode_id,
            "title": title, "language": language, "profile": profile, "root": str(self.root.resolve()), "source": "chat",
        }

        assets: list[Path] = []
        narration: Path | None = None
        subtitles: Path | None = None
        music: Path | None = None
        edit: Path | None = None
        graded: Path | None = None
        subtitled: Path | None = None
        final_outputs: dict[str, Path] = {}

        def script_processor(data):
            return {**data, "stage": "SCRIPT", "text": production.load_script()}

        def source_stage(stage: str, key: str, extra: dict[str, Any] | None = None):
            def process(data):
                payload = {"source": "chat", "episode_id": job.episode_id, "title": title, "language": language}
                if extra:
                    payload.update(extra)
                return {**data, "stage": stage, key: payload}
            return process

        def development_processor(data):
            return source_stage("DEVELOPMENT", "development", {"source_text_sha256": hashlib.sha256(script_text.encode("utf-8")).hexdigest()})(data)

        def story_processor(data):
            return {**data, "stage": "STORY", "story": {"title": title, "language": language, "narrative": script_text, "source": "chat"}}

        def world_processor(data):
            return {**data, "stage": "WORLD", "world": {"episode_id": job.episode_id, "title": title, "language": language, "premise": script_text, "source": "chat"}}

        def character_processor(data):
            return {**data, "stage": "CHARACTER", "character": {"episode_id": job.episode_id, "title": title, "language": language, "source_text": script_text, "source": "chat"}}

        def series_bible_processor(data):
            return {**data, "stage": "SERIES_BIBLE", "series_bible": {"episode_id": job.episode_id, "title": title, "language": language, "premise": script_text, "source": "chat"}}

        def research_processor(data):
            return source_stage("RESEARCH", "research", {"grounded_in_request": True})(data)

        def preproduction_processor(data):
            return source_stage("PRE_PRODUCTION", "pre_production", {"ready": True})(data)

        def sequence_processor(data):
            production.build_scene_plan(data["text"])
            return {**data, "stage": "SEQUENCE", "scene_count": len(production.scenes)}

        def scene_processor(data):
            return {**data, "stage": "SCENE", "scene_count": len(production.scenes)}

        def shot_processor(data):
            return {**data, "stage": "SHOT", "shots": [scene.direction for scene in production.scenes]}

        def storyboard_processor(data):
            return {**data, "stage": "STORYBOARD", "storyboard": {"scene_count": len(production.scenes)}}

        def animatic_processor(data):
            return {**data, "stage": "ANIMATIC", "animatic": {"scene_count": len(production.scenes)}}

        def visual_processor(data):
            nonlocal assets
            assets = production.generate_visual_assets()
            return {**data, "stage": "VISUAL", "assets": [str(p) for p in assets]}

        def asset_processor(data):
            return {**data, "stage": "ASSET", "assets": [str(p) for p in assets]}

        def camera_processor(data):
            return {**data, "stage": "CAMERA", "camera": [s.direction["camera"] for s in production.scenes]}

        def depth_processor(data):
            return {**data, "stage": "DEPTH", "depth": [s.direction["depth"] for s in production.scenes]}

        def motion_processor(data):
            return {**data, "stage": "MOTION", "motion": [s.direction["motion"] for s in production.scenes]}

        def light_processor(data):
            return {**data, "stage": "LIGHT", "lighting": [s.direction["lighting"] for s in production.scenes]}

        def narration_processor(data):
            nonlocal narration, subtitles
            narration = production.synthesize_narration(data["text"])
            subtitles = production.build_subtitles(narration)
            return {**data, "stage": "NARRATION", "narration": str(narration), "subtitle_source": str(subtitles)}

        def music_processor(data):
            nonlocal music
            from .media import generate_ambient_music
            music = production.dirs["audio"] / "ambient_music.wav"
            generate_ambient_music(max(production.max_duration, 30.0) + 4.0, music)
            return {**data, "stage": "MUSIC", "music": str(music)}

        def edit_processor(data):
            nonlocal edit
            if narration is None or music is None:
                raise RuntimeError("EDIT requires narration and music")
            edit = production.assemble_edit(production.render_shots(assets), narration, music)
            return {**data, "stage": "EDIT", "edit": str(edit)}

        def color_processor(data):
            nonlocal graded
            from .media import apply_color_grade
            if edit is None:
                raise RuntimeError("COLOR requires edit")
            graded = production.dirs["master"] / "graded.mp4"
            apply_color_grade(edit, graded)
            return {**data, "stage": "COLOR", "graded": str(graded)}

        def subtitle_processor(data):
            nonlocal subtitled
            from .media import burn_subtitles
            if graded is None or subtitles is None:
                raise RuntimeError("SUBTITLE requires graded video and subtitle track")
            subtitled = production.dirs["master"] / "subtitled.mp4"
            burn_subtitles(graded, subtitles, subtitled)
            return {**data, "stage": "SUBTITLE", "subtitled": str(subtitled)}

        def master_processor(data):
            from .media import master_encode
            if subtitled is None:
                raise RuntimeError("MASTER requires subtitled video")
            youtube = production.dirs["delivery"] / f"episode-{job.episode_id}-youtube.mp4"
            master_encode(subtitled, youtube, profile="youtube")
            final_outputs["youtube"] = youtube
            if profile in {"tiktok", "both"}:
                tiktok = production.dirs["delivery"] / f"episode-{job.episode_id}-tiktok.mp4"
                master_encode(subtitled, tiktok, profile="tiktok")
                final_outputs["tiktok"] = tiktok
            return {**data, "stage": "MASTER", "outputs": {k: str(v) for k, v in final_outputs.items()}}

        def qc_processor(data):
            from .media import validate_master
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("QC requires master output")
            qc = validate_master(final, min_duration=30.0)
            if not qc["passed"]:
                raise RuntimeError(f"QC failed: {qc}")
            return {**data, "stage": "QC", "qc": qc}

        def delivery_processor(data):
            final = final_outputs["youtube"]
            alias = production.dirs["delivery"] / f"episode-{job.episode_id}-FINAL.mp4"
            alias.write_bytes(final.read_bytes())
            final_outputs["final"] = alias
            manifest = {
                "episode_id": job.episode_id, "title": title, "language": language, "profile": profile,
                "source": "chat", "source_script": str(script_path.resolve()),
                "outputs": {k: str(v) for k, v in final_outputs.items()},
                "directing": [scene.direction for scene in production.scenes],
            }
            (production.root / "production_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            return {**data, "stage": "DELIVERY", "artifact": str(alias), "manifest": str(production.root / "production_manifest.json")}

        processors = {
            "SCRIPT": script_processor, "DEVELOPMENT": development_processor, "STORY": story_processor,
            "WORLD": world_processor, "CHARACTER": character_processor, "SERIES_BIBLE": series_bible_processor,
            "RESEARCH": research_processor, "PRE_PRODUCTION": preproduction_processor, "SEQUENCE": sequence_processor,
            "SCENE": scene_processor, "SHOT": shot_processor, "STORYBOARD": storyboard_processor,
            "ANIMATIC": animatic_processor, "VISUAL": visual_processor, "ASSET": asset_processor,
            "CAMERA": camera_processor, "DEPTH": depth_processor, "MOTION": motion_processor, "LIGHT": light_processor,
            "VFX": source_stage("VFX", "vfx"), "ATMOSPHERE": source_stage("ATMOSPHERE", "atmosphere"),
            "NARRATION": narration_processor, "DIALOGUE": source_stage("DIALOGUE", "dialogue"),
            "SOUND": source_stage("SOUND", "sound"), "MUSIC": music_processor, "AUDIO": source_stage("AUDIO", "audio"),
            "EDIT": edit_processor, "COLOR": color_processor, "SUBTITLE": subtitle_processor,
            "MASTER": master_processor, "QC": qc_processor, "DELIVERY": delivery_processor,
        }

        total = len(PRODUCTION_STAGES)
        current = dict(state)
        for index, stage in enumerate(PRODUCTION_STAGES):
            progress = (index / total) * 100.0
            self._set_stage(job, stage, progress)
            self._log(job, f"[FACTORY] {stage} ({progress:.0f}%)")
            execution = pipeline.execute_stage(
                project=f"episode-{job.episode_id}", stage=stage, unit_type="production_stage",
                unit_id=f"episode-{job.episode_id}:{stage}", input_data=current,
                processor=processors[stage], validator=lambda result: isinstance(result, dict) and bool(result), run_id=run.id,
            )
            if execution.status != "COMPLETED":
                raise RuntimeError(f"Production stage failed: {stage}: {execution.error}")
            current.update(execution.output)

        saved_run = pipeline.orchestrator.runs.get(run.id)
        if saved_run is not None:
            saved_run.mark_completed()
            pipeline.orchestrator.runs.save(saved_run)
        if "final" not in final_outputs:
            raise RuntimeError("Canonical production completed without FINAL MP4")

        job.final_mp4 = str(final_outputs["final"])
        self._set_stage(job, "DELIVERY", 100.0)
        job.status = "COMPLETED"
        self._log(job, f"[FACTORY] FINAL MP4: {job.final_mp4}")
        return {"episode_id": job.episode_id, "title": title, "language": language, "final_mp4": job.final_mp4, "outputs": {k: str(v) for k, v in final_outputs.items()}, "scenes": len(production.scenes)}

    def execute(self, episode_id: str, profile: str = "both", script_path: Path | None = None) -> ProductionJob:
        job = self.create_job(episode_id, profile, script_path)
        job.status = "RUNNING"
        script = script_path or self.ensure_episode_script(job.episode_id)
        try:
            job.metadata["result"] = self.run_episode_production(job, script, profile)
            return job
        except Exception as exc:
            job.status = "FAILED"
            job.error = str(exc)
            self._log(job, f"[ERROR] {exc}")
            self._log(job, traceback.format_exc())
            raise

    def execute_async(self, episode_id: str, profile: str = "both", script_path: Path | None = None) -> ProductionJob:
        job = self.create_job(episode_id, profile, script_path)
        def worker() -> None:
            job.status = "RUNNING"
            try:
                script = script_path or self.ensure_episode_script(job.episode_id)
                job.metadata["result"] = self.run_episode_production(job, script, profile)
            except Exception as exc:
                job.status = "FAILED"
                job.error = str(exc)
                self._log(job, f"[ERROR] {exc}")
                self._log(job, traceback.format_exc())
        threading.Thread(target=worker, daemon=False).start()
        return job

    def handle_chat(self, message: str) -> dict[str, Any]:
        if message.strip().lower() in {"status", "progress", "state"}:
            active = [j for j in self.jobs.values() if j.status in {"RUNNING", "QUEUED"}]
            if not active:
                return {"reply": "No active production.", "action": None}
            job = active[-1]
            return {"reply": f"Episode {job.episode_id}: {job.status} — {job.stage} ({job.progress:.0f}%)", "action": None, "job_id": job.job_id}
        return {"reply": "Use the Chat production entry with Episode ID, Title, Language and the complete script.", "action": "await_script"}
