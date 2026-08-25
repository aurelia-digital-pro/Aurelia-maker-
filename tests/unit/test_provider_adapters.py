from pathlib import Path

from aurelia.providers import (
    CinematicMusicProvider,
    EdgeTTSProvider,
    EspeakProvider,
    PillowProvider,
    SynthAmbientProvider,
)


def test_local_provider_generate_and_validate_contracts(tmp_path: Path):
    image = PillowProvider().generate(
        "A cinematic mountain observatory at blue hour",
        tmp_path / "shot.png",
        scene_index=0,
        title="Observatory",
        width=320,
        height=180,
    )
    music = CinematicMusicProvider().generate(
        1.5, tmp_path / "music.wav", emotional_arc=["intro", "climax"]
    )
    ambient = SynthAmbientProvider().generate(
        "mountain", 1.5, tmp_path / "ambient.wav", seed=7
    )
    edge_provider = EdgeTTSProvider()
    narration = edge_provider.generate(
        "The observatory wakes beneath the first stars.", tmp_path / "narration.wav"
    )
    espeak = EspeakProvider().generate(
        "A second local voice confirms the signal.", tmp_path / "espeak.wav"
    )

    providers_and_outputs = [
        (PillowProvider(), image),
        (CinematicMusicProvider(), music),
        (SynthAmbientProvider(), ambient),
        (EdgeTTSProvider(), narration),
        (EspeakProvider(), espeak),
    ]
    for provider, output in providers_and_outputs:
        assert output.is_file() and output.stat().st_size > 500
        assert provider.validate(output)

    assert edge_provider.provenance["provider"] == "edge-tts"
    assert edge_provider.provenance["voice"]
    assert edge_provider.provenance["language"] == "en"
    assert edge_provider.provenance["fallback"] is False
    assert edge_provider.provenance["duration_s"] > 0
    assert edge_provider.provenance["sample_rate"] == 22050
