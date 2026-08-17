"""AURELIA Maker — Factory runner: canonical Chat/CLI to FINAL MP4 path."""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .episode_engine import EpisodeProduction
from .production_contract import PRODUCTION_STAGES
from .production_pipeline import build_production_pipeline

LogFn = Callable[[str], None]
ProgressFn = Callable[[str, str], None]


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
    """Runs episode production through the canonical Factory pipeline."""

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
        job.stage = stage
        job.progress = progress

    def resolve_episode_id(self, text: str) -> str | None:
        patterns = [
            r"(?:create|produce|make|generate|build)\s+episode\s+(\d{1,4})",
            r"episode\s+(\d{1,4})",
            r"(\d{4})",
        ]
        lowered = text.lower().strip()
        for pattern in patterns:
            match = re.search(pattern, lowered)
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
        job = ProductionJob(
            job_id=str(uuid.uuid4())[:8],
            episode_id=episode_id.zfill(4) if episode_id.isdigit() else episode_id,
            metadata={"profile": profile},
        )
        if script_path:
            job.metadata["script"] = str(script_path)
        self.jobs[job.job_id] = job
        return job

    def run_factory_metadata(self, job: ProductionJob, script_path: Path, profile: str) -> None:
        """Execute SCRIPT through PRE_PRODUCTION for provenance before live rendering."""
        pipeline = build_production_pipeline(self.output / f"episode-{job.episode_id}" / "factory")
        run = pipeline.orchestrator.create_run(
            project=f"episode-{job.episode_id}",
            metadata={"mode": "factory", "profile": profile},
        )
        job.metadata["run_id"] = getattr(run, "id", getattr(run, "run_id", ""))
        processors = pipeline.build_real_processors()
        early_stages = PRODUCTION_STAGES[: PRODUCTION_STAGES.index("PRE_PRODUCTION") + 1]
        current = {
            "script": str(script_path.resolve()),
            "episode": job.episode_id,
            "profile": profile,
            "root": str(self.root),
        }
        total = len(PRODUCTION_STAGES)
        for index, stage in enumerate(early_stages):
            self._set_stage(job, stage, (index / total) * 15.0)
            self._log(job, f"[FACTORY] {stage}")
            execution = pipeline.execute_stage(
                project=f"episode-{job.episode_id}",
                stage=stage,
                unit_type="production_stage",
                unit_id=f"episode-{job.episode_id}:{stage}",
                input_data=current,
                processor=processors[stage],
                validator=lambda result: isinstance(result, dict) and bool(result),
                run_id=job.metadata.get("run_id"),
            )
            if execution.status != "COMPLETED":
                raise RuntimeError(f"Factory stage failed: {stage}")
            current.update(execution.output)

    def run_episode_production(self, job: ProductionJob, script_path: Path, profile: str = "both") -> dict[str, Any]:
        """Run the real episode through ProductionPipeline.execute_production()."""
        self._set_stage(job, "PRODUCTION", 20.0)
        self._log(job, f"[FACTORY] Starting canonical production — Episode {job.episode_id}")

        pipeline = build_production_pipeline(
            self.output / f"episode-{job.episode_id}" / "factory"
        )
        production = EpisodeProduction(
            episode_id=job.episode_id,
            root=self.output / f"episode-{job.episode_id}",
            script_path=script_path,
            profile=profile,
            log=lambda message: self._log(job, f"[FACTORY] {message}"),
        )
        state: dict[str, Any] = {
            "script": str(script_path.resolve()),
            "episode": job.episode_id,
            "profile": profile,
            "root": str(self.root),
            "production": production,
        }
        assets: list[Path] = []
        narration: Path | None = None
        subtitles: Path | None = None
        music: Path | None = None
        edit: Path | None = None
        graded: Path | None = None
        subtitled: Path | None = None
        final_outputs: dict[str, Path] = {}

        def stage_passthrough(data: dict[str, Any], stage: str) -> dict[str, Any]:
            return {**data, "stage": stage}

        def script_processor(data: dict[str, Any]) -> dict[str, Any]:
            text = production.load_script()
            return {**data, "stage": "SCRIPT", "text": text}

        def sequence_processor(data: dict[str, Any]) -> dict[str, Any]:
            scenes = production.build_scene_plan(data["text"])
            return {**data, "stage": "SEQUENCE", "scenes": scenes}

        def scene_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "stage": "SCENE", "scene_count": len(production.scenes)}

        def shot_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {
                **data,
                "stage": "SHOT",
                "shots": [scene.direction for scene in production.scenes],
            }

        def visual_processor(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal assets
            assets = production.generate_visual_assets()
            return {**data, "stage": "VISUAL", "assets": [str(p) for p in assets]}

        def asset_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "stage": "ASSET", "assets": [str(p) for p in assets]}

        def camera_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "stage": "CAMERA", "camera": [s.direction["camera"] for s in production.scenes]}

        def depth_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "stage": "DEPTH", "depth": [s.direction["depth"] for s in production.scenes]}

        def motion_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "stage": "MOTION", "motion": [s.direction["motion"] for s in production.scenes]}

        def light_processor(data: dict[str, Any]) -> dict[str, Any]:
            return {**data, "stage": "LIGHT", "lighting": [s.direction["lighting"] for s in production.scenes]}

        def narration_processor(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal narration, subtitles
            narration = production.synthesize_narration(data["text"])
            subtitles = production.build_subtitles(narration)
            return {**data, "stage": "NARRATION", "narration": str(narration), "subtitle_source": str(subtitles)}

        def music_processor(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal music
            duration = max(production.max_duration, 30.0)
            music = production.dirs["audio"] / "ambient_music.wav"
            from .media import generate_ambient_music
            generate_ambient_music(duration + 4.0, music)
            return {**data, "stage": "MUSIC", "music": str(music)}

        def edit_processor(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal edit
            if narration is None or music is None:
                raise RuntimeError("EDIT requires narration and music")
            clips = production.render_shots(assets)
            edit = production.assemble_edit(clips, narration, music)
            return {**data, "stage": "EDIT", "edit": str(edit)}

        def color_processor(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal graded
            from .media import apply_color_grade
            if edit is None:
                raise RuntimeError("COLOR requires edit")
            graded = production.dirs["master"] / "graded.mp4"
            apply_color_grade(edit, graded)
            production._emit("Color grading complete.")
            return {**data, "stage": "COLOR", "graded": str(graded)}

        def subtitle_processor(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal subtitled
            from .media import burn_subtitles
            if graded is None or subtitles is None:
                raise RuntimeError("SUBTITLE requires graded video and subtitle track")
            subtitled = production.dirs["master"] / "subtitled.mp4"
            burn_subtitles(graded, subtitles, subtitled)
            production._emit("Subtitles burned as the single text layer.")
            return {**data, "stage": "SUBTITLE", "subtitled": str(subtitled)}

        def master_processor(data: dict[str, Any]) -> dict[str, Any]:
            from .media import master_encode
            if subtitled is None:
                raise RuntimeError("MASTER requires subtitled video")
            final_youtube = production.dirs["delivery"] / f"episode-{job.episode_id}-youtube.mp4"
            master_encode(subtitled, final_youtube, profile="youtube")
            final_outputs["youtube"] = final_youtube
            if profile in {"tiktok", "both"}:
                final_tiktok = production.dirs["delivery"] / f"episode-{job.episode_id}-tiktok.mp4"
                master_encode(subtitled, final_tiktok, profile="tiktok")
                final_outputs["tiktok"] = final_tiktok
            return {**data, "stage": "MASTER", "outputs": {k: str(v) for k, v in final_outputs.items()}}

        def qc_processor(data: dict[str, Any]) -> dict[str, Any]:
            from .media import validate_master
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("QC requires master output")
            qc = validate_master(final, min_duration=30.0)
            if not qc["passed"]:
                raise RuntimeError(f"QC failed: {qc}")
            return {**data, "stage": "QC", "qc": qc}

        def delivery_processor(data: dict[str, Any]) -> dict[str, Any]:
            final = final_outputs["youtube"]
            alias = production.dirs["delivery"] / f"episode-{job.episode_id}-FINAL.mp4"
            alias.write_bytes(final.read_bytes())
            final_outputs["final"] = alias
            manifest = {
                "episode_id": job.episode_id,
                "profile": profile,
                "outputs": {k: str(v) for k, v in final_outputs.items()},
                "directing": [scene.direction for scene in production.scenes],
            }
            import json
            (production.root / "production_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {**data, "stage": "DELIVERY", "artifact": str(alias)}

        processors = {
            "SCRIPT": script_processor,
            "DEVELOPMENT": lambda d: stage_passthrough(d, "DEVELOPMENT"),
            "STORY": lambda d: stage_passthrough(d, "STORY"),
            "WORLD": lambda d: stage_passthrough(d, "WORLD"),
            "CHARACTER": lambda d: stage_passthrough(d, "CHARACTER"),
            "SERIES_BIBLE": lambda d: stage_passthrough(d, "SERIES_BIBLE"),
            "RESEARCH": lambda d: stage_passthrough(d, "RESEARCH"),
            "PRE_PRODUCTION": lambda d: stage_passthrough(d, "PRE_PRODUCTION"),
            "SEQUENCE": sequence_processor,
            "SCENE": scene_processor,
            "SHOT": shot_processor,
            "STORYBOARD": lambda d: stage_passthrough(d, "STORYBOARD"),
            "ANIMATIC": lambda d: stage_passthrough(d, "ANIMATIC"),
            "VISUAL": visual_processor,
            "ASSET": asset_processor,
            "CAMERA": camera_processor,
            "DEPTH": depth_processor,
            "MOTION": motion_processor,
            "LIGHT": light_processor,
            "ATMOSPHERE": lambda d: stage_passthrough(d, "ATMOSPHERE"),
            "VFX": lambda d: stage_passthrough(d, "VFX"),
            "NARRATION": narration_processor,
            "DIALOGUE": lambda d: stage_passthrough(d, "DIALOGUE"),
            "SOUND": lambda d: stage_passthrough(d, "SOUND"),
            "MUSIC": music_processor,
            "AUDIO": lambda d: stage_passthrough(d, "AUDIO"),
            "EDIT": edit_processor,
            "COLOR": color_processor,
            "SUBTITLE": subtitle_processor,
            "MASTER": master_processor,
            "QC": qc_processor,
            "DELIVERY": delivery_processor,
        }
        validators = {stage: (lambda result: isinstance(result, dict) and bool(result)) for stage in PRODUCTION_STAGES}

        def stage_progress(message: str) -> None:
            self._log(job, f"[FACTORY] {message}")

        # Execute the canonical stage chain. The actual media work is performed
        # by the processors above, not by the legacy produce_episode() shortcut.
        results = pipeline.execute_production(
            project=f"episode-{job.episode_id}",
            input_data=state,
            processors=processors,
            validators=validators,
            run_id=job.metadata.get("run_id"),
        )
        _ = results, stage_progress

        if "final" not in final_outputs:
            raise RuntimeError("Canonical pipeline completed without FINAL MP4")

        job.final_mp4 = str(final_outputs["final"])
        job.status = "COMPLETED"
        job.progress = 100.0
        job.stage = "DELIVERY"
        self._log(job, f"[FACTORY] FINAL MP4: {job.final_mp4}")
        return {
            "episode_id": job.episode_id,
            "final_mp4": job.final_mp4,
            "outputs": {k: str(v) for k, v in final_outputs.items()},
            "scenes": len(production.scenes),
        }

    def execute(self, episode_id: str, profile: str = "both", script_path: Path | None = None) -> ProductionJob:
        job = self.create_job(episode_id, profile, script_path)
        job.status = "RUNNING"
        script = script_path or self.ensure_episode_script(job.episode_id)
        try:
            self.run_factory_metadata(job, script, profile)
            result = self.run_episode_production(job, script, profile)
            job.metadata["result"] = result
            job.status = "COMPLETED"
        except Exception as exc:
            job.status = "FAILED"
            job.error = str(exc)
            self._log(job, f"[ERROR] {exc}")
            raise
        return job

    def execute_async(self, episode_id: str, profile: str = "both", script_path: Path | None = None) -> ProductionJob:
        job = self.create_job(episode_id, profile, script_path)

        def worker() -> None:
            job.status = "RUNNING"
            try:
                script = script_path or self.ensure_episode_script(job.episode_id)
                self.run_factory_metadata(job, script, profile)
                result = self.run_episode_production(job, script, profile)
                job.metadata["result"] = result
            except Exception as exc:
                job.status = "FAILED"
                job.error = str(exc)
                self._log(job, f"[ERROR] {exc}")

        thread = threading.Thread(target=worker, daemon=False)
        thread.start()
        return job

    def handle_chat(self, message: str) -> dict[str, Any]:
        text = message.strip()
        if not text:
            return {"reply": "Send an episode command followed by the complete script.", "action": "await_script"}
        lowered = text.lower().strip()

        if lowered in {"status", "progress", "state", "????"}:
            active = [j for j in self.jobs.values() if j.status in {"RUNNING", "QUEUED"}]
            if not active:
                return {"reply": "No active production.", "action": None}
            job = active[-1]
            return {"reply": f"Episode {job.episode_id}: {job.status} — Stage {job.stage} ({job.progress:.0f}%)", "action": None, "job_id": job.job_id}

        episode_id = self.resolve_episode_id(text)
        if not episode_id:
            return {"reply": "AURELIA Maker ready. Use: Create Episode <ID>, then provide the complete episode script.", "action": "await_script"}

        profile = "both"
        profile_match = re.search(r"(?:profile|mode)\s*[:=]\s*(youtube|tiktok|both)", lowered)
        if profile_match:
            profile = profile_match.group(1)

        lines = text.splitlines()
        script_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if re.search(r"(?:create|produce|make|generate|build)\s+episode\s+\d{1,4}", stripped, re.IGNORECASE):
                continue
            if re.fullmatch(r"(?:profile|mode)\s*[:=]\s*(?:youtube|tiktok|both)", stripped, re.IGNORECASE):
                continue
            script_lines.append(line)

        script_text = "\n".join(script_lines).strip()
        script_path = self.default_script_path(episode_id)
        if not script_text:
            return {"reply": f"Episode {episode_id} is recognized. Paste the complete script in the same Chat message. Expected script file: {script_path}", "action": "await_script", "episode_id": episode_id, "profile": profile}

        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text, encoding="utf-8")
        job = self.execute_async(episode_id, profile=profile, script_path=script_path)
        return {"reply": f"Episode {episode_id} accepted. Script saved. Profile: {profile}. Factory pipeline started — FINAL MP4.", "action": "produce", "job_id": job.job_id, "episode_id": episode_id, "profile": profile, "script": str(script_path)}


__all__ = ["FactoryRunner", "ProductionJob"]
