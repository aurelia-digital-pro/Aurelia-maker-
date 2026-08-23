from aurelia.planner import plan_scenes

script = (
    "في الفجر اكتشف الفريق إشارة غامضة في قلب المدينة. "
    "قادهم الأثر إلى مختبر مهجور تحت الأرض. "
    "هناك واجهوا قراراً يغير مستقبلهم إلى الأبد. "
    "وفي النهاية اختاروا حماية الإنسان قبل كل شيء."
)
scenes = plan_scenes(script, min_scenes=3, max_scenes=20)
assert len(scenes) >= 3, f"expected >=3 scenes, got {len(scenes)}"
assert " ".join(scene["text"] for scene in scenes) == script
print(f"MULTI-SCENE PLANNER PASS: {len(scenes)} scenes")
