"""Music provider abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MusicProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, duration: float, output: str | Path, emotional_arc: list[str] | None = None, **kwargs: Any) -> Path:
        raise NotImplementedError

    def validate(self, output: str | Path) -> bool:
        path = Path(output)
        return path.is_file() and path.stat().st_size > 0


class CinematicMusicProvider(MusicProvider):
    name = "numpy-pydub-cinematic"

    def generate(self, duration: float, output: str | Path, emotional_arc: list[str] | None = None, **kwargs: Any) -> Path:
        from ..music_engine import generate_cinematic_music
        return Path(generate_cinematic_music(duration, output, emotional_arc=emotional_arc or [], **kwargs))


__all__ = ["MusicProvider", "CinematicMusicProvider"]
