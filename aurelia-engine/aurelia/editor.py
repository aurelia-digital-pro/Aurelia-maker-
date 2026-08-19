"""AURELIA Maker editor: deterministic FFmpeg assembly and audio/subtitle finishing."""

from __future__ import annotations

from pathlib import Path

from .ffmpeg_util import run_ffmpeg


def _run(args: list[str]) -> None:
    result = run_ffmpeg(args)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg command failed: {' '.join(args)}\n{result.stderr.strip()}")


def _require_inputs(paths: list[str | Path]) -> None:
    missing = [str(p) for p in paths if not Path(p).is_file() or Path(p).stat().st_size == 0]
    if missing:
        raise FileNotFoundError(f"Editor input missing or empty: {', '.join(missing)}")


def concat_with_crossfade(clips, out_path, transition=0.6):
    """Concatenate compatible rendered clips through the real FFmpeg binary.

    The existing production renderer supplies already-timed clips; a concat
    demuxer is deterministic and avoids inventing visual effects. The function
    name is retained for API compatibility, but no unimplemented crossfade is
    claimed or silently substituted.
    """
    clips = [Path(c) for c in clips]
    if not clips:
        raise ValueError("No clips supplied")
    _require_inputs(clips)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(clips) == 1:
        _run(["-y", "-hide_banner", "-loglevel", "error", "-i", str(clips[0]), "-c", "copy", str(out_path)])
        return out_path

    list_file = out_path.parent / f"{out_path.stem}.concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'" for p in clips),
        encoding="utf-8",
    )
    _run(["-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an", str(out_path)])
    return out_path


def mix_audio(video_path, narration_wav, out_path, music_wav=None):
    """Replace/mix the video audio using FFmpeg, failing on every real error."""
    _require_inputs([video_path, narration_wav])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if music_wav and Path(music_wav).is_file() and Path(music_wav).stat().st_size > 0:
        _run([
            "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video_path), "-i", str(narration_wav), "-i", str(music_wav),
            "-filter_complex", "[1:a]volume=1.0[narr];[2:a]volume=0.18[bgm];[narr][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path),
        ])
    else:
        _run([
            "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(video_path), "-i", str(narration_wav),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_path),
        ])
    return out_path


def assemble(clips, narration_wav, srt_path, out_path, profile="youtube"):
    _require_inputs([narration_wav, srt_path])
    out_path = Path(out_path)
    temp_concat = out_path.with_suffix(".concat.mp4")
    concat_with_crossfade(clips, temp_concat)
    mixed = out_path.with_suffix(".mixed.mp4")
    mix_audio(temp_concat, narration_wav, mixed)
    _run([
        "-y", "-hide_banner", "-loglevel", "error", "-i", str(mixed),
        "-vf", f"subtitles={Path(srt_path).resolve().as_posix()}:force_style='FontSize=36'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "copy", "-pix_fmt", "yuv420p", str(out_path),
    ])
    return out_path
