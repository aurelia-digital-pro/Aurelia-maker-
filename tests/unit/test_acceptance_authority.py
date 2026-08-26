from pathlib import Path

import pytest

from aurelia.acceptance_authority import (
    PRODUCTION_COMPLETE_STATE,
    build_local_proof,
    mark_github_success,
    validate_github_success,
)


def _proof(tmp_path: Path) -> tuple[dict, Path]:
    artifact = tmp_path / "episode-0003-FINAL.mp4"
    artifact.write_bytes(b"valid-final-artifact")
    proof = build_local_proof(
        job_id="job-current",
        episode_id="0003",
        commit_sha="sha-current",
        artifact_path=artifact,
        artifact_sha256="artifact-sha",
        qc_passed=True,
        source_text_sha256="source-sha",
    )
    assert proof["acceptance_state"] == PRODUCTION_COMPLETE_STATE
    assert proof["accepted"] is False
    return proof, artifact


def _validate(proof: dict, artifact: Path, *, conclusion="success", run_id="run-1"):
    return validate_github_success(
        proof,
        current_job_id="job-current",
        current_commit_sha="sha-current",
        current_artifact=artifact,
        current_artifact_sha256="artifact-sha",
        github_run_id=run_id,
        github_conclusion=conclusion,
    )


def test_local_production_is_not_final_acceptance(tmp_path):
    proof, artifact = _proof(tmp_path)
    ok, reason = _validate(proof, artifact)
    assert ok is False
    assert "proof github_run_id" in reason
    assert proof["acceptance_state"] == PRODUCTION_COMPLETE_STATE
    assert proof["accepted"] is False


@pytest.mark.parametrize("conclusion", ["running", "failure", "cancelled", "cancelling", "timed_out", "exit 124"])
def test_non_success_github_conclusion_can_never_pass(tmp_path, conclusion):
    proof, artifact = _proof(tmp_path)
    proof = mark_github_success(proof, run_id="run-1") if conclusion == "success" else proof
    ok, reason = _validate(proof, artifact, conclusion=conclusion)
    assert ok is False
    assert "not success" in reason


def test_matching_success_is_authoritative(tmp_path):
    proof, artifact = _proof(tmp_path)
    proof = mark_github_success(proof, run_id="run-1")
    ok, reason = _validate(proof, artifact)
    assert ok is True
    assert "bound" in reason


@pytest.mark.parametrize("field,value", [("job_id", "old-job"), ("commit_sha", "old-sha"), ("github_run_id", "old-run"), ("artifact_sha256", "old-artifact")])
def test_stale_or_mismatched_proof_is_rejected(tmp_path, field, value):
    proof, artifact = _proof(tmp_path)
    proof = mark_github_success(proof, run_id="run-1")
    proof[field] = value
    ok, reason = _validate(proof, artifact)
    assert ok is False
    assert reason


def test_production_candidate_state_is_distinct_from_success():
    assert PRODUCTION_COMPLETE_STATE != "COMPLETED"


def test_workflow_requires_authoritative_gitHub_gate():
    root = Path(__file__).parents[2]
    workflow = (root / ".github/workflows/production-e2e-test.yml").read_text(encoding="utf-8")
    assert "proof['accepted'] is False" in workflow
    assert "proof.update({" in workflow
    assert "'github_conclusion': 'success'" in workflow
    assert "assert proof['commit_sha'] == os.environ['GITHUB_SHA']" in workflow
    assert "'PRODUCTION_COMPLETE', 'COMPLETED', 'FAILED', 'STOPPED'" in workflow
    assert "Production failed: {job.status}" in workflow


def test_browser_chat_opens_final_after_factory_completion_without_ci_dependency():
    root = Path(__file__).parents[2]
    app = (root / "web/app.js").read_text(encoding="utf-8")
    assert 'if (job.status === "COMPLETED")' in app
    assert 'job.status === "COMPLETED" && job.github_conclusion' not in app
    assert 'AWAITING_GITHUB_ACTIONS' not in app


def test_server_video_endpoint_requires_completed_factory_job():
    root = Path(__file__).parents[2]
    server = (root / "aurelia/server.py").read_text(encoding="utf-8")
    assert 'job.status != "COMPLETED"' in server
    assert "Video not ready" in server
    assert "GitHub Actions acceptance is required" not in server


def test_factory_success_state_is_independent_of_github(monkeypatch, tmp_path):
    from aurelia.factory_runner import FactoryRunner

    script = tmp_path / "script.txt"
    script.write_text("Title: Independent\n\nA valid production script.", encoding="utf-8")
    runner = FactoryRunner(tmp_path / "factory")

    def succeed(job, script_path, profile):
        job.status = "COMPLETED"
        job.final_mp4 = str(tmp_path / "factory" / "final.mp4")
        return {"acceptance_state": "COMPLETED", "final_mp4": job.final_mp4}

    monkeypatch.setattr(runner, "run_episode_production", succeed)
    job = runner.execute("0007", profile="youtube", script_path=script)
    assert job.status == "COMPLETED"


def test_factory_failure_remains_nonzero_and_failed(monkeypatch, tmp_path):
    from aurelia.factory_runner import FactoryRunner

    script = tmp_path / "script.txt"
    script.write_text("Title: Failure\n\nA valid production script.", encoding="utf-8")
    runner = FactoryRunner(tmp_path / "factory")

    def fail(job, script_path, profile):
        raise RuntimeError("MASTER failed")

    monkeypatch.setattr(runner, "run_episode_production", fail)
    try:
        runner.execute("0008", profile="youtube", script_path=script)
    except RuntimeError as exc:
        assert str(exc) == "MASTER failed"
    else:
        raise AssertionError("Factory failure was incorrectly converted to success")
    failed = next(iter(runner.jobs.values()))
    assert failed.status == "FAILED"
    assert failed.error == "MASTER failed"
