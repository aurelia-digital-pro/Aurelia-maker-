"""Deterministic depth-map construction for cinematic 2.5D treatments.

The repository does not ship a monocular-depth model.  This module therefore
uses a transparent, deterministic saliency heuristic rather than claiming
metric depth: luminance, local edge energy, and a soft center prior are blended
into an 8-bit grayscale depth map.  The map is suitable for controlled
parallax compositing and is always accompanied by explicit provenance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


DEPTH_METHOD = "deterministic-saliency-v1"


def build_depth_map(source: str | Path, output: str | Path) -> Path:
    """Create a deterministic grayscale depth/saliency map for ``source``."""
    source_path = Path(source)
    output_path = Path(output)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        image = image.convert("RGB")
        gray = ImageOps.grayscale(image)
        luminance = np.asarray(gray, dtype=np.float32) / 255.0
        edges = np.asarray(gray.filter(ImageFilter.FIND_EDGES), dtype=np.float32) / 255.0
        h, w = luminance.shape
        yy, xx = np.mgrid[0:h, 0:w]
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
        radius = np.sqrt(((xx - cx) / max(w, 1)) ** 2 + ((yy - cy) / max(h, 1)) ** 2)
        center_prior = np.clip(1.0 - radius * 1.65, 0.0, 1.0)
        depth = (0.48 * center_prior) + (0.32 * luminance) + (0.20 * edges)
        depth -= float(depth.min())
        peak = float(depth.max())
        if peak > 0:
            depth /= peak
        result = Image.fromarray(np.uint8(np.clip(depth * 255.0, 0.0, 255.0)), mode="L")
        result.save(output_path, "PNG", optimize=True)
    return output_path


def depth_provenance(source: str | Path, artifact: str | Path) -> dict[str, Any]:
    """Return auditable provenance for a generated heuristic depth artifact."""
    return {
        "method": DEPTH_METHOD,
        "source": str(Path(source).resolve()),
        "artifact": str(Path(artifact).resolve()),
        "metric_depth": False,
        "purpose": "controlled_2.5d_parallax",
    }


def process_depth(data: dict[str, Any]) -> dict[str, Any]:
    output = data.get("output")
    source = data.get("input") or data.get("asset") or data.get("visual") or data.get("camera")
    if output is None:
        raise ValueError("DEPTH requires output path")
    if source is None:
        raise ValueError("DEPTH requires an input artifact")
    source_path = Path(source)
    output_path = build_depth_map(source_path, output)
    return {
        "stage": "DEPTH",
        "artifact": str(output_path),
        "provenance": depth_provenance(source_path, output_path),
    }


__all__ = ["DEPTH_METHOD", "build_depth_map", "depth_provenance", "process_depth"]
