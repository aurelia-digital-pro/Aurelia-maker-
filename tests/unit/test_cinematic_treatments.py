from pathlib import Path
import subprocess

from PIL import Image, ImageDraw

from aurelia.depth import DEPTH_METHOD, build_depth_map
from aurelia.scene_analyzer import SceneAnalyzer
from aurelia.shot_designer import ShotDesigner
from aurelia.visuals import CinematicVisualEngine


def _analysis(text: str, title: str, index: int = 0, total: int = 3):
    return SceneAnalyzer().analyze(
        scene_id=f"scene-{index}", title=title, text=text,
        scene_index=index, total_scenes=total,
    )


def test_shot_treatments_follow_scene_semantics():
    designer = ShotDesigner()
    wonder = _analysis(
        "اكتشاف جديد في الفضاء يكشف عالمًا مجهولًا ومذهلًا.",
        "بوابة إلى المجهول",
    )
    tense = _analysis(
        "خطر وتهديد وضغط وصراع يقترب من الشخصية.",
        "لحظة المواجهة",
        index=1,
    )
    calm = _analysis(
        "هدوء وسكينة وتأمل في غابة عند الغروب.",
        "مساحة للتأمل",
        index=2,
    )
    wonder_treatments = {s.cinematic_treatment for s in designer.design(wonder, 12.0)}
    tense_treatments = {s.cinematic_treatment for s in designer.design(tense, 12.0)}
    calm_treatments = {s.cinematic_treatment for s in designer.design(calm, 12.0)}
    assert "layered_reveal" in wonder_treatments
    assert "subject_follow" in tense_treatments
    assert "atmospheric_drift" in calm_treatments


def test_depth_map_is_explicit_heuristic_artifact(tmp_path: Path):
    source = tmp_path / "source.png"
    depth = tmp_path / "depth.png"
    image = Image.new("RGB", (160, 90), (20, 30, 60))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 10, 70, 78), fill=(210, 100, 40))
    draw.ellipse((90, 20, 145, 75), fill=(220, 210, 90))
    image.save(source)
    build_depth_map(source, depth)
    with Image.open(depth) as result:
        assert result.mode == "L"
        assert result.size == image.size
        assert result.getextrema()[1] > result.getextrema()[0]
    assert DEPTH_METHOD == "deterministic-saliency-v1"


def test_parallax_treatment_renders_depth_artifact_without_freeze(tmp_path: Path):
    source = tmp_path / "source.png"
    video = tmp_path / "parallax.mp4"
    depth = tmp_path / "depth.png"
    image = Image.new("RGB", (320, 180), (25, 40, 70))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 15, 110, 165), fill=(180, 95, 45))
    draw.ellipse((180, 30, 300, 150), fill=(220, 205, 90))
    image.save(source)
    CinematicVisualEngine(width=320, height=180, fps=24).render_motion(
        source, video, 2.0,
        camera={"movement": "tracking", "zoom_start": 1.0, "zoom_end": 1.15},
        depth={"mode": "parallax", "parallax_strength": 0.10, "artifact_path": str(depth)},
        vfx={"grain": 0.02, "vignette": 0.0, "bloom": 0.0},
    )
    assert video.is_file() and depth.is_file()
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
         "-vf", "freezedetect=n=-60dB:d=0.5", "-an", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert "freeze_duration" not in result.stderr


def test_scene_prompt_preserves_content_and_treatment_without_continuity():
    from aurelia.ai_visual import build_scene_prompt

    space = build_scene_prompt(
        "Cosmos", "مجرة بعيدة ونجوم وفراغ كوني",
        {"environment": "space", "motion": {"type": "orbit"}, "cinematic_treatment": "layered_reveal", "depth_mode": "parallax"},
    )
    lab = build_scene_prompt(
        "Laboratory", "مختبر علمي وأجهزة وتجربة وضوء بارد",
        {"environment": "laboratory", "motion": {"type": "dolly_in"}, "cinematic_treatment": "subject_follow", "depth_mode": "focus_plane"},
    )
    assert space != lab
    assert "layered_reveal" in space
    assert "parallax" in space
    assert "subject_follow" in lab
    assert "focus_plane" in lab
