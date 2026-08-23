"""Ambient provider abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AmbientProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, environment: str, duration: float, output: str | Path, **kwargs: Any) -> Path:
        raise NotImplementedError

    def validate(self, output: str | Path) -> bool:
        path = Path(output)
        return path.is_file() and path.stat().st_size > 0


class SynthAmbientProvider(AmbientProvider):
    name = "numpy-ambient"

    def generate(self, environment: str, duration: float, output: str | Path, **kwargs: Any) -> Path:
        from ..ambient_synth import synthesize_ambient
        return synthesize_ambient(environment, duration, output, **kwargs)


__all__ = ["AmbientProvider", "SynthAmbientProvider"]
