"""AURELIA Maker — FastAPI web server with Chat, progress, and job-bound delivery."""

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

WEB = ROOT / "web"
OUTPUT = ROOT / "output"

app = FastAPI(title="AURELIA Maker", version="1.0.0")
runner = FactoryRunner(ROOT)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
def health():
    return {"status": "ok", "factory": "connected", "production_entry": "chat_only"}


@app.get("/api/episodes")
def list_episodes():
    episodes = []
    if OUTPUT.exists():
        for episode_dir in sorted(OUTPUT.glob("episode-*")):
            if not episode_dir.is_dir():
                continue
            jobs = []
            for job_dir in sorted(episode_dir.glob("job-*")):
                manifest = job_dir / "production_manifest.json"
                final_candidates = list((job_dir / "delivery").glob("*-FINAL.mp4"))
                final = final_candidates[0] if len(final_candidates) == 1 else None
                valid = bool(final and validate_master(final, min_duration=30.0)["passed"])
                jobs.append({
                    "job_id": job_dir.name.replace("job-", ""),
                    "has_final": valid,
                    "final_mp4": str(final) if valid else "",
                    "manifest": str(manifest) if manifest.is_file() else "",
                })
            episodes.append({
                "id": episode_dir.name.replace("episode-", ""),
                "path": str(episode_dir),
                "jobs": jobs,
                "has_final": any(job["has_final"] for job in jobs),
            })
    return {"episodes": episodes}


@app.get("/api/jobs")
def list_jobs():
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "episode_id": j.episode_id,
                "status": j.status,
                "stage": j.stage,
                "progress": j.progress,
                "final_mp4": j.final_mp4,
                "download_url": j.metadata.get("download_url", ""),
                "error": j.error,
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
        "job_id": job.job_id,
        "episode_id": job.episode_id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "final_mp4": job.final_mp4,
        "download_url": job.metadata.get("download_url", ""),
        "error": job.error,
        "logs": job.logs[-200:],
    }


@app.get("/api/jobs/{job_id}/video")
def get_job_video(job_id: str):
    job = runner.jobs.get(job_id)
    if not job or job.status != "COMPLETED" or not job.final_mp4:
        return {"error": "Video not ready"}
    path = Path(job.final_mp4).resolve()
    if not path.is_file():
        return {"error": "Video artifact not found"}
    validation = validate_master(path, min_duration=30.0)
    if not validation["passed"]:
        return {"error": "Video artifact failed validation", "validation": validation}
    return FileResponse(path, media_type="video/mp4", filename=f"episode-{job.episode_id}-FINAL.mp4")


@app.post("/api/chat")
def chat(req: ChatRequest):
    return handle_chat_production(runner, req.message)


@app.get("/api/video/{episode_id}")
def get_video(episode_id: str):
    ep = episode_id.zfill(4)
    completed = [j for j in runner.jobs.values() if j.episode_id == ep and j.status == "COMPLETED" and j.final_mp4]
    if not completed:
        return {"error": "No completed video for this episode in the current server session"}
    job = completed[-1]
    return get_job_video(job.job_id)


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
                if job.status in {"COMPLETED", "FAILED"}:
                    await websocket.send_text(f"[DONE] {job.status}")
                    if job.final_mp4:
                        await websocket.send_text(f"[FINAL] {job.final_mp4}")
                    break
            import asyncio
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


if WEB.exists():
    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
