"""AURELIA Maker — FactoryRunner with ProductionLogger wired per-job.

Key serialization rule:
  - `_scene_assets` (dict[str, list[Path]]) lives ONLY in a closure variable,
    never in the `data` dict that flows through the stage pipeline.
  - All Path objects returned in `data` are str()-converted at source.
  - This prevents PosixPath JSON serialization errors in factory.py fingerprint.

Cancel flag: job.metadata["cancel_requested"] = True → checked per stage.
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
        logger = ProductionLogger(
            job_id=job.job_id,
            episode_id=job.episode_id,
            log_dir=log_dir,
        )
        original_write = logger._write

        def _write_and_sync(record: dict, line: str) -> None:
            original_write(record, line)
            with self._lock:
                job.logs.append(line)
            print(line, flush=True)

        logger._write = _write_and_sync  # type: ignore[method-assign]

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
        line = message.strip()
        with self._lock:
            job.logs.append(line)
        print(line, flush=True)

    def _set_stage(self, job: ProductionJob, stage: str, progress: float) -> None:
        with self._lock:
            job.stage = stage
            job.progress = max(0.0, min(100.0, progress))

    def _check_cancel(self, job: ProductionJob) -> None:
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
                if raw in {"arabic", "ar", "\u0639\u0631\u0628\u064a", "\u0627\u0644\u0639\u0631\u0628\u064a\u0629",
                           "\u0639\u0631\u0628\u064a\u0629", "arab"}:
                    language = "ar"
                elif raw in {"english", "en", "\u0625\u0646\u062c\u0644\u064a\u0632\u064a",
                             "\u0627\u0644\u0625\u0646\u062c\u0644\u064a\u0632\u064a\u0629", "eng"}:
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
        from .media import (
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

        production = EpisodeProduction(
            episode_id=job.episode_id,
            root=production_root,
            script_path=script_path,
            profile=profile,
            language=language,
            log=logger,
        )

        # Serializable-only initial state (no Path objects in values)
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

        # Closure-only variables (NEVER put in data dict — contain Path objects)
        _scene_assets: dict[str, list[Path]] = {}
        narration: Path | None = None
        subtitles: Path | None = None
        music: Path | None = None
        edit: Path | None = None
        final_outputs: dict[str, Path] = {}

        # ── stage processors ───────────────────────────────────────────────

        def script_processor(data: dict) -> dict:
            loaded = production.load_script().strip()
            return {**data, "stage": "SCRIPT", "text": loaded,
                    "script_chars": len(loaded), "script_words": len(loaded.split())}

        def development_processor(data: dict) -> dict:
            from .development import develop_story_concept
            concept = develop_story_concept(data["text"])
            return {**data, "stage": "DEVELOPMENT",
                    "genre": concept.get("genre", ""),
                    "theme": concept.get("theme", ""),
                    "logline": concept.get("logline", "")}

        def story_processor(data: dict) -> dict:
            from .development import extract_story_structure
            structure = extract_story_structure(data["text"])
            return {**data, "stage": "STORY",
                    "acts": structure.get("acts", 3),
                    "turning_points": structure.get("turning_points", [])}

        def world_processor(data: dict) -> dict:
            from .world import build_world_context
            world = build_world_context(data["text"])
            return {**data, "stage": "WORLD",
                    "setting": world.get("setting", ""),
                    "time_period": world.get("time_period", ""),
                    "atmosphere": world.get("atmosphere", "")}

        def character_processor(data: dict) -> dict:
            from .development import extract_characters
            chars = extract_characters(data["text"])
            return {**data, "stage": "CHARACTER",
                    "character_count": len(chars),
                    "characters": [c.get("name", "?") for c in chars[:10]]}

        def series_bible_processor(data: dict) -> dict:
            from .series_system import build_series_bible_entry
            entry = build_series_bible_entry(
                episode_id=job.episode_id, title=title, language=language,
                text=data["text"], profile=profile,
            )
            return {**data, "stage": "SERIES_BIBLE",
                    "series_title": entry.get("series_title", title),
                    "episode_number": entry.get("episode_number", job.episode_id)}

        def research_processor(data: dict) -> dict:
            from .research import research_topic
            facts = research_topic(data["text"])
            return {**data, "stage": "RESEARCH",
                    "fact_count": len(facts),
                    "facts": facts[:5]}

        def preproduction_processor(data: dict) -> dict:
            scenes = production.build_scene_plan(data["text"])
            return {**data, "stage": "PRE_PRODUCTION",
                    "scene_count": len(scenes),
                    "total_planned_duration": sum(s.duration for s in scenes)}

        def sequence_processor(data: dict) -> dict:
            total_shots = sum(len(s.shots) for s in production.scenes)
            return {**data, "stage": "SEQUENCE",
                    "scene_count": len(production.scenes),
                    "total_shots": total_shots}

        def scene_processor(data: dict) -> dict:
            return {**data, "stage": "SCENE",
                    "scenes": [{
                        "index": s.index, "title": s.title,
                        "duration": s.duration, "movement": s.movement,
                    } for s in production.scenes]}

        def shot_processor(data: dict) -> dict:
            shot_summary = [
                {"scene": s.index, "shots": len(s.shots),
                 "motions": [sh.get("motion_intent", "?") for sh in s.shots]}
                for s in production.scenes
            ]
            return {**data, "stage": "SHOT", "shot_summary": shot_summary}

        def storyboard_processor(data: dict) -> dict:
            return {**data, "stage": "STORYBOARD",
                    "storyboard_scenes": len(production.scenes)}

        def animatic_processor(data: dict) -> dict:
            return {**data, "stage": "ANIMATIC",
                    "animatic_duration": sum(s.duration for s in production.scenes)}

        def visual_processor(data: dict) -> dict:
            nonlocal _scene_assets
            _scene_assets = production.generate_visual_assets()
            return {
                **data, "stage": "VISUAL",
                "visual_count": production._total_visual_assets,
                # Serializable summary only — no Path objects
                "visual_scene_keys": list(_scene_assets.keys()),
            }

        def asset_processor(data: dict) -> dict:
            return {**data, "stage": "ASSET",
                    "asset_count": production._total_visual_assets}

        def camera_processor(data: dict) -> dict:
            movements = [s.direction.get("camera", {}).get("movement", "?") for s in production.scenes]
            return {**data, "stage": "CAMERA", "movements": movements}

        def depth_processor(data: dict) -> dict:
            depths = [s.direction.get("depth", {}).get("depth_of_field", 0.0) for s in production.scenes]
            return {**data, "stage": "DEPTH", "dof_values": depths}

        def motion_processor(data: dict) -> dict:
            return {**data, "stage": "MOTION",
                    "motions": [s.direction.get("motion", {}) for s in production.scenes]}

        def light_processor(data: dict) -> dict:
            return {**data, "stage": "LIGHT",
                    "lighting_count": len(production.scenes)}

        def _meta(stage_name: str, key: str):
            def processor(data: dict) -> dict:
                return {**data, "stage": stage_name, key: True}
            return processor

        def narration_processor(data: dict) -> dict:
            nonlocal narration
            narration = production.synthesize_narration(data["text"])
            dur = 0.0
            try:
                from .media import probe_duration as _pd
                dur = _pd(narration)
            except Exception:
                pass
            return {**data, "stage": "NARRATION",
                    "narration_duration": dur,
                    "narration_language": production.language}

        def music_processor(data: dict) -> dict:
            nonlocal music
            planned_dur = max(5.0, sum(s.duration for s in production.scenes))
            narration_dur = 0.0
            if narration is not None:
                try:
                    from .media import probe_duration as _pd
                    narration_dur = _pd(narration)
                except Exception:
                    pass
            total_dur = max(planned_dur, narration_dur)
            music_path = production.dirs["audio"] / "ambient_music.wav"
            from .media import generate_ambient_music
            generate_ambient_music(total_dur + 4.0, music_path)
            music = music_path
            return {**data, "stage": "MUSIC",
                    "music_duration": total_dur + 4.0,
                    "music_path": str(music_path)}

        def edit_processor(data: dict) -> dict:
            nonlocal edit
            if narration is None:
                raise RuntimeError("EDIT requires NARRATION")
            clips = production.render_shots(_scene_assets)
            edit = production.assemble_edit(clips, narration, music)
            return {**data, "stage": "EDIT",
                    "clip_count": len(clips),
                    "edit_path": str(edit)}

        def color_processor(data: dict) -> dict:
            if edit is None:
                raise RuntimeError("COLOR requires EDIT")
            graded = production.dirs["master"] / "graded.mp4"
            from .media import apply_color_grade
            apply_color_grade(edit, graded)
            return {**data, "stage": "COLOR",
                    "graded_path": str(graded)}

        def subtitle_processor(data: dict) -> dict:
            nonlocal subtitles
            if narration is None:
                raise RuntimeError("SUBTITLE requires NARRATION")
            subtitles = production.build_subtitles(narration)
            return {**data, "stage": "SUBTITLE",
                    "subtitle_path": str(subtitles)}

        def master_processor(data: dict) -> dict:
            if edit is None:
                raise RuntimeError("MASTER requires EDIT")
            if subtitles is None:
                raise RuntimeError("MASTER requires SUBTITLE")
            graded = production.dirs["master"] / "graded.mp4"
            if not graded.is_file():
                from .media import apply_color_grade
                apply_color_grade(edit, graded)
            subtitled = production.dirs["master"] / "subtitled.mp4"
            from .media import burn_subtitles, master_encode
            burn_subtitles(graded, subtitles, subtitled)
            final_youtube = production.dirs["delivery"] / f"episode-{job.episode_id}-youtube.mp4"
            master_encode(subtitled, final_youtube, profile="youtube")
            final_outputs["youtube"] = final_youtube
            if profile in {"tiktok", "both"}:
                final_tiktok = production.dirs["delivery"] / f"episode-{job.episode_id}-tiktok.mp4"
                master_encode(subtitled, final_tiktok, profile="tiktok")
                final_outputs["tiktok"] = final_tiktok
            return {**data, "stage": "MASTER",
                    "master_path": str(final_youtube)}

        def qc_processor(data: dict) -> dict:
            from .qc_engine import run_qc
            if "youtube" not in final_outputs:
                raise RuntimeError("QC requires MASTER")
            planned_dur = max(5.0, sum(s.duration for s in production.scenes))
            qc = run_qc(
                video_path=final_outputs["youtube"],
                srt_path=subtitles,
                min_duration_s=max(5.0, planned_dur * 0.5),
                planned_duration_s=planned_dur,
                scene_count=len(production.scenes),
            )
            if qc["warnings"]:
                for w in qc["warnings"]:
                    logger.info(f"[QC][WARNING] check={w['name']} value={w['message']}")
            if qc["delivery_blocked"]:
                fatal_msgs = [f"{c['name']}: {c['message']}" for c in qc['fatals']]
                raise RuntimeError(
                    f"QC FATAL — mp4_fatals={fatal_msgs}"
                )
            return {**data, "stage": "QC", "qc_passed": qc["passed"],
                    "qc_fatals": len(qc["fatals"]),
                    "qc_warnings": len(qc["warnings"])}  # no Path, serializable

        def delivery_processor(data: dict) -> dict:
            from .delivery import process_delivery
            final = final_outputs.get("youtube")
            if final is None:
                raise RuntimeError("DELIVERY requires master artifact")
            planned_dur = max(5.0, sum(s.duration for s in production.scenes))
            min_dur = max(5.0, planned_dur * 0.5)
            validation = validate_master(final, min_duration=min_dur)
            # Use total asset count (shots), not scene count for validate_visual_manifest
            total_assets = production._total_visual_assets or None
            visual_qc = validate_visual_manifest(
                production.visual_manifest_path,
                expected_asset_count=total_assets,
            )
            validation["visual_content"] = visual_qc
            validation["passed"] = validation["passed"] and visual_qc["passed"]
            if not validation["passed"]:
                failed_visual = visual_qc.get("failed_checks", [])
                details = visual_qc.get("check_details", {})
                raise RuntimeError(
                    f"DELIVERY rejected:"
                    f" master_passed={validate_master(final, min_duration=min_dur)['passed']}"
                    f" visual_qc_passed={visual_qc['passed']}"
                    f" visual_failed={failed_visual}"
                    f" details={details}"
                )
            alias = production.dirs["delivery"] / f"episode-{job.episode_id}-FINAL.mp4"
            delivered = process_delivery({
                "input":    str(final),
                "output":   str(alias),
                "min_duration": min_dur,
                "expected_sha256": None,
            })
            final_outputs["final"] = Path(delivered["artifact"])  # closure only
            manifest = {
                "job_id":   job.job_id,
                "episode_id": job.episode_id,
                "title":    title,
                "language": language,
                "profile":  profile,
                "source":   "chat",
                "source_script":     str(script_path),
                "source_text_sha256": source_sha256,
                "outputs":  {k: str(v) for k, v in final_outputs.items()},
                "delivery_validation": delivered["validation"],
                "directing":    [scene.direction for scene in production.scenes],
                "environments": [s.direction.get("environment", "?") for s in production.scenes],
            }
            (production.root / "production_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return {
                **data, "stage": "DELIVERY",
                "artifact": str(final_outputs["final"]),
                "manifest": str(production.root / "production_manifest.json"),
                # Serializable delivery summary only
                "delivery_artifact": delivered["artifact"],
            }

        processors = {
            "SCRIPT":       script_processor,
            "DEVELOPMENT":  development_processor,
            "STORY":        story_processor,
            "WORLD":        world_processor,
            "CHARACTER":    character_processor,
            "SERIES_BIBLE": series_bible_processor,
            "RESEARCH":     research_processor,
            "PRE_PRODUCTION": preproduction_processor,
            "SEQUENCE":     sequence_processor,
            "SCENE":        scene_processor,
            "SHOT":         shot_processor,
            "STORYBOARD":   storyboard_processor,
            "ANIMATIC":     animatic_processor,
            "VISUAL":       visual_processor,
            "ASSET":        asset_processor,
            "CAMERA":       camera_processor,
            "DEPTH":        depth_processor,
            "MOTION":       motion_processor,
            "LIGHT":        light_processor,
            "VFX":          _meta("VFX",       "vfx"),
            "ATMOSPHERE":   _meta("ATMOSPHERE", "atmosphere"),
            "NARRATION":    narration_processor,
            "DIALOGUE":     _meta("DIALOGUE",  "dialogue"),
            "SOUND":        _meta("SOUND",     "sound"),
            "MUSIC":        music_processor,
            "AUDIO":        _meta("AUDIO",     "audio"),
            "EDIT":         edit_processor,
            "COLOR":        color_processor,
            "SUBTITLE":     subtitle_processor,
            "MASTER":       master_processor,
            "QC":           qc_processor,
            "DELIVERY":     delivery_processor,
        }

        total = len(PRODUCTION_STAGES)
        current = dict(state)
        for index, stage in enumerate(PRODUCTION_STAGES):
            self._check_cancel(job)
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
                raise RuntimeError(
                    f"Production stage failed: {stage}: {execution.error}"
                )
            current.update(execution.output)
            self._set_stage(job, stage, ((index + 1) / total) * 100.0)

        if "final" not in final_outputs:
            raise RuntimeError("Canonical production completed without FINAL MP4")

        planned_dur = max(5.0, sum(s.duration for s in production.scenes))
        min_dur = max(5.0, planned_dur * 0.5)
        final_validation = validate_master(final_outputs["final"], min_duration=min_dur)
        total_assets = production._total_visual_assets or None
        visual_qc = validate_visual_manifest(
            production.visual_manifest_path,
            expected_asset_count=total_assets,
        )
        final_validation["visual_content"] = visual_qc
        final_validation["passed"] = final_validation["passed"] and visual_qc["passed"]
        if not final_validation["passed"]:
            failed_visual = visual_qc.get("failed_checks", [])
            details = visual_qc.get("check_details", {})
            raise RuntimeError(
                f"FINAL MP4 validation failed:"
                f" master={final_validation['checks']}"
                f" visual_qc_passed={visual_qc['passed']}"
                f" visual_failed={failed_visual}"
                f" details={details}"
            )

        saved_run = pipeline.orchestrator.runs.get(run.id)
        if saved_run is not None:
            saved_run.mark_completed()
            pipeline.orchestrator.runs.save(saved_run)

        job.final_mp4 = str(final_outputs["final"])
        job.metadata["download_url"] = f"/api/jobs/{job.job_id}/video"
        self._set_stage(job, "DELIVERY", 100.0)
        job.status = "COMPLETED"
        logger.info(f"[FACTORY] COMPLETED \u2014 FINAL MP4: {job.final_mp4}")

        return {
            "job_id":    job.job_id,
            "episode_id": job.episode_id,
            "title":     title,
            "language":  language,
            "final_mp4": job.final_mp4,
            "download_url": job.metadata["download_url"],
            "outputs":   {k: str(v) for k, v in final_outputs.items()},
            "scenes":    len(production.scenes),
            "total_assets": production._total_visual_assets,
            "source_text_sha256": source_sha256,
            "logger_lines": len(logger.lines),
            "fallbacks":    len(logger.fallback_summary()),
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
                job.metadata["result"] = self.run_episode_production(
                    job, script_path, profile
                )
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
        if message.strip().lower() in {
            "status", "progress", "state",
            "\u0627\u0644\u062d\u0627\u0644\u0629", "\u0627\u0644\u062a\u0642\u062f\u0645",
        }:
            active = [j for j in self.jobs.values()
                      if j.status in {"RUNNING", "QUEUED"}]
            if not active:
                return {"reply": "No active production.", "action": None}
            job = active[-1]
            return {
                "reply": f"Episode {job.episode_id}: {job.status} \u2014 "
                         f"{job.stage} ({job.progress:.0f}%)",
                "action": None, "job_id": job.job_id,
            }
        return {
            "reply": "Use Chat production entry with Episode ID, Title, Language "
                     "and the complete script.",
            "action": "await_script",
        }
