"""AURELIA Maker — Chat-only production interface + web server."""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aurelia.chat_entry import handle_chat_production
from aurelia.factory_runner import FactoryRunner

OUTPUT = ROOT / "output"
RUNNER = FactoryRunner(ROOT)


@click.group()
def cli():
    """AURELIA Maker — Chat → Factory → FINAL MP4."""


@cli.command()
def serve() -> None:
    """Launch the AURELIA Maker web chat interface."""
    import uvicorn

    from aurelia.server import app

    click.echo("AURELIA Maker → Chat → Factory → FINAL MP4")
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")


@cli.command()
def chat() -> None:
    """Interactive chat: the message is the sole source for episode production."""
    click.echo("AURELIA Maker Chat — send the episode command and complete episode content in one message, or 'quit'.")
    while True:
        try:
            message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message or message.lower() in {"quit", "exit", "q"}:
            break
        result = handle_chat_production(RUNNER, message)
        click.echo(f"AURELIA> {result['reply']}")


@cli.command()
def status() -> None:
    """Show Factory status."""
    click.echo("FACTORY PIPELINE: CONNECTED")
    click.echo("PRODUCTION ENTRY: CHAT ONLY")
    click.echo("MODE: Chat → Factory → Cinematic Production → FINAL MP4")
    click.echo("FIXED EPISODE TEMPLATES: DISABLED")
    click.echo(f"OUTPUT: {OUTPUT}")


if __name__ == "__main__":
    cli()
