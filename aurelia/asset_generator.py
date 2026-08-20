"""AURELIA Maker — procedural cinematic visual asset generation (enhanced).

This file extends the original asset generator with multiple visual styles
and variation controls so the factory produces diverse scene plates instead
of a single static template.
"""

from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops


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


def _apply_vignette(image: Image.Image, strength: float = 0.6) -> Image.Image:
    width, height = image.size
    vign = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(vign)
    maxrad = math.hypot(width / 2, height / 2)
    for y in range(height):
        for x in range(width):
            d = math.hypot(x - width / 2, y - height / 2)
            v = int(255 * (1 - min(1.0, (d / maxrad) ** (1.2 / max(0.01, strength)))))
            vign.putpixel((x, y), v)
    return ImageChops.multiply(image.convert("RGB"), Image.merge("RGB", (vign, vign, vign)))


def _add_nebula(image: Image.Image, seed: int, tint: Tuple[int, int, int], blobs: int = 6) -> Image.Image:
    rng = random.Random(seed ^ 0x9E3779B9)
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = image.size
    for i in range(blobs):
        rx = int(rng.uniform(0.2, 0.8) * w)
        ry = int(rng.uniform(0.2, 0.8) * h)
        rw = int(rng.uniform(0.2, 0.6) * w)
        rh = int(rng.uniform(0.08, 0.3) * h)
        color = tuple(min(255, int(t * rng.uniform(0.6, 1.2))) for t in tint)
        alpha = int(rng.uniform(30, 90))
        draw.ellipse((rx - rw, ry - rh, rx + rw, ry + rh), fill=(*color, alpha))
    blurred = overlay.filter(ImageFilter.GaussianBlur(radius=rw * 0.08))
    return Image.alpha_composite(image.convert("RGBA"), blurred).convert("RGB")


def _add_grain(image: Image.Image, amount: float = 0.06, seed: int = 0) -> Image.Image:
    rng = random.Random(seed)
    w, h = image.size
    arr = np.array(image).astype(np.int16)
    grain = (np.random.RandomState(rng.randint(0, 2 ** 31 - 1)).randint(-30, 30, size=(h, w, 1))).astype(np.int16)
    arr = np.clip(arr + (grain * amount), 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


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
    """Generate a cinematic scene plate with style variation.

    The generator now supports multiple styles (starfield, nebula, minimal,
    painterly). Variation is still deterministic from content so reruns are
    reproducible, but different scripts/content produce distinct plates.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seed = _content_seed(scene_index, title, text)
    rng = random.Random(seed)

    # Choose a palette and a visual style deterministically
    palette = PALETTES[seed % len(PALETTES)]
    style = seed % 4  # 0..3 styles

    # base gradient
    image = _gradient(width, height, palette["top"], palette["bottom"])
    draw = ImageDraw.Draw(image)

    if style == 0:
        # Classic starfield + glow orb (original behavior)
        _draw_stars(draw, width, height, 180 + (seed % 120), seed=seed)
        cx = width // 2 + int(120 * math.sin(seed * 0.00017))
        cy = height // 2 + int(80 * math.cos(seed * 0.00013))
        radius = 240 + (seed % 120)
        image = _draw_glow_orb(image, cx, cy, radius, palette["accent"])  # type: ignore[arg-type]

    elif style == 1:
        # Nebula-forward: fewer stars, colorful nebula blobs
        _draw_stars(draw, width, height, 90 + (seed % 80), seed=seed)
        tint = palette["accent"]
        image = _add_nebula(image, seed, tint, blobs=6)
        # subtle central glow
        cx = int(width * rng.uniform(0.45, 0.55))
        cy = int(height * rng.uniform(0.35, 0.55))
        radius = int(180 + (seed % 160) * 0.6)
        image = _draw_glow_orb(image, cx, cy, radius, tuple(int(c * 0.9) for c in tint))  # type: ignore[arg-type]

    elif style == 2:
        # Minimal/graphic: geometric accents, low star density
        _draw_stars(draw, width, height, 60 + (seed % 60), seed=seed)
        # draw large diagonal light band
        band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        bd = ImageDraw.Draw(band)
        band_color = tuple(int(c * 0.25) for c in palette["accent"]) + (100,)
        bd.polygon([(0, height * 0.6), (width * 0.6, 0), (width, 0), (0, height)], fill=band_color)
        band = band.filter(ImageFilter.GaussianBlur(radius=80))
        image = Image.alpha_composite(image.convert("RGBA"), band).convert("RGB")

    else:
        # Painterly: multiple layered glow orbs and increased grain
        _draw_stars(draw, width, height, 140 + (seed % 100), seed=seed)
        for i in range(3):
            cx = int(width * rng.uniform(0.3, 0.7)) + int((i - 1) * 80)
            cy = int(height * rng.uniform(0.3, 0.6)) + int((i - 1) * 40)
            radius = int(120 + (seed % 200) * (0.5 + i * 0.2))
            tint = tuple(min(255, int(math.floor(c * (0.6 + i * 0.2)))) for c in palette["accent"])  # type: ignore[index]
            image = _draw_glow_orb(image, cx, cy, radius, tint)  # type: ignore[arg-type]
        image = _add_nebula(image, seed ^ 0xC0FFEE, tuple(min(255, int(c * 1.1)) for c in palette["accent"]))

    # decorative lines (kept but varied)
    draw = ImageDraw.Draw(image)
    line_count = 1 + (seed % 3)
    for i in range(line_count):
        y = int(height * (0.12 + i * 0.03)) + rng.randint(-6, 6)
        draw.line([(0, y), (width, y + 40)], fill=palette["accent"], width=1)

    # Optionally add a small badge only on the title card; for scenes keep minimal
    # We no longer bake a fixed "AURELIA MAKER" badge into every scene plate.

    # Post-process: blur, grain, vignette (amount varies by seed)
    image = image.filter(ImageFilter.GaussianBlur(radius=0.2 + (seed % 7) * 0.05))
    image = _add_grain(image, amount=0.04 + ((seed % 5) * 0.01), seed=seed)
    if (seed % 3) != 0:
        image = _apply_vignette(image, strength=0.6)

    image.save(output_path, "PNG", optimize=True)
    return output_path


def generate_title_card(
    title: str,
    subtitle: str,
    output: str | Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Generate opening title card with subtle variation based on title text."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seed = int(hashlib.sha256(title.encode("utf-8") + subtitle.encode("utf-8") + b"::title").hexdigest()[:16], 16)
    rng = random.Random(seed)
    palette = PALETTES[seed % len(PALETTES)]

    image = _gradient(width, height, palette["top"], palette["bottom"])
    draw = ImageDraw.Draw(image)
    _draw_stars(draw, width, height, 220 + (seed % 120), seed=seed)

    # Choose a decorative glow position so titles differ
    cx = int(width * rng.uniform(0.4, 0.6))
    cy = int(height * rng.uniform(0.35, 0.55))
    image = _draw_glow_orb(image, cx, cy, 320 + (seed % 200), palette["accent"])  # type: ignore[arg-type]

    title_font = _get_font(96)
    sub_font = _get_font(42)

    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, height // 2 - 80), title, fill=(255, 255, 255), font=title_font)

    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        sw = bbox[2] - bbox[0]
        draw.text(((width - sw) // 2, height // 2 + 60), subtitle, fill=(180, 200, 255), font=sub_font)

    # Small scene-badge on title is acceptable; keep it subtle
    badge = f"AURELIA MAKER  ·  {subtitle}" if subtitle else "AURELIA MAKER"
    draw.text((80, 60), badge, fill=tuple(min(255, int(c * 0.9)) for c in palette["accent"]), font=_get_font(22))

    image = image.filter(ImageFilter.GaussianBlur(radius=0.2))
    image.save(output_path, "PNG", optimize=True)
    return output_path


__all__ = ["generate_scene_image", "generate_title_card"]
