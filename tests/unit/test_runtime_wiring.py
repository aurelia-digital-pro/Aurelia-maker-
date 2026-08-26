from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import aurelia.visual_backend as visual_backend


ROOT = Path(__file__).resolve().parents[2]


def test_zero_force_fallback_reports_real_cloud_primary(monkeypatch):
    monkeypatch.setenv("AURELIA_FORCE_FALLBACK", "0")
    monkeypatch.setattr(
        visual_backend,
        "probe_sd_backend",
        lambda: {"available": False, "model_id": "", "error": "not installed"},
    )
    monkeypatch.setattr(
        "aurelia.visual_api.api_status",
        lambda: {"forced_backend": "pollinations", "pollinations": True},
    )
    monkeypatch.setattr(
        shutil,
        "which",
        lambda command: "/usr/local/bin/edge-tts" if command == "edge-tts" else None,
    )

    status = visual_backend.backend_status()

    assert status["primary"] == "cloud-api/pollinations"
    assert status["tts_backends"][0] == "edge-tts"


def test_one_force_fallback_reports_pillow_only_when_enabled(monkeypatch):
    monkeypatch.setenv("AURELIA_FORCE_FALLBACK", "1")
    monkeypatch.setattr(
        visual_backend,
        "probe_sd_backend",
        lambda: {"available": False, "model_id": "", "error": "forced"},
    )
    monkeypatch.setattr(
        "aurelia.visual_api.api_status",
        lambda: {"forced_backend": "pollinations", "pollinations": True},
    )

    assert visual_backend.backend_status()["primary"] == "pillow-fallback"


def test_replit_project_and_api_deployment_use_canonical_launcher():
    replit = tomllib.loads((ROOT / ".replit").read_text(encoding="utf-8"))
    api_artifact = tomllib.loads(
        (ROOT / "artifacts/api-server/.replit-artifact/artifact.toml").read_text(
            encoding="utf-8"
        )
    )

    assert replit["run"] == ["bash", "scripts/start-canonical.sh"]
    assert api_artifact["services"][0]["production"]["run"]["args"] == [
        "bash",
        "scripts/start-api-with-canonical.sh",
    ]
    production_env = api_artifact["services"][0]["production"]["run"]["env"]
    assert production_env["AURELIA_PRODUCTION_MODE"] == "1"
    assert production_env["AURELIA_FORCE_FALLBACK"] == "0"
    assert production_env["AURELIA_ALLOW_DEGRADED_TTS"] == "0"


def test_canonical_launchers_have_strict_python_entrypoint():
    for name in ("start-canonical.sh", "start-api-with-canonical.sh"):
        content = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "python3 -m aurelia.generate serve" in content
        assert 'AURELIA_PRODUCTION_MODE="${AURELIA_PRODUCTION_MODE:-1}"' in content
        assert 'AURELIA_FORCE_FALLBACK="${AURELIA_FORCE_FALLBACK:-0}"' in content
        assert 'AURELIA_ALLOW_DEGRADED_TTS="${AURELIA_ALLOW_DEGRADED_TTS:-0}"' in content
