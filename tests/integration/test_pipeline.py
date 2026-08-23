from aurelia.planner import plan_scenes
from aurelia.scene_analyzer import SceneAnalyzer
from aurelia.shot_designer import ShotDesigner


def test_chat_to_scenes_to_shots_without_generation():
    script = "A signal appears in the city. The team follows it underground. They choose to protect one another."
    scenes = plan_scenes(script, min_scenes=3)
    analyzed = SceneAnalyzer().analyze_sequence(scenes)
    shots = [ShotDesigner().design(item, 12.0) for item in analyzed]
    assert len(scenes) >= 3
    assert all(group for group in shots)
