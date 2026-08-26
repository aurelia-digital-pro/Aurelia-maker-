from pathlib import Path
import json
import subprocess

import pytest

from aurelia.media import generate_ambient_music, generate_sound_design, mix_narration_and_music
from aurelia.providers.audio import EdgeTTSProvider
from aurelia.qc_engine import measure_audio_quality


def test_edge_tts_fails_loudly_when_unavailable(monkeypatch, tmp_path: Path):
    real_which = __import__("shutil").which
    monkeypatch.setattr(
        "aurelia.providers.audio.shutil.which",
        lambda name: None if name == "edge-tts" else real_which(name),
    )
    provider = EdgeTTSProvider(allow_degraded=False)
    with pytest.raises(RuntimeError, match="requires Edge Neural provider"):
        provider.generate("هذا اختبار صوت عربي", tmp_path / "narration.wav", language="ar")


def test_edge_tts_reports_timeout_attempts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "aurelia.providers.audio.shutil.which",
        lambda name: "/fake/edge-tts" if name == "edge-tts" else None,
    )
    monkeypatch.setattr("aurelia.providers.audio.time.sleep", lambda _seconds: None)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("/fake/edge-tts", 10)

    monkeypatch.setattr("aurelia.providers.audio.subprocess.run", timeout)
    provider = EdgeTTSProvider(
        allow_degraded=False, max_attempts=2, timeout_seconds=10
    )
    with pytest.raises(RuntimeError, match=r"timed out.*attempt 1.*attempt 2"):
        provider.generate("هذا اختبار timeout", tmp_path / "narration.wav", language="ar")


def test_synthesize_script_passes_complete_text_to_edge(monkeypatch, tmp_path: Path):
    from aurelia.tts import synthesize_script

    source = "Title: اختبار\nLanguage: ar\n\nهذه جملة عربية كاملة. وهذه جملة ثانية."
    captured = {}

    def fake_generate(self, text, output, language="auto", **_kwargs):
        captured.update(text=text, output=Path(output), language=language)
        self.provenance = {"provider": "edge-tts", "fallback": False}
        return Path(output)

    monkeypatch.setattr(
        "aurelia.providers.audio.EdgeTTSProvider.generate", fake_generate
    )
    result = synthesize_script(source, tmp_path / "narration.wav", language="ar")

    assert captured == {
        "text": source,
        "output": tmp_path / "narration.wav",
        "language": "ar",
    }
    assert result["provider"] == "edge-tts"
    assert result["fallback"] is False


def test_degraded_tts_requires_explicit_opt_in(monkeypatch, tmp_path: Path):
    real_which = __import__("shutil").which
    monkeypatch.setattr(
        "aurelia.providers.audio.shutil.which",
        lambda name: None if name == "edge-tts" else real_which(name),
    )
    monkeypatch.setenv("AURELIA_PRODUCTION_MODE", "0")
    provider = EdgeTTSProvider(allow_degraded=True)
    output = tmp_path / "degraded.wav"
    provider.generate("A local degraded test", output, language="en")
    assert output.is_file() and provider.provenance["fallback"] is True
    assert provider.provenance["provider"] == "espeak-ng"
    assert provider.provenance["degraded"] is True


def test_audio_mix_consumes_all_authored_layers(tmp_path: Path):
    video = tmp_path / "video.mp4"
    narration = tmp_path / "narration.wav"
    music = tmp_path / "music.wav"
    ambient = tmp_path / "ambient.wav"
    sound_design = tmp_path / "sound.wav"
    mixed = tmp_path / "mixed.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=24",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(video),
        ],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:sample_rate=22050", "-t", "30", "-c:a", "pcm_s16le", str(narration)],
        check=True,
    )
    generate_ambient_music(34.0, music)
    generate_ambient_music(34.0, ambient)
    generate_sound_design(30.0, [5.0, 15.0], sound_design)
    mix_narration_and_music(video, narration, mixed, music, sound_design, ambient)
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=sample_rate,channels,codec_name",
         "-of", "json", str(mixed)], text=True,
    ))
    audio = next(stream for stream in probe["streams"] if stream.get("codec_name") == "aac")
    assert int(audio["sample_rate"]) == 48000
    assert int(audio["channels"]) == 2
    assert float(probe["format"]["duration"]) >= 30.0


def test_audio_quality_measurement_on_accepted_final_artifact():
    final = Path("/tmp/aurelia-artifact-32674094316/runs/e2e/episode-0001-FINAL.mp4")
    if not final.is_file():
        pytest.skip("accepted production artifact is not present in this checkout")
    result = measure_audio_quality(final)
    assert result["passed"] is True
    assert -18.0 <= result["integrated_lufs"] <= -14.0
    assert result["true_peak_dbfs"] <= -1.0
    assert result["sample_clipping_detected"] is False
