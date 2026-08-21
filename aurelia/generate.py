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
    """◈  AURELIA Maker — Chat → Factory → FINAL MP4.

    Commands:

      serve    — launch the web chat interface (http://127.0.0.1:8765)

      chat     — interactive CLI chat

      produce  — produce one episode from a script file

      status   — print factory status

    Quick start:

        python -m aurelia.generate serve

    Then open http://127.0.0.1:8765 and send:

        أنشئ فيلمًا وثائقيًا بالعربية عن ...
        العنوان: ...
        اللغة: ar

        [script content here]
    """


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8765, type=int, help="Bind port")
def serve(host: str, port: int) -> None:
    """Launch the AURELIA Maker web chat interface."""
    import uvicorn
    from aurelia.server import app

    click.echo(f"AURELIA Maker ◈  http://{host}:{port}")
    click.echo("Chat → Factory → Cinematic Production → FINAL MP4")
    click.echo("Press Ctrl+C to stop.")
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
def chat() -> None:
    """Interactive CLI chat (Arabic and English supported)."""
    click.echo(
        "AURELIA Maker Chat \u25c8\n"
        "أرسل الأمر + محتوى الحلقة في رسالة واحدة.\n"
        "Send: Episode ID + Title + Language + complete script in one message.\n"
        "Type 'quit' to exit.\n"
    )
    while True:
        try:
            message = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message or message.lower() in {"quit", "exit", "q"}:
            break
        result = handle_chat_production(RUNNER, message)
        click.echo(f"AURELIA> {result['reply']}")
        if result.get("action") == "produce" and result.get("job_id"):
            _wait_for_job(RUNNER, result["job_id"])


@cli.command()
@click.option("--script", required=True, type=click.Path(exists=True), help="Path to script file")
@click.option("--episode", default=None, help="Episode ID (auto-generated if omitted)")
@click.option("--profile", default="both", type=click.Choice(["youtube", "tiktok", "both"]), help="Output profile")
def produce(script: str, episode: str | None, profile: str) -> None:
    """Produce one episode from a script file (Arabic or English)."""
    import hashlib
    from pathlib import Path as P

    script_path = P(script).resolve()
    text = script_path.read_text(encoding="utf-8").strip()

    if not episode:
        # Auto-generate from content hash
        h = int(hashlib.md5(text[:200].encode("utf-8")).hexdigest(), 16)
        episode = str(h % 9000 + 1000)

    click.echo(f"AURELIA Maker ◈  Episode {episode}  Profile: {profile}")
    click.echo(f"Script: {script_path}")

    # Inject episode command so chat_entry can parse it
    message = f"Create Episode {episode}\n{text}"
    result = handle_chat_production(RUNNER, message)
    click.echo(f"AURELIA> {result['reply']}")

    if result.get("action") == "produce" and result.get("job_id"):
        _wait_for_job(RUNNER, result["job_id"])
    elif result.get("action") != "produce":
        click.echo(f"[WARN] Unexpected response: {result}")
        raise SystemExit(1)


@cli.command(name="status")
def status_cmd() -> None:
    """Print factory status and available outputs."""
    click.echo("AURELIA Maker ◈")
    click.echo("FACTORY PIPELINE: CONNECTED")
    click.echo("PRODUCTION ENTRY: CHAT ONLY (Arabic + English)")
    click.echo(f"OUTPUT: {OUTPUT}")

    outputs = sorted(OUTPUT.glob("episode-*/job-*/delivery/*-FINAL.mp4")) if OUTPUT.exists() else []
    if outputs:
        click.echo(f"\nAvailable Final MP4s ({len(outputs)}):")
        for f in outputs[-10:]:
            click.echo(f"  {f}")
    else:
        click.echo("\nNo Final MP4s produced yet.")


def _wait_for_job(runner: FactoryRunner, job_id: str) -> None:
    """Poll and display progress for an async production job."""
    import time
    last_log_count = 0
    while True:
        job = runner.jobs.get(job_id)
        if job is None:
            click.echo("[ERROR] Job disappeared.")
            break
        # Print new log lines
        logs = job.logs
        for line in logs[last_log_count:]:
            click.echo(line)
        last_log_count = len(logs)

        if job.status == "COMPLETED":
            click.echo(f"\n[DONE] FINAL MP4: {job.final_mp4}")
            break
        elif job.status == "FAILED":
            click.echo(f"\n[FAILED] {job.error}")
            raise SystemExit(1)
        time.sleep(1.5)


if __name__ == "__main__":
    cli()
