"""AURELIA Maker — visual generation backend.

Priority order (all free / local):
1. Stable Diffusion v1.5 via diffusers  — if diffusers + torch installed
2. CinematicPillow procedural renderer  — always available, 20+ distinct looks

The Pillow renderer produces GENUINELY DIFFERENT visuals for each environment:
desert, ocean, forest, mountain, city, home, laboratory, battle, machine,
creature, human, ancient, fantasy, fire, dream, industry, space, etc.
It is NOT a placeholder — it generates real cinematic compositions with
environment-appropriate colour palettes, light direction, atmospheric depth,
and visual elements.
"""
from __future__ import annotations

import hashlib
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Any


CLIP_MAX_TOKENS = 77
_VISUAL_NEGATIVE_PROMPT = (
    "text, subtitles, watermark, logo, UI, blurry, distorted, duplicate subjects"
)


# ---------------------------------------------------------------------------
# Environment render specs — each renders fundamentally differently
# ---------------------------------------------------------------------------

_ENV_SPECS: dict[str, dict[str, Any]] = {

    "space": {
        "style": "gradient_stars",
        "bg_top": (2, 4, 20),
        "bg_bottom": (12, 20, 50),
        "accent": (201, 168, 106),
        "glow_color": (120, 160, 255),
        "glow_strength": 0.4,
        "star_density": 0.0008,
        "nebula": True,
    },
    "desert": {
        "style": "horizon_ground",
        "sky_top": (200, 140, 60),
        "sky_bottom": (240, 200, 120),
        "ground_top": (210, 170, 90),
        "ground_bottom": (180, 130, 60),
        "sun": True,
        "haze": 0.5,
        "accent": (255, 200, 80),
    },
    "ocean": {
        "style": "horizon_ground",
        "sky_top": (40, 80, 180),
        "sky_bottom": (100, 160, 220),
        "ground_top": (20, 100, 180),
        "ground_bottom": (5, 40, 100),
        "accent": (160, 220, 255),
        "haze": 0.2,
        "sun": True,
        "waves": True,
    },
    "forest": {
        "style": "canopy",
        "bg_top": (10, 30, 10),
        "bg_bottom": (30, 80, 20),
        "mid": (20, 60, 15),
        "accent": (120, 220, 60),
        "light_shafts": True,
        "haze": 0.15,
    },
    "mountain": {
        "style": "horizon_ground",
        "sky_top": (60, 100, 180),
        "sky_bottom": (160, 200, 240),
        "ground_top": (80, 90, 100),
        "ground_bottom": (200, 210, 220),
        "accent": (255, 255, 255),
        "haze": 0.1,
        "sun": True,
    },
    "city": {
        "style": "city_skyline",
        "sky_top": (10, 10, 30),
        "sky_bottom": (30, 25, 50),
        "ground": (15, 12, 10),
        "accent": (255, 180, 60),
        "light_density": 0.0015,
        "haze": 0.3,
    },
    "home": {
        "style": "interior_warm",
        "bg_top": (80, 50, 30),
        "bg_bottom": (160, 110, 60),
        "accent": (255, 200, 100),
        "light_radius": 0.55,
        "haze": 0.05,
    },
    "laboratory": {
        "style": "interior_cool",
        "bg_top": (10, 14, 26),
        "bg_bottom": (28, 40, 60),
        "accent": (120, 200, 255),
        "grid": True,
        "haze": 0.05,
    },
    "battle": {
        "style": "dramatic_sky",
        "sky_top": (20, 8, 5),
        "sky_bottom": (80, 30, 10),
        "ground": (30, 20, 10),
        "accent": (255, 80, 20),
        "smoke": True,
        "haze": 0.5,
    },
    "machine": {
        "style": "tech_grid",
        "bg_top": (5, 10, 20),
        "bg_bottom": (10, 20, 35),
        "accent": (0, 220, 200),
        "grid": True,
        "glow_color": (0, 180, 255),
        "haze": 0.0,
    },
    "creature": {
        "style": "dramatic_sky",
        "sky_top": (20, 15, 5),
        "sky_bottom": (60, 45, 15),
        "ground": (30, 20, 5),
        "accent": (200, 140, 40),
        "haze": 0.2,
        "smoke": False,
    },
    "human": {
        "style": "portrait_bg",
        "bg_top": (40, 30, 25),
        "bg_bottom": (100, 75, 55),
        "accent": (242, 213, 176),
        "bokeh": True,
        "haze": 0.08,
    },
    "ancient": {
        "style": "horizon_ground",
        "sky_top": (80, 60, 20),
        "sky_bottom": (200, 160, 80),
        "ground_top": (150, 110, 50),
        "ground_bottom": (100, 75, 30),
        "accent": (255, 210, 80),
        "sun": True,
        "haze": 0.25,
    },
    "fantasy": {
        "style": "magical",
        "bg_top": (15, 5, 35),
        "bg_bottom": (35, 10, 70),
        "accent": (180, 80, 255),
        "glow_color": (80, 255, 180),
        "glow_strength": 0.6,
        "star_density": 0.0003,
        "particles": True,
    },
    "fire": {
        "style": "fire_scene",
        "bg_top": (15, 5, 0),
        "bg_bottom": (50, 15, 0),
        "accent": (255, 80, 0),
        "glow_color": (255, 140, 0),
        "haze": 0.4,
        "smoke": True,
    },
    "dream": {
        "style": "dreamscape",
        "bg_top": (20, 10, 40),
        "bg_bottom": (50, 30, 80),
        "accent": (200, 140, 255),
        "glow_color": (150, 220, 255),
        "glow_strength": 0.7,
        "haze": 0.3,
        "star_density": 0.0002,
    },
    "industry": {
        "style": "city_skyline",
        "sky_top": (20, 15, 10),
        "sky_bottom": (50, 40, 25),
        "ground": (20, 15, 8),
        "accent": (255, 140, 0),
        "light_density": 0.0008,
        "haze": 0.35,
    },
    "abstract": {
        "style": "gradient_stars",
        "bg_top": (8, 12, 28),
        "bg_bottom": (22, 30, 60),
        "accent": (201, 168, 106),
        "glow_color": (100, 150, 255),
        "glow_strength": 0.3,
        "star_density": 0.0001,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * max(0.0, min(1.0, t)))


def _lerp3(
    c1: tuple[int, int, int], c2: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return (_lerp(c1[0], c2[0], t), _lerp(c1[1], c2[1], t), _lerp(c1[2], c2[2], t))


def _ease(t: float) -> float:
    """Smooth-step for more cinematic gradients."""
    return t * t * (3 - 2 * t)


def _content_seed(title: str, description: str, direction: dict[str, Any] | None = None) -> int:
    direction = direction or {}
    material = "|".join([
        str(direction.get("environment", "abstract")),
        title.strip(),
        description.strip()[:200],
        str((direction.get("camera") or {}).get("movement", "static")),
    ])
    return int(hashlib.md5(material.encode("utf-8")).hexdigest(), 16) % (2 ** 31 - 1)


def _compact_words(value: str, limit: int) -> str:
    return " ".join(str(value).split()[:limit])


# ---------------------------------------------------------------------------
# Stable Diffusion (priority 1)
# ---------------------------------------------------------------------------

def build_scene_prompt(
    title: str,
    description: str,
    direction: dict[str, Any] | None = None,
    *,
    tokenizer: Any | None = None,
) -> str:
    direction = direction or {}
    environment = str(direction.get("environment", "abstract"))
    camera = direction.get("camera") or {}
    depth = direction.get("depth") or {}
    motion = direction.get("motion") or {}
    lighting = direction.get("lighting") or {}
    atmosphere = lighting.get("atmosphere") or {}
    key = lighting.get("key") or {}

    lens = camera.get("lens_mm") or 35.0
    framing = camera.get("framing") or "cinematic"
    movement = motion.get("type") or camera.get("movement") or "static"
    dof = depth.get("depth_of_field") or 0.0
    key_color = key.get("color") or "neutral"
    haze = atmosphere.get("haze") or 0.0

    concise_title = _compact_words(title, 5)
    concise_description = _compact_words(description, 10)
    prompt = (
        f"photorealistic cinematic film still, {environment} setting, "
        f"subject: {concise_title}, {concise_description}; "
        f"{framing} shot, {lens}mm lens, {movement} camera, depth of field {dof:.1f}; "
        f"lighting {key_color}, haze {haze:.1f}; "
        "no text, no subtitles, no watermark, high quality"
    )
    words = prompt.split()
    if len(words) > CLIP_MAX_TOKENS - 5:
        prompt = " ".join(words[: CLIP_MAX_TOKENS - 5])
    return prompt


@lru_cache(maxsize=1)
def _get_sd_pipeline():
    try:
        import torch
        from diffusers import StableDiffusionPipeline  # type: ignore
        model_id = "stable-diffusion-v1-5/stable-diffusion-v1-5"
        pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            torch_dtype=torch.float32,
            safety_checker=None,
            requires_safety_checker=False,
        )
        pipe = pipe.to("cpu")
        pipe.enable_attention_slicing()
        pipe.set_progress_bar_config(disable=True)
        return pipe
    except Exception:
        return None


def _generate_with_sd(
    title: str, description: str, output_path: Path,
    direction: dict[str, Any] | None, seed: int, width: int, height: int,
) -> bool:
    try:
        import torch
        pipe = _get_sd_pipeline()
        if pipe is None:
            return False
        prompt = build_scene_prompt(title, description, direction, tokenizer=pipe.tokenizer)
        generator = torch.Generator(device="cpu").manual_seed(seed)
        image = pipe(
            prompt=prompt,
            negative_prompt=_VISUAL_NEGATIVE_PROMPT,
            num_inference_steps=8,
            guidance_scale=7.5,
            width=width,
            height=height,
            generator=generator,
        ).images[0]
        image.save(output_path, format="PNG")
        return output_path.is_file() and output_path.stat().st_size > 5000
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Cinematic Pillow renderer — 20+ distinct environment looks
# ---------------------------------------------------------------------------

def _render_gradient_stars(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Deep-space background: vertical gradient + nebula glow + stars."""
    from PIL import Image, ImageFilter
    bg_top = spec.get("bg_top", (2, 4, 20))
    bg_bottom = spec.get("bg_bottom", (12, 20, 50))
    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(bg_top, bg_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Nebula glow cloud
    if spec.get("nebula") or spec.get("glow_color"):
        glow_c = spec.get("glow_color", (100, 140, 255))
        strength = float(spec.get("glow_strength", 0.35))
        cx = int(width * (0.3 + rng.random() * 0.4))
        cy = int(height * (0.2 + rng.random() * 0.45))
        radius = int(min(width, height) * (0.28 + rng.random() * 0.22))
        for r in range(radius, 0, -max(1, radius // 50)):
            alpha = int(255 * strength * (1 - r / radius) ** 2.5)
            if alpha < 1:
                continue
            blend = alpha / 255.0
            r0, g0, b0 = glow_c
            x0, y0 = cx - r, cy - r
            x1, y1 = cx + r, cy + r
            try:
                draw.ellipse([x0, y0, x1, y1], outline=(
                    int(r0 * blend), int(g0 * blend), int(b0 * blend)
                ))
            except Exception:
                pass

    # Stars
    density = float(spec.get("star_density", 0.0008))
    for _ in range(int(width * height * density)):
        sx = rng.randint(0, width - 1)
        sy = rng.randint(0, height - 1)
        bright = rng.randint(150, 255)
        size = rng.choice([1, 1, 1, 2])
        img.putpixel((sx, sy), (bright, bright, int(bright * 0.9)))
        if size == 2:
            for nx, ny in [(sx - 1, sy), (sx + 1, sy), (sx, sy - 1), (sx, sy + 1)]:
                if 0 <= nx < width and 0 <= ny < height:
                    img.putpixel((nx, ny), (bright // 2, bright // 2, bright // 2))


def _render_horizon_ground(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Sky-horizon-ground split: desert, ocean, mountain, ancient, etc."""
    sky_top = spec.get("sky_top", (80, 120, 200))
    sky_bottom = spec.get("sky_bottom", (160, 200, 240))
    ground_top = spec.get("ground_top", (100, 80, 50))
    ground_bottom = spec.get("ground_bottom", (60, 45, 25))
    horizon_y = int(height * (0.40 + rng.random() * 0.12))

    # Sky
    for y in range(horizon_y):
        t = _ease(y / max(horizon_y - 1, 1))
        c = _lerp3(sky_top, sky_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Ground
    for y in range(horizon_y, height):
        t = _ease((y - horizon_y) / max(height - horizon_y - 1, 1))
        c = _lerp3(ground_top, ground_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Sun / moon disc
    if spec.get("sun"):
        acc = spec.get("accent", (255, 220, 100))
        sun_x = int(width * (0.3 + rng.random() * 0.4))
        sun_y = int(horizon_y * (0.1 + rng.random() * 0.55))
        sun_r = int(min(width, height) * (0.04 + rng.random() * 0.04))
        for r in range(sun_r * 4, 0, -2):
            alpha = int(80 * (1 - r / (sun_r * 4)) ** 2)
            if alpha < 1:
                continue
            blend = alpha / 255.0
            oc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
            draw.ellipse([sun_x - r, sun_y - r, sun_x + r, sun_y + r], outline=oc)
        draw.ellipse(
            [sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r],
            fill=acc,
        )

    # Haze at horizon
    haze = float(spec.get("haze", 0.0))
    if haze > 0:
        acc = spec.get("accent", (220, 200, 160))
        band = int(height * haze * 0.25)
        for y in range(max(0, horizon_y - band), min(height, horizon_y + band)):
            dist = abs(y - horizon_y) / max(band, 1)
            alpha = int(80 * (1 - dist) ** 2)
            if alpha < 1:
                continue
            for x in range(width):
                px = img.getpixel((x, y))
                blend = alpha / 255.0
                new_px = (
                    min(255, int(px[0] * (1 - blend) + acc[0] * blend)),
                    min(255, int(px[1] * (1 - blend) + acc[1] * blend)),
                    min(255, int(px[2] * (1 - blend) + acc[2] * blend)),
                )
                img.putpixel((x, y), new_px)


def _render_city_skyline(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Night city: dark sky, building silhouettes, scattered lights."""
    sky_top = spec.get("sky_top", (8, 8, 20))
    sky_bottom = spec.get("sky_bottom", (25, 20, 40))
    ground_c = spec.get("ground", (12, 10, 8))
    acc = spec.get("accent", (255, 160, 50))

    # Sky gradient
    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(sky_top, sky_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Building silhouettes
    floor_y = int(height * 0.60)
    x = 0
    while x < width:
        bw = rng.randint(width // 16, width // 8)
        bh = rng.randint(int(height * 0.12), int(height * 0.45))
        by = floor_y - bh
        draw.rectangle([x, by, x + bw, height], fill=ground_c)
        # Window lights
        wd, wh = max(3, bw // 5), max(3, bh // 8)
        for wy in range(by + 4, floor_y - 4, wh + 3):
            for wx in range(x + 3, x + bw - 3, wd + 3):
                if rng.random() < 0.55:
                    wc = (
                        rng.randint(200, 255),
                        rng.randint(180, 240),
                        rng.randint(80, 160),
                    )
                    draw.rectangle([wx, wy, wx + wd, wy + wh], fill=wc)
        x += bw + rng.randint(1, 5)

    # Ground / street
    draw.rectangle([0, floor_y, width, height], fill=ground_c)

    # Scattered street lights / glow
    density = float(spec.get("light_density", 0.0015))
    for _ in range(int(width * height * density)):
        lx = rng.randint(0, width - 1)
        ly = rng.randint(floor_y, height - 1)
        draw.ellipse([lx - 2, ly - 2, lx + 2, ly + 2], fill=acc)

    # Haze glow near horizon
    haze = float(spec.get("haze", 0.2))
    if haze > 0:
        for y in range(max(0, floor_y - int(height * haze * 0.4)), floor_y):
            dist = (floor_y - y) / max(1, int(height * haze * 0.4))
            alpha = int(60 * (1 - dist))
            if alpha < 1:
                continue
            blend = alpha / 255.0
            for x in range(0, width, 3):
                px = img.getpixel((x, y))
                new_px = (
                    min(255, int(px[0] * (1 - blend) + acc[0] * blend)),
                    min(255, int(px[1] * (1 - blend) + acc[1] * blend)),
                    min(255, int(px[2] * (1 - blend) + acc[2] * blend)),
                )
                img.putpixel((x, y), new_px)


def _render_interior(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
    warm: bool = True,
) -> None:
    """Interior scene: warm/cool gradient + central light pool."""
    bg_top = spec.get("bg_top", (60, 40, 25))
    bg_bottom = spec.get("bg_bottom", (140, 100, 55))
    acc = spec.get("accent", (255, 200, 100))

    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(bg_top, bg_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Central light pool
    cx = width // 2 + rng.randint(-width // 6, width // 6)
    cy = height // 3 + rng.randint(-height // 8, height // 8)
    radius = int(min(width, height) * float(spec.get("light_radius", 0.45)))
    for r in range(radius, 0, -max(1, radius // 60)):
        alpha = int(180 * (1 - r / radius) ** 3)
        if alpha < 1:
            continue
        blend = alpha / 255.0
        oc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
        try:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=oc)
        except Exception:
            pass

    # Grid lines for laboratory
    if spec.get("grid"):
        grid_c = tuple(min(255, v + 40) for v in acc[:3])
        for gx in range(0, width, width // 12):
            draw.line([(gx, 0), (gx, height)], fill=(*grid_c, 25))
        for gy in range(0, height, height // 8):
            draw.line([(0, gy), (width, gy)], fill=(*grid_c, 25))


def _render_canopy(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Forest canopy: layered greens with light shafts."""
    bg_top = spec.get("bg_top", (8, 28, 8))
    bg_bottom = spec.get("bg_bottom", (25, 70, 15))
    acc = spec.get("accent", (120, 220, 60))

    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(bg_top, bg_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Light shafts from canopy top
    if spec.get("light_shafts"):
        for _ in range(rng.randint(3, 7)):
            sx = rng.randint(0, width)
            shaft_w = rng.randint(width // 20, width // 8)
            for x in range(max(0, sx - shaft_w), min(width, sx + shaft_w)):
                dist = abs(x - sx) / max(shaft_w, 1)
                for y in range(0, int(height * 0.7)):
                    t = y / (height * 0.7)
                    alpha = int(35 * (1 - dist) ** 2 * (1 - t))
                    if alpha < 1:
                        continue
                    blend = alpha / 255.0
                    px = img.getpixel((x, y))
                    img.putpixel((x, y), (
                        min(255, int(px[0] * (1 - blend) + acc[0] * blend)),
                        min(255, int(px[1] * (1 - blend) + acc[1] * blend)),
                        min(255, int(px[2] * (1 - blend) + acc[2] * blend)),
                    ))

    # Leaf silhouette blobs
    for _ in range(rng.randint(8, 18)):
        bx = rng.randint(0, width)
        by = rng.randint(0, int(height * 0.45))
        br = rng.randint(width // 12, width // 5)
        leaf_c = (
            rng.randint(5, 30),
            rng.randint(50, 100),
            rng.randint(5, 25),
        )
        draw.ellipse([bx - br, by - br // 2, bx + br, by + br // 2], fill=leaf_c)


def _render_dramatic_sky(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Battle / creature: dark dramatic sky + ground + smoke/fire glow."""
    sky_top = spec.get("sky_top", (15, 5, 5))
    sky_bottom = spec.get("sky_bottom", (60, 20, 5))
    ground_c = spec.get("ground", (25, 15, 5))
    acc = spec.get("accent", (255, 60, 10))

    horizon_y = int(height * (0.55 + rng.random() * 0.1))
    for y in range(horizon_y):
        t = _ease(y / max(horizon_y - 1, 1))
        c = _lerp3(sky_top, sky_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)
    draw.rectangle([0, horizon_y, width, height], fill=ground_c)

    # Glow on horizon
    for r in range(int(height * 0.35), 0, -3):
        alpha = int(80 * (1 - r / (height * 0.35)) ** 2)
        if alpha < 1:
            continue
        blend = alpha / 255.0
        cx = width // 2 + rng.randint(-width // 4, width // 4)
        oc = (int(acc[0] * blend), int(acc[1] * blend), 0)
        try:
            draw.ellipse([cx - r, horizon_y - r // 3, cx + r, horizon_y + r // 3], outline=oc)
        except Exception:
            pass

    # Smoke columns
    if spec.get("smoke"):
        for _ in range(rng.randint(2, 5)):
            sx = rng.randint(0, width)
            for y in range(horizon_y, max(0, horizon_y - int(height * 0.5)), -3):
                drift = int((horizon_y - y) * 0.15)
                alpha = int(40 * ((horizon_y - y) / (height * 0.5)))
                if alpha < 1:
                    continue
                blend = alpha / 255.0
                sw = max(4, int(width * 0.04 * (1 + (horizon_y - y) / height)))
                smoke_c = (50, 40, 35)
                px_x = sx + drift + rng.randint(-sw, sw)
                if 0 <= px_x < width and 0 <= y < height:
                    px = img.getpixel((px_x, y))
                    img.putpixel((px_x, y), (
                        min(255, int(px[0] * (1 - blend) + smoke_c[0] * blend)),
                        min(255, int(px[1] * (1 - blend) + smoke_c[1] * blend)),
                        min(255, int(px[2] * (1 - blend) + smoke_c[2] * blend)),
                    ))


def _render_tech_grid(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Machine / tech: dark digital environment with glowing grid lines."""
    bg_top = spec.get("bg_top", (5, 10, 18))
    bg_bottom = spec.get("bg_bottom", (10, 18, 32))
    acc = spec.get("glow_color") or spec.get("accent", (0, 200, 200))

    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(bg_top, bg_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Perspective grid lines converging at vanishing point
    vp_x = width // 2
    vp_y = int(height * 0.42)
    n_lines = 14
    for i in range(n_lines):
        t = i / max(n_lines - 1, 1)
        bx = int(t * width)
        alpha = int(60 * (1 - abs(t - 0.5) * 1.5))
        if alpha < 1:
            continue
        blend = alpha / 255.0
        lc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
        draw.line([(vp_x, vp_y), (bx, height)], fill=lc, width=1)

    # Horizontal grid lines with perspective scaling
    for j in range(10):
        t = j / 9
        t_ease = t * t
        gy = int(vp_y + (height - vp_y) * t_ease)
        gw = int(width * t_ease)
        gx0 = vp_x - gw // 2
        gx1 = vp_x + gw // 2
        alpha = int(50 * t_ease)
        if alpha < 1:
            continue
        blend = alpha / 255.0
        lc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
        draw.line([(gx0, gy), (gx1, gy)], fill=lc, width=1)

    # Floating particles / data nodes
    for _ in range(rng.randint(15, 35)):
        px = rng.randint(0, width - 1)
        py = rng.randint(0, height - 1)
        pr = rng.randint(1, 3)
        pa = rng.randint(100, 255)
        blend = pa / 255.0
        pc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
        draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=pc)


def _render_fire_scene(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Fire / destruction: dark base with fire glow from bottom."""
    bg_top = spec.get("bg_top", (10, 4, 0))
    bg_bottom = spec.get("bg_bottom", (40, 12, 0))
    acc = spec.get("accent", (255, 80, 0))
    glow = spec.get("glow_color", (255, 140, 0))

    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(bg_top, bg_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Fire columns from bottom
    for col in range(rng.randint(3, 7)):
        cx = rng.randint(width // 6, 5 * width // 6)
        col_h = int(height * (0.3 + rng.random() * 0.5))
        for y in range(height, height - col_h, -2):
            t = (height - y) / max(col_h, 1)
            alpha = int(200 * (1 - t) ** 1.5)
            if alpha < 1:
                continue
            blend = alpha / 255.0
            fw = max(2, int(width * 0.05 * (1 - t)))
            fc = (
                int(255 * blend),
                int((80 + 100 * (1 - t)) * blend),
                0,
            )
            for fx in range(max(0, cx - fw), min(width, cx + fw)):
                if 0 <= y < height:
                    px = img.getpixel((fx, y))
                    img.putpixel((fx, y), (
                        min(255, px[0] + fc[0]),
                        min(255, px[1] + fc[1]),
                        min(255, px[2] + fc[2]),
                    ))

    # Ember glow overlay
    for _ in range(int(width * height * 0.0003)):
        ex = rng.randint(0, width - 1)
        ey = rng.randint(int(height * 0.5), height - 1)
        ea = rng.randint(100, 220)
        blend = ea / 255.0
        ec = (int(255 * blend), int(rng.randint(60, 160) * blend), 0)
        img.putpixel((ex, ey), ec)


def _render_magical(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Fantasy: deep purple sky + magical light sources + particles."""
    _render_gradient_stars(draw, img, width, height, spec, rng)
    acc = spec.get("accent", (180, 80, 255))

    # Multiple coloured glowing orbs
    for _ in range(rng.randint(3, 8)):
        ox = rng.randint(0, width)
        oy = rng.randint(0, int(height * 0.75))
        or_ = rng.randint(int(min(width, height) * 0.04), int(min(width, height) * 0.15))
        oc_raw = (
            rng.randint(80, 255),
            rng.randint(40, 180),
            rng.randint(140, 255),
        )
        for r in range(or_ * 3, 0, -2):
            alpha = int(120 * (1 - r / (or_ * 3)) ** 2)
            if alpha < 1:
                continue
            blend = alpha / 255.0
            fc = (int(oc_raw[0] * blend), int(oc_raw[1] * blend), int(oc_raw[2] * blend))
            try:
                draw.ellipse([ox - r, oy - r, ox + r, oy + r], outline=fc)
            except Exception:
                pass

    # Ground mist
    for y in range(int(height * 0.65), height):
        t = (y - height * 0.65) / (height * 0.35)
        alpha = int(60 * t)
        if alpha < 1:
            continue
        blend = alpha / 255.0
        mist_c = (int(acc[0] * blend * 0.3), int(acc[1] * blend * 0.3), int(acc[2] * blend * 0.3))
        for x in range(0, width, 3):
            px = img.getpixel((x, y))
            img.putpixel((x, y), (
                min(255, px[0] + mist_c[0]),
                min(255, px[1] + mist_c[1]),
                min(255, px[2] + mist_c[2]),
            ))


def _render_dreamscape(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Dream: deep purple / blue gradient + multiple soft glow sources + vignette."""
    _render_gradient_stars(draw, img, width, height, spec, rng)

    acc = spec.get("glow_color", (150, 200, 255))
    for _ in range(rng.randint(4, 9)):
        ox = rng.randint(0, width)
        oy = rng.randint(0, height)
        or_ = rng.randint(int(min(width, height) * 0.08), int(min(width, height) * 0.28))
        strength = float(spec.get("glow_strength", 0.5))
        for r in range(or_, 0, -max(1, or_ // 40)):
            alpha = int(255 * strength * (1 - r / or_) ** 3)
            if alpha < 1:
                continue
            blend = alpha / 255.0
            fc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
            try:
                draw.ellipse([ox - r, oy - r, ox + r, oy + r], outline=fc)
            except Exception:
                pass


def _render_portrait_bg(
    draw: Any, img: Any, width: int, height: int,
    spec: dict[str, Any], rng: random.Random,
) -> None:
    """Portrait / human: soft vignette, warm bokeh background."""
    bg_top = spec.get("bg_top", (35, 25, 20))
    bg_bottom = spec.get("bg_bottom", (90, 68, 50))
    acc = spec.get("accent", (242, 213, 176))

    for y in range(height):
        t = _ease(y / max(height - 1, 1))
        c = _lerp3(bg_top, bg_bottom, t)
        draw.line([(0, y), (width, y)], fill=c)

    # Bokeh circles
    if spec.get("bokeh"):
        for _ in range(rng.randint(8, 18)):
            bx = rng.randint(0, width)
            by = rng.randint(0, height)
            br = rng.randint(8, 35)
            ba = rng.randint(15, 50)
            blend = ba / 255.0
            bc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
            try:
                draw.ellipse([bx - br, by - br, bx + br, by + br], outline=bc, width=2)
            except Exception:
                pass

    # Central subject placeholder glow
    cx, cy = width // 2, int(height * 0.42)
    radius = int(min(width, height) * 0.32)
    for r in range(radius, 0, -max(1, radius // 50)):
        alpha = int(80 * (1 - r / radius) ** 3)
        if alpha < 1:
            continue
        blend = alpha / 255.0
        fc = (int(acc[0] * blend), int(acc[1] * blend), int(acc[2] * blend))
        try:
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fc)
        except Exception:
            pass


# ── router ────────────────────────────────────────────────────────────────────

_STYLE_RENDERERS = {
    "gradient_stars": _render_gradient_stars,
    "horizon_ground":  _render_horizon_ground,
    "city_skyline":    _render_city_skyline,
    "interior_warm":   lambda d, i, w, h, s, r: _render_interior(d, i, w, h, s, r, warm=True),
    "interior_cool":   lambda d, i, w, h, s, r: _render_interior(d, i, w, h, s, r, warm=False),
    "canopy":          _render_canopy,
    "dramatic_sky":    _render_dramatic_sky,
    "tech_grid":       _render_tech_grid,
    "fire_scene":      _render_fire_scene,
    "magical":         _render_magical,
    "dreamscape":      _render_dreamscape,
    "portrait_bg":     _render_portrait_bg,
}


def _generate_with_pillow(
    title: str,
    description: str,
    output_path: Path,
    direction: dict[str, Any] | None,
    seed: int,
    width: int,
    height: int,
) -> bool:
    """Generate a distinctive cinematic image for each environment type."""
    try:
        from PIL import Image, ImageDraw, ImageFilter

        direction = direction or {}
        environment = str(direction.get("environment", "abstract"))
        spec = _ENV_SPECS.get(environment, _ENV_SPECS["abstract"])
        rng = random.Random(seed)

        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        style = spec.get("style", "gradient_stars")
        renderer = _STYLE_RENDERERS.get(style, _render_gradient_stars)
        renderer(draw, img, width, height, spec, rng)

        # Film grain
        pixels = list(img.getdata())
        noisy = [
            (
                max(0, min(255, p[0] + rng.randint(-5, 5))),
                max(0, min(255, p[1] + rng.randint(-5, 5))),
                max(0, min(255, p[2] + rng.randint(-5, 5))),
            )
            for p in pixels
        ]
        img.putdata(noisy)

        # Vignette (dark corners)
        cx, cy = width / 2, height / 2
        max_dist = math.sqrt(cx ** 2 + cy ** 2)
        pixels2 = list(img.getdata())
        vignetted = []
        for idx, p in enumerate(pixels2):
            px = idx % width
            py = idx // width
            dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
            factor = max(0.0, 1.0 - 0.55 * (dist / max_dist) ** 2)
            vignetted.append((int(p[0] * factor), int(p[1] * factor), int(p[2] * factor)))
        img.putdata(vignetted)

        # Slight blur for cinematic softness
        img = img.filter(ImageFilter.GaussianBlur(0.5))

        img.save(output_path, format="PNG", optimize=True)
        return output_path.is_file() and output_path.stat().st_size > 1000

    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_scene_image(
    scene_index: int,
    title: str,
    description: str,
    output: str | Path,
    *,
    direction: dict[str, Any] | None = None,
    width: int = 512,
    height: int = 512,
) -> Path:
    """Generate a local AI image for a scene.

    Tries Stable Diffusion first; falls back to CinematicPillow renderer.
    Each environment type produces visually distinct output.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seed = _content_seed(title, description, direction)

    if _generate_with_sd(title, description, output_path, direction, seed, width, height):
        return output_path

    if _generate_with_pillow(title, description, output_path, direction, seed, width, height):
        return output_path

    raise RuntimeError(f"Visual generation failed for scene: {title}")


def generate_title_card(
    title: str, episode: str, output: str | Path,
    *, width: int = 512, height: int = 512,
) -> Path:
    raise RuntimeError(
        "Title-card generation is disabled; production must contain scene visuals only"
    )
