"""Chat-only production entry for AURELIA Maker."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .factory_runner import FactoryRunner


def handle_chat_production(runner: FactoryRunner, message: str) -> dict[str, Any]:
    """Parse one Chat message and start production from its supplied content only."""
    text = message.strip()
    if not text:
        return {"reply": "Send an episode command followed by the complete script.", "action": "await_script"}

    lowered = text.lower().strip()
    if lowered in {"status", "progress", "state", "????"}:
        return runner.handle_chat(text)

    episode_id = runner.resolve_episode_id(text)
    if not episode_id:
        return {
            "reply": "AURELIA Maker ready. Send the episode command and the complete episode content in Chat.",
            "action": "await_script",
        }

    profile = "both"
    profile_match = re.search(r"(?:profile|mode)\s*[:=]\s*(youtube|tiktok|both)", lowered)
    if profile_match:
        profile = profile_match.group(1)

    script_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.search(
            r"(?:create|produce|make|generate|build)\s+episode\s+\d{1,4}",
            stripped,
            re.IGNORECASE,
        ):
            continue
        if re.fullmatch(
            r"(?:profile|mode)\s*[:=]\s*(?:youtube|tiktok|both)",
            stripped,
            re.IGNORECASE,
        ):
            continue
        script_lines.append(line)

    script_text = "\n".join(script_lines).strip()
    if not script_text:
        return {
            "reply": f"Episode {episode_id} is recognized. Paste the complete episode content in the same Chat message.",
            "action": "await_script",
            "episode_id": episode_id,
            "profile": profile,
        }

    # This file is created uniquely from the current Chat message. Nothing in
    # scripts/ is consulted or used as an automatic episode template.
    chat_input_dir = runner.output / ".chat_inputs"
    chat_input_dir.mkdir(parents=True, exist_ok=True)
    script_path = chat_input_dir / f"episode-{episode_id}-{uuid.uuid4().hex}.txt"
    script_path.write_text(script_text, encoding="utf-8")

    job = runner.execute_async(episode_id, profile=profile, script_path=script_path)
    return {
        "reply": f"Episode {episode_id} accepted from Chat. Factory pipeline started — FINAL MP4.",
        "action": "produce",
        "job_id": job.job_id,
        "episode_id": episode_id,
        "profile": profile,
        "script_source": "chat",
    }
