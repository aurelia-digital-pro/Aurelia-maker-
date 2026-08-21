"""AURELIA Maker — single production path from current Chat request to FINAL MP4."""

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
        """Extract episode ID from the message text (Arabic or English)."""
        patterns = [
            # Arabic command patterns
            r'(?:episode|حلقة|الحلقة|episode)\s+(\d{1,4})',
            r'(?:create|produce|make|generate|build|أنشئ|أنتج|اصنع|انتج)\s+(?:episode|حلقة|الحلقة)?\s*(\d{1,4})',
            r'(?:episode|حلقة)\s*(\d{1,4})',
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
        """Extract title and language from the production request."""
        title = ""
        language = ""
        for line in script_text.splitlines():
            # Title (English and Arabic keys)
            m = re.match(
                r'^\s*(?:title|العنوان|عنوان)\s*[:=]\s*(.+?)\s*$',
                line, re.IGNORECASE,
            )
            if m:
                title = m.group(1).strip()
                continue
            # Language
            m = re.match(
                r'^\s*(?:language|lang|اللغة|لغة)\s*[:=]\s*(.+?)\s*$',
                line, re.IGNORECASE,
            )
            if m:
                language = m.group(1).strip().lower()
                # Normalize language value
                if language in {"arabic", "ar", "عربي", "العربية", "عربية"}:
                    language = "ar"
                elif language in {"english", "en", "إنجليزي", "الإنجليزية"}:
                    language = "en"
                continue

        # Fallback title from Markdown heading
        if not title:
            heading = next(
                (m.group(1).strip()
                 for m in re.finditer(r'^\s*#+\s+(.+?)\s*$', script_text, re.MULTILINE)),
                "",
            )
            title = heading

        # Auto-detect language from content if not specified
        if not language:
            arabic_chars = len(re.findall(r'[\u0600-\u06FF]', script_text))
            language = "ar" if arabic_chars > len(script_text) * 0.15 else "en"

        if not title:
            raise ValueError(
                "Production request must contain a real title "
                "(Title: ... / العنوان: ... or a Markdown heading)"
            )
        return title, language

    def run_episode_production(
        self, job: ProductionJob, script_path: Path, profile: str = "both"
    ) -> dict[str, Any]:
        from .delivery import process_delivery
        from .media import (
            generate_ambient_music, inspect_final_video_visuals,
            probe_duration, validate_master, validate_visual_manifest,
        )

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

        # Every job owns an immutable output directory.
        production_root = (
            self.output / f"episode-{job.episode_id}" / f"job-{job.job_id}"
        )
        production_root.mkdir(parents=True, exist_ok=False)
        factory_root = production_root / "factory"
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

        production = EpisodeProduction(
            episode_id=job.episode_id,
            root=production_root,
            script_path=script_path,
            profile=profile,
            language=language,
            log=lambda message: self._log(job, f"[FACTORY] {message}"),
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

        # Mutable production artifacts (filled as stages execute)
        assets: list[Path] = []
        narration: Path | None = None
        subtitles: Path | None = None
        music: Path | None = None
        edit: Path | None = None
        graded: Path | None = None
        subtitled: Path | None = None
        final_outputs: dict[str, Path] = {}

        # ── metadata stages ──────────────────────────────────────────────────

        def script_processor(data: dict) -> dict:
            loaded = production.load_script().strip()
            if loaded != data["text"].strip():
                raise RuntimeError(
                    "SCRIPT input changed: production is not using the current Chat request"
                )
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

        # ── scene / shot planning stages ─────────────────────────────────────

        def sequence_processor(data: dict) -> dict:
            production.build_scene_plan(data["text"])
            if not production.scenes:
                raise RuntimeError("SEQUENCE produced no scenes from the current Chat request")
            return {**data, "stage": "SEQUENCE", "scene_count": len(production.scenes)}

        def scene_processor(data: dict) -> dict:
            return {**data, "stage": "SCENE", "scene_count": len(production.scenes)}

        def shot_processor(data: dict) -> dict:
            return {**data, "stage": "SHOT", "shots": [s.direction for s in production.scenes]}

        def storyboard_processor(data: dict) -> dict:
            return {**data, "stage": "STORYBOARD", "storyboard": {"scene_count": len(production.scenes)}}

        def animatic_processor(data: dict) -> dict:
            return {**data, "stage": "ANIMATIC", "animatic": {"scene_count": len(production.scenes)}}

        # ── visual stages ─────────────────────────────────────────────────────

        def visual_processor(data: dict) -> dict:
            nonlocal assets
            assets = production.generate_visual_assets()
            if not assets or any(not p.is_file() or p.stat().st_size == 0 for p in assets):
                raise RuntimeError("VISUAL produced no valid visual assets")
            return {**data, "stage": "VISUAL", "assets": [str(p) for p in assets]}

        def asset_processor(data: dict) -> dict:
            return {**data, "stage": "ASSET", "assets": [str(p) for p in assets]}

        def camera_processor(data: dict) -> dict:
            return {**data, "stage": "CAMERA", "camera": [s.direction["camera"] for s in production.scenes]}

        def depth_processor(data: dict) -> dict:
            return {**data, "stage": "DEPTH", "depth": [s.direction["depth"] for s in production.scenes]}

        def motion_processor(data: dict) -> dict:
            return {**data, "stage": "MOTION", "motion": [s.direction["motion"] for s in production.scenes]}

        def light_processor(data: dict) -> dict:
            return {**data, "stage": "LIGHT", "light": [s.direction["lighting"] for s in production.scenes]}

        # ── audio stages ──────────────────────────────────────────────────────

        def narration_processor(data: dict) -> dict:
            nonlocal narration, subtitles
            narration = production.synthesize_narration(data["text"])
            if narration is None or not narration.is_file() or narration.stat().st_size < 1000:
                raise RuntimeError("NARRATION synthesis failed")
            # Build subtitle track now that we have narration timing
            subtitles = production.build_subtitles(narration)
            return {**data, "stage": "NARRATION", "narration": str(narration)}

        def music_processor(data: dict) -> dict:
            nonlocal music
            narration_dur = probe_duration(narration) if narration else 60.0
            target_dur = max(
                narration_dur,
                sum(s.duration for s in production.scenes) + 8.0,
                30.0,
            )
            music = production.dirs["audio"] / "ambient_music.wav"
            generate_ambient_music(target_dur + 4.0, music)
            if not music.is_file() or music.stat().st_size < 100:
                raise RuntimeError("MUSIC generation failed")
            return {**data, "stage": "MUSIC", "music": str(music)}

        # ── editing stages ────────────────────────────────────────────────────

        def edit_processor(data: dict) -> dict:
            nonlocal edit
            if narration is None:
                raise RuntimeError("EDIT requires narration")
            clips = production.render_shots(assets)
            edit = production.assemble_edit(clips, narration, music)
            return {**data, "stage": "EDIT", "edit": str(edit)}

        def color_processor(data: dict) -> dict:
            nonlocal graded
            from .media import apply_color_grade
            if edit is None:
                raise RuntimeError("COLOR requires edit")
            graded = production.dirs["master"] / "graded.mp4"
            apply_color_grade(edit, graded)
            return {**data, "stage": "COLOR", "graded": str(graded)}

        def subtitle_processor(data: dict) -> dict:
            nonlocal subtitled
            from .media import burn_subtitles
            if graded is None:
                raise RuntimeError("SUBTITLE requires graded video")
            subtitled = production.dirs["master"] / "subtitled.mp4"
            if subtitles is not None and subtitles.is_file():
                burn_subtitles(graded, subtitles, subtitled)
            else:
                # No subtitles available — pass through graded
                import shutil
                shutil.copy2(graded, subtitled)
            return {**data, "stage": "SUBTITLE", "subtitled": str(subtitled)}

        def master_processor(data: dict) -> dict:
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
            for path in final_outputs.values():
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError(f"MASTER produced invalid output: {path}")
            return {**data, "stage": "MASTER", "outputs": {k: str(v) for k, v in final_outputs.items()}}

        def qc_processor(data: dict) -> dict:
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("QC requires master output")
            qc = validate_master(final, min_duration=30.0)
            visual_qc = validate_visual_manifest(
                production.visual_manifest_path, len(production.scenes), source_sha256
            )
            frame_qc = inspect_final_video_visuals(final)
            qc["visual_content"] = visual_qc
            qc["frame_content"] = frame_qc
            qc["passed"] = qc["passed"] and visual_qc["passed"] and frame_qc["passed"]
            if not qc["passed"]:
                raise RuntimeError(f"QC failed: {qc}")
            return {**data, "stage": "QC", "qc": qc}

        def delivery_processor(data: dict) -> dict:
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("DELIVERY requires the current job's master artifact")
            validation = validate_master(final, min_duration=30.0)
            visual_qc = validate_visual_manifest(
                production.visual_manifest_path, len(production.scenes), source_sha256
            )
            frame_qc = inspect_final_video_visuals(final)
            validation["visual_content"] = visual_qc
            validation["frame_content"] = frame_qc
            validation["passed"] = (
                validation["passed"] and visual_qc["passed"] and frame_qc["passed"]
            )
            if not validation["passed"]:
                raise RuntimeError(f"DELIVERY rejected master artifact: {validation}")
            alias = production.dirs["delivery"] / f"episode-{job.episode_id}-FINAL.mp4"
            delivered = process_delivery({
                "input": str(final), "output": str(alias),
                "min_duration": 30.0, "expected_sha256": None,
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
            }
            manifest_path = production.root / "production_manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {
                **data, "stage": "DELIVERY",
                "artifact": str(final_outputs["final"]),
                "manifest": str(manifest_path),
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
            self._set_stage(job, stage, (index / total) * 100.0)
            self._log(job, f"[FACTORY] {stage} ({job.progress:.0f}%)")
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

        final_validation = validate_master(final_outputs["final"], min_duration=30.0)
        visual_qc = validate_visual_manifest(
            production.visual_manifest_path, len(production.scenes), source_sha256
        )
        frame_qc = inspect_final_video_visuals(final_outputs["final"])
        final_validation["visual_content"] = visual_qc
        final_validation["frame_content"] = frame_qc
        final_validation["passed"] = (
            final_validation["passed"] and visual_qc["passed"] and frame_qc["passed"]
        )
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
        self._log(job, f"[FACTORY] FINAL MP4: {job.final_mp4}")
        return {
            "job_id": job.job_id, "episode_id": job.episode_id,
            "title": title, "language": language,
            "final_mp4": job.final_mp4,
            "download_url": job.metadata["download_url"],
            "outputs": {k: str(v) for k, v in final_outputs.items()},
            "scenes": len(production.scenes),
            "source_text_sha256": source_sha256,
        }

    def execute(
        self, episode_id: str, profile: str = "both",
        script_path: Path | None = None
    ) -> ProductionJob:
        if script_path is None:
            raise ValueError("Production requires a current Chat input; no script fallback is permitted")
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
            raise ValueError("Production requires a current Chat input; no script fallback is permitted")
        job = self.create_job(episode_id, profile, script_path)

        def worker() -> None:
            job.status = "RUNNING"
            try:
                job.metadata["result"] = self.run_episode_production(job, script_path, profile)
            except Exception as exc:
                job.status = "FAILED"
                job.error = str(exc)
                self._log(job, f"[ERROR] {exc}")
                self._log(job, traceback.format_exc())

        threading.Thread(target=worker, daemon=False).start()
        return job

    def handle_chat(self, message: str) -> dict[str, Any]:
        if message.strip().lower() in {"status", "progress", "state", "الحالة", "التقدم"}:
            active = [j for j in self.jobs.values() if j.status in {"RUNNING", "QUEUED"}]
            if not active:
                return {"reply": "No active production.", "action": None}
            job = active[-1]
            return {
                "reply": f"Episode {job.episode_id}: {job.status} — {job.stage} ({job.progress:.0f}%)",
                "action": None, "job_id": job.job_id,
            }
        return {
            "reply": "Use the Chat production entry with Episode ID, Title, Language and the complete script.",
            "action": "await_script",
        }
