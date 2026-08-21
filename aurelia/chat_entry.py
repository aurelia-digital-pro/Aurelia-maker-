"""Chat-only production entry for AURELIA Maker.

Supports Arabic and English commands:
  Arabic:  أنشئ فيلمًا وثائقيًا سينمائيًا بالعربية عن ...
           أنتج حلقة 0013 ...
  English: Create Episode 0013 ...
           Produce episode 42 ...

If no episode number is provided, one is auto-generated from the title hash.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from .factory_runner import FactoryRunner


_ARABIC_PRODUCTION_RE = re.compile(
    r'(?:أنشئ|أنتج|اصنع|انتج|أنشئي|ابنِ|صنع|إنتاج|أريد|أريدك|قم بإنتاج)',
    re.IGNORECASE,
)
_STATUS_WORDS = {
    "status", "progress", "state",
    "الحالة", "التقدم", "الوضع", "حالة",
}


def _auto_episode_id(text: str) -> str:
    """Generate a stable 4-digit episode ID from the title/content hash."""
    h = int(hashlib.md5(text.strip()[:200].encode("utf-8")).hexdigest(), 16)
    return str(h % 9000 + 1000)  # 1000–9999


def _detect_profile(text: str) -> str:
    lowered = text.lower()
    if re.search(r'tiktok|تيك.?توك|عمودي|vertical|9:16', lowered):
        return "tiktok"
    if re.search(r'youtube|يوتيوب|أفقي|horizontal|16:9', lowered):
        return "youtube"
    return "both"


def handle_chat_production(runner: FactoryRunner, message: str) -> dict[str, Any]:
    """Parse one Chat message and start production from its supplied content only."""
    text = message.strip()
    if not text:
        return {
            "reply": (
                "أرسل رسالة تحتوي على الأمر ومحتوى الحلقة الكامل.\n"
                "Send an episode command followed by the complete script."
            ),
            "action": "await_script",
        }

    # Status query
    if text.strip().lower() in _STATUS_WORDS:
        return runner.handle_chat(text)

    # Detect episode ID (from text or auto-generate)
    episode_id = runner.resolve_episode_id(text)
    is_arabic_command = bool(_ARABIC_PRODUCTION_RE.search(text))
    is_english_command = bool(
        re.search(
            r'(?:create|produce|make|generate|build)\s+(?:episode|film|movie|documentary|video)',
            text, re.IGNORECASE,
        )
    )

    # If no explicit episode ID but has production intent, auto-generate
    if not episode_id and (is_arabic_command or is_english_command):
        episode_id = _auto_episode_id(text)

    if not episode_id:
        return {
            "reply": (
                "AURELIA جاهزة.\n"
                "أرسل الأمر ومحتوى الحلقة الكامل في رسالة واحدة.\n\n"
                "مثال عربي:\n"
                "أنشئ فيلمًا وثائقيًا سينمائيًا بالعربية عن الذكاء الاصطناعي\n"
                "العنوان: عقول خفية\nاللغة: ar\n\n[محتوى الحلقة هنا]\n\n"
                "English example:\n"
                "Create Episode 0001\nTitle: Hidden Minds\nLanguage: en\n\n[script here]"
            ),
            "action": "await_script",
        }

    profile = _detect_profile(text)

    # Strip command line from script body
    script_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        # Skip pure command lines
        if re.search(
            r'^(?:create|produce|make|generate|build|أنشئ|أنتج|اصنع|انتج)'
            r'(?:\s+(?:episode|حلقة|فيلم|film|movie|documentary))?\s*\d*\s*$',
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
                f"تم تحديد الحلقة {episode_id}. "
                "الرجاء إرسال محتوى الحلقة الكامل في نفس الرسالة.\n"
                f"Episode {episode_id} recognized. "
                "Please include the complete script in the same Chat message."
            ),
            "action": "await_script",
            "episode_id": episode_id,
            "profile": profile,
        }

    # Write script to unique temp file (never reads from scripts/ directory)
    chat_input_dir = runner.output / ".chat_inputs"
    chat_input_dir.mkdir(parents=True, exist_ok=True)
    script_path = chat_input_dir / f"episode-{episode_id}-{uuid.uuid4().hex}.txt"
    script_path.write_text(script_text, encoding="utf-8")

    job = runner.execute_async(episode_id, profile=profile, script_path=script_path)
    return {
        "reply": (
            f"✓ الحلقة {episode_id} مقبولة. بدأ المصنع الإنتاج → FINAL MP4.\n"
            f"Episode {episode_id} accepted. Factory pipeline started → FINAL MP4."
        ),
        "action": "produce",
        "job_id": job.job_id,
        "episode_id": episode_id,
        "profile": profile,
        "script_source": "chat",
    }
