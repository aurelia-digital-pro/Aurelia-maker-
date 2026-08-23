from pathlib import Path

from aurelia.series_manager import SeriesManager


def test_episode_0089_series_continuity_persists(tmp_path: Path):
    manager = SeriesManager(tmp_path)
    series = manager.create_series(
        "aurelia-test",
        "The Signal",
        language="en",
        description="A continuity smoke series",
    )
    manager.set_visual_language(
        series.id,
        palette="indigo, ember, silver",
        grade="cool shadows with warm practicals",
    )
    manager.add_character(
        series.id,
        "mira",
        "Mira",
        description="A systems cartographer",
        visual_profile="short dark hair, copper field jacket",
        first_episode="0088",
    )
    manager.add_location(
        series.id,
        "relay",
        "Relay Station",
        description="A high-altitude antenna site",
        visual_profile="weathered steel, blue-hour fog",
        first_episode="0088",
    )
    first = manager.add_episode(series.id, 1, 88, title="The First Signal", language="en")
    second = manager.add_episode(series.id, 1, 89, title="The Return Signal", language="en")
    manager.update_episode_status(
        series.id,
        first.id,
        "completed",
        final_mp4="/tmp/episode-0088-FINAL.mp4",
        run_id="series-smoke-0088",
        story_state={"signal_strength": "faint", "location": "relay"},
    )

    reloaded = SeriesManager(tmp_path)
    context = reloaded.get_continuity_context(series.id, second.id)
    assert context["visual_language"]["palette"] == "indigo, ember, silver"
    assert context["characters"][0]["visual_profile"] == "short dark hair, copper field jacket"
    assert context["locations"][0]["name"] == "Relay Station"
    assert context["story_state"] == {"signal_strength": "faint", "location": "relay"}
    persisted_first = reloaded.get_series(series.id).seasons[0].episodes[0]
    assert persisted_first.status == "completed"
    assert persisted_first.final_mp4.endswith("episode-0088-FINAL.mp4")
    assert second.number == 89
