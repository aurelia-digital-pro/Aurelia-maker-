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

    local = Path(__file__).resolve().parents[1] / "tools" / "ffmpeg.exe"
    if local.exists():
        paths.append(str(local))

    return paths


def ffmpeg_binary() -> str:
    for path in _candidate_paths():
        if path and Path(path).exists():
            return path
    raise RuntimeError(
        "FFmpeg not found. Install FFmpeg or run: pip install imageio-ffmpeg"
    )


def ffprobe_binary() -> str:
    ffmpeg = Path(ffmpeg_binary())
    probe = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    if probe.exists():
        return str(probe)

    which = shutil.which("ffprobe")
    if which:
        return which

    sibling = ffmpeg.parent / ("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    if sibling.exists():
        return str(sibling)

    return ffmpeg_binary()


def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [ffmpeg_binary(), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def run_ffprobe(args: list[str]) -> subprocess.CompletedProcess[str]:
    cmd = [ffprobe_binary(), *args]
    return subprocess.run(cmd, capture_output=True, text=True)
