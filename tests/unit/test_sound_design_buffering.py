from pathlib import Path
import wave

from aurelia.media import generate_sound_design


def test_sound_design_writes_valid_buffered_stereo_pcm(tmp_path: Path):
    output = generate_sound_design(1.5, [0.3], tmp_path / "sound.wav")

    assert output.is_file()
    with wave.open(str(output), "rb") as audio:
        assert audio.getnchannels() == 2
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 48_000
        assert audio.getnframes() == 5 * 48_000
        samples = audio.readframes(audio.getnframes())

    assert len(samples) == 5 * 48_000 * 4
    assert any(samples), "scene-boundary sound-design cue must not be silent"


def test_sound_design_without_scene_boundaries_is_silent_bed(tmp_path: Path):
    output = generate_sound_design(1.0, [], tmp_path / "silent.wav")

    with wave.open(str(output), "rb") as audio:
        samples = audio.readframes(audio.getnframes())

    assert samples
    assert not any(samples)
