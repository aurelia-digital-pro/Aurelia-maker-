"""Audio/TTS provider abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AudioProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, text: str, output: str | Path, language: str = "en", **kwargs: Any) -> Path:
        raise NotImplementedError

    def validate(self, output: str | Path) -> bool:
        path = Path(output)
        return path.is_file() and path.stat().st_size > 0


class EdgeTTSProvider(AudioProvider):
    """Compatibility name for the repository's local auto-detecting TTS chain.

    The current project does not call Microsoft Edge TTS.  Its production TTS
    implementation is offline and selects Piper/Kokoro/espeak/pyttsx3 based on
    what is installed, so this adapter deliberately delegates without passing
    unsupported backend arguments.
    """

    name = "offline-auto"

    def generate(self, text: str, output: str | Path, language: str = "en", **kwargs: Any) -> Path:
        from ..tts import synthesize_script
        synthesize_script(text, Path(output))
        return Path(output)


class EspeakProvider(AudioProvider):
    """Explicit espeak-ng adapter used when deterministic local speech is needed."""

    name = "espeak-ng"

    def generate(self, text: str, output: str | Path, language: str = "en", **kwargs: Any) -> Path:
        from ..tts import _detect_lang, _try_espeak
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not text or not text.strip() or not _try_espeak(text, destination, _detect_lang(text)):
            raise RuntimeError("espeak-ng TTS failed to produce a WAV artifact")
        return destination


def best_available() -> AudioProvider:
    return EdgeTTSProvider()


__all__ = ["AudioProvider", "EdgeTTSProvider", "EspeakProvider", "best_available"]
