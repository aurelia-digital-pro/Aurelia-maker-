"""AURELIA Maker — final Cinematic Production Factory acceptance gate."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .factory import build_canonical_production_pipeline
from .production_contract import PRODUCTION_STAGES


def run_final_acceptance() -> dict[str, object]:
    """Verify that the complete factory is structurally ready."""

    with TemporaryDirectory() as directory:
        root = Path(directory)

        pipeline = build_canonical_production_pipeline(root)

        pipeline.validate()

        if pipeline.stages != PRODUCTION_STAGES:
            raise RuntimeError(
                "Canonical production stage contract mismatch"
            )

        if not pipeline.stages:
            raise RuntimeError(
                "Production pipeline is empty"
            )

        return {
            "accepted": True,
            "stages": len(pipeline.stages),
            "production": False,
            "episode_generated": False,
        }


if __name__ == "__main__":
    result = run_final_acceptance()

    assert result["accepted"] is True
    assert result["production"] is False
    assert result["episode_generated"] is False

    print("FINAL CINEMATIC PRODUCTION FACTORY: ACCEPTED")
    print(f"PRODUCTION STAGES: {result['stages']}")
    print("EPISODE GENERATED: NO")
