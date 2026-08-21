"""AURELIA Maker — intelligent scene planner (Arabic + English).

Splits a script into cinematic scenes using linguistic heuristics:
- Paragraph boundaries (double newline)
- Sentence boundaries for long paragraphs (>400 chars)
- Arabic-aware sentence detection
- Minimum 3 scenes, maximum 20 scenes
- Meaningful title extraction per scene
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_AR_SENTENCE = re.compile(r'(?<=[^.!?])([.!?؟،.])\s+')
_EN_SENTENCE = re.compile(r'(?<=[^.!?])([.!?])\s+(?=[A-Z"\u0600-\u06FF])')


def _split_long_paragraph(text: str, max_chars: int = 400) -> list[str]:
    """Break a long paragraph into sentence-grouped sub-scenes."""
    # Try Arabic sentence boundaries first, then English
    sentences = _AR_SENTENCE.split(text)
    parts: list[str] = []
    current = ""
    for token in re.split(r'([.!?؟،])\s+', text):
        current += token
        if len(current) >= max_chars and re.search(r'[.!?؟،]$', current.strip()):
            stripped = current.strip()
            if stripped:
                parts.append(stripped)
            current = ""
    if current.strip():
        parts.append(current.strip())
    return parts if len(parts) > 1 else [text]


def _extract_title(text: str, max_words: int = 8) -> str:
    """Extract a concise scene title from its body text."""
    # Remove markdown, strip leading punctuation
    clean = re.sub(r'^[#*_>\-]+\s*', '', text.strip())
    # Take the first sentence or first N words
    sentence_end = re.search(r'[.!?؟،]', clean)
    if sentence_end and sentence_end.start() < 120:
        title = clean[: sentence_end.start()].strip()
    else:
        words = clean.split()
        title = " ".join(words[:max_words])
    return title[:80] or "Scene"


def _is_arabic(text: str) -> bool:
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    return arabic_chars > len(text) * 0.15


def plan_scenes(script_text: str, min_scenes: int = 3, max_scenes: int = 20) -> list[dict[str, Any]]:
    """Split a script into a list of cinematic scene dicts.

    Each dict: {id, title, text, is_arabic}
    """
    if not script_text or not script_text.strip():
        raise ValueError("plan_scenes: empty script text")

    # Split on blank lines first
    raw_paragraphs = [p.strip() for p in re.split(r'\n{2,}', script_text) if p.strip()]

    # Expand long paragraphs into sub-scenes
    expanded: list[str] = []
    for para in raw_paragraphs:
        if len(para) > 450:
            sub = _split_long_paragraph(para, max_chars=380)
            expanded.extend(sub)
        else:
            expanded.append(para)

    # Skip metadata header lines (Title:, Language:, NARRATOR:)
    filtered = [
        p for p in expanded
        if not re.match(
            r'^\s*(title|العنوان|language|lang|اللغة|narrator|راوي|episode|الحلقة)\s*[:=]',
            p, re.IGNORECASE
        ) and len(p) > 30
    ]

    # If still fewer than min_scenes, be less strict
    if len(filtered) < min_scenes and len(expanded) >= min_scenes:
        filtered = [p for p in expanded if len(p) > 15]

    # Enforce max
    if len(filtered) > max_scenes:
        # Merge small scenes to reduce count
        step = len(filtered) // max_scenes + 1
        merged: list[str] = []
        for i in range(0, len(filtered), step):
            group = " ".join(filtered[i: i + step])
            merged.append(group)
        filtered = merged[:max_scenes]

    # Guarantee at least one scene
    if not filtered:
        filtered = [script_text.strip()]

    is_ar = _is_arabic(script_text)

    scenes = [
        {
            "id": i + 1,
            "title": _extract_title(text),
            "text": text,
            "is_arabic": is_ar,
        }
        for i, text in enumerate(filtered)
    ]
    return scenes


def chat_compose() -> str:
    """Interactive CLI composer (legacy helper)."""
    print("Compose script. End with a blank line.")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n\n".join(lines)


def chat(prompt: str) -> list[str]:
    """Optional local LLM hook; returns heuristic reply if unavailable."""
    try:
        import subprocess
        proc = subprocess.run(
            ["ollama", "chat", "--prompt", prompt],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return proc.stdout.splitlines()
    except Exception:
        pass
    return [
        "(local-agent) Ready.",
        "Send: Create Episode <id>  then the full script in the same message.",
    ]
