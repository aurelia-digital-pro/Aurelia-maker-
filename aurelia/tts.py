"""Canonical narration API for AURELIA Maker.

Production narration uses :class:`EdgeTTSProvider` exclusively. The small
espeak adapter remains available only for explicit degraded, non-production
use through ``EspeakProvider``; it is never selected silently by production.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_AR_RE = re.compile(r"[\u0600-\u06FF]")


def _is_arabic(text: str) -> bool:
    return len(_AR_RE.findall(text)) > len(text) * 0.15


def _detect_lang(text: str) -> str:
    return "ar" if _is_arabic(text) else "en"


def _try_espeak(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt the explicit degraded local adapter. Returns True on success."""
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        return False
    try:
        if lang == "ar":
            voices = (("ar+m1", "120", "45"), ("ar", "120", "45"))
        else:
            voices = (
                ("en-us+f3", "148", "52"),
                ("en-gb+f4", "145", "50"),
                ("en", "145", "50"),
            )
        for voice, speed, pitch in voices:
            result = subprocess.run(
                [
                    espeak,
                    "-s", speed,
                    "-p", pitch,
                    "-v", voice,
                    "-w", str(out_wav),
                    text,
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if result.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 500:
                return True
    except Exception:
        pass
    return False


def synthesize_script(
    text: str,
    out_wav: Path,
    *,
    language: str = "auto",
    voice: str | None = None,
    allow_degraded: bool | None = None,
) -> dict:
    """Synthesize narration through the strict provider-aware production path.

    Edge Neural TTS is the default for every language. A local espeak path is
    available only when explicitly requested with ``allow_degraded=True`` (or
    ``AURELIA_ALLOW_DEGRADED_TTS=1`` outside production mode); no silent
    substitution is permitted for production acceptance.
    """
    from .providers.audio import EdgeTTSProvider

    provider = EdgeTTSProvider(voice=voice, allow_degraded=allow_degraded)
    output = provider.generate(text, Path(out_wav), language=language)
    return dict(provider.provenance)


__all__ = ["synthesize_script", "_detect_lang", "_try_espeak"]
