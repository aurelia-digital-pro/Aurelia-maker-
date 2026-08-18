"""Resolve FFmpeg/ffprobe binaries for AURELIA Maker."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _candidate_paths() -> list[str]:
    paths: list[str] = []
    env = os.environ.get("FFMPEG_PATH") or os.environ.get("FFMPEG_BINARY")
    if env:
        paths.append(env)
    which = shutil.which("ffmpeg")
    if which:
        paths.append(which)
    try:
        import imageio_ffmpeg
        paths.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    local_names = ("ffmpeg.exe", "ffmpeg")
    for name in local_names:
        local = Path(__file__).resolve().parents[1] / "tools" / name
        if local.exists():
            paths.append(str(local))
    return paths


def ffmpeg_binary() -> str:
    for path in _candidate_paths():
        if path and Path(path).exists():
            return path
    raise RuntimeError("FFmpeg not found. Install FFmpeg or install imageio-ffmpeg.")


def ffprobe_binary() -> str:
    ffmpeg = Path(ffmpeg_binary())
    names = ("ffprobe.exe", "ffprobe")
    for name in names:
        sibling = ffmpeg.with_name(name)
        if sibling.exists():
            return str(sibling)
    which = shutil.which("ffprobe")
    if which:
        return which
    raise RuntimeError("ffprobe not found alongside FFmpeg or on PATH")


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([ffmpeg_binary(), *args], capture_output=True, text=True)


def run_ffprobe(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([ffprobe_binary(), *args], capture_output=True, text=True)
