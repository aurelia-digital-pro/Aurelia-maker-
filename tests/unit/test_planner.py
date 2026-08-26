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


def test_distinct_location_sentences_remain_separate_scene_units():
    script = (
        "Inside a laboratory, instruments glow beneath cool light. "
        "At sunset, a city street reflects orange windows. "
        "Beyond the coast, waves cross the open ocean."
    )
    scenes = plan_scenes(script, min_scenes=3, max_scenes=20)
    assert len(scenes) == 3
    assert "laboratory" in scenes[0]["text"]
    assert "city" in scenes[1]["text"]
    assert "ocean" in scenes[2]["text"]
