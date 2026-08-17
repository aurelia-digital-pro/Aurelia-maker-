"""Regression checks for content-driven cinematic direction.

This check uses a real repository episode script supplied explicitly by the
caller. It never renders a fake episode and never invokes the production
shortcut. The perturbation test keeps scene position and duration constant
while changing only scene meaning.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from aurelia.ai_visual import build_scene_prompt
from aurelia.directing_engine import DirectingEngine
from aurelia.planner import plan_scenes


def normalized(plan: dict) -> dict:
    """Remove identity-only fields so reverse tests compare decisions, not IDs."""
    return {
        "environment": plan["environment"],
        "camera": {k: v for k, v in plan["camera"].items() if k != "shot_id"},
        "depth": {k: v for k, v in plan["depth"].items() if k != "shot_id"},
        "motion": {k: v for k, v in plan["motion"].items() if k != "shot_id"},
        "lighting": {k: v for k, v in plan["lighting"].items() if k != "shot_id"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True, help="Path to a real repository episode script")
    args = parser.parse_args()

    script_path = Path(args.script)
    if not script_path.exists() or not script_path.is_file():
        raise SystemExit(f"Missing real episode script: {script_path}")

    text = script_path.read_text(encoding="utf-8").strip()
    scenes = plan_scenes(text)
    if not scenes:
        raise SystemExit("The selected real episode produced no scenes")

    director = DirectingEngine()
    selected = scenes[:5]
    decisions = []
    prompts = []
    for index, scene in enumerate(selected):
        decision = director.direct(f"test:scene:{index}", scene["title"], scene["text"], 18.0)
        decisions.append(normalized(decision))
        prompts.append(build_scene_prompt(scene["title"], scene["text"], decision))

    # A real script must produce semantic information in the directing path.
    if not any(item["environment"] != "abstract" for item in decisions):
        raise SystemExit("No semantic environment was derived from the real episode")

    # Content perturbation: same scene position and duration, different meaning.
    base = selected[0]
    space = director.direct("same-index", "Cosmos", "مجرة بعيدة، نجوم، فراغ كوني، ضوء قادم من أعماق الكون", 18.0)
    lab = director.direct("same-index", "Laboratory", "مختبر علمي، أجهزة، علماء، تجربة، ضوء بارد", 18.0)
    if normalized(space) == normalized(lab):
        raise SystemExit("Content perturbation failed: directing decisions are identical")
    space_prompt = build_scene_prompt("Cosmos", "مجرة بعيدة، نجوم، فراغ كوني، ضوء قادم من أعماق الكون", space)
    lab_prompt = build_scene_prompt("Laboratory", "مختبر علمي، أجهزة، علماء، تجربة، ضوء بارد", lab)
    if space_prompt == lab_prompt:
        raise SystemExit("Content perturbation failed: visual prompts are identical")

    # Reverse test: same semantic content at different scene IDs must retain
    # the same cinematic decisions once identity fields are removed.
    reverse_a = director.direct("episode:scene:001", base["title"], base["text"], 18.0)
    reverse_b = director.direct("episode:scene:099", base["title"], base["text"], 18.0)
    if normalized(reverse_a) != normalized(reverse_b):
        raise SystemExit("Reverse test failed: scene position changes directing decisions")

    print("CINEMATIC_INTELLIGENCE: PASS")
    print(f"REAL_SCRIPT: {script_path}")
    print(f"SCENES_CHECKED: {len(selected)}")
    print(f"ENVIRONMENTS: {[item['environment'] for item in decisions]}")
    print(f"PROMPTS_CONTENT_DRIVEN: {len(set(prompts)) == len(prompts)}")
    print("CONTENT_PERTURBATION: PASS")
    print("REVERSE_TEST: PASS")


if __name__ == "__main__":
    main()
