import hashlib
from pathlib import Path

from aurelia import episode_engine
from aurelia.episode_engine import EpisodeProduction, ScenePlan
from aurelia.visual_checkpoint import VisualCheckpoint


def test_checkpoint_requires_the_expected_shot_path(tmp_path: Path):
    checkpoint = VisualCheckpoint(tmp_path / "generation_checkpoint.json")
    first = tmp_path / "scene_01_shot_00.png"
    second = tmp_path / "scene_01_shot_01.png"
    first.write_bytes(b"x" * 2000)
    checkpoint.mark_done(0, 0, first, "cloud-api/pollinations", {"backend": "cloud-api/pollinations"})

    assert checkpoint.is_done(0, 0, first) is True
    assert checkpoint.is_done(0, 0, second) is False


def test_visual_generation_calls_each_shot_once_and_resumes(tmp_path, monkeypatch):
    script = tmp_path / "script.txt"
    script.write_text("Title: Test\n\nA visual story about space and a laboratory.", encoding="utf-8")
    production = EpisodeProduction("0007", tmp_path / "run", script, language="en")
    production.scenes = [
        ScenePlan(
            index=0,
            title="Scene",
            text="A visual story about space and a laboratory.",
            direction={"environment": "space", "lighting": {"key": {"color": "blue"}}},
            analysis={"primary_subject": "a spacecraft"},
            shots=[
                {"shot_index": 0, "description": "wide spacecraft", "framing": "wide", "motion_intent": "slow_drift"},
                {"shot_index": 1, "description": "close spacecraft", "framing": "close_up", "motion_intent": "push_in"},
            ],
        )
    ]
    monkeypatch.setattr(episode_engine, "assert_production_visual_provider", lambda logger=None: "cloud-api/pollinations")
    calls = []

    def fake_generate(scene_index, title, text, output, **kwargs):
        calls.append((scene_index, kwargs.get("shot_index"), Path(output)))
        Path(output).write_bytes(b"x" * 2000)
        return {
            "backend": "cloud-api/pollinations",
            "fallback": False,
            "fallback_reason": "",
            "prompt": kwargs.get("visual_note", ""),
            "seed": 1,
            "elapsed_s": 0.1,
        }

    monkeypatch.setattr(episode_engine, "generate_visual", fake_generate)
    assets = production.generate_visual_assets()
    assert sorted((scene, shot) for scene, shot, _ in calls) == [(0, 0), (0, 1)]
    assert len(assets["0"]) == 2

    calls.clear()
    resumed = production.generate_visual_assets()
    assert calls == []
    assert [p.name for p in resumed["0"]] == ["scene_01_shot_00.png", "scene_01_shot_01.png"]
    assert production._total_visual_assets == 2
