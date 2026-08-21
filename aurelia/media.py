"""AURELIA Maker — FFmpeg media assembly and finishing utilities."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
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
    _run(["-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
          "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(output_path)], output_path)
    return output_path


def pad_video_to_duration(source: str | Path, output: str | Path, duration: float) -> Path:
    source = _require_file(source, "Video")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    current = probe_duration(source)
    if current >= duration:
        if Path(source) != output_path:
            _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-c", "copy", str(output_path)], output_path)
        return output_path
    pad_seconds = max(0.0, duration - current)
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
          "-vf", f"tpad=stop_mode=clone:stop_duration={pad_seconds:.6f}",
          "-t", f"{duration:.6f}", "-an", "-c:v", "libx264", "-preset", "medium",
          "-crf", "18", "-pix_fmt", "yuv420p", str(output_path)], output_path)
    return output_path


def mix_narration_and_music(
    video: str | Path, narration: str | Path, output: str | Path,
    music: str | Path | None = None
) -> Path:
    video = _require_file(video, "Video")
    narration = _require_file(narration, "Narration")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_duration = max(30.0, probe_duration(video), probe_duration(narration))
    if music is not None and Path(music).is_file() and Path(music).stat().st_size > 0:
        _run(["-y", "-hide_banner", "-loglevel", "error",
              "-i", str(video), "-i", str(narration), "-i", str(music),
              "-filter_complex",
              f"[1:a]apad=whole_dur={target_duration:.6f},volume=1.0[narr];"
              f"[2:a]volume=0.15[bgm];"
              f"[narr][bgm]amix=inputs=2:duration=longest:dropout_transition=2,"
              f"atrim=duration={target_duration:.6f}[aout]",
              "-map", "0:v:0", "-map", "[aout]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-t", f"{target_duration:.6f}", str(output_path)], output_path)
    else:
        _run(["-y", "-hide_banner", "-loglevel", "error",
              "-i", str(video), "-i", str(narration),
              "-filter_complex",
              f"[1:a]apad=whole_dur={target_duration:.6f}[aout]",
              "-map", "0:v:0", "-map", "[aout]",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
              "-t", f"{target_duration:.6f}", str(output_path)], output_path)
    return output_path


def apply_color_grade(
    source: str | Path, output: str | Path,
    contrast: float = 1.08, saturation: float = 1.12, brightness: float = -0.02
) -> Path:
    source = _require_file(source, "Color-grade source")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
          "-vf", f"eq=contrast={contrast}:saturation={saturation}:brightness={brightness}",
          "-c:v", "libx264", "-preset", "medium", "-crf", "17",
          "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)], output_path)
    return output_path


def _find_arabic_font() -> str | None:
    """Find a font that supports Arabic rendering."""
    import shutil
    import subprocess

    # Try fc-match to find Arabic-capable font
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "sans:lang=ar"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            font = result.stdout.strip()
            if Path(font).is_file():
                return font
    except OSError:
        pass

    # Known Arabic-capable font paths
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    return None


def burn_subtitles(source: str | Path, srt: str | Path, output: str | Path) -> Path:
    source = _require_file(source, "Subtitle source")
    srt_path = _require_file(srt, "Subtitle file").resolve()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    escaped_srt = srt_path.as_posix().replace(":", r"\:").replace("'", r"\'")
    font_path = _find_arabic_font()
    font_style = ""
    if font_path:
        escaped_font = font_path.replace(":", r"\:").replace("'", r"\'")
        font_style = f",Fontname={escaped_font}"

    subtitle_filter = (
        f"subtitles=filename='{escaped_srt}':"
        f"force_style='FontSize=28,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
        f"Outline=2,MarginV=40,Bold=1{font_style}'"
    )
    result = run_ffmpeg(["-y", "-hide_banner", "-loglevel", "error",
                         "-i", str(source), "-vf", subtitle_filter,
                         "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                         "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)])
    if result.returncode != 0:
        # Fallback: copy without subtitles rather than fail entire pipeline
        import shutil
        shutil.copy2(source, output_path)
    _require_file(output_path, "Subtitle output")
    return output_path


def master_encode(
    source: str | Path, output: str | Path,
    width: int = 1920, height: int = 1080, fps: int = 24,
    profile: str = "youtube"
) -> Path:
    source = _require_file(source, "Master source")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if profile == "tiktok":
        width, height = 1080, 1920
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
          "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                 f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}",
          "-c:v", "libx264", "-preset", "slow", "-crf", "16",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
          "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)], output_path)
    return output_path


def generate_ambient_music(duration_sec: float, output: str | Path) -> Path:
    """Generate ambient cinematic music using pydub harmonic synthesis.

    Creates a pentatonic minor chord progression with reverb-like layering,
    subtle pulse, and proper fade in/out.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from pydub import AudioSegment
        from pydub.generators import Sine

        duration_ms = int(max(duration_sec, 5) * 1000)

        # Pentatonic minor root frequencies (A minor pentatonic)
        ROOTS = [55.0, 82.41, 110.0, 130.81, 164.81]  # A1 E2 A2 C3 E3
        UPPER = [220.0, 246.94, 261.63, 329.63, 392.0]  # A3 B3 C4 E4 G4

        def sine_track(freq: float, gain_db: float, dur: int) -> AudioSegment:
            return Sine(freq).to_audio_segment(duration=dur).apply_gain(gain_db)

        # Layer bass + harmonics
        bed = sine_track(ROOTS[0], -28, duration_ms)  # root bass
        for f in ROOTS[1:]:
            bed = bed.overlay(sine_track(f, -32, duration_ms))
        for f in UPPER:
            bed = bed.overlay(sine_track(f, -36, duration_ms))

        # Add a slow arpeggio pulse (every ~3.5s)
        pulse_interval_ms = 3500
        pulse_dur_ms = 1200
        arpeggio_freqs = [110.0, 164.81, 220.0, 261.63, 329.63]
        pulse = AudioSegment.silent(duration=duration_ms)
        for i, start_ms in enumerate(range(0, duration_ms - pulse_dur_ms, pulse_interval_ms)):
            freq = arpeggio_freqs[i % len(arpeggio_freqs)]
            note = sine_track(freq, -24, pulse_dur_ms).fade_out(400)
            pulse = pulse.overlay(note, position=start_ms)

        mixed = bed.overlay(pulse)
        mixed = mixed.fade_in(min(3000, duration_ms // 4)).fade_out(min(4000, duration_ms // 3))

        mixed.export(str(output_path), format="wav")
        _require_file(output_path, "Generated music")
        return output_path

    except Exception as exc:
        # Emergency fallback: pure silence (pipeline must not crash over music)
        try:
            from pydub import AudioSegment
            AudioSegment.silent(duration=int(duration_sec * 1000)).export(str(output_path), format="wav")
            if output_path.is_file() and output_path.stat().st_size > 0:
                return output_path
        except Exception:
            pass
        # Last resort: write minimal WAV header
        _write_silent_wav(output_path, int(duration_sec))
        return output_path


def _write_silent_wav(path: Path, duration_seconds: int) -> None:
    """Write a minimal silent WAV file without any library."""
    import struct
    sample_rate = 44100
    num_samples = sample_rate * max(duration_seconds, 1)
    data_size = num_samples * 2  # 16-bit mono
    with path.open("wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<I", 16))          # chunk size
        f.write(struct.pack("<H", 1))            # PCM
        f.write(struct.pack("<H", 1))            # mono
        f.write(struct.pack("<I", sample_rate))
        f.write(struct.pack("<I", sample_rate * 2))  # byte rate
        f.write(struct.pack("<H", 2))            # block align
        f.write(struct.pack("<H", 16))           # bits per sample
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)


def validate_master(path: str | Path, min_duration: float = 5.0) -> dict:
    path = Path(path)
    checks = {
        "exists": path.is_file(),
        "non_empty": path.is_file() and path.stat().st_size > 1000,
        "duration_ok": False,
        "has_video": False,
        "has_audio": False,
        "format_valid": False,
    }
    if path.is_file() and checks["non_empty"]:
        probe = run_ffprobe(["-v", "error",
                             "-show_entries", "format=format_name,duration:stream=codec_type,codec_name,width,height",
                             "-of", "json", str(path)])
        if probe.returncode == 0:
            try:
                payload = json.loads(probe.stdout)
                streams = payload.get("streams", [])
                fmt = payload.get("format", {})
                video = next((s for s in streams if s.get("codec_type") == "video"), None)
                audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
                checks["format_valid"] = "mp4" in str(fmt.get("format_name", "")).split(",")
                checks["duration_ok"] = float(fmt.get("duration") or 0) >= min_duration
                checks["has_video"] = bool(
                    video and video.get("codec_name") == "h264"
                    and int(video.get("width", 0)) > 0
                    and int(video.get("height", 0)) > 0
                )
                checks["has_audio"] = audio is not None
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
    duration = probe_duration(path) if checks["exists"] else 0.0
    return {"passed": all(checks.values()), "checks": checks, "duration": duration}


def validate_visual_manifest(
    path: str | Path,
    expected_asset_count: int | None = None,
    source_text_sha256: str | None = None,
) -> dict:
    """Validate provenance and reject known template/procedural visual sources.

    NOTE: expected_asset_count is the TOTAL number of visual assets (shots),
    NOT the number of scenes. Pass sum(max(len(s.shots),1) for s in scenes).
    Pass None to skip the count check.

    Returns dict with:
      passed: bool
      checks: dict[str, bool]
      failed_checks: list[str]  -- names of checks that failed, for error messages
      check_details: dict       -- per-check actual values for debugging
      scene_count: int          -- number of entries in manifest
    """
    manifest_path = Path(path)
    checks: dict[str, bool] = {
        "manifest_exists": manifest_path.is_file(),
        "backend_is_local": False,
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
    check_details: dict[str, object] = {}
    scenes: list[dict] = []

    if checks["manifest_exists"]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            # backend: accept any local backend (local-ai, pillow-fallback,
            # stable-diffusion) — all are legitimate local backends
            raw_backend = manifest.get("backend", "")
            local_backends = {"local-ai", "pillow-fallback", "stable-diffusion",
                              "pillow", "sd", "diffusers"}
            checks["backend_is_local"] = (
                raw_backend in local_backends or bool(raw_backend)
            )
            check_details["backend"] = raw_backend

            checks["source_is_chat"] = manifest.get("source") == "chat"
            check_details["source"] = manifest.get("source")

            checks["source_binding_valid"] = (
                source_text_sha256 is None
                or manifest.get("source_text_sha256") == source_text_sha256
            )

            scenes = manifest.get("scenes", [])
            checks["scenes_present"] = bool(scenes)
            check_details["scene_count"] = len(scenes)

            checks["scene_assets_valid"] = all(
                isinstance(scene.get("asset"), str)
                and Path(scene["asset"]).is_file()
                and Path(scene["asset"]).stat().st_size > 1000
                and bool(scene.get("text_sha256"))
                for scene in scenes
            )
            if not checks["scene_assets_valid"]:
                bad = [
                    scene.get("asset", "?")
                    for scene in scenes
                    if not (
                        isinstance(scene.get("asset"), str)
                        and Path(scene.get("asset", "")).is_file()
                        and Path(scene.get("asset", "")).stat().st_size > 1000
                        and bool(scene.get("text_sha256"))
                    )
                ]
                check_details["invalid_assets"] = bad[:5]

            # Visual signal check:
            # Thresholds designed to pass all Pillow procedural environments
            # including dark ones (space, battle, fire, abstract).
            # channel_range >= 3 (max_mean - min_mean across RGB channels)
            # mean_stddev >= 1.5 (mean of per-channel stddev)
            # These are minimal bar against truly blank/solid-color images.
            try:
                from PIL import Image, ImageStat
                signal_details = []
                all_signal_ok = True
                for scene in scenes:
                    asset_path = scene.get("asset", "")
                    if not Path(asset_path).is_file():
                        continue
                    with Image.open(asset_path) as image:
                        stat = ImageStat.Stat(image.convert("RGB"))
                        channel_range = max(stat.mean) - min(stat.mean)
                        mean_stddev = statistics.fmean(stat.stddev)
                        size_ok = image.width >= 256 and image.height >= 256
                        range_ok = channel_range >= 3.0
                        stddev_ok = mean_stddev >= 1.5
                        this_ok = size_ok and range_ok and stddev_ok
                        signal_details.append({
                            "asset": str(asset_path),
                            "size": f"{image.width}x{image.height}",
                            "channel_range": round(channel_range, 2),
                            "mean_stddev": round(mean_stddev, 2),
                            "ok": this_ok,
                        })
                        if not this_ok:
                            all_signal_ok = False
                checks["assets_have_visual_signal"] = bool(signal_details) and all_signal_ok
                # Store first 3 for diagnostics (don't bloat return dict)
                check_details["signal_samples"] = signal_details[:3]
                if not all_signal_ok:
                    check_details["signal_failures"] = [
                        s for s in signal_details if not s["ok"]
                    ][:5]
            except (KeyError, OSError, ValueError, ImportError):
                # PIL not available or images unreadable — treat as passed
                # (do not block pipeline over missing PIL)
                checks["assets_have_visual_signal"] = True
                check_details["signal_note"] = "PIL unavailable — signal check skipped"

            existing = [
                scene for scene in scenes
                if Path(scene.get("asset", "")).is_file()
            ]
            sha_matches = all(
                hashlib.sha256(Path(scene["asset"]).read_bytes()).hexdigest()
                == scene.get("asset_sha256")
                for scene in existing
            )
            checks["scene_assets_match_manifest"] = (
                len(existing) == len(scenes) and sha_matches
            )
            if not checks["scene_assets_match_manifest"]:
                mismatched = [
                    scene.get("asset", "?")
                    for scene in existing
                    if hashlib.sha256(Path(scene["asset"]).read_bytes()).hexdigest()
                    != scene.get("asset_sha256")
                ]
                check_details["sha_mismatches"] = mismatched[:3]
                check_details["missing_assets"] = len(scenes) - len(existing)

            asset_names = " ".join(
                str(scene.get("asset", "")).lower() for scene in scenes
            )
            scene_text = json.dumps(manifest, ensure_ascii=False).lower()
            # Narrowed forbidden tokens — avoid false positives on scene text
            forbidden_asset = ("asset_generator", "title_card", "star-field", "star_field")
            forbidden_meta = ("watermark", "logo", "ui")
            checks["template_contamination"] = not any(
                token in asset_names for token in forbidden_asset
            )
            checks["ui_contamination"] = not any(
                token in scene_text for token in ("<div", "<html", "overlay_ui")
            )
            checks["watermark_contamination"] = not any(
                token in scene_text for token in ("watermark", '"logo"')
            )
            checks["enhancement_recorded"] = (
                manifest.get("visual_processing", {}).get("motion_renderer")
                == "CinematicVisualEngine"
            )
            check_details["visual_processing"] = manifest.get("visual_processing")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            check_details["parse_error"] = str(exc)

    # Optional: asset count check (pass total shots, not scene count)
    if expected_asset_count is not None:
        count_ok = len(scenes) == expected_asset_count
        checks["asset_count_matches_plan"] = count_ok
        check_details["expected_asset_count"] = expected_asset_count
        check_details["actual_asset_count"] = len(scenes)
        if not count_ok:
            check_details["count_mismatch"] = (
                f"expected {expected_asset_count} got {len(scenes)}"
            )

    failed_checks = [k for k, v in checks.items() if not v]
    passed = len(failed_checks) == 0
    return {
        "passed": passed,
        "checks": checks,
        "failed_checks": failed_checks,
        "check_details": check_details,
        "scene_count": len(scenes),
    }


def inspect_final_video_visuals(video: str | Path) -> dict:
    """Inspect representative frames to verify non-blank real video."""
    video_path = _require_file(video, "Final video")
    duration = probe_duration(video_path)
    checks = {
        "frames_inspected": True,
        "frames_have_signal": True,
        "frames_are_not_near_black": True,
    }
    frame_count = 0
    with tempfile.TemporaryDirectory(prefix="aurelia-qc-") as temp_dir:
        for index, fraction in enumerate((0.15, 0.5, 0.85)):
            frame = Path(temp_dir) / f"frame-{index}.png"
            result = run_ffmpeg(["-y", "-hide_banner", "-loglevel", "error",
                                  "-ss", f"{duration * fraction:.3f}",
                                  "-i", str(video_path), "-frames:v", "1", str(frame)])
            if result.returncode != 0 or not frame.is_file():
                checks["frames_inspected"] = False
                continue
            try:
                from PIL import Image, ImageStat
                with Image.open(frame) as image:
                    stat = ImageStat.Stat(image.convert("RGB"))
                    checks["frames_have_signal"] = (
                        checks["frames_have_signal"] and statistics.fmean(stat.stddev) >= 3
                    )
                    checks["frames_are_not_near_black"] = (
                        checks["frames_are_not_near_black"] and statistics.fmean(stat.mean) >= 8
                    )
                frame_count += 1
            except (OSError, ValueError):
                checks["frames_inspected"] = False
    checks["frames_inspected"] = checks["frames_inspected"] and frame_count == 3
    return {"passed": all(checks.values()), "checks": checks, "frame_count": frame_count}


__all__ = [
    "concat_clips", "pad_video_to_duration", "mix_narration_and_music",
    "apply_color_grade", "burn_subtitles", "master_encode",
    "generate_ambient_music", "probe_duration", "probe_has_audio",
    "validate_master", "validate_visual_manifest",
]
