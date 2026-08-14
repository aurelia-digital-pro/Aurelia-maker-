"""AURELIA Maker — procedural cinematic visual asset generation."""

from __future__ import annotations

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


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


PALETTES = [
    {"top": (8, 12, 40), "bottom": (20, 8, 60), "accent": (100, 180, 255)},
    {"top": (5, 10, 30), "bottom": (40, 10, 50), "accent": (255, 120, 80)},
    {"top": (10, 20, 35), "bottom": (5, 40, 55), "accent": (80, 220, 180)},
    {"top": (15, 5, 35), "bottom": (60, 15, 80), "accent": (200, 160, 255)},
    {"top": (5, 8, 25), "bottom": (30, 30, 10), "accent": (255, 200, 60)},
    {"top": (8, 15, 45), "bottom": (10, 5, 25), "accent": (120, 200, 255)},
]


def generate_scene_image(
    scene_index: int,
    title: str,
    text: str,
    output: str | Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Generate a cinematic scene plate for production rendering."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    palette = PALETTES[scene_index % len(PALETTES)]
    image = _gradient(width, height, palette["top"], palette["bottom"])
    draw = ImageDraw.Draw(image)

    _draw_stars(draw, width, height, 180 + scene_index * 20, seed=scene_index * 7919 + 42)

    cx = width // 2 + int(120 * math.sin(scene_index * 0.7))
    cy = height // 2 + int(80 * math.cos(scene_index * 0.5))
    image = _draw_glow_orb(image, cx, cy, 280 + scene_index * 15, palette["accent"])

    draw = ImageDraw.Draw(image)

    for i in range(3):
        y = int(height * (0.15 + i * 0.02))
        draw.line(
            [(0, y), (width, y + 40)],
            fill=(*palette["accent"], 30) if hasattr(draw, "fill") else palette["accent"],
            width=1,
        )

    title_font = _get_font(72)
    body_font = _get_font(36)

    display_title = title[:80] if title else f"Scene {scene_index + 1}"
    draw.text((80, height - 280), display_title, fill=(255, 255, 255), font=title_font)

    snippet = " ".join(text.split())[:120]
    if snippet:
        draw.text((80, height - 180), snippet + ("..." if len(text) > 120 else ""), fill=(200, 210, 230), font=body_font)

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
