"""AURELIA Maker — FFmpeg media assembly and finishing utilities."""

from __future__ import annotations
import json
from pathlib import Path
from .ffmpeg_util import run_ffmpeg, run_ffprobe


def _run(args: list[str]) -> None:
    result = run_ffmpeg(args)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg command failed:\n{' '.join(args)}\n{result.stderr}")


def probe_duration(path: str | Path) -> float:
    result = run_ffprobe(["-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    if result.returncode != 0:
        return 0.0
    try:
        return float(json.loads(result.stdout).get("format", {}).get("duration", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0.0


def probe_has_audio(path: str | Path) -> bool:
    result = run_ffprobe(["-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    return result.returncode == 0 and bool(result.stdout.strip())


def concat_clips(clips: list[str | Path], output: str | Path) -> Path:
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    if not clips: raise ValueError("No clips supplied")
    if len(clips) == 1:
        output_path.write_bytes(Path(clips[0]).read_bytes()); return output_path
    list_file = output_path.parent / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{Path(c).resolve().as_posix()}'" for c in clips), encoding="utf-8")
    _run(["-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(output_path)])
    return output_path


def mix_narration_and_music(video: str | Path, narration: str | Path, output: str | Path, music: str | Path | None = None) -> Path:
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    video = Path(video); narration = Path(narration)
    if music and Path(music).exists():
        _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(narration), "-i", str(music), "-filter_complex", "[1:a]volume=1.0[narr];[2:a]volume=0.18[bgm];[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]", "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output_path)])
    else:
        _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(narration), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output_path)])
    return output_path


def apply_color_grade(source: str | Path, output: str | Path, contrast: float = 1.08, saturation: float = 1.12, brightness: float = -0.02) -> Path:
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", f"eq=contrast={contrast}:saturation={saturation}:brightness={brightness}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)])
    return output_path


def burn_subtitles(source: str | Path, srt: str | Path, output: str | Path) -> Path:
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path = Path(srt).resolve()
    escaped_srt = srt_path.as_posix().replace(":", r"\:").replace("'", r"\'")
    subtitle_filter = f"subtitles=filename='{escaped_srt}':force_style='FontSize=28,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,MarginV=40'"
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", subtitle_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)])
    return output_path


def master_encode(source: str | Path, output: str | Path, width: int = 1920, height: int = 1080, fps: int = 24, profile: str = "youtube") -> Path:
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    if profile == "tiktok": width, height = 1080, 1920
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)])
    return output_path


def generate_ambient_music(duration_sec: float, output: str | Path) -> Path:
    from pydub import AudioSegment
    from pydub.generators import Sine
    output_path = Path(output); output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_ms = int(max(duration_sec, 5) * 1000)
    mixed = Sine(55).to_audio_segment(duration=duration_ms).apply_gain(-22).overlay(Sine(110).to_audio_segment(duration=duration_ms).apply_gain(-26)).overlay(Sine(165).to_audio_segment(duration=duration_ms).apply_gain(-30)).fade_in(2000).fade_out(3000)
    mixed.export(str(output_path), format="wav")
    return output_path


def validate_master(path: str | Path, min_duration: float = 5.0) -> dict:
    path = Path(path)
    checks = {"exists": path.exists(), "non_empty": path.exists() and path.stat().st_size > 1000, "duration_ok": probe_duration(path) >= min_duration, "has_video": False, "has_audio": False}
    if path.exists():
        video = run_ffprobe(["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(path)])
        try:
            streams = json.loads(video.stdout).get("streams", [])
            checks["has_video"] = video.returncode == 0 and bool(streams) and streams[0].get("codec_name") == "h264" and int(streams[0].get("width", 0)) > 0 and int(streams[0].get("height", 0)) > 0
        except (ValueError, TypeError, json.JSONDecodeError):
            checks["has_video"] = False
        checks["has_audio"] = probe_has_audio(path)
    return {"passed": all(checks.values()), "checks": checks, "duration": probe_duration(path) if path.exists() else 0}

__all__ = ["concat_clips", "mix_narration_and_music", "apply_color_grade", "burn_subtitles", "master_encode", "generate_ambient_music", "probe_duration", "probe_has_audio", "validate_master"]
