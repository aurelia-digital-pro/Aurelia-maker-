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
import re
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


def visual_variation_preflight(video_path: Path | str, threshold: float = 0.005) -> dict[str, Any]:
    """Measure 10-second decoded frame differences before mastering.

    This is intentionally the same principle and threshold used by final QC;
    it is an early diagnostic gate, not a replacement for run_qc().
    """
    path = Path(video_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not path.is_file():
        return {
            "passed": False,
            "minimum_diff": 0.0,
            "threshold": threshold,
            "video_path": str(path),
            "message": "ffmpeg unavailable or video path missing",
        }
    frames: list[bytes] = []
    try:
        duration_probe = _ffprobe(path).get("format", {}).get("duration", 0.0)
        duration = float(duration_probe or 0.0)
    except Exception:
        duration = 0.0
    for timestamp in range(0, int(duration), 10):
        try:
            sample = subprocess.run(
                [ffmpeg, "-v", "error", "-ss", str(timestamp), "-i", str(path),
                 "-frames:v", "1", "-vf", "scale=64:36,format=gray",
                 "-f", "rawvideo", "pipe:1"],
                capture_output=True, timeout=30,
            )
            if sample.returncode == 0 and sample.stdout:
                frames.append(sample.stdout)
        except Exception:
            pass
    diffs: list[float] = []
    for first, second in zip(frames, frames[1:]):
        size = min(len(first), len(second))
        if size:
            diffs.append(sum(abs(first[i] - second[i]) for i in range(size)) / (size * 255.0))
    minimum = min(diffs) if diffs else 0.0
    passed = bool(diffs) and minimum >= threshold
    return {
        "passed": passed,
        "minimum_diff": minimum,
        "threshold": threshold,
        "video_path": str(path),
        "message": "" if passed else (
            f"minimum 10s sample diff {minimum:.4f} < {threshold:.3f}; "
            "likely insufficient real scene motion or provider variation"
        ),
    }


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
    required_artifacts: list[Path | str] | None = None,
    narration_path: Path | str | None = None,
    expected_text_path: Path | str | None = None,
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

    # Required downstream artifacts. These are hard failures because a final
    # video without its declared production inputs is not auditable.
    if required_artifacts:
        for artifact in required_artifacts:
            artifact_path = Path(artifact)
            artifact_ok = artifact_path.is_file() and artifact_path.stat().st_size > 0
            checks.append(_check(
                "required_artifact",
                artifact_ok,
                "FATAL",
                "" if artifact_ok else f"Missing required artifact: {artifact_path}",
            ))

    # Full-stream decodeability. A valid container/stream probe is not enough.
    decode_ok = True
    decode_msg = ""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            decode = subprocess.run(
                [ffmpeg, "-v", "error", "-i", str(video_path), "-map", "0:v:0", "-f", "null", "-"],
                capture_output=True, timeout=180,
            )
            decode_ok = decode.returncode == 0
            if not decode_ok:
                decode_msg = decode.stderr.decode("utf-8", errors="replace")[-500:]
        except Exception as exc:
            decode_ok = False
            decode_msg = str(exc)
    else:
        decode_ok = False
        decode_msg = "ffmpeg is unavailable"
    checks.append(_check("full_decode", decode_ok, "FATAL", "" if decode_ok else decode_msg))

    # Production-level freeze detection. A motion-rendered shot may be calm,
    # but a repeated frame longer than half a second is never acceptable in a
    # finished film stream.
    freeze_ok = True
    freeze_msg = ""
    if ffmpeg and duration > 0:
        try:
            freeze = subprocess.run(
                [ffmpeg, "-i", str(video_path), "-vf", "freezedetect=n=-60dB:d=0.5", "-an", "-f", "null", "-"],
                capture_output=True, timeout=180,
            )
            stderr = freeze.stderr.decode("utf-8", errors="replace")
            values = [float(v) for v in re.findall(r"freeze_duration:\s*([0-9.]+)", stderr)]
            long_freezes = [v for v in values if v > 0.5]
            freeze_ok = not long_freezes
            if not freeze_ok:
                freeze_msg = "freeze durations over 0.5s: " + ", ".join(f"{v:.3f}s" for v in long_freezes[:8])
        except Exception as exc:
            freeze_ok = False
            freeze_msg = f"freezedetect failed: {exc}"
    checks.append(_check("freeze_frames", freeze_ok, "FATAL", "" if freeze_ok else freeze_msg))

    # Sample the encoded video at multiple timestamps. This catches frozen or
    # duplicated output that can still pass ordinary container checks.
    sample_hashes: list[str] = []
    variation_msg = ""
    if ffmpeg and duration > 0:
        for fraction in (0.2, 0.5, 0.8):
            timestamp = max(0.0, min(duration - 0.05, duration * fraction))
            try:
                frame = subprocess.run(
                    [ffmpeg, "-v", "error", "-ss", f"{timestamp:.3f}", "-i", str(video_path),
                     "-frames:v", "1", "-f", "image2", "-c:v", "png", "pipe:1"],
                    capture_output=True, timeout=60,
                )
                if frame.returncode == 0 and frame.stdout:
                    sample_hashes.append(hashlib.sha256(frame.stdout).hexdigest())
            except Exception:
                pass
    unique_samples = len(set(sample_hashes))
    variation_ok = len(sample_hashes) >= 2 and unique_samples >= 2
    if not variation_ok:
        variation_msg = f"Only {unique_samples} unique encoded frames from {len(sample_hashes)} samples"
    checks.append(_check("temporal_variation", variation_ok, "FATAL", "" if variation_ok else variation_msg))

    # Stronger 10-second-window visual variation gate. Frames are decoded at a
    # small analysis size, then adjacent mean absolute pixel differences are
    # measured; this checks motion rather than merely distinct timestamps.
    variation = visual_variation_preflight(video_path, threshold=0.005)
    checks.append(_check(
        "visual_variation",
        bool(variation["passed"]),
        "FATAL",
        str(variation.get("message", "")),
    ))

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

        # Subtitle completeness is a delivery requirement: cues must be
        # parseable, cover the beginning and end of the final video, and have
        # positive durations with non-empty text. The producer preserves the
        # full narration text by splitting long scene text into cues.
        subtitle_complete = False
        subtitle_message = "Subtitle track unavailable"
        if srt_ok:
            try:
                raw = srt_path.read_text(encoding="utf-8-sig")
                cues = []
                blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n").strip())
                for block in blocks:
                    lines = [line.strip() for line in block.split("\n") if line.strip()]
                    timing = next((line for line in lines if "-->" in line), "")
                    text_lines = [line for line in lines if "-->" not in line and not line.isdigit()]
                    if not timing or not text_lines:
                        continue
                    start_text, end_text = [part.strip() for part in timing.split("-->", 1)]
                    def parse_time(value: str) -> float:
                        hh, mm, rest = value.replace(",", ".").split(":")
                        return int(hh) * 3600 + int(mm) * 60 + float(rest)
                    start = parse_time(start_text)
                    end = parse_time(end_text)
                    cues.append((start, end, " ".join(text_lines)))
                first_start = cues[0][0] if cues else duration
                last_end = cues[-1][1] if cues else 0.0
                malformed = any(end <= start or not text for start, end, text in cues)
                actual_words = re.findall(r"[\w']+", " ".join(text for _, _, text in cues).lower())
                coverage = 1.0
                if expected_text_path and Path(expected_text_path).is_file():
                    expected_raw = Path(expected_text_path).read_text(encoding="utf-8", errors="replace")
                    expected_raw = "\n".join(line for line in expected_raw.splitlines() if not re.match(r"^\s*(episode|title|language)\s*[:=]", line, re.I))
                    expected_words = re.findall(r"[\w']+", expected_raw.lower())
                    from collections import Counter
                    have, need = Counter(actual_words), Counter(expected_words)
                    covered = sum(min(have[word], count) for word, count in need.items())
                    coverage = covered / max(1, len(expected_words))
                subtitle_complete = bool(cues) and first_start <= 0.5 and last_end >= max(0.0, duration - 2.0) and coverage >= 0.90 and not malformed
                if not subtitle_complete:
                    subtitle_message = f"cues={len(cues)}, word_coverage={coverage:.3f}, coverage={first_start:.2f}s..{last_end:.2f}s for video {duration:.2f}s"
                else:
                    subtitle_message = ""
            except (OSError, ValueError, UnicodeError) as exc:
                subtitle_message = f"Subtitle parse failed: {exc}"
        checks.append(_check("subtitle_completeness", subtitle_complete, "FATAL", subtitle_message))

    narration_ok = True
    narration_message = ""
    if narration_path is not None:
        narration_file = Path(narration_path)
        narration_ok = narration_file.is_file() and narration_file.stat().st_size > 0
        if narration_ok:
            narration_probe = _ffprobe(narration_file)
            narration_fmt = narration_probe.get("format", {})
            try:
                narration_duration = float(narration_fmt.get("duration") or 0)
                narration_ok = narration_duration > 0 and abs(narration_duration - duration) <= max(5.0, duration * 0.05)
                if not narration_ok:
                    narration_message = f"narration={narration_duration:.2f}s vs video={duration:.2f}s"
            except (TypeError, ValueError):
                narration_ok = False
                narration_message = "narration duration could not be measured"
        else:
            narration_message = f"narration file missing or empty: {narration_file}"
    checks.append(_check("narration_audible", narration_ok, "FATAL", "" if narration_ok else narration_message))

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

    # Audio/video duration relationship
    av_duration_ok = True
    av_duration_msg = ""
    if audio_streams:
        try:
            audio_duration = float(audio_streams[0].get("duration") or 0)
            if audio_duration > 0 and abs(audio_duration - duration) > 1.0:
                av_duration_ok = False
                av_duration_msg = f"Audio duration {audio_duration:.2f}s vs video {duration:.2f}s"
        except Exception:
            pass
    checks.append(_check("av_duration", av_duration_ok, "WARNING", "" if av_duration_ok else av_duration_msg))

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


__all__ = ["run_qc", "visual_variation_preflight"]
