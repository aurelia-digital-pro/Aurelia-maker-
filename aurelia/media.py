"""AURELIA Maker — FFmpeg media assembly and finishing utilities."""

from __future__ import annotations

import hashlib
import json
import statistics
import tempfile
from pathlib import Path

from .ffmpeg_util import ffmpeg_binary, run_ffmpeg, run_ffprobe


def _require_file(path: str | Path, label: str) -> Path:
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0:
        raise FileNotFoundError(f"{label} is missing or empty: {p}")
    return p


def _run(args: list[str], output: str | Path | None = None) -> None:
    result = run_ffmpeg(args)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg command failed:\n{' '.join(args)}\n{result.stderr.strip()}")
    if output is not None:
        _require_file(output, "FFmpeg output")


def probe_duration(path: str | Path) -> float:
    path = _require_file(path, "Media input")
    result = run_ffprobe(["-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    if result.returncode != 0:
        return 0.0
    try:
        return float(json.loads(result.stdout).get("format", {}).get("duration", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return 0.0


def probe_has_audio(path: str | Path) -> bool:
    path = _require_file(path, "Media input")
    result = run_ffprobe(["-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    return result.returncode == 0 and bool(result.stdout.strip())


def concat_clips(clips: list[str | Path], output: str | Path) -> Path:
    if not clips:
        raise ValueError("No clips supplied")
    clips = [_require_file(c, "Concat clip") for c in clips]
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(clips[0]), "-c", "copy", str(output_path)], output_path)
        return output_path
    list_file = output_path.parent / f"{output_path.stem}.concat.txt"
    list_file.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in clips), encoding="utf-8")
    _run(["-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(output_path)], output_path)
    return output_path


def pad_video_to_duration(source: str | Path, output: str | Path, duration: float) -> Path:
    """Extend a short visual edit by holding its final frame."""
    source = _require_file(source, "Video")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    current = probe_duration(source)
    if current >= duration:
        if Path(source) != output_path:
            _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-c", "copy", str(output_path)], output_path)
        return output_path
    pad_seconds = max(0.0, duration - current)
    _run(
        [
            "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
            "-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.6f}",
            "-t", f"{duration:.6f}", "-an", "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-pix_fmt", "yuv420p", str(output_path),
        ],
        output_path,
    )
    return output_path


def mix_narration_and_music(video: str | Path, narration: str | Path, output: str | Path, music: str | Path | None = None) -> Path:
    video = _require_file(video, "Video")
    narration = _require_file(narration, "Narration")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_duration = max(30.0, probe_duration(video), probe_duration(narration))
    if music is not None and Path(music).is_file() and Path(music).stat().st_size > 0:
        music = Path(music)
        _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(narration), "-i", str(music), "-filter_complex", f"[1:a]apad=whole_dur={target_duration:.6f},volume=1.0[narr];[2:a]volume=0.18[bgm];[narr][bgm]amix=inputs=2:duration=longest:dropout_transition=2,atrim=duration={target_duration:.6f}[aout]", "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{target_duration:.6f}", str(output_path)], output_path)
    else:
        _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(video), "-i", str(narration), "-filter_complex", f"[1:a]apad=whole_dur={target_duration:.6f}[aout]", "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{target_duration:.6f}", str(output_path)], output_path)
    return output_path


def apply_color_grade(source: str | Path, output: str | Path, contrast: float = 1.08, saturation: float = 1.12, brightness: float = -0.02) -> Path:
    source = _require_file(source, "Color-grade source")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", f"eq=contrast={contrast}:saturation={saturation}:brightness={brightness}", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)], output_path)
    return output_path


def burn_subtitles(source: str | Path, srt: str | Path, output: str | Path) -> Path:
    source = _require_file(source, "Subtitle source")
    srt_path = _require_file(srt, "Subtitle file").resolve()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_srt = srt_path.as_posix().replace(":", r"\:").replace("'", r"\'")
    subtitle_filter = f"subtitles=filename='{escaped_srt}':force_style='FontSize=28,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,MarginV=40'"
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", subtitle_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)], output_path)
    return output_path


def master_encode(source: str | Path, output: str | Path, width: int = 1920, height: int = 1080, fps: int = 24, profile: str = "youtube") -> Path:
    source = _require_file(source, "Master source")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if profile == "tiktok":
        width, height = 1080, 1920
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}", "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)], output_path)
    return output_path


def generate_ambient_music(duration_sec: float, output: str | Path) -> Path:
    from pydub import AudioSegment
    from pydub.generators import Sine
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    AudioSegment.converter = ffmpeg_binary()
    duration_ms = int(max(duration_sec, 5) * 1000)
    mixed = Sine(55).to_audio_segment(duration=duration_ms).apply_gain(-22).overlay(Sine(110).to_audio_segment(duration=duration_ms).apply_gain(-26)).overlay(Sine(165).to_audio_segment(duration=duration_ms).apply_gain(-30)).fade_in(2000).fade_out(3000)
    mixed.export(str(output_path), format="wav")
    _require_file(output_path, "Generated music")
    return output_path


def validate_master(path: str | Path, min_duration: float = 5.0) -> dict:
    path = Path(path)
    checks = {"exists": path.is_file(), "non_empty": path.is_file() and path.stat().st_size > 1000, "duration_ok": False, "has_video": False, "has_audio": False, "format_valid": False}
    if path.is_file() and checks["non_empty"]:
        probe = run_ffprobe(["-v", "error", "-show_entries", "format=format_name,duration:stream=codec_type,codec_name,width,height", "-of", "json", str(path)])
        if probe.returncode == 0:
            try:
                payload = json.loads(probe.stdout)
                streams = payload.get("streams", [])
                fmt = payload.get("format", {})
                video = next((s for s in streams if s.get("codec_type") == "video"), None)
                audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
                checks["format_valid"] = "mp4" in str(fmt.get("format_name", "")).split(",")
                checks["duration_ok"] = float(fmt.get("duration") or 0) >= min_duration
                checks["has_video"] = bool(video and video.get("codec_name") == "h264" and int(video.get("width", 0)) > 0 and int(video.get("height", 0)) > 0)
                checks["has_audio"] = audio is not None
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
    duration = probe_duration(path) if checks["exists"] else 0.0
    return {"passed": all(checks.values()), "checks": checks, "duration": duration}


def validate_visual_manifest(path: str | Path, expected_scene_count: int | None = None, source_text_sha256: str | None = None) -> dict:
    """Validate provenance and reject known template/procedural visual sources."""
    manifest_path = Path(path)
    checks = {
        "manifest_exists": manifest_path.is_file(),
        "backend_is_local_ai": False,
        "source_is_chat": False,
        "source_binding_valid": source_text_sha256 is None,
        "scenes_present": False,
        "scene_assets_valid": False,
        "scene_assets_match_manifest": False,
        "template_contamination": False,
        "ui_contamination": False,
        "watermark_contamination": False,
        "assets_have_visual_signal": False,
        "enhancement_recorded": False,
    }
    scenes: list[dict] = []
    if checks["manifest_exists"]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checks["backend_is_local_ai"] = manifest.get("backend") == "local-ai"
            checks["source_is_chat"] = manifest.get("source") == "chat"
            checks["source_binding_valid"] = source_text_sha256 is None or manifest.get("source_text_sha256") == source_text_sha256
            scenes = manifest.get("scenes", [])
            checks["scenes_present"] = bool(scenes)
            checks["scene_assets_valid"] = all(
                isinstance(scene.get("asset"), str)
                and Path(scene["asset"]).is_file()
                and Path(scene["asset"]).stat().st_size > 1000
                and bool(scene.get("text_sha256"))
                for scene in scenes
            )
            try:
                from PIL import Image, ImageStat
                signals = []
                for scene in scenes:
                    with Image.open(scene["asset"]) as image:
                        stat = ImageStat.Stat(image.convert("RGB"))
                        signals.append((image.width >= 256 and image.height >= 256, max(stat.mean) - min(stat.mean) >= 8, statistics.fmean(stat.stddev) >= 4))
                checks["assets_have_visual_signal"] = bool(signals) and all(all(signal) for signal in signals)
            except (KeyError, OSError, ValueError):
                checks["assets_have_visual_signal"] = False
            existing = [scene for scene in scenes if Path(scene.get("asset", "")).is_file()]
            checks["scene_assets_match_manifest"] = len(existing) == len(scenes) and all(
                hashlib.sha256(Path(scene["asset"]).read_bytes()).hexdigest() == scene.get("asset_sha256")
                for scene in scenes
            )
            asset_names = " ".join(str(scene.get("asset", "")).lower() for scene in scenes)
            scene_text = json.dumps(manifest, ensure_ascii=False).lower()
            forbidden = ("asset_generator", "title_card", "star-field", "star_field", "scene ", "aurelia maker", "watermark", "logo", "ui")
            checks["template_contamination"] = not any(token in asset_names or token in scene_text for token in forbidden)
            checks["ui_contamination"] = not any(token in scene_text for token in ("ui", "prompt", "source text", "overlay"))
            checks["watermark_contamination"] = not any(token in scene_text for token in ("watermark", "logo"))
            checks["enhancement_recorded"] = manifest.get("visual_processing", {}).get("motion_renderer") == "CinematicVisualEngine"
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    if expected_scene_count is not None:
        checks["scene_count_matches_plan"] = len(scenes) == expected_scene_count
    return {"passed": all(checks.values()), "checks": checks, "scene_count": len(scenes)}


def inspect_final_video_visuals(video: str | Path) -> dict:
    """Inspect representative frames so a valid container cannot hide a blank template."""
    video_path = _require_file(video, "Final video")
    duration = probe_duration(video_path)
    checks = {"frames_inspected": True, "frames_have_signal": True, "frames_are_not_near_black": True}
    frame_count = 0
    with tempfile.TemporaryDirectory(prefix="aurelia-qc-") as temp_dir:
        for index, fraction in enumerate((0.15, 0.5, 0.85)):
            frame = Path(temp_dir) / f"frame-{index}.png"
            result = run_ffmpeg(["-y", "-hide_banner", "-loglevel", "error", "-ss", f"{duration * fraction:.3f}", "-i", str(video_path), "-frames:v", "1", str(frame)])
            if result.returncode != 0 or not frame.is_file():
                checks["frames_inspected"] = False
                continue
            try:
                from PIL import Image, ImageStat
                with Image.open(frame) as image:
                    stat = ImageStat.Stat(image.convert("RGB"))
                    checks["frames_have_signal"] = checks["frames_have_signal"] and statistics.fmean(stat.stddev) >= 3
                    checks["frames_are_not_near_black"] = checks["frames_are_not_near_black"] and statistics.fmean(stat.mean) >= 8
                frame_count += 1
            except (OSError, ValueError):
                checks["frames_inspected"] = False
    checks["frames_inspected"] = checks["frames_inspected"] and frame_count == 3
    return {"passed": all(checks.values()), "checks": checks, "frame_count": frame_count}


__all__ = ["concat_clips", "pad_video_to_duration", "mix_narration_and_music", "apply_color_grade", "burn_subtitles", "master_encode", "generate_ambient_music", "probe_duration", "probe_has_audio", "validate_master", "validate_visual_manifest"]
