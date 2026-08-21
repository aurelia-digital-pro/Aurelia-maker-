"""AURELIA Maker \u2014 FastAPI production server.

Endpoints:
  GET  /api/health
  GET  /api/status          \u2014 backend availability (SD, TTS, Pillow)
  GET  /api/episodes        \u2014 completed episode history
  GET  /api/jobs            \u2014 all current-session jobs
  GET  /api/jobs/{id}       \u2014 job state + logs + QC + outputs
  GET  /api/jobs/{id}/video \u2014 stream final MP4
  POST /api/jobs/{id}/stop  \u2014 request job cancellation
  POST /api/jobs/{id}/retry \u2014 restart a failed/stopped job
  POST /api/chat            \u2014 start production from chat message
  WS   /ws/terminal/{id}    \u2014 live log stream for a job
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
from aurelia.visual_backend import backend_status

WEB    = ROOT / "web"
OUTPUT = ROOT / "output"

app    = FastAPI(title="AURELIA Maker", version="2.0.0")
runner = FactoryRunner(ROOT)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# \u2500\u2500 models \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

class ChatRequest(BaseModel):
    message: str
    language: str = "auto"
    profile: str = "both"


# \u2500\u2500 health \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

@app.get("/api/health")
def health():
    return {"status": "ok", "factory": "connected", "version": "2.0.0"}


# \u2500\u2500 backend status \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

@app.get("/api/status")
def status():
    """Return real-time backend availability for the UI status badges."""
    try:
        s = backend_status()
    except Exception as exc:
        s = {"error": str(exc), "sd_available": False, "pillow_available": True, "primary": "pillow-fallback"}
    return s


# \u2500\u2500 episodes (history) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

@app.get("/api/episodes")
def list_episodes():
    episodes = []
    if OUTPUT.exists():
        for episode_dir in sorted(OUTPUT.glob("episode-*")):
            if not episode_dir.is_dir():
                continue
            jobs = []
            for job_dir in sorted(episode_dir.glob("job-*")):
                manifest         = job_dir / "production_manifest.json"
                final_candidates = list((job_dir / "delivery").glob("*-FINAL.mp4"))
                final = final_candidates[0] if len(final_candidates) == 1 else None
                valid = bool(final and validate_master(final, min_duration=5.0)["passed"])
                jobs.append({
                    "job_id":    job_dir.name.replace("job-", ""),
                    "has_final": valid,
                    "final_mp4": str(final) if valid else "",
                    "manifest":  str(manifest) if manifest.is_file() else "",
                })
            episodes.append({
                "id":       episode_dir.name.replace("episode-", ""),
                "path":     str(episode_dir),
                "jobs":     jobs,
                "has_final": any(j["has_final"] for j in jobs),
            })
    return {"episodes": episodes}


# \u2500\u2500 jobs \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

@app.get("/api/jobs")
def list_jobs():
    return {
        "jobs": [
            {
                "job_id":        j.job_id,
                "episode_id":    j.episode_id,
                "status":        j.status,
                "stage":         j.stage,
                "progress":      j.progress,
                "final_mp4":     j.final_mp4,
                "download_url":  j.metadata.get("download_url", ""),
                "error":         j.error,
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
        "job_id":      job.job_id,
        "episode_id":  job.episode_id,
        "status":      job.status,
        "stage":       job.stage,
        "progress":    job.progress,
        "final_mp4":   job.final_mp4,
        "download_url": job.metadata.get("download_url", ""),
        "error":       job.error,
        "logs":        job.logs[-500:],
        "scene_info":  job.metadata.get("scene_info", ""),
        "total_shots": job.metadata.get("total_shots", 0),
        "outputs":     job.metadata.get("outputs", {}),
        "qc":          job.metadata.get("qc", {}),
    }


@app.get("/api/jobs/{job_id}/video")
def get_job_video(job_id: str):
    job = runner.jobs.get(job_id)
    if not job or job.status != "COMPLETED" or not job.final_mp4:
        return {"error": "Video not ready"}
    path = Path(job.final_mp4).resolve()
    if not path.is_file():
        return {"error": "Video artifact not found"}
    validation = validate_master(path, min_duration=5.0)
    if not validation["passed"]:
        return {"error": "Video artifact failed validation", "validation": validation}
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"episode-{job.episode_id}-FINAL.mp4",
    )


@app.post("/api/jobs/{job_id}/stop")
def stop_job(job_id: str):
    """Request job cancellation. Sets a cancel flag; the runner checks it."""
    job = runner.jobs.get(job_id)
    if not job:
        return {"error": "not found"}
    job.metadata["cancel_requested"] = True
    job.status = "STOPPING"
    return {"status": "cancel_requested", "job_id": job_id}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str):
    """Retry a failed/stopped job from the beginning using the same script."""
    job = runner.jobs.get(job_id)
    if not job:
        return {"error": "not found"}
    if job.status not in {"FAILED", "STOPPING", "STOPPED"}:
        return {"error": f"Cannot retry job in status {job.status}"}
    # Re-submit via chat_entry using the original message stored in metadata
    original_msg = job.metadata.get("original_message", "")
    if not original_msg:
        return {"error": "No original message to retry"}
    result = handle_chat_production(runner, original_msg)
    return {"status": "retry_started", "job_id": result.get("job_id"), "reply": result.get("reply")}


# \u2500\u2500 chat (primary production entrypoint) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

@app.post("/api/chat")
def chat(req: ChatRequest):
    return handle_chat_production(runner, req.message)


# \u2500\u2500 WebSocket live logs \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

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


# \u2500\u2500 static frontend \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n

if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
