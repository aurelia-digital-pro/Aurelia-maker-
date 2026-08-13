"""AURELIA Maker — canonical Factory production entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aurelia.production_pipeline import build_production_pipeline


OUTPUT = ROOT / "output"


@click.group()
def cli():
    """AURELIA Maker canonical production interface."""


@cli.command()
@click.option("--script", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--episode", required=True)
@click.option(
    "--profile",
    default="both",
    type=click.Choice(["youtube", "tiktok", "both"]),
)
def generate(script: str, episode: str, profile: str) -> None:
    """Execute production through the canonical Factory pipeline."""
    pipeline = build_production_pipeline(OUTPUT / f"episode-{episode}")

    text = Path(script).read_text(encoding="utf-8")

    run = pipeline.orchestrator.create_run(
        project=f"episode-{episode}",
        metadata={
            "script": str(Path(script).resolve()),
            "profile": profile,
            "mode": "factory",
        },
    )

    print(f"FACTORY RUN CREATED: {getattr(run, "id", getattr(run, "run_id", "unknown"))}")
    print(f"STAGES: {len(pipeline.stages)}")
    print("PRODUCTION MODE: FACTORY")
    results = pipeline.execute_production(
        project=f"episode-{episode}",
        input_data={
            "script": str(Path(script).resolve()),
            "episode": episode,
            "profile": profile,
        },
        processors=pipeline.build_real_processors(),
        validators={
            "SCRIPT": lambda result: bool(
                result
                and result.get("script")
                and Path(result["script"]).exists()
                and result.get("text", "").strip()
            )
        },
        run_id=getattr(run, "id", getattr(run, "run_id", None)),
    )
    print(f"FACTORY STAGES EXECUTED: {len(results)}")


@cli.command()
def status() -> None:
    """Show canonical Factory status."""
    pipeline = build_production_pipeline(OUTPUT / "_factory_status")
    print("FACTORY PIPELINE: CONNECTED")
    print(f"STAGES: {len(pipeline.stages)}")
    print("LEGACY MVP PATH: NOT USED")


if __name__ == "__main__":
    cli()
