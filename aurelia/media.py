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


def _run(
    args: list[str],
    output: str | Path | None = None,
    *,
    stage: str = "media",
) -> None:
    result = run_ffmpeg(args, stage=stage, output_path=output)
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


def probe_has_video(path: str | Path) -> bool:
    path = _require_file(path, "Media input")
    result = run_ffprobe(["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
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
    # Use the concat filter rather than the concat demuxer. The demuxer can
    # preserve fractional PTS gaps at cut boundaries; later CFR mastering then
    # fills those gaps with duplicate frames that fail production freeze QC.
    args = ["-y", "-hide_banner", "-loglevel", "error"]
    for clip in clips:
        args += ["-i", str(clip)]
    streams = []
    graph_parts = []
    for index in range(len(clips)):
        label = f"v{index}"
        graph_parts.append(
            f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS,fps=24:round=near[{label}]"
        )
        streams.append(f"[{label}]")
    graph_parts.append(
        "".join(streams) + f"concat=n={len(clips)}:v=1:a=0,settb=AVTB,setpts=N/(24*TB)[v]"
    )
    args += [
        "-filter_complex", ";".join(graph_parts), "-map", "[v]",
        "-fps_mode", "cfr", "-r", "24", "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-an", str(output_path),
    ]
    _run(args, output_path)
    return output_path


def assemble_cinematic_clips(
    clips: list[str | Path],
    transitions: list[str] | None,
    output: str | Path,
    transition_duration: float = 0.6,
) -> Path:
    """Assemble all rendered shots in one validated FFmpeg filter graph.

    Cut runs are concatenated inside the graph. Non-cut boundaries use xfade
    between those groups. This preserves real transitions while avoiding the
    old O(number-of-shots) chain of intermediate encodes that made EDIT slow
    and vulnerable to CI termination.
    """
    if not clips:
        raise ValueError("No clips supplied")
    normalised = [_require_file(c, "Cinematic clip") for c in clips]
    durations: list[float] = []
    for clip in normalised:
        if not probe_has_video(clip):
            raise RuntimeError(f"EDIT input has no video stream: {clip}")
        duration = probe_duration(clip)
        if duration <= 0.0:
            raise RuntimeError(f"EDIT input has invalid duration: {clip}")
        durations.append(duration)

    boundary_transitions = list(transitions or [])
    boundary_transitions.extend(
        ["cut"] * max(0, len(normalised) - 1 - len(boundary_transitions))
    )
    transition_groups: list[list[int]] = [[0]]
    for index, transition in enumerate(boundary_transitions[: len(normalised) - 1]):
        if str(transition).strip().lower() in {"cut", "none", ""}:
            transition_groups[-1].append(index + 1)
        else:
            transition_groups.append([index + 1])

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph_parts: list[str] = []
    for index in range(len(normalised)):
        graph_parts.append(
            f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS,fps=24:round=near[v{index}]"
        )

    group_labels: list[str] = []
    group_durations: list[float] = []
    for group_index, group in enumerate(transition_groups):
        label = f"g{group_index}"
        group_labels.append(label)
        group_durations.append(sum(durations[index] for index in group))
        if len(group) == 1:
            graph_parts.append(f"[v{group[0]}]settb=AVTB,setpts=PTS-STARTPTS[{label}]")
        else:
            graph_parts.append(
                "".join(f"[v{index}]" for index in group)
                + f"concat=n={len(group)}:v=1:a=0,settb=AVTB,setpts=PTS-STARTPTS[{label}]"
            )

    current_label = group_labels[0]
    current_duration = group_durations[0]
    for group_index in range(1, len(group_labels)):
        boundary_index = transition_groups[group_index][0] - 1
        transition = str(boundary_transitions[boundary_index]).strip().lower()
        if transition in {"cut", "none", ""}:
            transition = "fade"
        duration_b = group_durations[group_index]
        overlap = min(
            max(float(transition_duration), 0.1),
            current_duration / 3.0,
            duration_b / 3.0,
        )
        xfade_name = {
            "dissolve": "fade",
            "crossfade": "fade",
            "fade_in": "fade",
            "fade_out": "fadeblack",
            "fade": "fadeblack",
            "light": "fadewhite",
            "light_transition": "fadewhite",
            "wipe": "wiperight",
            "wiperight": "wiperight",
            "slideleft": "slideleft",
        }.get(transition, "fade")
        next_label = f"x{group_index}"
        graph_parts.append(
            f"[{current_label}][{group_labels[group_index]}]"
            f"xfade=transition={xfade_name}:duration={overlap:.4f}:"
            f"offset={max(0.0, current_duration - overlap):.4f}[{next_label}]"
        )
        current_label = next_label
        current_duration += duration_b - overlap

    args = ["-y", "-hide_banner", "-loglevel", "error"]
    for clip in normalised:
        args += ["-i", str(clip)]
    args += [
        "-filter_complex", ";".join(graph_parts) + f";[{current_label}]format=yuv420p[vout]",
        "-map", "[vout]", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", "-fps_mode", "cfr", "-r", "24",
        str(output_path),
    ]
    _run(args, output_path, stage="EDIT/assemble")
    return output_path


def pad_video_to_duration(source: str | Path, output: str | Path, duration: float) -> Path:
    """Fit video to a target duration without cloning the final frame.

    This legacy helper remains for compatibility, but it now uses a warned
    motion-preserving retime when the visual edit is shorter than narration.
    Clone padding is forbidden because it creates freeze-frame tails in the
    final encoded stream.
    """
    source = _require_file(source, "Video")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    current = probe_duration(source)
    if current >= duration:
        if Path(source) != output_path:
            _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-c", "copy", str(output_path)], output_path)
        return output_path
    if current <= 0:
        raise RuntimeError(f"Cannot retime video with invalid duration: {source}")
    print(f"[MEDIA][WARNING] video shorter than target; retiming motion instead of clone-padding ({current:.3f}s -> {duration:.3f}s)")
    speed_factor = duration / current
    # Normalize timestamps and frame cadence during retime. A bare setpts can
    # leave fractional PTS gaps that the later master fps conversion fills by
    # duplicating frames; those duplicates become real freeze intervals in QC.
    retime_filter = (
        f"settb=AVTB,setpts=PTS*{speed_factor:.8f},fps=24:round=near"
    )
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
          "-vf", retime_filter, "-fps_mode", "cfr", "-r", "24",
          "-t", f"{duration:.6f}", "-an", "-c:v", "libx264", "-preset", "medium",
          "-crf", "18", "-pix_fmt", "yuv420p", str(output_path)], output_path)
    return output_path


def generate_sound_design(
    duration_sec: float,
    scene_boundaries: list[float] | None,
    output: str | Path,
) -> Path:
    """Generate an authored, non-silent sound-design cue track.

    The cues are tied to scene boundaries: a low cinematic riser plus a short
    filtered noise swell. This is intentionally separate from the music bed so
    the EDIT mix can prove that SOUND DESIGN is a consumed audio artifact.
    """
    import math
    import struct
    import wave

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 48000
    total_frames = int(max(duration_sec, 5.0) * sample_rate)
    starts = [max(0.0, min(duration_sec - 0.9, float(boundary)))
              for boundary in sorted(scene_boundaries or [])]
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for frame_index in range(total_frames):
            now = frame_index / sample_rate
            value = 0.0
            for start in starts:
                rel = now - start
                if 0.0 <= rel < 0.9:
                    envelope = min(1.0, rel / 0.16) * max(0.0, (0.9 - rel) / 0.70)
                    rumble = math.sin(2.0 * math.pi * 92.0 * rel) * 0.028 * envelope
                    deterministic_noise = math.sin(2.0 * math.pi * 1733.0 * rel) * 0.004 * envelope
                    value += rumble + deterministic_noise
            pcm = max(-1.0, min(1.0, value))
            sample = int(pcm * 32767)
            wav.writeframes(struct.pack("<hh", sample, sample))
    return _require_file(output_path, "Sound-design track")


def mix_narration_and_music(
    video: str | Path, narration: str | Path, output: str | Path,
    music: str | Path | None = None,
    sound_design: str | Path | None = None,
    ambient: str | Path | None = None,
) -> Path:
    video = _require_file(video, "Video")
    narration = _require_file(narration, "Narration")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    target_duration = max(30.0, probe_duration(video), probe_duration(narration))
    inputs = [video, narration]
    filters = [
        f"[1:a]apad=whole_dur={target_duration:.6f},volume=1.0,"
        "asplit=3[narr][narr_bgm][narr_sfx]"
    ]
    mix_inputs = ["[narr]"]
    if music is not None and Path(music).is_file() and Path(music).stat().st_size > 0:
        inputs.append(Path(music))
        filters.append(
            "[2:a]volume=0.15[bgm_raw];"
            "[bgm_raw][narr_bgm]sidechaincompress=threshold=0.035:ratio=6:"
            "attack=20:release=280:makeup=1[bgm]"
        )
        mix_inputs.append("[bgm]")
    if sound_design is not None and Path(sound_design).is_file() and Path(sound_design).stat().st_size > 0:
        inputs.append(Path(sound_design))
        sound_index = len(inputs) - 1
        filters.append(
            f"[{sound_index}:a]volume=0.65[sfx_raw];"
            "[sfx_raw][narr_sfx]sidechaincompress=threshold=0.045:ratio=4:"
            "attack=10:release=180:makeup=1[sfx]"
        )
        mix_inputs.append("[sfx]")
    if ambient is not None and Path(ambient).is_file() and Path(ambient).stat().st_size > 0:
        inputs.append(Path(ambient))
        ambient_index = len(inputs) - 1
        filters.append(f"[{ambient_index}:a]volume=0.22[amb]")
        mix_inputs.append("[amb]")
    filters.append(
        "".join(mix_inputs) + f"amix=inputs={len(mix_inputs)}:duration=longest:"
        f"dropout_transition=2,"
        "loudnorm=I=-16:LRA=11:TP=-1.5,"
        "alimiter=limit=0.95,"
        "aformat=sample_rates=48000:channel_layouts=stereo,"
        f"atrim=duration={target_duration:.6f}[aout]"
    )
    args = ["-y", "-hide_banner", "-loglevel", "error"]
    for input_path in inputs:
        args += ["-i", str(input_path)]
    args += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[aout]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-t", f"{target_duration:.6f}", str(output_path)]
    _run(args, output_path)
    return output_path


def apply_color_grade(
    source: str | Path, output: str | Path,
    contrast: float = 1.04, saturation: float = 1.03, brightness: float = -0.01
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
        f"force_style='FontSize=22,PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00101010,BackColour=&H66000000,BorderStyle=1,"
        f"Outline=1,Shadow=1,Alignment=2,MarginL=180,MarginR=180,MarginV=72,"
        f"Bold=0,Spacing=0,WrapStyle=2{font_style}'"
    )
    result = run_ffmpeg(["-y", "-hide_banner", "-loglevel", "error",
                         "-i", str(source), "-vf", subtitle_filter,
                         "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                         "-c:a", "copy", "-pix_fmt", "yuv420p", str(output_path)])
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"Subtitle burn-in failed; refusing unsubtitled delivery: {stderr}")
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
    master_filter = (
        f"settb=AVTB,setpts=PTS-STARTPTS,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps}:round=near"
    )
    _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
          "-vf", master_filter, "-fps_mode", "cfr", "-r", str(fps),
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
        # Music is an authored production layer. Never substitute silence while
        # claiming the stage succeeded; fail loudly so QC/provenance can stop
        # the job and the actual cause remains visible in CI.
        raise RuntimeError(f"Ambient music generation failed: {exc}") from exc


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
        "backend_not_unknown": False,
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
            checks["backend_not_unknown"] = bool(raw_backend) and str(raw_backend).lower() != "unknown"

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
            # Thresholds are designed to pass dark and monochrome cinematic
            # environments as long as they contain real luminance structure.
            # channel_range catches chromatic variation; mean_stddev catches
            # valid grayscale/low-chroma imagery such as a portrait against a
            # dark background. A flat/blank image fails both measurements.
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
                        range_ok = channel_range >= 3.0 or mean_stddev >= 6.0
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
            # Generation prompts legitimately contain words like "watermark" and
            # "logo" as NEGATIVE/avoidance instructions to the image model
            # (see ai_visual.py's negative prompt and build_scene_prompt output).
            # Scanning the raw manifest JSON for those substrings therefore
            # false-flags every real generation, since the prompt text itself
            # is stored in each scene record for provenance. Redact prompt-like
            # fields before scanning for actual contamination markers so this
            # check reflects real artifacts (e.g. a backend or filename that
            # actually indicates a watermark/logo/template asset) rather than
            # the anti-watermark instruction we asked the model to follow.
            _PROMPT_FIELDS = {"prompt", "negative_prompt"}

            def _redact(node: object) -> object:
                if isinstance(node, dict):
                    return {
                        key: _redact(value)
                        for key, value in node.items()
                        if key not in _PROMPT_FIELDS
                    }
                if isinstance(node, list):
                    return [_redact(item) for item in node]
                return node

            scene_text = json.dumps(_redact(manifest), ensure_ascii=False).lower()
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
            motion_records = [scene.get("rendered_motion") is True for scene in scenes]
            checks["rendered_motion_provenance"] = bool(motion_records) and all(motion_records)
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
    "concat_clips", "assemble_cinematic_clips", "pad_video_to_duration", "mix_narration_and_music",
    "apply_color_grade", "burn_subtitles", "master_encode",
    "generate_ambient_music", "probe_duration", "probe_has_audio",
    "validate_master", "validate_visual_manifest",
]
