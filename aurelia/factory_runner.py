"""AURELIA Maker — FactoryRunner with ProductionLogger wired per-job.

Every job gets a ProductionLogger instance.
All log lines flow through it to:
  1. job.logs list (streamed to WebSocket + UI)
  2. NDJSON file in output/episode-N/job-N/production_logger.ndjson

Cancel flag: job.metadata["cancel_requested"] = True → checked in stage loop.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .episode_engine import EpisodeProduction
from .production_contract import PRODUCTION_STAGES
from .production_logger import ProductionLogger
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

    def _make_logger(self, job: ProductionJob, log_dir: Path) -> ProductionLogger:
        """Create a ProductionLogger bound to this job.

        All messages emitted through it are appended to job.logs so the
        WebSocket and UI see them in real-time.
        """
        logger = ProductionLogger(
            job_id=job.job_id,
            episode_id=job.episode_id,
            log_dir=log_dir,
        )
        # Monkey-patch the _write method to also sync lines into job.logs
        original_write = logger._write

        def _write_and_sync(record: dict, line: str) -> None:
            original_write(record, line)
            with self._lock:
                job.logs.append(line)
            print(line, flush=True)

        logger._write = _write_and_sync  # type: ignore[method-assign]

        # Patch info() separately (it doesn’t call _write)
        original_info = logger.info

        def _info_and_sync(message: str) -> None:
            original_info(message)
            with self._lock:
                if not job.logs or job.logs[-1] != message:
                    job.logs.append(message)
            print(message, flush=True)

        logger.info = _info_and_sync  # type: ignore[method-assign]
        return logger

    def _log(self, job: ProductionJob, message: str) -> None:
        """Direct log (used when no ProductionLogger is available yet)."""
        line = message.strip()
        with self._lock:
            job.logs.append(line)
        print(line, flush=True)

    def _set_stage(self, job: ProductionJob, stage: str, progress: float) -> None:
        with self._lock:
            job.stage = stage
            job.progress = max(0.0, min(100.0, progress))

    def _check_cancel(self, job: ProductionJob) -> None:
        """Raise RuntimeError if stop was requested."""
        if job.metadata.get("cancel_requested"):
            raise RuntimeError("[STOP] Job cancelled by user")

    def resolve_episode_id(self, text: str) -> str | None:
        patterns = [
            r'(?:episode|\u062d\u0644\u0642\u0629|\u0627\u0644\u062d\u0644\u0642\u0629)\s+(\d{1,4})',
            r'(?:create|produce|make|generate|build|\u0623\u0646\u0634\u0626|\u0623\u0646\u062a\u062c|\u0627\u0635\u0646\u0639|\u0627\u0646\u062a\u062c)\s+(?:episode|\u062d\u0644\u0642\u0629|\u0627\u0644\u062d\u0644\u0642\u0629)?\s*(\d{1,4})',
            r'(?:episode|\u062d\u0644\u0642\u0629)\s*(\d{1,4})',
            r'\b(\d{4})\b',
            r'\b(\d{3})\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).zfill(4)
        return None

    def create_job(
        self, episode_id: str, profile: str = "both",
        script_path: Path | None = None
    ) -> ProductionJob:
        if not episode_id or not episode_id.strip():
            raise ValueError("Production requires an episode identifier")
        normalized = episode_id.zfill(4) if episode_id.isdigit() else episode_id.strip()
        job = ProductionJob(
            job_id=uuid.uuid4().hex,
            episode_id=normalized,
            metadata={"profile": profile},
        )
        if script_path is not None:
            job.metadata["script"] = str(script_path.resolve())
        with self._lock:
            self.jobs[job.job_id] = job
        return job

    @staticmethod
    def _extract_metadata(script_text: str) -> tuple[str, str]:
        title = ""
        language = ""
        for line in script_text.splitlines():
            m = re.match(
                r'^\s*(?:title|\u0627\u0644\u0639\u0646\u0648\u0627\u0646|\u0639\u0646\u0648\u0627\u0646)\s*[:=]\s*(.+?)\s*$',
                line, re.IGNORECASE,
            )
            if m:
                title = m.group(1).strip()
                continue
            m = re.match(
                r'^\s*(?:language|lang|\u0627\u0644\u0644\u063a\u0629|\u0644\u063a\u0629)\s*[:=]\s*(.+?)\s*$',
                line, re.IGNORECASE,
            )
            if m:
                raw = m.group(1).strip().lower()
                if raw in {"arabic", "ar", "\u0639\u0631\u0628\u064a", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629", "\u0639\u0631\u0628\u064a\u0629", "arab"}:
                    language = "ar"
                elif raw in {"english", "en", "\u0625\u0646\u062c\u0644\u064a\u0632\u064a", "\u0627\u0644\u0625\u0646\u062c\u0644\u064a\u0632\u064a\u0629", "eng"}:
                    language = "en"
                else:
                    language = raw[:2]
                continue
        if not title:
            heading = next(
                (m.group(1).strip()
                 for m in re.finditer(r'^\s*#+\s+(.+?)\s*$', script_text, re.MULTILINE)),
                "",
            )
            title = heading
        if not language:
            arabic_chars = len(re.findall(r'[\u0600-\u06FF]', script_text))
            language = "ar" if arabic_chars > len(script_text) * 0.15 else "en"
        if not title:
            for line in script_text.splitlines():
                stripped = line.strip()
                if stripped and len(stripped) > 5:
                    title = stripped[:80]
                    break
        if not title:
            raise ValueError(
                "Production request must contain a real title "
                "(Title: ... / \u0627\u0644\u0639\u0646\u0648\u0627\u0646: ... or a Markdown heading)"
            )
        return title, language

    def run_episode_production(
        self, job: ProductionJob, script_path: Path, profile: str = "both"
    ) -> dict[str, Any]:
        from .delivery import process_delivery
        from .media import (
            inspect_final_video_visuals,
            probe_duration,
            validate_master,
            validate_visual_manifest,
        )
        from .qc_engine import run_qc

        script_path = Path(script_path).resolve()
        if not script_path.is_file():
            raise FileNotFoundError(
                f"Chat production input does not exist: {script_path}"
            )
        script_text = script_path.read_text(encoding="utf-8").strip()
        if not script_text:
            raise ValueError(f"Empty production request: {script_path}")

        title, language = self._extract_metadata(script_text)
        source_sha256 = hashlib.sha256(script_text.encode("utf-8")).hexdigest()

        production_root = (
            self.output / f"episode-{job.episode_id}" / f"job-{job.job_id}"
        )
        production_root.mkdir(parents=True, exist_ok=False)
        factory_root = production_root / "factory"
        factory_root.mkdir(parents=True, exist_ok=True)

        # ── Wire ProductionLogger to this job ──
        logger = self._make_logger(job, log_dir=production_root)
        logger.info(f"[FACTORY] Job {job.job_id} | Episode {job.episode_id} | {title}")
        logger.info(f"[FACTORY] Language: {language} | Profile: {profile}")

        pipeline = build_production_pipeline(factory_root)
        run = pipeline.orchestrator.create_run(
            project=f"episode-{job.episode_id}-{job.job_id}",
            metadata={
                "mode": "production", "source": "chat",
                "job_id": job.job_id, "episode_id": job.episode_id,
                "title": title, "language": language,
                "profile": profile, "source_text_sha256": source_sha256,
            },
        )
        job.metadata.update({
            "run_id": run.id, "title": title, "language": language,
            "source_text_sha256": source_sha256,
            "production_root": str(production_root),
        })

        # Use logger as the EpisodeProduction log callable
        production = EpisodeProduction(
            episode_id=job.episode_id,
            root=production_root,
            script_path=script_path,
            profile=profile,
            language=language,
            log=logger,
        )

        state: dict[str, Any] = {
            "script": str(script_path),
            "text": production.load_script(),
            "episode": job.episode_id,
            "job_id": job.job_id,
            "title": title,
            "language": language,
            "profile": profile,
            "root": str(self.root.resolve()),
            "source": "chat",
            "source_text_sha256": source_sha256,
        }

        assets: list[Path] = []
        narration: Path | None = None
        subtitles: Path | None = None
        music: Path | None = None
        edit: Path | None = None
        final_outputs: dict[str, Path] = {}

        # ── stage processors ───────────────────────────────────────────────

        def script_processor(data: dict) -> dict:
            loaded = production.load_script().strip()
            return {**data, "stage": "SCRIPT", "text": loaded, "source_text_sha256": source_sha256}

        def _meta(stage: str, key: str, extra: dict[str, Any] | None = None):
            def process(data: dict) -> dict:
                payload: dict[str, Any] = {
                    "source": "chat", "job_id": job.job_id,
                    "episode_id": job.episode_id, "title": title,
                    "language": language, "source_text_sha256": source_sha256,
                }
                if extra:
                    payload.update(extra)
                return {**data, "stage": stage, key: payload}
            return process

        development_processor = _meta("DEVELOPMENT", "development", {"grounded_in_request": True})
        story_processor = _meta("STORY", "story", {"narrative": script_text[:500]})
        world_processor = _meta("WORLD", "world", {"premise": script_text[:500]})
        character_processor = _meta("CHARACTER", "character", {"source_text": script_text[:500]})
        series_bible_processor = _meta("SERIES_BIBLE", "series_bible", {"premise": script_text[:500]})
        research_processor = _meta("RESEARCH", "research", {"grounded_in_request": True})
        preproduction_processor = _meta("PRE_PRODUCTION", "pre_production", {"ready": True})

        def sequence_processor(data: dict) -> dict:
            production.build_scene_plan(data["text"])
            if not production.scenes:
                raise RuntimeError("SEQUENCE produced no scenes")
            job.metadata["total_shots"] = sum(len(s.shots) for s in production.scenes)
            return {**data, "stage": "SEQUENCE", "scene_count": len(production.scenes)}

        def scene_processor(data: dict) -> dict:
            job.metadata["scene_info"] = str(len(production.scenes))
            return {**data, "stage": "SCENE", "scenes": [s.title for s in production.scenes]}

        def shot_processor(data: dict) -> dict:
            return {**data, "stage": "SHOT",
                    "total_shots": job.metadata.get("total_shots", 0)}

        def storyboard_processor(data: dict) -> dict:
            return {**data, "stage": "STORYBOARD"}

        def animatic_processor(data: dict) -> dict:
            return {**data, "stage": "ANIMATIC"}

        def visual_processor(data: dict) -> dict:
            nonlocal assets
            t0 = logger.stage_start("VISUAL", "generating shot visuals")
            scene_assets = production.generate_visual_assets()
            # Store as flat list of paths for compatibility, keyed dict for render
            all_paths: list[Path] = []
            for paths in scene_assets.values():
                all_paths.extend(paths)
            assets = all_paths
            data["_scene_assets"] = scene_assets
            # Report fallbacks in metadata
            from .visual_backend import probe_sd_backend
            probe = probe_sd_backend()
            job.metadata["visual_backend"] = {
                "primary": "stable-diffusion" if probe["available"] else "pillow-fallback",
                "sd_available": probe["available"],
            }
            job.metadata["outputs"] = job.metadata.get("outputs", {})
            job.metadata["outputs"]["visuals"] = str(production.dirs["visuals"])
            logger.stage_ok("VISUAL", t0, f"{len(all_paths)} images")
            return {**data, "stage": "VISUAL", "asset_count": len(all_paths)}

        def asset_processor(data: dict) -> dict:
            return {**data, "stage": "ASSET"}

        def camera_processor(data: dict) -> dict:
            return {**data, "stage": "CAMERA"}

        def depth_processor(data: dict) -> dict:
            return {**data, "stage": "DEPTH"}

        def motion_processor(data: dict) -> dict:
            return {**data, "stage": "MOTION"}

        def light_processor(data: dict) -> dict:
            return {**data, "stage": "LIGHT"}

        def narration_processor(data: dict) -> dict:
            nonlocal narration
            t0 = logger.stage_start("NARRATION", f"lang={language}")
            narration = production.synthesize_narration(data["text"])
            logger.stage_ok("NARRATION", t0, output_ref=str(narration))
            job.metadata["outputs"] = job.metadata.get("outputs", {})
            job.metadata["outputs"]["narration"] = str(narration)
            return {**data, "stage": "NARRATION", "narration": str(narration)}

        def music_processor(data: dict) -> dict:
            nonlocal music
            from .media import generate_ambient_music, probe_duration
            planned_dur = sum(s.duration for s in production.scenes) + 8.0
            music = production.dirs["audio"] / "ambient_music.wav"
            t0 = logger.stage_start("MUSIC", f"{planned_dur:.0f}s")
            generate_ambient_music(planned_dur + 4.0, music)
            logger.stage_ok("MUSIC", t0, output_ref=str(music))
            return {**data, "stage": "MUSIC", "music": str(music)}

        def edit_processor(data: dict) -> dict:
            nonlocal edit
            if narration is None:
                raise RuntimeError("EDIT requires narration")
            t0 = logger.stage_start("EDIT", "concat + mix")
            scene_assets = data.get("_scene_assets", {})
            clips = production.render_shots(scene_assets)
            edit = production.assemble_edit(clips, narration, music)
            logger.stage_ok("EDIT", t0, output_ref=str(edit))
            job.metadata["outputs"] = job.metadata.get("outputs", {})
            job.metadata["outputs"]["edit"] = str(edit)
            return {**data, "stage": "EDIT", "edit": str(edit)}

        def color_processor(data: dict) -> dict:
            return {**data, "stage": "COLOR"}

        def subtitle_processor(data: dict) -> dict:
            nonlocal subtitles
            if narration is None:
                raise RuntimeError("SUBTITLE requires narration")
            subtitles = production.build_subtitles(narration)
            return {**data, "stage": "SUBTITLE", "srt": str(subtitles)}

        def master_processor(data: dict) -> dict:
            if edit is None:
                raise RuntimeError("MASTER requires edit")
            if subtitles is None:
                raise RuntimeError("MASTER requires subtitles")
            t0 = logger.stage_start("MASTER", "grade + encode")
            outputs = production.finish(edit, subtitles)
            final_outputs.update(outputs)
            logger.stage_ok("MASTER", t0, output_ref=str(outputs.get("final", "")))
            job.metadata["outputs"] = job.metadata.get("outputs", {})
            job.metadata["outputs"].update({k: str(v) for k, v in outputs.items()})
            return {**data, "stage": "MASTER",
                    "outputs": {k: str(v) for k, v in outputs.items()}}

        def qc_processor(data: dict) -> dict:
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("QC requires master output")
            planned_dur = max(5.0, sum(s.duration for s in production.scenes))
            min_dur = max(5.0, planned_dur * 0.5)
            qc = run_qc(
                video_path=final,
                srt_path=subtitles,
                min_duration_s=min_dur,
                planned_duration_s=planned_dur,
                scene_count=len(production.scenes),
            )
            logger.qc_result(
                passed=qc["passed"],
                checks=qc["checks"],
                output_ref=str(final),
            )
            job.metadata["qc"] = qc
            if qc["warnings"]:
                for w in qc["warnings"]:
                    logger.stage_warn("QC", w["message"])
            if qc["delivery_blocked"]:
                raise RuntimeError(
                    f"QC FATAL: {[c['message'] for c in qc['fatals']]}"
                )
            return {**data, "stage": "QC", "qc": qc}

        def delivery_processor(data: dict) -> dict:
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("DELIVERY requires master artifact")
            planned_dur = max(5.0, sum(s.duration for s in production.scenes))
            min_dur = max(5.0, planned_dur * 0.5)
            validation = validate_master(final, min_duration=min_dur)
            visual_qc = validate_visual_manifest(
                production.visual_manifest_path, len(production.scenes)
            )
            validation["visual_content"] = visual_qc
            validation["passed"] = validation["passed"] and visual_qc["passed"]
            if not validation["passed"]:
                raise RuntimeError(f"DELIVERY rejected: {validation}")
            alias = production.dirs["delivery"] / f"episode-{job.episode_id}-FINAL.mp4"
            from .delivery import process_delivery
            delivered = process_delivery({
                "input": str(final), "output": str(alias),
                "min_duration": min_dur, "expected_sha256": None,
            })
            final_outputs["final"] = Path(delivered["artifact"])
            manifest = {
                "job_id": job.job_id, "episode_id": job.episode_id,
                "title": title, "language": language,
                "profile": profile, "source": "chat",
                "source_script": str(script_path),
                "source_text_sha256": source_sha256,
                "outputs": {k: str(v) for k, v in final_outputs.items()},
                "delivery_validation": delivered["validation"],
                "directing": [scene.direction for scene in production.scenes],
                "environments": [s.direction.get("environment", "?") for s in production.scenes],
            }
            (production.root / "production_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {
                **data, "stage": "DELIVERY",
                "artifact": str(final_outputs["final"]),
                "manifest": str(production.root / "production_manifest.json"),
                "delivery": delivered,
            }

        processors = {
            "SCRIPT": script_processor,
            "DEVELOPMENT": development_processor,
            "STORY": story_processor,
            "WORLD": world_processor,
            "CHARACTER": character_processor,
            "SERIES_BIBLE": series_bible_processor,
            "RESEARCH": research_processor,
            "PRE_PRODUCTION": preproduction_processor,
            "SEQUENCE": sequence_processor,
            "SCENE": scene_processor,
            "SHOT": shot_processor,
            "STORYBOARD": storyboard_processor,
            "ANIMATIC": animatic_processor,
            "VISUAL": visual_processor,
            "ASSET": asset_processor,
            "CAMERA": camera_processor,
            "DEPTH": depth_processor,
            "MOTION": motion_processor,
            "LIGHT": light_processor,
            "VFX": _meta("VFX", "vfx"),
            "ATMOSPHERE": _meta("ATMOSPHERE", "atmosphere"),
            "NARRATION": narration_processor,
            "DIALOGUE": _meta("DIALOGUE", "dialogue"),
            "SOUND": _meta("SOUND", "sound"),
            "MUSIC": music_processor,
            "AUDIO": _meta("AUDIO", "audio"),
            "EDIT": edit_processor,
            "COLOR": color_processor,
            "SUBTITLE": subtitle_processor,
            "MASTER": master_processor,
            "QC": qc_processor,
            "DELIVERY": delivery_processor,
        }

        total = len(PRODUCTION_STAGES)
        current = dict(state)
        for index, stage in enumerate(PRODUCTION_STAGES):
            self._check_cancel(job)  # honour stop requests
            self._set_stage(job, stage, (index / total) * 100.0)
            logger.info(f"[FACTORY] {stage} ({job.progress:.0f}%)")
            execution = pipeline.execute_stage(
                project=f"episode-{job.episode_id}-{job.job_id}",
                stage=stage,
                unit_type="production_stage",
                unit_id=f"{job.job_id}:{stage}",
                input_data=current,
                processor=processors[stage],
                validator=lambda result: isinstance(result, dict) and bool(result),
                run_id=run.id,
            )
            if execution.status != "COMPLETED":
                raise RuntimeError(f"Production stage failed: {stage}: {execution.error}")
            current.update(execution.output)
            self._set_stage(job, stage, ((index + 1) / total) * 100.0)

        if "final" not in final_outputs:
            raise RuntimeError("Canonical production completed without FINAL MP4")

        planned_dur = max(5.0, sum(s.duration for s in production.scenes))
        min_dur = max(5.0, planned_dur * 0.5)
        final_validation = validate_master(final_outputs["final"], min_duration=min_dur)
        visual_qc = validate_visual_manifest(
            production.visual_manifest_path, len(production.scenes)
        )
        final_validation["visual_content"] = visual_qc
        final_validation["passed"] = final_validation["passed"] and visual_qc["passed"]
        if not final_validation["passed"]:
            raise RuntimeError(f"FINAL MP4 validation failed: {final_validation}")

        saved_run = pipeline.orchestrator.runs.get(run.id)
        if saved_run is not None:
            saved_run.mark_completed()
            pipeline.orchestrator.runs.save(saved_run)

        job.final_mp4 = str(final_outputs["final"])
        job.metadata["download_url"] = f"/api/jobs/{job.job_id}/video"
        self._set_stage(job, "DELIVERY", 100.0)
        job.status = "COMPLETED"
        logger.info(f"[FACTORY] COMPLETED — FINAL MP4: {job.final_mp4}")

        return {
            "job_id": job.job_id, "episode_id": job.episode_id,
            "title": title, "language": language,
            "final_mp4": job.final_mp4,
            "download_url": job.metadata["download_url"],
            "outputs": {k: str(v) for k, v in final_outputs.items()},
            "scenes": len(production.scenes),
            "source_text_sha256": source_sha256,
            "logger_lines": len(logger.lines),
            "fallbacks": len(logger.fallback_summary()),
        }

    def execute(
        self, episode_id: str, profile: str = "both",
        script_path: Path | None = None
    ) -> ProductionJob:
        if script_path is None:
            raise ValueError("Production requires a current Chat input")
        job = self.create_job(episode_id, profile, script_path)
        job.status = "RUNNING"
        try:
            job.metadata["result"] = self.run_episode_production(job, script_path, profile)
            return job
        except Exception as exc:
            job.status = "FAILED"
            job.error = str(exc)
            self._log(job, f"[ERROR] {exc}")
            self._log(job, traceback.format_exc())
            raise

    def execute_async(
        self, episode_id: str, profile: str = "both",
        script_path: Path | None = None
    ) -> ProductionJob:
        if script_path is None:
            raise ValueError("Production requires a current Chat input")
        job = self.create_job(episode_id, profile, script_path)

        def worker() -> None:
            job.status = "RUNNING"
            try:
                job.metadata["result"] = self.run_episode_production(job, script_path, profile)
            except RuntimeError as exc:
                if "[STOP]" in str(exc):
                    job.status = "STOPPED"
                    job.error = "Stopped by user"
                else:
                    job.status = "FAILED"
                    job.error = str(exc)
                    self._log(job, f"[ERROR] {exc}")
                    self._log(job, traceback.format_exc())
            except Exception as exc:
                job.status = "FAILED"
                job.error = str(exc)
                self._log(job, f"[ERROR] {exc}")
                self._log(job, traceback.format_exc())

        threading.Thread(target=worker, daemon=False).start()
        return job

    def handle_chat(self, message: str) -> dict[str, Any]:
        if message.strip().lower() in {"status", "progress", "state",
                                        "\u0627\u0644\u062d\u0627\u0644\u0629", "\u0627\u0644\u062a\u0642\u062f\u0645"}:
            active = [j for j in self.jobs.values() if j.status in {"RUNNING", "QUEUED"}]
            if not active:
                return {"reply": "No active production.", "action": None}
            job = active[-1]
            return {
                "reply": f"Episode {job.episode_id}: {job.status} — {job.stage} ({job.progress:.0f}%)",
                "action": None, "job_id": job.job_id,
            }
        return {
            "reply": "Use Chat production entry with Episode ID, Title, Language and the complete script.",
            "action": "await_script",
        }
