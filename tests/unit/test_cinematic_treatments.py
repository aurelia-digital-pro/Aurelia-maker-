from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageStat

from aurelia.depth import DEPTH_METHOD, build_depth_map
from aurelia.directing_engine import DirectingEngine
from aurelia.episode_engine import EpisodeProduction, ScenePlan
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
    frame = tmp_path / "parallax-frame.png"
    decoded = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", "1.0", "-i", str(video),
         "-frames:v", "1", str(frame)],
        capture_output=True, text=True, check=False,
    )
    assert decoded.returncode == 0
    means = ImageStat.Stat(Image.open(frame).convert("RGB")).mean
    assert max(means) - min(means) >= 5.0


def test_directing_uses_content_specific_environment_and_palette():
    director = DirectingEngine()
    concept = director.direct(
        "scene-1", "The Algorithm", "An abstract algorithm maps signals into a visual network.",
        duration=8.0, scene_analysis={"emotional_register": "wonder", "preferred_shots": ["wide"]},
    )
    person = director.direct(
        "scene-2", "The Researcher", "A woman stands alone beside a window.",
        duration=8.0, scene_analysis={"emotional_register": "calm", "preferred_shots": ["medium"]},
    )
    assert concept["environment"] in {"abstract", "machine"}
    assert concept["environment"] != "human"
    assert "algorithm" in concept["environment_description"]
    assert len(concept["visual_palette"]) >= 3
    assert person["environment"] == "human"


def test_negated_human_cues_do_not_force_portrait_environment():
    director = DirectingEngine()
    result = director.direct(
        "scene-3", "Opening", "No face or person appears; a luminous signal map fills the frame.",
        duration=8.0, scene_analysis={"emotional_register": "wonder", "preferred_shots": ["wide"]},
    )
    assert result["environment"] != "human"

    arabic_result = director.direct(
        "scene-3-ar", "لا تظهر وجوه أو شخصيات", "تظهر خريطة ضوء هندسية في فضاء واسع.",
        duration=8.0, scene_analysis={"emotional_register": "wonder", "preferred_shots": ["wide"]},
    )
    assert arabic_result["environment"] != "human"


def test_scene_title_beats_cross_scene_substring_matches():
    director = DirectingEngine()
    result = director.direct(
        "scene-4", "The Laboratory", "A researcher moves inside a room near the sea.",
        duration=8.0, scene_analysis={"emotional_register": "calm", "preferred_shots": ["wide"]},
    )
    assert result["environment"] == "laboratory"


def test_episode_scene_plan_passes_analysis_to_directing(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("Title: Content direction\nLanguage: en\nbody", encoding="utf-8")
    production = EpisodeProduction("0002", tmp_path / "episode", script)
    scenes = production.build_scene_plan(
        "An algorithm maps signals across a technical network.\n\n"
        "A mountain archive preserves a quiet historical memory.\n\n"
        "A river at dawn reflects a hopeful future."
    )
    assert scenes
    assert all(scene.direction.get("visual_palette") for scene in scenes)
    assert all(scene.direction.get("environment_description") for scene in scenes)
    assert all(scene.analysis.get("visual_objective") for scene in scenes)


def test_scene_prompt_keeps_shot_detail_and_blocks_generic_people():
    from aurelia.ai_visual import build_scene_prompt

    prompt = build_scene_prompt(
        "Network", "A signal map links distant instruments.",
        {
            "environment": "machine",
            "shot_visual_note": "red bridge over a frozen river, wide establishing reveal",
            "visual_palette": ["graphite", "electric cyan"],
            "cinematic_treatment": "layered_reveal",
            "depth_mode": "parallax",
        },
    )
    assert "red bridge" in prompt
    assert "environment and objects only" in prompt
    assert "portrait" not in prompt.lower()
    assert "layered_reveal" in prompt


def test_subtitles_wrap_to_restrained_lines_without_losing_words(tmp_path, monkeypatch):
    script = tmp_path / "script.txt"
    script.write_text("Title: Safe captions\nLanguage: ar\nbody", encoding="utf-8")
    production = EpisodeProduction("0001", tmp_path / "episode", script, language="ar")
    production.scenes = [ScenePlan(
        index=0,
        title="Scene",
        text="هذه جملة عربية طويلة تشرح كيف يتحول المعنى إلى صورة واضحة داخل المشهد السينمائي دون أن تحجب الترجمة الموضوع أو التفاصيل المهمة.",
        duration=10.0,
    )]
    monkeypatch.setattr("aurelia.episode_engine.probe_duration", lambda _path: 10.0)
    srt = production.build_subtitles(tmp_path / "narration.wav")
    blocks = [block for block in srt.read_text(encoding="utf-8").split("\n\n") if block.strip()]
    text_lines = [line for block in blocks for line in block.splitlines()[2:]]
    assert text_lines
    assert max(len(line) for line in text_lines) <= 42
    flattened = " ".join(text_lines).replace("  ", " ")
    assert "المعنى" in flattened
    assert "التفاصيل" in flattened


def test_nonhuman_scene_prompt_frontloads_positive_environment_and_removes_negated_people():
    from aurelia.ai_visual import build_scene_prompt

    prompt = build_scene_prompt(
        "لا تظهر وجوه أو شخصيات؛ المكان نفسه هو الموضوع",
        "في غرفة تخطيط دافئة، تستقر الأوراق والبطاقات الزمنية فوق طاولة طويلة. لا تظهر وجوه أو شخصيات.",
        {
            "environment": "home",
            "visual_palette": ["warm ivory", "wood brown", "window gold"],
            "shot_visual_note": "long table and glass board, wide establishing reveal",
            "cinematic_treatment": "layered_reveal",
            "depth_mode": "parallax",
        },
    )
    assert prompt.startswith("photorealistic cinematic environmental documentary frame; home setting")
    assert "empty warm planning room" in prompt
    assert "long table and glass board" in prompt
    assert "warm ivory" in prompt
    assert "portrait" not in prompt.lower()
    assert "female" not in prompt.lower()
    assert "face" not in prompt.lower()
    assert "no people" not in prompt.lower()
    assert "layered_reveal" in prompt
    assert "parallax" in prompt


def test_nonhuman_prompt_budget_keeps_environment_and_shot_grammar():
    from aurelia.ai_visual import build_scene_prompt

    prompt = build_scene_prompt(
        "Technical laboratory",
        "مختبر تقني، دوائر شفافة، أجهزة قياس، شاشات بعيدة، وإضاءة زرقاء.",
        {
            "environment": "laboratory",
            "visual_palette": ["cool white", "glass blue", "technical teal"],
            "shot_visual_note": "glass panels and blue signal nodes, lateral tracking shot",
            "cinematic_treatment": "subject_follow",
            "depth_mode": "focus_plane",
        },
    )
    assert len(prompt.split()) <= 72
    assert prompt.index("environment subject:") < prompt.index("story focus:")
    assert "empty production laboratory" in prompt
    assert "blue signal nodes" in prompt
    assert "subject_follow" in prompt
    assert "focus_plane" in prompt


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
