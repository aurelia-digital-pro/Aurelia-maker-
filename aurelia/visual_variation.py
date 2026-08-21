"""AURELIA Maker — visual generation with production-run variation.

Wraps ai_visual.generate_scene_image() and adds:

1. variation_seed() — adds run-level variation so the same script text
   does NOT produce identical images across different production runs.
   Content identity is preserved; visual output varies.

2. generate_scene_image_varied() — drop-in replacement that accepts
   visual_note (from ShotSpec) and run_id (from EpisodeProduction)
   to produce shot-specific, run-varied visual output.

The underlying ai_visual._ENV_SPECS and _STYLE_RENDERERS are preserved
as the procedural fallback when Stable Diffusion is unavailable.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from .ai_visual import generate_scene_image as _base_generate


def variation_seed(base_seed: int, run_id: str = "") -> int:
    """Add production-run variation to prevent identical visual outputs.

    Separates content identity (title + text + environment -> base_seed)
    from visual variation (run_id). The same content produces different
    visuals across different production runs.

    Args:
        base_seed: deterministic seed from content identity
        run_id: unique production-run identifier (job_id, episode_id, timestamp)

    Returns:
        New seed with run-level variation applied.
    """
    if not run_id:
        run_id = str(int(time.time() * 1000) % 99991)
    combined = f"{base_seed}|variation|{run_id}"
    return int(hashlib.md5(combined.encode("utf-8")).hexdigest(), 16) % (2**31 - 1)


def generate_scene_image_varied(
    scene_index: int,
    title: str,
    description: str,
    output: str | Path,
    *,
    direction: dict[str, Any] | None = None,
    width: int = 512,
    height: int = 512,
    visual_note: str = "",
    run_id: str = "",
) -> Path:
    """Generate a scene image with shot-specific context and run-level variation.

    Advantages over base generate_scene_image():
    - visual_note: enriches description with shot-specific framing/function context,
      so different shots of the same scene receive distinct image generation prompts
    - run_id: prevents identical outputs across different production runs of the
      same script, by mixing run identity into the description before seeding

    Falls back to ai_visual.generate_scene_image() which tries:
    1. Stable Diffusion v1.5 (if diffusers + torch installed)
    2. CinematicPillow procedural renderer (always available)

    Args:
        scene_index: zero-based scene index
        title: scene title
        description: scene body text
        output: output path for generated image
        direction: directing plan dict (environment, camera, depth, motion, lighting)
        width: image width in pixels
        height: image height in pixels
        visual_note: short shot-specific description (from ShotSpec.visual_note)
        run_id: unique production run identifier for visual variation
    """
    enriched = description
    if visual_note:
        enriched = f"{description} | {visual_note}"
    if run_id:
        enriched = f"{enriched} [run:{run_id[:12]}]"

    return _base_generate(
        scene_index=scene_index,
        title=title,
        description=enriched,
        output=output,
        direction=direction,
        width=width,
        height=height,
    )


__all__ = ["variation_seed", "generate_scene_image_varied"]
