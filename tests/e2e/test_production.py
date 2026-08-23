from pathlib import Path

from aurelia.ambient_synth import synthesize_ambient
from aurelia.music_engine import generate_cinematic_music
from aurelia.providers import SynthAmbientProvider


def test_mock_provider_production_artifacts(tmp_path: Path):
    music = generate_cinematic_music(3.0, tmp_path / "music.wav", emotional_arc=["build", "climax"])
    ambient = synthesize_ambient("forest", 3.0, tmp_path / "ambient.wav")
    assert music.is_file() and music.stat().st_size > 1000
    assert SynthAmbientProvider().validate(ambient)
