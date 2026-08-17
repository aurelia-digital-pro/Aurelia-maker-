"""Local AI visual backend for AURELIA Maker.

Uses Stable Diffusion through diffusers on the local machine. No hosted API is
required. The model is downloaded once into the local Hugging Face cache.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

_MODEL_ID = os.getenv("AURELIA_IMAGE_MODEL", "runwayml/stable-diffusion-v1-5")
_PIPE = None


def _pipeline():
    global _PIPE
    if _PIPE is not None:
        return _PIPE

    import torch
    from diffusers import StableDiffusionPipeline

    if torch.cuda.is_available():
        dtype = torch.float16
        device = "cuda"
    else:
        dtype = torch.float32
        device = "cpu"

    pipe = StableDiffusionPipeline.from_pretrained(
        _MODEL_ID,
        torch_dtype=dtype,
        safety_checker=None,
    )
    pipe = pipe.to(device)
    if device == "cpu":
        pipe.enable_attention_slicing()

    _PIPE = pipe
    return _PIPE


def _scene_prompt(scene_index: int, title: str, text: str) -> str:
    return (
        "cinematic documentary frame, AURELIA visual language, "
        "photorealistic, natural volumetric light, restrained contrast, "
        "35mm cinematography, realistic scale, coherent architecture, "
        "no text, no captions, no logos, no watermark; "
        f"scene {scene_index + 1}: {title}; {text}"
    )


def generate_scene_image(
    scene_index: int,
    title: str,
    text: str,
    output: str | Path,
    width: int = 768,
    height: int = 512,
) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pipe = _pipeline()
    generator = None
    try:
        import torch
        generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu")
        generator.manual_seed(41000 + scene_index)
    except Exception:
        pass

    image = pipe(
        prompt=_scene_prompt(scene_index, title, text),
        num_inference_steps=int(os.getenv("AURELIA_IMAGE_STEPS", "20")),
        guidance_scale=float(os.getenv("AURELIA_IMAGE_GUIDANCE", "7.0")),
        width=width,
        height=height,
        generator=generator,
    ).images[0]

    image.convert("RGB").save(output_path, "PNG", optimize=True)
    return output_path


def generate_title_card(
    title: str,
    subtitle: str,
    output: str | Path,
    width: int = 768,
    height: int = 512,
) -> Path:
    # Title cards deliberately remain deterministic and legible; generated
    # scene plates carry the AI visual content while FFmpeg handles motion.
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (4, 7, 18))
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(24, width // 16))
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(16, width // 32))
    except OSError:
        font = ImageFont.load_default()
        small = font
    draw.text((width // 2, height // 2 - 35), title, fill=(235, 235, 235), font=font, anchor="mm")
    draw.text((width // 2, height // 2 + 35), subtitle, fill=(180, 195, 220), font=small, anchor="mm")
    image.save(output_path, "PNG", optimize=True)
    return output_path


__all__ = ["generate_scene_image", "generate_title_card"]
