from aurelia.transitions import TransitionType, select_transition


def test_scene_boundary_uses_dissolve_by_default():
    spec = select_transition({}, {"shot_function": "establishing"}, scene_change=True)
    assert spec.kind is TransitionType.DISSOLVE
    assert spec.duration == 0.5


def test_action_shot_uses_hard_cut():
    assert select_transition({}, {"shot_function": "action"}).kind is TransitionType.HARD_CUT
