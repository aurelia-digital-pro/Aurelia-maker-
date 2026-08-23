from pathlib import Path

from PIL import Image, ImageDraw

from aurelia.qc_engine import visual_variation_preflight
from aurelia.visuals import CinematicVisualEngine


def test_visual_preflight_rejects_static_video(tmp_path: Path):
    source = tmp_path / "static.png"
    video = tmp_path / "static.mp4"
    Image.new("RGB", (320, 180), (20, 25, 35)).save(source)
    CinematicVisualEngine(width=320, height=180, fps=24).render_motion(
        source, video, 20.0, camera={"movement": "static", "zoom_start": 1.0, "zoom_end": 1.0}, vfx={}
    )
    result = visual_variation_preflight(video)
    assert result["threshold"] == 0.005
    assert result["passed"] is False


def test_visual_preflight_accepts_real_camera_motion(tmp_path: Path):
    source = tmp_path / "changing.png"
    video = tmp_path / "changing.mp4"
    image = Image.new("RGB", (320, 180), (40, 90, 150))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 140, 160), fill=(180, 80, 35))
    draw.ellipse((190, 35, 300, 145), fill=(220, 205, 90))
    draw.line((0, 170, 320, 40), fill=(245, 245, 245), width=8)
    image.save(source)
    CinematicVisualEngine(width=320, height=180, fps=24).render_motion(
        source, video, 20.0, camera={"movement": "pan_right", "zoom_start": 1.0, "zoom_end": 1.45}, vfx={}
    )
    result = visual_variation_preflight(video)
    assert result["threshold"] == 0.005
    assert result["passed"] is True


def test_motion_render_has_no_long_freeze_on_low_texture_plate(tmp_path: Path):
    import re
    import subprocess

    source = tmp_path / "low_texture.png"
    video = tmp_path / "low_texture.mp4"
    Image.new("RGB", (320, 180), (80, 80, 80)).save(source)
    CinematicVisualEngine(width=320, height=180, fps=24).render_motion(
        source, video, 2.0,
        camera={"movement": "static", "zoom_start": 1.0, "zoom_end": 1.0},
        vfx={},
    )
    result = subprocess.run(
        ["ffmpeg", "-i", str(video), "-vf", "freezedetect=n=-60dB:d=0.5",
         "-an", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    durations = [float(value) for value in re.findall(r"freeze_duration:\s*([0-9.]+)", result.stderr)]
    assert result.returncode == 0
    assert not [duration for duration in durations if duration > 0.5]
