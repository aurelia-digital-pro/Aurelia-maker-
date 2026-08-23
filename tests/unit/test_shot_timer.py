from aurelia.shot_timer import allocate


def test_allocations_sum_exactly_and_respect_bounds():
    shots = [{"function": "establishing"}, {"function": "action"}, {"function": "climax"}, {"function": "resolution"}]
    durations = allocate(shots, 24.0)
    assert abs(sum(durations) - 24.0) < 1e-6
    assert min(durations) >= 2.0
    assert max(durations) <= 15.0
