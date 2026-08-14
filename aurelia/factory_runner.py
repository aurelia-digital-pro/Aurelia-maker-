"""AURELIA Maker â€” Factory runner: canonical path from Chat/CLI to FINAL MP4."""

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
        return self.scripts / f"episode-{episode_id}.txt"

    def ensure_episode_script(self, episode_id: str) -> Path:
        path = self.default_script_path(episode_id)
        if not path.exists():
            raise FileNotFoundError(
                f"No script supplied for Episode {episode_id}: {path}"
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
        """Execute early Factory stages (SCRIPT â†’ PRE_PRODUCTION) for provenance."""
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
        self._log(job, f"[FACTORY] Starting cinematic production â€” Episode {job.episode_id}")

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

        thread = threading.Thread(target=worker, daemon=False)
        thread.start()
        return job

    def handle_chat(self, message: str) -> dict[str, Any]:
        """
        Canonical Chat -> Script -> Factory entry point.

        Accepted message format:

            Create Episode 0016
            Profile: tiktok

            Full episode script...

        Profile is optional and defaults to both.
        The script is persisted before Factory execution.
        """
        text = message.strip()
        if not text:
            return {
                "reply": "Send an episode command followed by the complete script.",
                "action": "await_script",
            }

        lowered = text.lower().strip()

        # Status commands are exact commands only.
        # This prevents words such as "status" inside a script
        # from accidentally interrupting production.
        if lowered in {"status", "progress", "state", "????"}:
            active = [
                j for j in self.jobs.values()
                if j.status in {"RUNNING", "QUEUED"}
            ]

            if not active:
                return {
                    "reply": "No active production.",
                    "action": None,
                }

            job = active[-1]
            return {
                "reply": (
                    f"Episode {job.episode_id}: {job.status} ? "
                    f"Stage {job.stage} ({job.progress:.0f}%)"
                ),
                "action": None,
                "job_id": job.job_id,
            }

        episode_id = self.resolve_episode_id(text)

        if not episode_id:
            return {
                "reply": (
                    "AURELIA Maker ready. Use:\n\n"
                    "Create Episode 0016\n"
                    "Profile: tiktok\n\n"
                    "Then paste the complete episode script."
                ),
                "action": "await_script",
            }

        # --------------------------------------------------------
        # Resolve requested production profile.
        # --------------------------------------------------------
        profile = "both"
        profile_match = re.search(
            r"(?:profile|mode)\s*[:=]\s*(youtube|tiktok|both)",
            lowered,
        )

        if profile_match:
            profile = profile_match.group(1)

        # --------------------------------------------------------
        # Extract script from the Chat message.
        # --------------------------------------------------------
        lines = text.splitlines()
        script_lines: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Ignore the command line containing the episode number.
            if re.search(
                r"(?:create|produce|make|generate|build)\s+episode\s+\d{1,4}",
                stripped,
                re.IGNORECASE,
            ):
                continue

            # Ignore an explicit profile declaration.
            if re.fullmatch(
                r"(?:profile|mode)\s*[:=]\s*(?:youtube|tiktok|both)",
                stripped,
                re.IGNORECASE,
            ):
                continue

            script_lines.append(line)

        script_text = "\n".join(script_lines).strip()

        script_path = self.default_script_path(episode_id)

        # --------------------------------------------------------
        # A production command without script does NOT fabricate
        # content. The Chat waits for the real episode script.
        # --------------------------------------------------------
        if not script_text:
            return {
                "reply": (
                    f"Episode {episode_id} is recognized. "
                    f"Paste the complete script in the same Chat message. "
                    f"Expected script file: {script_path}"
                ),
                "action": "await_script",
                "episode_id": episode_id,
                "profile": profile,
            }

        # --------------------------------------------------------
        # Persist the exact script supplied through Chat.
        # --------------------------------------------------------
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(script_text, encoding="utf-8")

        # --------------------------------------------------------
        # Launch the canonical Factory pipeline.
        # --------------------------------------------------------
        job = self.execute_async(
            episode_id,
            profile=profile,
            script_path=script_path,
        )

        return {
            "reply": (
                f"Episode {episode_id} accepted. "
                f"Script saved. Profile: {profile}. "
                f"Factory pipeline started ? FINAL MP4."
            ),
            "action": "produce",
            "job_id": job.job_id,
            "episode_id": episode_id,
            "profile": profile,
            "script": str(script_path),
        }


__all__ = ["FactoryRunner", "ProductionJob"]
