"""Visual continuity constraints shared across shots and episodes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContinuityContext:
    palette: list[str] = field(default_factory=list)
    environment_description: str = ""
    lighting_key: str = ""
    character_anchors: dict[str, str] = field(default_factory=dict)

    def as_prompt(self) -> str:
        parts: list[str] = []
        if self.environment_description:
            parts.append(f"continuity environment: {self.environment_description}")
        if self.palette:
            parts.append(f"continuity palette: {', '.join(self.palette)}")
        if self.lighting_key:
            parts.append(f"continuity lighting: {self.lighting_key}")
        if self.character_anchors:
            anchors = "; ".join(f"{k}: {v}" for k, v in self.character_anchors.items())
            parts.append(f"continuity character anchors: {anchors}")
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "palette": list(self.palette),
            "environment_description": self.environment_description,
            "lighting_key": self.lighting_key,
            "character_anchors": dict(self.character_anchors),
        }


__all__ = ["ContinuityContext"]
