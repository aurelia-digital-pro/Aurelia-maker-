from pathlib import Path

import pytest

from aurelia.acceptance_authority import (
    PRODUCTION_COMPLETE_STATE,
    PENDING_STATE,
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


def test_pending_state_constant_is_distinct_from_success():
    assert PENDING_STATE != "COMPLETED"


def test_workflow_requires_authoritative_gitHub_gate():
    root = Path(__file__).parents[2]
    workflow = (root / ".github/workflows/production-e2e-test.yml").read_text(encoding="utf-8")
    assert 'AURELIA_GITHUB_AUTHORITATIVE: "1"' in workflow
    assert "proof['accepted'] is False" in workflow
    assert "proof.update({" in workflow
    assert "'github_conclusion': 'success'" in workflow
    assert "assert proof['commit_sha'] == os.environ['GITHUB_SHA']" in workflow


def test_browser_chat_only_opens_final_after_github_success():
    root = Path(__file__).parents[2]
    app = (root / "web/app.js").read_text(encoding="utf-8")
    guard = 'job.status === "COMPLETED" && job.github_conclusion === "success" && job.github_run_id'
    assert guard in app
    assert 'job.status === "AWAITING_GITHUB_ACTIONS"' in app


def test_server_video_endpoint_requires_completed_job_and_github_message():
    root = Path(__file__).parents[2]
    server = (root / "aurelia/server.py").read_text(encoding="utf-8")
    assert 'job.status != "COMPLETED"' in server
    assert "GitHub Actions acceptance is required" in server
