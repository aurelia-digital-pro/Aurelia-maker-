from aurelia.ai_visual import build_scene_prompt
from aurelia.continuity import ContinuityContext


def test_continuity_context_serializes_and_enters_prompt():
    context = ContinuityContext(
        palette=["deep blue", "amber"],
        environment_description="abandoned temple at dawn",
        lighting_key="warm backlight",
        character_anchors={"Mira": "grey coat"},
    )
    prompt = build_scene_prompt(
        "Mira", "Mira enters the temple", {"continuity": context.to_dict(), "shot_function": "establishing"}
    )
    assert "abandoned temple at dawn" in prompt
    assert "deep blue" in prompt
    assert "Mira" in prompt
