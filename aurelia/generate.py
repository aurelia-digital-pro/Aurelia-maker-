"""AURELIA Maker — canonical production interface + web server."""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aurelia.factory_runner import FactoryRunner

OUTPUT = ROOT / "output"
RUNNER = FactoryRunner(ROOT)


@click.group()
def cli():
    """AURELIA Maker — Chat → Factory → FINAL MP4."""


@cli.command()
@click.option("--script", type=click.Path(exists=True, dir_okay=False))
@click.option("--episode", required=True)
@click.option(
    "--profile",
    default="both",
    type=click.Choice(["youtube", "tiktok", "both"]),
)
def generate(script: str | None, episode: str, profile: str) -> None:
    """Execute production through the canonical Factory pipeline."""
    script_path = Path(script) if script else RUNNER.ensure_episode_script(episode.zfill(4))
    click.echo(f"FACTORY: Episode {episode.zfill(4)}")
    click.echo(f"SCRIPT: {script_path}")
    click.echo("PRODUCTION MODE: FACTORY → FINAL MP4")

    job = RUNNER.execute(episode.zfill(4), profile=profile, script_path=script_path)
    click.echo(f"STATUS: {job.status}")
    click.echo(f"FINAL MP4: {job.final_mp4}")


@cli.command()
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
def serve(host: str, port: int) -> None:
    """Launch AURELIA Maker web interface."""
    import uvicorn

    from aurelia.server import app

    click.echo(f"AURELIA Maker → http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
def chat() -> None:
    """Interactive chat REPL for AURELIA Maker."""
    click.echo("AURELIA Maker Chat — type 'Create Episode 0013' or 'quit'")
    while True:
        try:
            message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message or message.lower() in {"quit", "exit", "q"}:
            break
        result = RUNNER.handle_chat(message)
        click.echo(f"AURELIA> {result['reply']}")


@cli.command()
def status() -> None:
    """Show Factory status."""
    click.echo("FACTORY PIPELINE: CONNECTED")
    click.echo("MODE: Chat → Factory → Cinematic Production → FINAL MP4")
    click.echo("LEGACY MVP PATH: DISABLED")
    click.echo(f"OUTPUT: {OUTPUT}")


if __name__ == "__main__":
    cli()
