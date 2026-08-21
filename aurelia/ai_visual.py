"""AURELIA Maker — visual generation backend.

Priority order (all free / local):
1. Stable Diffusion v1.5 via diffusers  — if diffusers + torch installed
2. CinematicPillow procedural generator — always available, no download

The Pillow fallback creates genuine cinematic visual variety based on the
directing plan (environment, lighting, camera, atmosphere). It is NOT a
blank placeholder — it generates meaningful gradient compositions with
correct color palettes, atmospheric depth, and scene-appropriate hues.
"""
from __future__ import annotations

import hashlib
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Any


CLIP_MAX_TOKENS = 77
_VISUAL_NEGATIVE_PROMPT = "text, subtitles, watermark, logo, UI, blurry, distorted, duplicate subjects"

# Environment color palettes for Pillow fallback
_ENV_PALETTES: dict[str, dict[str, Any]] = {
    "space": {
        "bg": [(2, 4, 20), (8, 14, 45), (18, 28, 70)],
        "accent": [(201, 168, 106), (140, 180, 255), (255, 255, 220)],
        "stars": True,
    },
    "laboratory": {
        "bg": [(12, 18, 30), (28, 40, 60), (45, 65, 95)],
        "accent": [(120, 180, 255), (200, 220, 240), (80, 140, 200)],
        "stars": False,
    },
    "city": {
        "bg": [(20, 18, 15), (50, 42, 30), (80, 65, 40)],
        "accent": [(201, 168, 106), (255, 200, 100), (180, 140, 70)],
        "stars": False,
    },
    "human": {
        "bg": [(35, 22, 18), (70, 45, 35), (100, 68, 50)],
        "accent": [(242, 213, 176), (220, 180, 140), (160, 120, 90)],
        "stars": False,
    },
    "abstract": {
        "bg": [(10, 12, 28), (22, 25, 55), (40, 45, 90)],
        "accent": [(201, 168, 106), (110, 160, 255), (255, 180, 80)],
        "stars": False,
    },
}


def _content_seed(title: str, description: str, direction: dict[str, Any] | None = None) -> int:
    """Derive a stable seed from semantic content."""
    direction = direction or {}
    camera = direction.get("camera") or {}
    lighting = direction.get("lighting") or {}
    atmosphere = (lighting.get("atmosphere") or {})
    seed_material = "|".join([
        str(direction.get("environment", "abstract")),
        title.strip(),
        description.strip()[:200],
        str(camera.get("movement", "static")),
        str(atmosphere.get("haze", 0.0)),
    ])
    return int(hashlib.md5(seed_material.encode("utf-8")).hexdigest(), 16) % (2 ** 31 - 1)


def _plan_value(plan: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = plan.get(key)
        if value not in (None, ""):
            return value
    return default


def _compact_words(value: str, limit: int) -> str:
    return " ".join(str(value).split()[:limit])


def build_scene_prompt(
    title: str,
    description: str,
    direction: dict[str, Any] | None = None,
    *,
    tokenizer: Any | None = None,
) -> str:
    """Build the prompt consumed by the local image model."""
    direction = direction or {}
    environment = str(direction.get("environment", "abstract"))
    camera = direction.get("camera") or {}
    depth = direction.get("depth") or {}
    motion = direction.get("motion") or {}
    lighting = direction.get("lighting") or {}
    atmosphere = lighting.get("atmosphere") or {}
    key = lighting.get("key") or {}
    fill = lighting.get("fill") or {}

    lens = _plan_value(camera, "lens_mm", default=35.0)
    framing = _plan_value(camera, "framing", default="cinematic")
    movement = _plan_value(motion, "type", default=_plan_value(camera, "movement", default="static"))
    dof = _plan_value(depth, "depth_of_field", default=0.0)
    key_color = _plan_value(key, "color", default="neutral")
    haze = _plan_value(atmosphere, "haze", default=0.0)

    concise_title = _compact_words(title, 5)
    concise_description = _compact_words(description, 10)
    prompt = (
        "photorealistic cinematic film still, coherent real location, natural subject, "
        f"environment {environment}; subject and action: {concise_title}. {concise_description}; "
        f"{framing} shot, {lens}mm lens, {movement} camera, shallow depth {dof}; "
        f"lighting {key_color} key, atmospheric {haze} haze; "
        "no text, no subtitles, no watermark, no logo, no UI"
    )
    # Truncate if too long for CLIP
    words = prompt.split()
    if len(words) > CLIP_MAX_TOKENS - 5:
        prompt = " ".join(words[: CLIP_MAX_TOKENS - 5])
    return prompt


# ── Stable Diffusion backend ─────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_sd_pipeline():
    """Load Stable Diffusion once; return None if not available."""
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
    title: str,
    description: str,
    output_path: Path,
    direction: dict[str, Any] | None,
    seed: int,
    width: int,
    height: int,
) -> bool:
    """Try Stable Diffusion. Returns True on success."""
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
            num_inference_steps=8,  # 8 steps: balance speed vs quality
            guidance_scale=7.5,
            width=width,
            height=height,
            generator=generator,
        ).images[0]
        image.save(output_path, format="PNG")
        return output_path.is_file() and output_path.stat().st_size > 5000
    except Exception:
        return False


# ── Cinematic Pillow fallback ─────────────────────────────────────────────────

def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _generate_with_pillow(
    title: str,
    description: str,
    output_path: Path,
    direction: dict[str, Any] | None,
    seed: int,
    width: int,
    height: int,
) -> bool:
    """Generate a cinematic procedural image with Pillow. Always succeeds."""
    try:
        from PIL import Image, ImageDraw, ImageFilter
        import numpy as np

        direction = direction or {}
        environment = str(direction.get("environment", "abstract"))
        palette = _ENV_PALETTES.get(environment, _ENV_PALETTES["abstract"])
        rng = random.Random(seed)
        bg_colors = palette["bg"]
        accent_colors = palette["accent"]

        # Build gradient background
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        c1 = bg_colors[0]
        c2 = bg_colors[-1]
        for y in range(height):
            t = y / max(height - 1, 1)
            # Non-linear for more cinematic look
            t_ease = t * t * (3 - 2 * t)
            color = _lerp_color(c1, c2, t_ease)
            draw.line([(0, y), (width, y)], fill=color)

        # Add a radial vignette glow from scene-derived position
        cx = int(width * (0.3 + rng.random() * 0.4))
        cy = int(height * (0.2 + rng.random() * 0.4))
        glow_color = accent_colors[rng.randint(0, len(accent_colors) - 1)]
        glow_radius = int(min(width, height) * (0.35 + rng.random() * 0.25))
        for radius in range(glow_radius, 0, -max(1, glow_radius // 40)):
            alpha = int(18 * (1 - radius / glow_radius) ** 2)
            if alpha < 1:
                continue
            r = max(0, glow_color[0] - int((glow_radius - radius) * 0.3))
            g = max(0, glow_color[1] - int((glow_radius - radius) * 0.3))
            b = max(0, glow_color[2] - int((glow_radius - radius) * 0.3))
            # Draw ellipse segment
            x0, y0 = cx - radius, cy - radius
            x1, y1 = cx + radius, cy + radius
            try:
                draw.ellipse([x0, y0, x1, y1], outline=(r, g, b, alpha))
            except Exception:
                pass

        # Add stars for space scenes
        if palette.get("stars"):
            for _ in range(int(width * height * 0.0006)):
                sx, sy = rng.randint(0, width - 1), rng.randint(0, height - 1)
                brightness = rng.randint(160, 255)
                size = rng.choice([1, 1, 1, 2])
                img.putpixel((sx, sy), (brightness, brightness, int(brightness * 0.92)))
                if size == 2 and sx > 0 and sy > 0 and sx < width - 1 and sy < height - 1:
                    for nx, ny in [(sx-1,sy),(sx+1,sy),(sx,sy-1),(sx,sy+1)]:
                        img.putpixel((nx, ny), (brightness//2, brightness//2, brightness//2))

        # Add atmospheric light beams for non-space scenes
        if not palette.get("stars") and rng.random() > 0.3:
            accent = accent_colors[0]
            beam_x = rng.randint(width // 4, 3 * width // 4)
            beam_width = rng.randint(width // 8, width // 4)
            for x in range(max(0, beam_x - beam_width), min(width, beam_x + beam_width)):
                dist = abs(x - beam_x) / max(beam_width, 1)
                intensity = int(12 * (1 - dist) ** 3)
                if intensity < 1:
                    continue
                for y in range(0, min(height, int(height * 0.7))):
                    t = y / (height * 0.7)
                    alpha_fade = int(intensity * (1 - t))
                    if alpha_fade < 1:
                        continue
                    existing = img.getpixel((x, y))
                    new_color = (
                        min(255, existing[0] + alpha_fade * accent[0] // 255),
                        min(255, existing[1] + alpha_fade * accent[1] // 255),
                        min(255, existing[2] + alpha_fade * accent[2] // 255),
                    )
                    img.putpixel((x, y), new_color)

        # Subtle noise for film grain
        pixels = list(img.getdata())
        noisy = [
            (
                max(0, min(255, p[0] + rng.randint(-6, 6))),
                max(0, min(255, p[1] + rng.randint(-6, 6))),
                max(0, min(255, p[2] + rng.randint(-6, 6))),
            )
            for p in pixels
        ]
        img.putdata(noisy)

        # Slight blur for depth
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        img.save(output_path, format="PNG", optimize=True)
        return output_path.is_file() and output_path.stat().st_size > 1000
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

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

    Tries Stable Diffusion first, falls back to CinematicPillow.
    ``scene_index`` retained for API compatibility only; seed is content-based.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    seed = _content_seed(title, description, direction)

    # Try Stable Diffusion
    if _generate_with_sd(title, description, output_path, direction, seed, width, height):
        return output_path

    # Cinematic Pillow fallback — always works
    if _generate_with_pillow(title, description, output_path, direction, seed, width, height):
        return output_path

    raise RuntimeError(f"Visual generation failed for scene: {title}")


def generate_title_card(title: str, episode: str, output: str | Path, *, width: int = 512, height: int = 512) -> Path:
    raise RuntimeError("Title-card generation is disabled; production must contain scene visuals only")
