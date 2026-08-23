from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from aurelia.media import pad_video_to_duration
from aurelia.transitions import TransitionSpec, TransitionType, apply_transition_ffmpeg
from aurelia.visuals import CinematicVisualEngine


def _freeze_durations(video: Path) -> list[float]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(video),
            "-vf", "freezedetect=n=-60dB:d=0.5",
            "-an", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-1000:]
    return [
        float(value)
        for value in re.findall(r"freeze_duration:\s*([0-9.]+)", result.stderr)
    ]


def _plate(path: Path) -> None:
    image = Image.new("RGB", (640, 360), (34, 58, 92))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 35, 230, 305), fill=(190, 105, 42), outline=(245, 230, 150), width=4)
    draw.ellipse((350, 80, 570, 300), fill=(54, 164, 142), outline=(235, 245, 250), width=4)
    draw.line((0, 330, 640, 30), fill=(230, 220, 150), width=5)
    image.save(path)


def _render(tmp_path: Path, name: str, motion: str, zoom_start: float, zoom_end: float) -> Path:
    source = tmp_path / f"{name}.png"
    output = tmp_path / f"{name}.mp4"
    _plate(source)
    CinematicVisualEngine(width=640, height=360, fps=24).render_motion(
        source,
        output,
        duration=6.0,
        camera={"movement": motion, "zoom_start": zoom_start, "zoom_end": zoom_end},
        lighting={"brightness": 1.0, "contrast": 1.0, "saturation": 1.0},
        atmosphere={},
        vfx={},
    )
    return output


def test_render_motion_no_freeze_static(tmp_path: Path):
    video = _render(tmp_path, "static", "static", 1.0, 1.0)
    assert not [x for x in _freeze_durations(video) if x > 0.5]


def test_render_motion_no_freeze_push_in(tmp_path: Path):
    video = _render(tmp_path, "push", "push_in", 1.0, 1.08)
    assert not [x for x in _freeze_durations(video) if x > 0.5]


def test_render_motion_no_freeze_pull_out(tmp_path: Path):
    # This is the production-shaped reverse range that previously became
    # 1.08 -> 0.86 and plateaued inside zoompan.
    video = _render(tmp_path, "pull", "pull_out", 1.08, 1.0)
    assert not [x for x in _freeze_durations(video) if x > 0.5]


def test_render_motion_no_freeze_slow_drift(tmp_path: Path):
    video = _render(tmp_path, "drift", "slow_drift", 1.0, 1.01)
    assert not [x for x in _freeze_durations(video) if x > 0.5]


def test_render_motion_no_freeze_reveal_wide(tmp_path: Path):
    video = _render(tmp_path, "reveal", "reveal_wide", 1.14, 1.0)
    assert not [x for x in _freeze_durations(video) if x > 0.5]


def test_render_motion_no_freeze_tracking(tmp_path: Path):
    video = _render(tmp_path, "tracking", "tracking", 1.0, 1.02)
    assert not [x for x in _freeze_durations(video) if x > 0.5]


def test_transition_no_freeze_dissolve(tmp_path: Path):
    first = _render(tmp_path, "first", "pull_out", 1.08, 1.0)
    second = _render(tmp_path, "second", "reveal_wide", 1.14, 1.0)
    output = tmp_path / "dissolve.mp4"
    apply_transition_ffmpeg(
        first,
        second,
        TransitionSpec(TransitionType.DISSOLVE, 0.5),
        output,
    )
    assert not [x for x in _freeze_durations(output) if x > 0.5]


def test_transition_no_freeze_crossfade(tmp_path: Path):
    first = _render(tmp_path, "first", "tracking", 1.0, 1.02)
    second = _render(tmp_path, "second", "slow_drift", 1.0, 1.02)
    output = tmp_path / "crossfade.mp4"
    apply_transition_ffmpeg(
        first,
        second,
        TransitionSpec(TransitionType.CROSSFADE, 0.3),
        output,
    )
    assert not [x for x in _freeze_durations(output) if x > 0.5]


def test_retime_no_freeze_for_shorter_edit(tmp_path: Path):
    source = _render(tmp_path, "source", "tracking", 1.0, 1.08)
    output = tmp_path / "retimed.mp4"
    pad_video_to_duration(source, output, 6.75)
    assert not [x for x in _freeze_durations(output) if x > 0.5]
