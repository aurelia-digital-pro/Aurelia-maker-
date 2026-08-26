from __future__ import annotations

import subprocess

import pytest

from aurelia.orchestrator import ProductionOrchestrator
from aurelia.production_contract import (
    PRODUCTION_STAGES,
    build_production_contracts,
    validate_production_contracts,
)
from aurelia.production_pipeline import ProductionPipeline
from aurelia.providers.audio import EdgeTTSProvider


def test_canonical_contracts_cover_every_stage_in_order():
    contracts = build_production_contracts()
    result = validate_production_contracts(contracts)
    assert result == {"valid": True, "count": len(PRODUCTION_STAGES), "errors": []}
    assert tuple(contracts) == PRODUCTION_STAGES
    assert all(contract.required_outputs for contract in contracts.values())


def test_pipeline_rejects_missing_stage_output_without_false_success(tmp_path):
    pipeline = ProductionPipeline(
        orchestrator=ProductionOrchestrator(tmp_path, max_retries=0)
    )
    pipeline.validate()
    input_data = {
        "episode_id": "0001",
        "title": "Contract test",
        "language": "en",
        "profile": "youtube",
        "source_text_sha256": "source-hash",
    }
    execution = pipeline.execute_stage(
        project="contract-test",
        stage="SCRIPT",
        unit_type="production_stage",
        unit_id="contract-test:SCRIPT",
        input_data=input_data,
        processor=lambda data: {**data, "stage": "SCRIPT"},
        validator=lambda _output: True,
    )
    assert execution.status == "FAILED"
    assert "SCRIPT missing required output: text" in execution.error
    assert execution.attempts == 1


def test_pipeline_accepts_valid_stage_payload(tmp_path):
    pipeline = ProductionPipeline(
        orchestrator=ProductionOrchestrator(tmp_path, max_retries=0)
    )
    input_data = {
        "episode_id": "0001",
        "title": "Contract test",
        "language": "en",
        "profile": "youtube",
        "source_text_sha256": "source-hash",
    }
    output = {
        **input_data,
        "stage": "SCRIPT",
        "text": "A complete script payload.",
        "script_chars": 27,
        "script_words": 4,
    }
    execution = pipeline.execute_stage(
        project="contract-test",
        stage="SCRIPT",
        unit_type="production_stage",
        unit_id="contract-test:SCRIPT-valid",
        input_data=input_data,
        processor=lambda _data: output,
        validator=lambda _output: True,
    )
    assert execution.status == "COMPLETED"


def test_runner_reuses_same_identity_but_distinguishes_retry(tmp_path):
    from aurelia.factory_runner import FactoryRunner

    script = tmp_path / "request.txt"
    script.write_text("Title: Idempotency\\nLanguage: en\\n\\nA stable request body.", encoding="utf-8")
    runner = FactoryRunner(tmp_path / "runner")

    first, reused = runner._get_or_create_job("0007", "youtube", script)
    assert reused is False
    first.status = "RUNNING"
    same, reused = runner._get_or_create_job("7", "youtube", script)
    assert reused is True
    assert same.job_id == first.job_id

    first.status = "FAILED"
    retry, reused = runner._get_or_create_job("0007", "youtube", script)
    assert reused is False
    assert retry.job_id != first.job_id
    assert retry.metadata["retry_of"] == first.job_id


def test_runner_failure_remains_nonzero_and_failed(monkeypatch, tmp_path):
    from aurelia.factory_runner import FactoryRunner

    script = tmp_path / "request.txt"
    script.write_text("Title: Failure\\nLanguage: en\\n\\nA request that fails in the engine.", encoding="utf-8")
    runner = FactoryRunner(tmp_path / "runner")

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic stage root cause")

    monkeypatch.setattr(runner, "run_episode_production", fail)
    with pytest.raises(RuntimeError, match="synthetic stage root cause"):
        runner.execute("0008", "youtube", script)
    jobs = list(runner.jobs.values())
    assert len(jobs) == 1
    assert jobs[0].status == "FAILED"
    assert jobs[0].error == "synthetic stage root cause"


def test_edge_tts_failure_preserves_segment_diagnostics(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "aurelia.providers.audio.shutil.which",
        lambda name: "/fake/edge-tts" if name == "edge-tts" else None,
    )
    monkeypatch.setattr("aurelia.providers.audio.time.sleep", lambda _seconds: None)

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("/fake/edge-tts", 10)

    monkeypatch.setattr("aurelia.providers.audio.subprocess.run", timeout)
    provider = EdgeTTSProvider(allow_degraded=False, max_attempts=2, timeout_seconds=10)
    with pytest.raises(RuntimeError) as caught:
        provider.generate(
            "هذا مقطع اختبار",
            tmp_path / "narration.wav",
            language="ar",
            segment_index=3,
        )
    message = str(caught.value)
    assert "provider=edge-tts" in message
    assert "voice=ar-SA-HamedNeural" in message
    assert "language=ar" in message
    assert "segment=3" in message
    assert "text_sha256=" in message
    assert "attempt=2" in message
    assert "timed out" in message
    assert "validation=failed" in message
    assert "output=" in message
