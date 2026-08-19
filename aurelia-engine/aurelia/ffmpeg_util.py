"""Resolve and execute FFmpeg/FFprobe consistently for AURELIA Maker."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _candidate_paths() -> list[str]:
    paths: list[str] = []
    for key in ("FFMPEG_PATH", "FFMPEG_BINARY"):
        value = os.environ.get(key)
        if value:
            paths.append(value)
    which = shutil.which("ffmpeg")
    if which:
        paths.append(which)
    try:
        import imageio_ffmpeg
        paths.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    tools = Path(__file__).resolve().parents[1] / "tools"
    for name in ("ffmpeg.exe", "ffmpeg"):
        local = tools / name
        if local.exists():
            paths.append(str(local))
    return paths


def _executable(path: str | Path) -> str | None:
    candidate = Path(path)
    if candidate.is_file() and (os.access(candidate, os.X_OK) or os.name == "nt"):
        return str(candidate)
    return None


def ffmpeg_binary() -> str:
    for path in _candidate_paths():
        executable = _executable(path)
        if executable:
            return executable
    raise RuntimeError("FFmpeg not found or not executable. Install FFmpeg or imageio-ffmpeg.")


def ffprobe_binary() -> str:
    ffmpeg = Path(ffmpeg_binary())
    for name in ("ffprobe.exe", "ffprobe"):
        sibling = ffmpeg.with_name(name)
        executable = _executable(sibling)
        if executable:
            return executable
    which = shutil.which("ffprobe")
    if which:
        return which
    raise RuntimeError("FFprobe not found alongside FFmpeg or on PATH.")


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [ffmpeg_binary(), "-nostdin", *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def run_ffprobe(args: list[str]) -> subprocess.CompletedProcess[str]:
    command = [ffprobe_binary(), *args]
    return subprocess.run(command, capture_output=True, text=True, check=False)
