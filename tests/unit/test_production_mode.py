from pathlib import Path

import pytest

from aurelia.visual_backend import assert_production_visual_provider, generate_visual


def test_production_mode_rejects_forced_fallback(monkeypatch):
    monkeypatch.setenv("AURELIA_PRODUCTION_MODE", "1")
    monkeypatch.setenv("AURELIA_FORCE_FALLBACK", "1")
    with pytest.raises(RuntimeError, match="cannot be used"):
        assert_production_visual_provider()


def test_production_mode_rejects_pillow_provider(monkeypatch):
    monkeypatch.setenv("AURELIA_PRODUCTION_MODE", "1")
    monkeypatch.setenv("AURELIA_FORCE_FALLBACK", "0")
    monkeypatch.setenv("AURELIA_VISUAL_BACKEND", "pillow")
    with pytest.raises(RuntimeError, match="REAL VISUAL PROVIDER"):
        assert_production_visual_provider()


def test_production_generation_rejects_fallback_before_writing(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AURELIA_PRODUCTION_MODE", "1")
    monkeypatch.setenv("AURELIA_FORCE_FALLBACK", "1")
    output = tmp_path / "should-not-exist.png"
    with pytest.raises(RuntimeError, match="cannot be used"):
        generate_visual(0, "No fallback", "Production contract", output)
    assert not output.exists()
