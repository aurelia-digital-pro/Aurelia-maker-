"""Real local text-to-image backend for AURELIA Maker."""
from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import Any


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


def _plan_value(plan: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = plan.get(key)
        if value not in (None, ""):
            return value
    return default


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
    """Generate a local AI image from scene content plus its semantic directing plan.

    ``scene_index`` is retained for API compatibility only. It is deliberately
    excluded from both the prompt and the random seed so that visual identity
    cannot be selected by scene position.
    """
    import torch

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    direction = direction or {}
    environment = str(direction.get("environment", "abstract"))
    camera = direction.get("camera") or {}
    depth = direction.get("depth") or {}
    motion = direction.get("motion") or {}
    lighting = direction.get("lighting") or {}
    atmosphere = lighting.get("atmosphere") or {}
    key = lighting.get("key") or {}
    fill = lighting.get("fill") or {}
    rim = lighting.get("rim") or {}

    lens = _plan_value(camera, "lens_mm", default=35.0)
    framing = _plan_value(camera, "framing", default="cinematic")
    movement = _plan_value(motion, "type", default=_plan_value(camera, "movement", default="static"))
    dof = _plan_value(depth, "depth_of_field", default=0.0)
    key_color = _plan_value(key, "color", default="neutral")
    fill_color = _plan_value(fill, "color", default="neutral")
    rim_color = _plan_value(rim, "color", default="neutral")
    fog = _plan_value(atmosphere, "fog", default=0.0)
    haze = _plan_value(atmosphere, "haze", default=0.0)
    dust = _plan_value(atmosphere, "dust", default=0.0)

    prompt = (
        "cinematic documentary still, AURELIA visual language, "
        "photorealistic, coherent physical environment, natural subject placement, "
        "deep blacks, subtle gold and blue accents, no text, no watermark, no logo, "
        f"semantic environment: {environment}, "
        f"scene meaning: {title}. {description}, "
        f"cinematography: {framing} framing, {lens}mm lens, {movement} camera movement, "
        f"depth of field: {dof}, "
        f"lighting: key {key_color}, fill {fill_color}, rim {rim_color}, "
        f"atmosphere: fog {fog}, haze {haze}, dust {dust}"
    )
    negative = "text, subtitles, narration, watermark, logo, UI, low quality, blurry, distorted, duplicate subjects"

    # Content, not scene position, determines the deterministic seed. This
    # keeps identical content stable while preventing index-based templates.
    seed_material = "|".join(
        [
            environment,
            title.strip(),
            description.strip(),
            str(lens),
            str(framing),
            str(movement),
            str(dof),
            str(key_color),
            str(fill_color),
            str(rim_color),
            str(fog),
            str(haze),
            str(dust),
        ]
    )
    seed = sum((position + 1) * ord(char) for position, char in enumerate(seed_material)) % (2**31 - 1)
    generator = torch.Generator(device="cpu").manual_seed(seed)

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
