"""AURELIA Maker — final real-video acceptance gate."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .production_pipeline import build_production_pipeline
from .production_contract import PRODUCTION_STAGES
from .qc import process_qc


def run_final_acceptance(
    episode_id: str,
    script_path: str | Path,
    output: str | Path = "runs/acceptance/final.mp4",
) -> dict[str, object]:
    """Run the real end-to-end video proof for one explicitly selected episode."""
    if not episode_id or not episode_id.isdigit() or len(episode_id) != 4:
        raise ValueError("episode_id must be an explicit four-digit value")

    output_path = Path(output)
    script = Path(script_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    expected_name = f"episode-{episode_id}.txt"
    if script.name != expected_name:
        raise ValueError(
            f"Episode/script mismatch: episode_id {episode_id} requires {expected_name}, got {script.name}"
        )
    if not script.exists():
        raise FileNotFoundError(script)

    pipeline = build_production_pipeline(output_path.parent)
    pipeline.validate()
    if tuple(pipeline.stages) != PRODUCTION_STAGES:
        raise RuntimeError("Canonical production stage contract mismatch")

    from scripts.real_video_acceptance import main as run_real_video_acceptance

    previous = list(sys.argv)
    try:
        sys.argv = [
            "real_video_acceptance",
            "--episode", episode_id,
            "--script", str(script),
            "--output", str(output_path),
        ]
        run_real_video_acceptance()
    finally:
        sys.argv = previous

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("FINAL MP4 was not produced")

    qc = process_qc({"video": str(output_path)})
    return {
        "accepted": True,
        "production": True,
        "episode_generated": True,
        "episode_id": episode_id,
        "script": str(script),
        "final_mp4": str(output_path),
        "qc": qc,
        "stages": len(PRODUCTION_STAGES),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run final acceptance for an explicitly selected episode")
    parser.add_argument("--episode", required=True, help="Exact four-digit episode id")
    parser.add_argument("--script", required=True, help="Exact episode script path")
    parser.add_argument("--output", default="runs/acceptance/final.mp4")
    args = parser.parse_args()

    result = run_final_acceptance(args.episode, args.script, args.output)
    assert result["accepted"] is True
    assert result["production"] is True
    assert result["episode_generated"] is True
    print("FINAL CINEMATIC PRODUCTION FACTORY: ACCEPTED")
    print(f"EPISODE: {result['episode_id']}")
    print(f"FINAL MP4: {result['final_mp4']}")
    print(f"QC: {result['qc']['status']}")
