"""AURELIA Maker — Factory runner: canonical path from Chat/CLI to FINAL MP4."""

from __future__ import annotations

import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .episode_engine import produce_episode
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

    def _set_stage(
        self,
        job: ProductionJob,
        stage: str,
        progress: float,
    ) -> None:
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
        path = self.scripts / f"episode-{episode_id}.txt"
        if path.exists():
            return path
        return self.scripts / "episode-0013.txt"

    def ensure_episode_script(self, episode_id: str) -> Path:
        path = self.scripts / f"episode-{episode_id}.txt"
        if path.exists():
            return path

        template = self.scripts / "episode-0013.txt"
        if template.exists() and episode_id != "0013":
            path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            return path

        if not path.exists():
            path.write_text(
                "AURELIA Maker introduction.\n\n"
                "This episode demonstrates cinematic production.\n\n"
                "Factory pipeline from script to final MP4.\n",
                encoding="utf-8",
            )
        return path

    def create_job(
        self,
        episode_id: str,
        profile: str = "both",
        script_path: Path | None = None,
    ) -> ProductionJob:
        job = ProductionJob(
            job_id=str(uuid.uuid4())[:8],
            episode_id=episode_id.zfill(4) if episode_id.isdigit() else episode_id,
            metadata={"profile": profile},
        )
        if script_path:
            job.metadata["script"] = str(script_path)
        self.jobs[job.job_id] = job
        return job

    def run_factory_metadata(
        self,
        job: ProductionJob,
        script_path: Path,
        profile: str,
    ) -> None:
        """Execute early Factory stages (SCRIPT → PRE_PRODUCTION) for provenance."""
        pipeline = build_production_pipeline(
            self.output / f"episode-{job.episode_id}" / "factory"
        )
        run = pipeline.orchestrator.create_run(
            project=f"episode-{job.episode_id}",
            metadata={"mode": "factory", "profile": profile},
        )
        job.metadata["run_id"] = getattr(run, "id", getattr(run, "run_id", ""))

        early_stages = [
            s for s in PRODUCTION_STAGES
            if PRODUCTION_STAGES.index(s) <= PRODUCTION_STAGES.index("PRE_PRODUCTION")
        ]
        processors = pipeline.build_real_processors()
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

    def run_episode_production(
        self,
        job: ProductionJob,
        script_path: Path,
        profile: str = "both",
    ) -> dict[str, Any]:
        self._set_stage(job, "PRODUCTION", 20.0)
        self._log(job, f"[FACTORY] Starting cinematic production — Episode {job.episode_id}")

        render_stages = [
            "SEQUENCE", "SCENE", "SHOT", "VISUAL", "CAMERA", "DEPTH", "MOTION",
            "LIGHT", "VFX", "NARRATION", "MUSIC", "EDIT", "COLOR", "SUBTITLE",
            "MASTER", "QC", "DELIVERY",
        ]
        total = len(PRODUCTION_STAGES)
        base_index = PRODUCTION_STAGES.index("SEQUENCE")

        def stage_log(message: str) -> None:
            self._log(job, message)
            for offset, name in enumerate(render_stages):
                if name.lower() in message.lower() or name in message:
                    progress = ((base_index + offset) / total) * 100.0
                    self._set_stage(job, name, min(progress, 95.0))
                    break

        result = produce_episode(
            episode_id=job.episode_id,
            script_path=script_path,
            output_root=self.output,
            profile=profile,
            log=stage_log,
        )

        for offset, name in enumerate(render_stages):
            self._set_stage(job, name, ((base_index + offset + 1) / total) * 100.0)

        job.final_mp4 = result["final_mp4"]
        job.status = "COMPLETED"
        job.progress = 100.0
        job.stage = "DELIVERY"
        self._log(job, f"[FACTORY] FINAL MP4: {result['final_mp4']}")
        return result

    def execute(
        self,
        episode_id: str,
        profile: str = "both",
        script_path: Path | None = None,
    ) -> ProductionJob:
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

    def execute_async(
        self,
        episode_id: str,
        profile: str = "both",
        script_path: Path | None = None,
    ) -> ProductionJob:
        job = self.create_job(episode_id, profile, script_path)

        def worker() -> None:
            job.status = "RUNNING"
            script = script_path or self.ensure_episode_script(job.episode_id)
            try:
                self.run_factory_metadata(job, script, profile)
                self.run_episode_production(job, script, profile)
            except Exception as exc:
                job.status = "FAILED"
                job.error = str(exc)
                self._log(job, f"[ERROR] {exc}")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return job

    def handle_chat(self, message: str) -> dict[str, Any]:
        text = message.strip()
        lowered = text.lower()

        if any(word in lowered for word in ("status", "progress", "حالة")):
            active = [j for j in self.jobs.values() if j.status in {"RUNNING", "QUEUED"}]
            if not active:
                return {
                    "reply": "No active production. Say: Create Episode 0013",
                    "action": None,
                }
            job = active[-1]
            return {
                "reply": (
                    f"Episode {job.episode_id}: {job.status} — "
                    f"Stage {job.stage} ({job.progress:.0f}%)"
                ),
                "action": None,
                "job": job.job_id,
            }

        episode_id = self.resolve_episode_id(text)
        if episode_id:
            job = self.execute_async(episode_id)
            return {
                "reply": (
                    f"Production started for Episode {episode_id}. "
                    f"Factory pipeline running → FINAL MP4."
                ),
                "action": "produce",
                "job_id": job.job_id,
                "episode_id": episode_id,
            }

        return {
            "reply": (
                "AURELIA Maker ready. Commands:\n"
                "• Create Episode 0013\n"
                "• Status\n"
                "• Produce Episode 0001"
            ),
            "action": None,
        }


__all__ = ["FactoryRunner", "ProductionJob"]
