"""Real local text-to-image backend for AURELIA Maker."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


CLIP_MAX_TOKENS = 77
_VISUAL_NEGATIVE_PROMPT = "text, subtitles, watermark, logo, UI, blurry, distorted, duplicate subjects"


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


def _compact_words(value: str, limit: int) -> str:
    return " ".join(str(value).split()[:limit])


def _prompt_token_count(text: str, tokenizer: Any | None) -> int:
    if tokenizer is None:
        return len(text.split())
    return len(tokenizer(text, truncation=False, add_special_tokens=True)["input_ids"])


def build_scene_prompt(
    title: str,
    description: str,
    direction: dict[str, Any] | None = None,
    *,
    tokenizer: Any | None = None,
) -> str:
    """Build the exact semantic prompt consumed by the local image model."""
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

    concise_title = _compact_words(title, 5)
    concise_description = _compact_words(description, 10)
    prompt = (
        "photorealistic cinematic film still, coherent real location, natural subject, "
        f"environment {environment}; subject and action: {concise_title}. {concise_description}; "
        f"{framing} shot, {lens}mm lens, {movement} camera, shallow depth {dof}; "
        f"lighting {key_color} key and {fill_color} fill, atmospheric {haze} haze; "
        "no text, no subtitles, no watermark, no logo, no UI"
    )
    if _prompt_token_count(prompt, tokenizer) > CLIP_MAX_TOKENS:
        raise ValueError(f"Scene prompt exceeds the CLIP limit ({CLIP_MAX_TOKENS} tokens)")
    return prompt


def _content_seed(title: str, description: str, direction: dict[str, Any] | None = None) -> int:
    """Derive a stable seed from semantic content, never from scene position."""
    direction = direction or {}
    camera = direction.get("camera") or {}
    depth = direction.get("depth") or {}
    motion = direction.get("motion") or {}
    lighting = direction.get("lighting") or {}
    atmosphere = lighting.get("atmosphere") or {}
    key = lighting.get("key") or {}
    fill = lighting.get("fill") or {}
    rim = lighting.get("rim") or {}
    seed_material = "|".join(
        [
            str(direction.get("environment", "abstract")),
            title.strip(),
            description.strip(),
            str(_plan_value(camera, "lens_mm", default=35.0)),
            str(_plan_value(camera, "framing", default="cinematic")),
            str(_plan_value(motion, "type", default=_plan_value(camera, "movement", default="static"))),
            str(_plan_value(depth, "depth_of_field", default=0.0)),
            str(_plan_value(key, "color", default="neutral")),
            str(_plan_value(fill, "color", default="neutral")),
            str(_plan_value(rim, "color", default="neutral")),
            str(_plan_value(atmosphere, "fog", default=0.0)),
            str(_plan_value(atmosphere, "haze", default=0.0)),
            str(_plan_value(atmosphere, "dust", default=0.0)),
        ]
    )
    return sum((position + 1) * ord(char) for position, char in enumerate(seed_material)) % (2**31 - 1)


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
    excluded from the prompt and random seed so visual identity cannot be
    selected by scene position.
    """
    import torch

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pipe = get_pipeline()
    prompt = build_scene_prompt(title, description, direction, tokenizer=pipe.tokenizer)
    negative = _VISUAL_NEGATIVE_PROMPT
    if _prompt_token_count(negative, pipe.tokenizer) > CLIP_MAX_TOKENS:
        raise RuntimeError("Configured negative prompt exceeds the CLIP token limit")
    generator = torch.Generator(device="cpu").manual_seed(_content_seed(title, description, direction))

    image = pipe(
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
    raise RuntimeError("Title-card generation is disabled in production")

    """Legacy helper retained only to give old callers an explicit failure."""
    import os
    import subprocess
    from PIL import ImageFont

    candidates: list[Path] = []
    configured = os.environ.get("AURELIA_TITLE_FONT")
    if configured:
        candidates.append(Path(configured))

    candidates.extend(
        Path(path)
        for path in (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf",
            "/usr/local/share/fonts/DejaVuSans.ttf",
            r"C:\\Windows\\Fonts\\segoeui.ttf",
            r"C:\\Windows\\Fonts\\arial.ttf",
        )
    )

    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", "sans:lang=ar"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidates.insert(0, Path(result.stdout.strip()))
    except OSError:
        pass

    for root in (
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts",
    ):
        if root.exists():
            candidates.extend(sorted(root.rglob("*.ttf")))
            candidates.extend(sorted(root.rglob("*.otf")))

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen or not candidate.is_file():
            continue
        seen.add(key)
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except (OSError, UnicodeError):
            continue

    raise RuntimeError(
        "No Unicode-capable TrueType/OpenType font is available for the AURELIA title card. "
        "Install a Unicode font such as DejaVu Sans or set AURELIA_TITLE_FONT to a valid font file."
    )


def generate_title_card(title: str, episode: str, output: str | Path, *, width: int = 512, height: int = 512) -> Path:
    raise RuntimeError("Title-card generation is disabled; production must contain scene visuals only")

    """Legacy API retained only to give old callers an explicit failure."""
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
