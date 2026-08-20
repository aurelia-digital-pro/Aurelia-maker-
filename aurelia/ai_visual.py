"""Real local text-to-image backend for AURELIA Maker.

This file was hardened to read aurelia/ai_config.json and to fail-closed with
clear instructions when the configured Hugging Face model requires an auth
token or when runtime dependencies are missing.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


def _load_config() -> dict[str, Any]:
    cfg_path = Path(__file__).parent / "ai_config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pipeline():
    # Import-time checks with clear error messages
    try:
        import torch
    except Exception as exc:  # pragma: no cover - runtime environment
        raise RuntimeError(
            "PyTorch is required for the local diffusers backend. Install it e.g.:\n"
            "  pip install torch torchvision --extra-index-url https://download.pytorch.org/whl/cpu"
        ) from exc

    try:
        from diffusers import StableDiffusionPipeline
    except Exception as exc:  # pragma: no cover - runtime environment
        raise RuntimeError(
            "diffusers is required for the local image backend. Install it with:\n"
            "  pip install diffusers[torch] transformers accelerate" 
        ) from exc

    cfg = _load_config()
    model_cfg = cfg.get("model") or {}
    model_id = model_cfg.get("id") or model_cfg.get("model_id") or "stabilityai/stable-diffusion-2-1"

    requires_token = bool(model_cfg.get("requires_token", False))
    cache_dir = cfg.get("cache_dir") or "~/.cache/aurelia/models"
    cache_dir = Path(cache_dir).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # If config declares the model requires a token, ensure the operator has set it
    if requires_token and os.environ.get("HUGGINGFACE_HUB_TOKEN") in (None, ""):
        raise RuntimeError(
            "The configured image model requires Hugging Face authentication but HUGGINGFACE_HUB_TOKEN is not set.\n"
            "To fix, either: \n"
            "  1) run: huggingface-cli login  (and provide a valid token), or\n"
            "  2) set environment variable HUGGINGFACE_HUB_TOKEN=<token> before running this production.\n"
            "If you prefer to use a local cached model, place the model files under the cache dir and set the model id in aurelia/ai_config.json accordingly.\n"
        )

    # Set device / precision according to config but keep safe defaults
    device_policy = (cfg.get("device_policy") or "auto").lower()
    precision = (cfg.get("precision") or "fp32").lower()

    # Determine device
    device = "cpu"
    if device_policy == "auto":
        try:
            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            device = "cpu"
    elif device_policy in ("cuda", "gpu"):
        device = "cuda"
    else:
        device = "cpu"

    # Choose dtype
    torch_dtype = torch.float32
    if precision in ("fp16", "fp_16", "float16") and device == "cuda":
        torch_dtype = torch.float16

    # Attempt to load the pipeline from pretrained. Provide cache_dir and auth handling.
    try:
        pipe = StableDiffusionPipeline.from_pretrained(
            model_id,
            cache_dir=str(cache_dir),
            torch_dtype=torch_dtype,
        )
    except Exception as exc:  # pragma: no cover - runtime environment
        # Surface a helpful message rather than failing with a raw stack trace
        raise RuntimeError(
            f"Failed to load model '{model_id}' from Hugging Face.\n"
            "Possible causes: model not downloaded, authentication required, or incompatible local environment.\n"
            "Suggested actions:\n"
            "  - If the model requires auth, run: huggingface-cli login\n"
            "  - Pre-download the model into the configured cache_dir (see aurelia/ai_config.json)\n"
            "  - Ensure compatible torch/diffusers versions are installed and sufficient RAM/VRAM is available.\n"
            f"Underlying error: {exc}") from exc

    # Move to device and configure performance helpers
    try:
        pipe = pipe.to(device)
        # enable attention slicing to reduce peak memory
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        if hasattr(pipe, "set_progress_bar_config"):
            pipe.set_progress_bar_config(disable=True)
    except Exception:
        # Best-effort; if this fails, we'll still return the pipeline object
        pass

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


def build_scene_prompt(title: str, description: str, direction: dict[str, Any] | None = None) -> str:
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

    return (
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
    try:
        import torch
    except Exception:
        raise RuntimeError("PyTorch is required to generate images. Install it before running production.")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = build_scene_prompt(title, description, direction)
    negative = "text, subtitles, narration, watermark, logo, UI, low quality, blurry, distorted, duplicate subjects"

    # Use stable content-derived seed
    generator = torch.Generator(device="cpu").manual_seed(_content_seed(title, description, direction))

    # Run the pipeline. Any pipeline errors should fail the job clearly.
    pipe = get_pipeline()
    result = pipe(
        prompt=prompt,
        negative_prompt=negative,
        num_inference_steps=2,
        guidance_scale=7.0,
        width=width,
        height=height,
        generator=generator,
    )
    image = result.images[0]
    image.save(output_path, format="PNG")

    return output_path


def _title_font(size: int):
    """Return a real Unicode-capable font; never fall back to Pillow's Latin-1 bitmap font."""
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
    """Generate a deterministic Unicode-safe title card without replacing the AI scene backend."""
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
