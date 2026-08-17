"""Real local text-to-image backend for AURELIA Maker."""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache


def _pipeline():
    import torch
    from diffusers import StableDiffusionPipeline

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


@lru_cache(maxsize=1)
def get_pipeline():
    return _pipeline()


def generate_scene_image(
    scene_index: int,
    title: str,
    description: str,
    output: str | Path,
    *,
    width: int = 512,
    height: int = 512,
) -> Path:
    """Generate a real AI image locally from the scene prompt."""
    import torch

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = (
        "cinematic documentary still, AURELIA visual language, "
        "photorealistic, dramatic natural lighting, deep blacks, subtle gold and blue accents, "
        "35mm composition, atmospheric depth, coherent architecture, no text, "
        f"scene {scene_index + 1}: {title}. {description}"
    )
    negative = "text, watermark, logo, UI, low quality, blurry, distorted"
    generator = torch.Generator(device="cpu").manual_seed(4100 + scene_index)
    image = get_pipeline()(
        prompt=prompt,
        negative_prompt=negative,
        num_inference_steps=2,
        guidance_scale=7.0,
        width=width,
        height=height,
        generator=generator,
    ).images[0]
    image.save(output_path, format="PNG")
    return output_path


def _title_font(size: int):
    """Return a Unicode-capable local font; keep a safe fallback for minimal runners."""
    from PIL import ImageFont

    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def generate_title_card(title: str, episode: str, output: str | Path, *, width: int = 512, height: int = 512) -> Path:
    """Generate a deterministic title card without replacing the AI scene backend."""
    from PIL import Image, ImageDraw

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (4, 6, 10))
    draw = ImageDraw.Draw(image)
    title_font = _title_font(max(18, width // 24))
    episode_font = _title_font(max(14, width // 32))
    draw.text((width // 2, height // 2 - 18), title, fill=(201, 168, 106), anchor="mm", font=title_font)
    draw.text((width // 2, height // 2 + 22), episode, fill=(220, 225, 232), anchor="mm", font=episode_font)
    image.save(output_path, format="PNG")
    return output_path
