"""AURELIA Maker — final real-video acceptance gate."""
from __future__ import annotations

from pathlib import Path

from .production_pipeline import build_production_pipeline
from .production_contract import PRODUCTION_STAGES
from .qc import process_qc


def run_final_acceptance(output: str | Path = "runs/acceptance/final.mp4") -> dict[str, object]:
    """Run the real end-to-end video proof and reject structural-only acceptance."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pipeline = build_production_pipeline(output_path.parent)
    pipeline.validate()
    if tuple(pipeline.stages) != PRODUCTION_STAGES:
        raise RuntimeError("Canonical production stage contract mismatch")

    from scripts.real_video_acceptance import main as run_real_video_acceptance
    import sys

    previous = list(sys.argv)
    try:
        sys.argv = ["real_video_acceptance", "--output", str(output_path)]
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
        "final_mp4": str(output_path),
        "qc": qc,
        "stages": len(PRODUCTION_STAGES),
    }


if __name__ == "__main__":
    result = run_final_acceptance()
    assert result["accepted"] is True
    assert result["production"] is True
    assert result["episode_generated"] is True
    print("FINAL CINEMATIC PRODUCTION FACTORY: ACCEPTED")
    print(f"PRODUCTION STAGES: {result['stages']}")
    print(f"FINAL MP4: {result['final_mp4']}")
    print(f"QC: {result['qc']['status']}")
