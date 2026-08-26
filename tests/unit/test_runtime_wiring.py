from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from types import SimpleNamespace

from aurelia.chat_entry import handle_chat_production

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


def test_chat_path_has_one_canonical_executor_and_edge_narration():
    chat_entry = (ROOT / "aurelia/chat_entry.py").read_text(encoding="utf-8")
    server = (ROOT / "aurelia/server.py").read_text(encoding="utf-8")
    episode_engine = (ROOT / "aurelia/episode_engine.py").read_text(encoding="utf-8")
    proxy = (ROOT / "artifacts/api-server/src/routes/productions.ts").read_text(
        encoding="utf-8"
    )

    assert "runner.execute_async" in chat_entry
    assert "handle_chat_production" in server
    assert "provider = EdgeTTSProvider()" in episode_engine
    assert "spawn(" not in proxy
    assert "run_job.py" not in proxy
    assert "independent status machine" in proxy
    assert "all dialogue segments failed" not in "".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "aurelia").rglob("*.py")
    )


def test_chat_entry_binds_authoritative_message_to_factory(tmp_path: Path):
    calls: list[dict[str, object]] = []

    class FakeRunner:
        output = tmp_path

        def resolve_episode_id(self, text: str) -> str | None:
            return "0007" if "0007" in text else None

        def execute_async(self, episode_id: str, *, profile: str, script_path: Path):
            calls.append(
                {
                    "episode_id": episode_id,
                    "profile": profile,
                    "script_path": script_path,
                }
            )
            return SimpleNamespace(job_id="job-chat-contract", metadata={})

    source = "اكتب فيلمًا وثائقيًا عن الذكاء الاصطناعي في الطب، مع سياق تاريخي واضح وتطورات مستقبلية." \
        " ناقش الفوائد والمخاطر والحوكمة بلغة عربية هادئة."
    result = handle_chat_production(
        FakeRunner(), f"أنشئ الحلقة 0007\nProfile: youtube\n{source}"
    )

    assert result["action"] == "produce"
    assert result["job_id"] == "job-chat-contract"
    assert result["episode_id"] == "0007"
    assert result["profile"] == "youtube"
    assert result["script_source"] == "chat"
    assert len(calls) == 1
    assert calls[0]["episode_id"] == "0007"
    assert calls[0]["profile"] == "youtube"
    assert Path(calls[0]["script_path"]).read_text(encoding="utf-8") == source


def test_api_readiness_fails_closed_without_canonical_backend():
    health = (ROOT / "artifacts/api-server/src/routes/health.ts").read_text(
        encoding="utf-8"
    )
    assert "AURELIA_CANONICAL_API_URL" in health
    assert "/api/health" in health
    assert "AbortSignal.timeout" in health
    assert 'res.status(503)' in health
