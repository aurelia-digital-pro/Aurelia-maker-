from aurelia.planner import plan_scenes


def test_short_sentence_script_splits_without_inventing_text():
    script = "One question appears. A hidden door opens. The team chooses courage."
    scenes = plan_scenes(script, min_scenes=3)
    assert len(scenes) == 3
    assert " ".join(scene["text"] for scene in scenes) == script


def test_chat_headers_are_not_scene_content():
    script = "Create Episode 0088\nTitle: Thought\nLanguage: en\n\nSilence arrives. A question follows. A mind changes."
    scenes = plan_scenes(script)
    assert len(scenes) >= 3
    assert all("Create Episode" not in scene["text"] for scene in scenes)


def test_long_film_reaches_five_scenes():
    script = " ".join(f"Sentence {i} develops the story." for i in range(1, 11))
    assert len(plan_scenes(script)) >= 5
