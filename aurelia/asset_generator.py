"""AURELIA Maker — procedural cinematic visual asset generation."""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _gradient(width: int, height: int, top: tuple, bottom: tuple) -> Image.Image:
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        t = y / max(height - 1, 1)
        arr[y, :, 0] = int(_lerp(top[0], bottom[0], t))
        arr[y, :, 1] = int(_lerp(top[1], bottom[1], t))
        arr[y, :, 2] = int(_lerp(top[2], bottom[2], t))
    return Image.fromarray(arr, "RGB")


def _draw_stars(draw: ImageDraw.ImageDraw, width: int, height: int, count: int, seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(count):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        r = rng.choice([1, 1, 1, 2])
        brightness = rng.randint(160, 255)
        draw.ellipse(
            (x - r, y - r, x + r, y + r),
            fill=(brightness, brightness, min(255, brightness + 20)),
        )


def _draw_glow_orb(
    image: Image.Image,
    cx: int,
    cy: int,
    radius: int,
    color: tuple[int, int, int],
) -> Image.Image:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(radius, 0, -2):
        alpha = int(80 * (1 - i / radius))
        draw.ellipse(
            (cx - i, cy - i, cx + i, cy + i),
            fill=(*color, alpha),
        )
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    raise RuntimeError(
        "No Unicode-capable TrueType font found. Install DejaVu Sans or Liberation Sans."
    )


PALETTES = [
    {"top": (8, 12, 40), "bottom": (20, 8, 60), "accent": (100, 180, 255)},
    {"top": (5, 10, 30), "bottom": (40, 10, 50), "accent": (255, 120, 80)},
    {"top": (10, 20, 35), "bottom": (5, 40, 55), "accent": (80, 220, 180)},
    {"top": (15, 5, 35), "bottom": (60, 15, 80), "accent": (200, 160, 255)},
    {"top": (5, 8, 25), "bottom": (30, 30, 10), "accent": (255, 200, 60)},
    {"top": (8, 15, 45), "bottom": (10, 5, 25), "accent": (120, 200, 255)},
]


def _content_seed(scene_index: int, title: str, text: str) -> int:
    """Derive deterministic visual variation from scene meaning, not position alone."""
    payload = f"{title}\n{text}".strip().encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") ^ (scene_index * 7919 + 42)


def generate_scene_image(
    scene_index: int,
    title: str,
    text: str,
    output: str | Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Generate a cinematic scene plate for production rendering.

    Visual variation is derived from the actual scene content. Scene narration is
    intentionally not baked into the plate; subtitles are rendered downstream.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seed = _content_seed(scene_index, title, text)
    palette = PALETTES[seed % len(PALETTES)]
    image = _gradient(width, height, palette["top"], palette["bottom"])
    draw = ImageDraw.Draw(image)

    _draw_stars(draw, width, height, 180 + (seed % 120), seed=seed)

    cx = width // 2 + int(120 * math.sin(seed * 0.00017))
    cy = height // 2 + int(80 * math.cos(seed * 0.00013))
    radius = 240 + (seed % 120)
    image = _draw_glow_orb(image, cx, cy, radius, palette["accent"])

    draw = ImageDraw.Draw(image)

    for i in range(3):
        y = int(height * (0.15 + i * 0.02))
        draw.line(
            [(0, y), (width, y + 40)],
            fill=palette["accent"],
            width=1,
        )

    # No title/narration is baked into scene plates. The subtitle track is the
    # single text layer for the rendered episode.
    badge = f"AURELIA MAKER  ·  SCENE {scene_index + 1:02d}"
    draw.text((80, 60), badge, fill=palette["accent"], font=_get_font(28))

    image = image.filter(ImageFilter.GaussianBlur(radius=0.3))
    image.save(output_path, "PNG", optimize=True)
    return output_path


def generate_title_card(
    title: str,
    subtitle: str,
    output: str | Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Generate opening title card."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    image = _gradient(width, height, (2, 4, 18), (12, 8, 40))
    draw = ImageDraw.Draw(image)
    _draw_stars(draw, width, height, 300, seed=13)

    image = _draw_glow_orb(image, width // 2, height // 2 - 40, 400, (80, 140, 255))
    draw = ImageDraw.Draw(image)

    title_font = _get_font(96)
    sub_font = _get_font(42)

    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, height // 2 - 80), title, fill=(255, 255, 255), font=title_font)

    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sw = bbox[2] - bbox[0]
        draw.text(((width - sw) // 2, height // 2 + 60), subtitle, fill=(180, 200, 255), font=sub_font)

    image.save(output_path, "PNG", optimize=True)
    return output_path


__all__ = ["generate_scene_image", "generate_title_card"]
