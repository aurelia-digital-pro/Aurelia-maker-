"""Disabled legacy visual API; canonical production uses local AI visuals."""

from pathlib import Path


def generate_scene_image(scene_index: int, title: str, text: str, output: str | Path, **kwargs) -> Path:
    raise RuntimeError("Legacy procedural scene generation is disabled; use the local AI visual backend")


def generate_title_card(title: str, subtitle: str, output: str | Path, **kwargs) -> Path:
    raise RuntimeError("Legacy title-card generation is disabled in production")


__all__ = ["generate_scene_image", "generate_title_card"]
