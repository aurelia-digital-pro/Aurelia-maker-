"""GitHub-authoritative production acceptance contract.

Local production may finish and produce a valid artifact, but that is only a
candidate result.  The final acceptance state is granted only by a successful
GitHub Actions run for the same commit, job, and artifact proof.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


PENDING_STATE = "AWAITING_GITHUB_ACTIONS"
PRODUCTION_COMPLETE_STATE = "PRODUCTION_COMPLETE"
SUCCESS_STATE = "COMPLETED"
FAILURE_STATES = {"FAILED", "CANCELLED", "CANCELLING"}


def current_commit_sha(root: str | Path) -> str:
    """Return the commit being executed, preferring GitHub's immutable SHA."""
    configured = os.environ.get("GITHUB_SHA", "").strip()
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def github_authoritative_run() -> bool:
    """Whether this process is the production process inside GitHub Actions."""
    return (
        os.environ.get("AURELIA_GITHUB_AUTHORITATIVE") == "1"
        and os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
        and bool(os.environ.get("GITHUB_SHA", "").strip())
        and bool(os.environ.get("GITHUB_RUN_ID", "").strip())
    )


def build_local_proof(
    *,
    job_id: str,
    episode_id: str,
    commit_sha: str,
    artifact_path: str | Path,
    artifact_sha256: str,
    qc_passed: bool,
    source_text_sha256: str,
) -> dict[str, Any]:
    """Create a non-success proof record for a locally completed production."""
    return {
        "acceptance_state": PRODUCTION_COMPLETE_STATE,
        "accepted": False,
        "production_completed": True,
        "job_id": job_id,
        "episode_id": episode_id,
        "commit_sha": commit_sha,
        "artifact": str(artifact_path),
        "artifact_sha256": artifact_sha256,
        "source_text_sha256": source_text_sha256,
        "qc_passed": bool(qc_passed),
        "github_run_id": "",
        "github_conclusion": "",
    }


def validate_github_success(
    proof: dict[str, Any],
    *,
    current_job_id: str,
    current_commit_sha: str,
    current_artifact: str | Path,
    current_artifact_sha256: str,
    github_run_id: str,
    github_conclusion: str,
) -> tuple[bool, str]:
    """Validate an attestation without trusting an artifact by itself.

    The function is deliberately strict: a running, failed, cancelled, stale,
    or exit-124 run can never produce a successful acceptance state.
    """
    if str(github_conclusion).lower() != "success":
        return False, f"GitHub Actions conclusion is not success: {github_conclusion!r}"
    if not github_run_id:
        return False, "GitHub Actions run id is missing"
    if proof.get("job_id") != current_job_id:
        return False, "proof job_id does not match the current job"
    if proof.get("commit_sha") != current_commit_sha:
        return False, "proof commit_sha does not match the current commit"
    if str(proof.get("github_run_id", "")) != str(github_run_id):
        return False, "proof github_run_id does not match the current run"
    if proof.get("github_conclusion") != "success":
        return False, "proof does not record a successful GitHub conclusion"
    if not proof.get("production_completed"):
        return False, "local production was not completed"
    if not proof.get("qc_passed") or proof.get("accepted") is not True:
        return False, "proof is not QC-accepted"
    if proof.get("artifact_sha256") != current_artifact_sha256:
        return False, "artifact hash does not match the current artifact"
    if str(Path(proof.get("artifact", "")).resolve()) != str(Path(current_artifact).resolve()):
        return False, "proof artifact path does not match the current artifact"
    return True, "GitHub Actions success is bound to the current production proof"


def mark_github_success(
    proof: dict[str, Any], *, run_id: str, conclusion: str = "success"
) -> dict[str, Any]:
    """Return a copied proof marked accepted only for a successful run."""
    if conclusion != "success":
        raise ValueError(f"Cannot mark proof accepted for conclusion={conclusion!r}")
    updated = dict(proof)
    updated.update(
        {
            "acceptance_state": SUCCESS_STATE,
            "accepted": True,
            "github_run_id": str(run_id),
            "github_conclusion": conclusion,
        }
    )
    return updated
