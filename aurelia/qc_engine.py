"""AURELIA — real QC engine with WARNING/FATAL distinction.

Checks:
  FATAL (block delivery):
    - file_exists          : output file exists
    - file_size            : file size > 100KB
    - video_stream         : FFprobe finds a video stream
    - audio_stream         : FFprobe finds an audio stream
    - min_duration         : duration >= min_duration_s
    - resolution           : width and height >= min values
    - fps                  : frame rate >= min fps
    - encoding             : codec = h264 or hevc
    - delivery_integrity   : SHA256 matches if reference supplied

  WARNING (log but allow delivery):
    - subtitle_file        : .srt file exists and is non-empty
    - black_frames         : FFprobe blackdetect finds no long black segments
    - av_sync              : audio start_time within 200ms of video start_time
    - target_duration      : actual duration within 10% of planned duration
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _ffprobe(path: Path) -> dict[str, Any]:
    """Run ffprobe and return parsed JSON or empty dict."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout.decode("utf-8", errors="replace"))
    except Exception:
        pass
    return {}


def _check(name: str, passed: bool, severity: str, message: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "severity": severity, "message": message}


def run_qc(
    video_path: Path | str,
    srt_path: Path | str | None = None,
    min_duration_s: float = 5.0,
    planned_duration_s: float | None = None,
    min_width: int = 640,
    min_height: int = 360,
    min_fps: float = 18.0,
    expected_sha256: str | None = None,
    scene_count: int | None = None,
) -> dict[str, Any]:
    """Run full QC on the final delivery MP4.

    Returns:
      {
        "passed": bool,          # True only if no FATAL failures
        "delivery_blocked": bool,
        "checks": [...],         # full check list
        "fatals": [...],         # FATAL failures only
        "warnings": [...],       # WARNING failures only
        "duration": float,
        "resolution": [w, h],
        "fps": float,
        "codecs": {"video": str, "audio": str},
      }
    """
    video_path = Path(video_path)
    checks: list[dict[str, Any]] = []

    # ── FATAL checks ──────────────────────────────────────────────────────

    # file exists
    exists = video_path.is_file()
    checks.append(_check("file_exists", exists, "FATAL",
                         "" if exists else f"File not found: {video_path}"))
    if not exists:
        return _build_result(checks, 0.0, [0, 0], 0.0, {})

    # file size
    size = video_path.stat().st_size
    size_ok = size > 100_000
    checks.append(_check("file_size", size_ok, "FATAL",
                         "" if size_ok else f"File too small: {size} bytes"))

    # FFprobe data
    probe = _ffprobe(video_path)
    streams = probe.get("streams", [])
    fmt     = probe.get("format", {})

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    has_video = len(video_streams) > 0
    has_audio = len(audio_streams) > 0
    checks.append(_check("video_stream", has_video, "FATAL",
                         "" if has_video else "No video stream found"))
    checks.append(_check("audio_stream", has_audio, "FATAL",
                         "" if has_audio else "No audio stream found"))

    # duration
    duration = 0.0
    try:
        duration = float(fmt.get("duration") or 0)
    except Exception:
        pass
    dur_ok = duration >= min_duration_s
    checks.append(_check("min_duration", dur_ok, "FATAL",
                         "" if dur_ok else f"Duration {duration:.1f}s < min {min_duration_s}s"))

    # resolution
    width = height = 0
    if video_streams:
        width  = int(video_streams[0].get("width",  0))
        height = int(video_streams[0].get("height", 0))
    res_ok = width >= min_width and height >= min_height
    checks.append(_check("resolution", res_ok, "FATAL",
                         "" if res_ok else f"Resolution {width}x{height} below {min_width}x{min_height}"))

    # fps
    fps = 0.0
    if video_streams:
        r_frame_rate = video_streams[0].get("r_frame_rate", "0/1")
        try:
            n, d = r_frame_rate.split("/")
            fps = float(n) / max(float(d), 1)
        except Exception:
            pass
    fps_ok = fps >= min_fps
    checks.append(_check("fps", fps_ok, "FATAL",
                         "" if fps_ok else f"FPS {fps:.1f} < min {min_fps}"))

    # encoding
    codec = ""
    if video_streams:
        codec = video_streams[0].get("codec_name", "").lower()
    codec_ok = codec in {"h264", "hevc", "avc"}
    checks.append(_check("encoding", codec_ok, "FATAL",
                         "" if codec_ok else f"Unexpected codec: {codec!r}"))

    # delivery integrity
    if expected_sha256:
        actual_sha = hashlib.sha256(video_path.read_bytes()).hexdigest()
        sha_ok = actual_sha == expected_sha256
        checks.append(_check("delivery_integrity", sha_ok, "FATAL",
                             "" if sha_ok else "SHA256 mismatch — file corrupted"))

    audio_codec = ""
    if audio_streams:
        audio_codec = audio_streams[0].get("codec_name", "")

    # ── WARNING checks ────────────────────────────────────────────────────

    # subtitles
    if srt_path:
        srt_path = Path(srt_path)
        srt_ok = srt_path.is_file() and srt_path.stat().st_size > 10
        checks.append(_check("subtitle_file", srt_ok, "WARNING",
                             "" if srt_ok else f"SRT not found or empty: {srt_path}"))

    # black frames (uses blackdetect filter)
    black_ok = True
    black_msg = ""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            result = subprocess.run(
                [
                    ffmpeg, "-i", str(video_path),
                    "-vf", "blackdetect=d=2:pix_th=0.10",
                    "-an", "-f", "null", "-",
                ],
                capture_output=True, timeout=60,
            )
            stderr = result.stderr.decode("utf-8", errors="replace")
            black_segments = [l for l in stderr.splitlines() if "black_start" in l]
            if len(black_segments) > 0:
                black_ok = False
                black_msg = f"{len(black_segments)} black segment(s) detected"
        except Exception:
            pass
    checks.append(_check("black_frames", black_ok, "WARNING",
                         "" if black_ok else black_msg))

    # AV sync
    av_sync_ok = True
    av_sync_msg = ""
    if video_streams and audio_streams:
        try:
            v_start = float(video_streams[0].get("start_time") or 0)
            a_start = float(audio_streams[0].get("start_time") or 0)
            if abs(v_start - a_start) > 0.200:
                av_sync_ok = False
                av_sync_msg = f"AV start time offset {abs(v_start-a_start)*1000:.0f}ms > 200ms"
        except Exception:
            pass
    checks.append(_check("av_sync", av_sync_ok, "WARNING",
                         "" if av_sync_ok else av_sync_msg))

    # target duration
    if planned_duration_s and planned_duration_s > 0:
        ratio = abs(duration - planned_duration_s) / max(planned_duration_s, 1)
        dur_target_ok = ratio <= 0.10
        checks.append(_check(
            "target_duration", dur_target_ok, "WARNING",
            "" if dur_target_ok else
            f"Duration {duration:.1f}s vs planned {planned_duration_s:.1f}s ({ratio*100:.0f}% off)",
        ))

    return _build_result(checks, duration, [width, height], fps,
                         {"video": codec, "audio": audio_codec})


def _build_result(
    checks: list[dict[str, Any]],
    duration: float,
    resolution: list[int],
    fps: float,
    codecs: dict[str, str],
) -> dict[str, Any]:
    fatals   = [c for c in checks if not c["passed"] and c["severity"] == "FATAL"]
    warnings = [c for c in checks if not c["passed"] and c["severity"] == "WARNING"]
    passed   = len(fatals) == 0
    return {
        "passed":           passed,
        "delivery_blocked": not passed,
        "checks":           checks,
        "fatals":           fatals,
        "warnings":         warnings,
        "duration":         duration,
        "resolution":       resolution,
        "fps":              fps,
        "codecs":           codecs,
    }


__all__ = ["run_qc"]
