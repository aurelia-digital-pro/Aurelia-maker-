from __future__ import annotations

import os
import shutil
import subprocess
import time
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


def _timeout_from_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(1.0, value)


def _command_text(binary: str, args: list[str]) -> str:
    return " ".join([binary, "-nostdin", *map(str, args)])


def _output_hint(args: list[str], output_path: str | Path | None) -> str:
    if output_path is not None:
        return str(output_path)
    for value in reversed(args):
        candidate = str(value)
        if not candidate.startswith("-") and ("/" in candidate or "\\" in candidate or "." in Path(candidate).name):
            return candidate
    return "unknown"


def run_ffmpeg(
    args: list[str],
    *,
    timeout_seconds: float | None = None,
    stage: str = "FFmpeg",
    output_path: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    binary = ffmpeg_binary()
    timeout = timeout_seconds or _timeout_from_env("AURELIA_FFMPEG_TIMEOUT_SECONDS", 900.0)
    command = [binary, "-nostdin", *args]
    started = time.monotonic()
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        stderr = exc.stderr or exc.stdout or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        detail = str(stderr).strip()[-1200:]
        raise RuntimeError(
            f"FFmpeg timeout: stage={stage} timeout_s={timeout:.1f} "
            f"elapsed_s={elapsed:.1f} output={_output_hint(args, output_path)} "
            f"stderr={detail or '<none>'} command={_command_text(binary, args)}"
        ) from exc


def run_ffprobe(
    args: list[str],
    *,
    timeout_seconds: float | None = None,
    stage: str = "FFprobe",
    input_path: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    binary = ffprobe_binary()
    timeout = timeout_seconds or _timeout_from_env("AURELIA_FFPROBE_TIMEOUT_SECONDS", 60.0)
    command = [binary, *args]
    started = time.monotonic()
    try:
        return subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        stderr = exc.stderr or exc.stdout or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"FFprobe timeout: stage={stage} timeout_s={timeout:.1f} "
            f"elapsed_s={elapsed:.1f} input={input_path or '<unknown>'} "
            f"stderr={str(stderr).strip()[-1200:] or '<none>'}"
        ) from exc
