"""AURELIA Maker — FastAPI server.

Endpoints:
  GET  /api/health
  GET  /api/status           — real backend availability (SD + TTS + Pillow)
  GET  /api/series           — list all series
  POST /api/series           — create a series
  GET  /api/series/{sid}     — series detail + continuity context
  POST /api/series/{sid}/season — add season
  POST /api/series/{sid}/episode — add episode
  GET  /api/episodes         — file-system episode history
  GET  /api/jobs             — session jobs
  GET  /api/jobs/{id}        — job detail + logs + QC
  GET  /api/jobs/{id}/video  — stream FINAL MP4
  POST /api/jobs/{id}/stop   — cancel
  POST /api/jobs/{id}/retry  — restart from original_message
  POST /api/chat             — start production
  WS   /ws/terminal/{id}     — live log stream
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aurelia.chat_entry import handle_chat_production
from aurelia.factory_runner import FactoryRunner
from aurelia.media import validate_master
from aurelia.series_manager import SeriesManager
from aurelia.visual_backend import backend_status

WEB    = ROOT / "web"
OUTPUT = ROOT / "output"
SERIES_STORE = ROOT / "output" / ".series"

app    = FastAPI(title="AURELIA Maker", version="3.0.0")
runner = FactoryRunner(ROOT)
series_mgr = SeriesManager(SERIES_STORE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── models ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    language: str = "auto"
    profile: str = "both"


class CreateSeriesRequest(BaseModel):
    series_id: str
    title: str
    language: str = "ar"
    description: str = ""


class AddSeasonRequest(BaseModel):
    season_number: int
    title: str = ""


class AddEpisodeRequest(BaseModel):
    season_number: int
    episode_number: int
    title: str = ""
    language: str = ""
    script_path: str = ""


# ── health ───────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "factory": "connected", "version": "3.0.0"}


# ── backend status ──────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    """Real-time backend availability for UI badges."""
    try:
        s = backend_status()
    except Exception as exc:
        s = {"error": str(exc), "sd_available": False,
             "pillow_available": True, "primary": "pillow-fallback"}
    return s


# ── series CRUD ───────────────────────────────────────────────────────

@app.get("/api/series")
def list_series():
    all_series = series_mgr.list_series()
    return {
        "series": [
            {
                "id": s.id,
                "title": s.title,
                "language": s.language,
                "description": s.description,
                "season_count": len(s.seasons),
                "episode_count": sum(len(sn.episodes) for sn in s.seasons),
            }
            for s in all_series
        ]
    }


@app.post("/api/series")
def create_series(req: CreateSeriesRequest):
    s = series_mgr.create_series(
        series_id=req.series_id,
        title=req.title,
        language=req.language,
        description=req.description,
    )
    return {"created": True, "series_id": s.id, "title": s.title}


@app.get("/api/series/{series_id}")
def get_series(series_id: str):
    s = series_mgr.get_series(series_id)
    if s is None:
        return {"error": "not found"}
    ctx = series_mgr.get_continuity_context(series_id)
    from dataclasses import asdict
    return {"series": asdict(s), "continuity_context": ctx}


@app.post("/api/series/{series_id}/season")
def add_season(series_id: str, req: AddSeasonRequest):
    try:
        season = series_mgr.add_season(series_id, req.season_number, req.title)
        return {"created": True, "season_id": season.id}
    except KeyError:
        return {"error": f"series {series_id!r} not found"}


@app.post("/api/series/{series_id}/episode")
def add_episode(series_id: str, req: AddEpisodeRequest):
    try:
        ep = series_mgr.add_episode(
            series_id=series_id,
            season_number=req.season_number,
            episode_number=req.episode_number,
            title=req.title,
            language=req.language,
            script_path=req.script_path,
        )
        return {"created": True, "episode_id": ep.id}
    except KeyError:
        return {"error": f"series {series_id!r} not found"}


# ── episodes (file-system history) ──────────────────────────────────────

@app.get("/api/episodes")
def list_episodes():
    episodes = []
    if OUTPUT.exists():
        for episode_dir in sorted(OUTPUT.glob("episode-*")):
            if not episode_dir.is_dir():
                continue
            jobs = []
            for job_dir in sorted(episode_dir.glob("job-*")):
                final_candidates = list((job_dir / "delivery").glob("*-FINAL.mp4"))
                final = final_candidates[0] if len(final_candidates) == 1 else None
                valid = bool(final and validate_master(final, min_duration=5.0)["passed"])
                jobs.append({
                    "job_id":   job_dir.name.replace("job-", ""),
                    "has_final": valid,
                    "final_mp4": str(final) if valid else "",
                })
            episodes.append({
                "id":       episode_dir.name.replace("episode-", ""),
                "path":     str(episode_dir),
                "jobs":     jobs,
                "has_final": any(j["has_final"] for j in jobs),
            })
    return {"episodes": episodes}


# ── jobs ────────────────────────────────────────────────────────────────────

@app.get("/api/jobs")
def list_jobs():
    return {
        "jobs": [
            {
                "job_id":       j.job_id,
                "episode_id":   j.episode_id,
                "status":       j.status,
                "stage":        j.stage,
                "progress":     j.progress,
                "final_mp4":    j.final_mp4,
                "download_url": j.metadata.get("download_url", ""),
                "error":        j.error,
            }
            for j in runner.jobs.values()
        ]
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = runner.jobs.get(job_id)
    if not job:
        return {"error": "not found"}
    return {
        "job_id":       job.job_id,
        "episode_id":   job.episode_id,
        "status":       job.status,
        "stage":        job.stage,
        "progress":     job.progress,
        "final_mp4":    job.final_mp4,
        "download_url": job.metadata.get("download_url", ""),
        "error":        job.error,
        "logs":         job.logs[-500:],
        "scene_info":   job.metadata.get("scene_info", ""),
        "total_shots":  job.metadata.get("total_shots", 0),
        "outputs":      job.metadata.get("outputs", {}),
        "qc":           job.metadata.get("qc", {}),
        "visual_backend": job.metadata.get("visual_backend", {}),
    }


@app.get("/api/jobs/{job_id}/video")
def get_job_video(job_id: str):
    job = runner.jobs.get(job_id)
    if not job or job.status != "COMPLETED" or not job.final_mp4:
        return {"error": "Video not ready"}
    path = Path(job.final_mp4).resolve()
    if not path.is_file():
        return {"error": "Video artifact not found"}
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"episode-{job.episode_id}-FINAL.mp4",
    )


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    job = runner.jobs.get(job_id)
    if not job:
        return {"error": "not found"}
    job.metadata["cancel_requested"] = True
    job.status = "STOPPING"
    return {"status": "cancel_requested", "job_id": job_id}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str):
    job = runner.jobs.get(job_id)
    if not job:
        return {"error": "not found"}
    if job.status not in {"FAILED", "STOPPING", "STOPPED"}:
        return {"error": f"Cannot retry job in status {job.status}"}
    original_msg = job.metadata.get("original_message", "")
    if not original_msg:
        return {"error": "No original message to retry"}
    result = handle_chat_production(runner, original_msg)
    return {"status": "retry_started", "job_id": result.get("job_id"),
            "reply": result.get("reply")}


# ── chat ──────────────────────────────────────────────────────────────────

@app.post("/api/chat")
def chat(req: ChatRequest):
    return handle_chat_production(runner, req.message)


# ── WebSocket live logs ─────────────────────────────────────────────────────

@app.websocket("/ws/terminal/{job_id}")
async def terminal_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    last_len = 0
    try:
        while True:
            job = runner.jobs.get(job_id)
            if job:
                logs = job.logs
                if len(logs) > last_len:
                    for line in logs[last_len:]:
                        await websocket.send_text(line)
                    last_len = len(logs)
                if job.status in {"COMPLETED", "FAILED", "STOPPED"}:
                    await websocket.send_text(f"[DONE] {job.status}")
                    if job.final_mp4:
                        await websocket.send_text(f"[FINAL] {job.final_mp4}")
                    break
                if job.metadata.get("cancel_requested"):
                    await websocket.send_text("[DONE] STOPPING")
                    break
            import asyncio
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


# ── static frontend ─────────────────────────────────────────────────────────

if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
