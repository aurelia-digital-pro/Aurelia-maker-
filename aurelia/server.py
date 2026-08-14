"""AURELIA Maker — FastAPI web server with Chat, progress, and terminal."""

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

from aurelia.factory_runner import FactoryRunner

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


class EpisodeRequest(BaseModel):
    episode_id: str
    profile: str = "both"


@app.get("/api/health")
def health():
    return {"status": "ok", "factory": "connected"}


@app.get("/api/episodes")
def list_episodes():
    episodes = []
    if OUTPUT.exists():
        for path in sorted(OUTPUT.glob("episode-*")):
            final = path / "delivery" / f"{path.name}-FINAL.mp4"
            manifest = path / "production_manifest.json"
            episodes.append({
                "id": path.name.replace("episode-", ""),
                "path": str(path),
                "has_final": final.exists(),
                "final_mp4": str(final) if final.exists() else "",
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
        "error": job.error,
        "logs": job.logs[-200:],
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    return runner.handle_chat(req.message)


@app.post("/api/episodes/produce")
def produce_episode(req: EpisodeRequest):
    job = runner.execute_async(req.episode_id.zfill(4), profile=req.profile)
    return {
        "job_id": job.job_id,
        "episode_id": job.episode_id,
        "status": job.status,
    }


@app.get("/api/video/{episode_id}")
def get_video(episode_id: str):
    ep = episode_id.zfill(4)
    candidates = [
        OUTPUT / f"episode-{ep}" / "delivery" / f"episode-{ep}-FINAL.mp4",
        OUTPUT / f"episode-{ep}" / "delivery" / f"episode-{ep}-youtube.mp4",
    ]
    for path in candidates:
        if path.exists():
            return FileResponse(path, media_type="video/mp4")
    return {"error": "Video not found"}


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
