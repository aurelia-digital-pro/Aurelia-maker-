"""Chat-only production entry for AURELIA Maker.

Stores original_message in job.metadata so /api/jobs/{id}/retry works.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from .factory_runner import FactoryRunner


_ARABIC_PRODUCTION_RE = re.compile(
    r'(?:\u0623\u0646\u0634\u0626|\u0623\u0646\u062a\u062c|\u0627\u0635\u0646\u0639|\u0627\u0646\u062a\u062c|\u0623\u0646\u0634\u0626\u064a|\u0627\u0628\u0646\u0650|\u0635\u0646\u0639|\u0625\u0646\u062a\u0627\u062c|\u0623\u0631\u064a\u062f|\u0623\u0631\u064a\u062f\u0643|\u0642\u0645 \u0628\u0625\u0646\u062a\u0627\u062c)',
    re.IGNORECASE,
)
_STATUS_WORDS = {
    "status", "progress", "state",
    "\u0627\u0644\u062d\u0627\u0644\u0629", "\u0627\u0644\u062a\u0642\u062f\u0645", "\u0627\u0644\u0648\u0636\u0639", "\u062d\u0627\u0644\u0629",
}


def _auto_episode_id(text: str) -> str:
    h = int(hashlib.md5(text.strip()[:200].encode("utf-8")).hexdigest(), 16)
    return str(h % 9000 + 1000)


def _detect_profile(text: str) -> str:
    lowered = text.lower()
    if re.search(r'tiktok|\u062a\u064a\u0643.?\u062a\u0648\u0643|\u0639\u0645\u0648\u062f\u064a|vertical|9:16', lowered):
        return "tiktok"
    if re.search(r'youtube|\u064a\u0648\u062a\u064a\u0648\u0628|\u0623\u0641\u0642\u064a|horizontal|16:9', lowered):
        return "youtube"
    return "both"


def handle_chat_production(runner: FactoryRunner, message: str) -> dict[str, Any]:
    """Parse one Chat message and start production.

    Stores message in job.metadata["original_message"] for retry support.
    """
    text = message.strip()
    if not text:
        return {
            "reply": (
                "\u0623\u0631\u0633\u0644 \u0631\u0633\u0627\u0644\u0629 \u062a\u062d\u062a\u0648\u064a \u0639\u0644\u0649 \u0627\u0644\u0623\u0645\u0631 \u0648\u0645\u062d\u062a\u0648\u0649 \u0627\u0644\u062d\u0644\u0642\u0629 \u0627\u0644\u0643\u0627\u0645\u0644.\n"
                "Send an episode command followed by the complete script."
            ),
            "action": "await_script",
        }

    if text.strip().lower() in _STATUS_WORDS:
        return runner.handle_chat(text)

    episode_id = runner.resolve_episode_id(text)
    is_arabic_command = bool(_ARABIC_PRODUCTION_RE.search(text))
    is_english_command = bool(
        re.search(
            r'(?:create|produce|make|generate|build)\s+(?:episode|film|movie|documentary|video)',
            text, re.IGNORECASE,
        )
    )

    if not episode_id and (is_arabic_command or is_english_command):
        episode_id = _auto_episode_id(text)

    if not episode_id:
        return {
            "reply": (
                "AURELIA \u062c\u0627\u0647\u0632\u0629.\n"
                "\u0623\u0631\u0633\u0644 \u0627\u0644\u0623\u0645\u0631 \u0648\u0645\u062d\u062a\u0648\u0649 \u0627\u0644\u062d\u0644\u0642\u0629 \u0627\u0644\u0643\u0627\u0645\u0644 \u0641\u064a \u0631\u0633\u0627\u0644\u0629 \u0648\u0627\u062d\u062f\u0629.\n\n"
                "\u0645\u062b\u0627\u0644 \u0639\u0631\u0628\u064a:\n"
                "\u0623\u0646\u0634\u0626 \u0641\u064a\u0644\u0645\u064b\u0627 \u0648\u062b\u0627\u0626\u0642\u064a\u064b\u0627 \u0633\u064a\u0646\u0645\u0627\u0626\u064a\u064b\u0627 \u0628\u0627\u0644\u0639\u0631\u0628\u064a\u0629 \u0639\u0646 \u0627\u0644\u0630\u0643\u0627\u0621 \u0627\u0644\u0627\u0635\u0637\u0646\u0627\u0639\u064a\n"
                "\u0627\u0644\u0639\u0646\u0648\u0627\u0646: \u0639\u0642\u0648\u0644 \u062e\u0641\u064a\u0629\n\u0627\u0644\u0644\u063a\u0629: ar\n\n[\u0645\u062d\u062a\u0648\u0649 \u0627\u0644\u062d\u0644\u0642\u0629 \u0647\u0646\u0627]\n\n"
                "English example:\n"
                "Create Episode 0001\nTitle: Hidden Minds\nLanguage: en\n\n[script here]"
            ),
            "action": "await_script",
        }

    profile = _detect_profile(text)

    # Strip command lines from script body
    script_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.search(
            r'^(?:create|produce|make|generate|build|\u0623\u0646\u0634\u0626|\u0623\u0646\u062a\u062c|\u0627\u0635\u0646\u0639|\u0627\u0646\u062a\u062c)'
            r'(?:\s+(?:episode|\u062d\u0644\u0642\u0629|\u0641\u064a\u0644\u0645|film|movie|documentary))?\s*\d*\s*$',
            stripped, re.IGNORECASE,
        ):
            continue
        if re.fullmatch(
            r'(?:profile|mode)\s*[:=]\s*(?:youtube|tiktok|both)',
            stripped, re.IGNORECASE,
        ):
            continue
        script_lines.append(line)

    script_text = "\n".join(script_lines).strip()

    if not script_text or len(script_text) < 50:
        return {
            "reply": (
                f"\u062a\u0645 \u062a\u062d\u062f\u064a\u062f \u0627\u0644\u062d\u0644\u0642\u0629 {episode_id}. "
                "\u0627\u0644\u0631\u062c\u0627\u0621 \u0625\u0631\u0633\u0627\u0644 \u0645\u062d\u062a\u0648\u0649 \u0627\u0644\u062d\u0644\u0642\u0629 \u0627\u0644\u0643\u0627\u0645\u0644 \u0641\u064a \u0646\u0641\u0633 \u0627\u0644\u0631\u0633\u0627\u0644\u0629.\n"
                f"Episode {episode_id} recognized. "
                "Please include the complete script in the same Chat message."
            ),
            "action": "await_script",
            "episode_id": episode_id,
            "profile": profile,
        }

    # Write script to unique temp file
    chat_input_dir = runner.output / ".chat_inputs"
    chat_input_dir.mkdir(parents=True, exist_ok=True)
    script_path = chat_input_dir / f"episode-{episode_id}-{uuid.uuid4().hex}.txt"
    script_path.write_text(script_text, encoding="utf-8")

    job = runner.execute_async(episode_id, profile=profile, script_path=script_path)

    # Store original message for retry
    job.metadata["original_message"] = message

    return {
        "reply": (
            f"\u2713 \u0627\u0644\u062d\u0644\u0642\u0629 {episode_id} \u0645\u0642\u0628\u0648\u0644\u0629. \u0628\u062f\u0623 \u0627\u0644\u0645\u0635\u0646\u0639 \u0627\u0644\u0625\u0646\u062a\u0627\u062c \u2192 FINAL MP4.\n"
            f"Episode {episode_id} accepted. Factory pipeline started \u2192 FINAL MP4."
        ),
        "action": "produce",
        "job_id": job.job_id,
        "episode_id": episode_id,
        "profile": profile,
        "script_source": "chat",
    }
