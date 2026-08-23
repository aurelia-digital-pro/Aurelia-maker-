from aurelia.scene_analyzer import SceneAnalyzer
from aurelia.shot_designer import ShotDesigner


def test_shot_design_has_motion_and_framing():
    analysis = SceneAnalyzer().analyze("1", "Opening", "The camera enters a vast city at dawn.")
    shots = ShotDesigner().design(analysis, 18.0)
    assert len(shots) >= 2
    assert all(shot.framing and shot.motion_intent for shot in shots)


def test_static_intent_has_micro_zoom():
    start, end = ShotDesigner()._zoom_range("static", 0.0)
    assert start == 1.0 and end >= 1.02
