"""Visual provider abstraction and runtime adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class VisualProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, prompt: str, output: str | Path, **kwargs: Any) -> Path:
        raise NotImplementedError

    def validate(self, output: str | Path) -> bool:
        path = Path(output)
        return path.is_file() and path.stat().st_size > 0


class PollinationsProvider(VisualProvider):
    name = "pollinations"

    def generate(self, prompt: str, output: str | Path, **kwargs: Any) -> Path:
        from ..visual_api import generate_via_api
        import hashlib
        seed = int.from_bytes(hashlib.sha256(prompt.encode()).digest()[:4], "big")
        ok, _backend = generate_via_api(
            prompt, seed, int(kwargs.get("width", 512)), int(kwargs.get("height", 512)),
            Path(output), logger=kwargs.get("logger")
        )
        if not ok:
            raise RuntimeError("Pollinations and configured cloud visual providers failed")
        return Path(output)


class PillowProvider(VisualProvider):
    name = "pillow"

    def generate(self, prompt: str, output: str | Path, **kwargs: Any) -> Path:
        from ..ai_visual import generate_scene_image
        return Path(generate_scene_image(
            int(kwargs.get("scene_index", 0)),
            str(kwargs.get("title", "")),
            prompt,
            output,
            direction=kwargs.get("direction"),
            width=int(kwargs.get("width", 512)),
            height=int(kwargs.get("height", 512)),
        ))


def best_available() -> VisualProvider:
    return PollinationsProvider()


__all__ = ["VisualProvider", "PollinationsProvider", "PillowProvider", "best_available"]
