"""AURELIA — primary visual backend router.

Priority chain (first available wins):
  1. Stable Diffusion (diffusers) — local GPU/CPU, real neural images
  2. Cloud API (Pollinations.ai FLUX free → Together → Replicate → FAL)
  3. Pillow procedural            — guaranteed local fallback, always works

Rules:
- SD failure is NEVER silent. WARNING is logged and chain continues.
- Cloud API failure is logged per backend; all are tried before Pillow.
- Pillow is NEVER declared as primary; it is "pillow-fallback" in provenance.
- AURELIA_FORCE_FALLBACK=1 skips SD and cloud, forces Pillow immediately.
- AURELIA_VISUAL_BACKEND=pollinations|together|replicate|fal|pillow overrides cloud priority.
- SD model configured via AURELIA_SD_MODEL env or ai_config.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── SD availability probe (cached per process) ───────────────────────────────

_SD_AVAILABLE: bool | None = None
_SD_MODEL_ID: str = ""
_SD_PROBE_ERROR: str = ""


def _cfg() -> dict[str, Any]:
    for p in [
        Path(__file__).resolve().parent / "ai_config.json",
        Path(__file__).resolve().parents[1] / "ai_config.json",
    ]:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def probe_sd_backend(force: bool = False) -> dict[str, Any]:
    """Probe whether a local Stable Diffusion pipeline can be loaded.

    Returns: {available, model_id, device, error}
    Caches result after first call unless force=True.
    """
    global _SD_AVAILABLE, _SD_MODEL_ID, _SD_PROBE_ERROR

    if _SD_AVAILABLE is not None and not force:
        return {
            "available": _SD_AVAILABLE,
            "model_id":  _SD_MODEL_ID,
            "error":     _SD_PROBE_ERROR,
        }

    if os.environ.get("AURELIA_FORCE_FALLBACK") == "1":
        _SD_AVAILABLE = False
        _SD_PROBE_ERROR = "AURELIA_FORCE_FALLBACK=1 — SD disabled by env"
        return {"available": False, "model_id": "", "error": _SD_PROBE_ERROR}

    cfg = _cfg()
    model_id = (
        os.environ.get("AURELIA_SD_MODEL")
        or cfg.get("model", {}).get("id", "")
        or "stabilityai/stable-diffusion-2-1"
    )
    try:
        import torch      # type: ignore  # noqa: F401
        import diffusers  # type: ignore  # noqa: F401
        _SD_AVAILABLE = True
        _SD_MODEL_ID  = model_id
        _SD_PROBE_ERROR = ""
        return {"available": True, "model_id": model_id, "error": ""}
    except ImportError as e:
        _SD_AVAILABLE = False
        _SD_MODEL_ID  = ""
        _SD_PROBE_ERROR = f"diffusers/torch not installed: {e}"
        return {"available": False, "model_id": "", "error": _SD_PROBE_ERROR}
    except Exception as e:
        _SD_AVAILABLE = False
        _SD_MODEL_ID  = ""
        _SD_PROBE_ERROR = str(e)
        return {"available": False, "model_id": "", "error": _SD_PROBE_ERROR}


_SD_PIPELINE = None


def _load_sd_pipeline() -> Any:
    """Load and cache the SD pipeline. Raises on failure."""
    global _SD_PIPELINE
    if _SD_PIPELINE is not None:
        return _SD_PIPELINE
    import torch
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

    cfg = _cfg()
    model_id = (
        _SD_MODEL_ID
        or os.environ.get("AURELIA_SD_MODEL")
        or "stabilityai/stable-diffusion-2-1"
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype  = torch.float16 if device == "cuda" else torch.float32
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id, torch_dtype=dtype,
        safety_checker=None, requires_safety_checker=False,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    if device == "cuda":
        pipe = pipe.to(device)
        try:
            pipe.enable_attention_slicing()
            pipe.enable_vae_slicing()
        except Exception:
            pass
    _SD_PIPELINE = pipe
    return pipe


def _generate_sd(
    prompt: str, negative_prompt: str, seed: int,
    width: int, height: int, steps: int, guidance: float, output: Path,
) -> bool:
    """Run SD inference. Returns True on success."""
    try:
        import torch
        pipe = _load_sd_pipeline()
        generator = torch.Generator().manual_seed(seed)
        result = pipe(
            prompt, negative_prompt=negative_prompt or None,
            width=width, height=height,
            num_inference_steps=steps, guidance_scale=guidance,
            generator=generator,
        )
        result.images[0].save(str(output))
        return output.is_file() and output.stat().st_size > 1000
    except Exception:
        return False


def _generate_pillow(
    scene_index: int, title: str, text: str, output: Path,
    direction: dict[str, Any] | None,
    width: int, height: int,
) -> None:
    """Pillow procedural fallback — always available."""
    from .ai_visual import generate_scene_image
    generate_scene_image(
        scene_index, title, text, output,
        direction=direction, width=width, height=height,
    )


# ── public entrypoint ─────────────────────────────────────────────────────────

def generate_visual(
    scene_index: int,
    title: str,
    text: str,
    output: Path | str,
    direction: dict[str, Any] | None = None,
    width: int = 512,
    height: int = 512,
    visual_note: str = "",
    run_id: str = "",
    logger: Any | None = None,
) -> dict[str, Any]:
    """Generate one scene visual.

    Chain:  SD (local GPU) → Cloud API (Pollinations.ai FLUX free → paid) → Pillow
    Returns provenance dict. Never raises on fallback — always produces a file.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(msg: str) -> None:
        if logger is not None:
            logger(msg)

    cfg      = _cfg()
    img_cfg  = cfg.get("image", cfg.get("visual", {}))
    steps    = int(img_cfg.get("steps", 20))
    guidance = float(img_cfg.get("guidance_scale", 7.5))
    neg_p    = img_cfg.get("negative_prompt", "")

    # Build cinematic prompt
    try:
        from .ai_visual import build_scene_prompt
        prompt = build_scene_prompt(title, text, direction)
    except Exception:
        env = (direction or {}).get("environment", "abstract")
        prompt = f"cinematic film still, {env} setting, {title}: {text}"
    if visual_note:
        prompt = f"{prompt}, {visual_note}"

    seed_str = f"{title}|{text}|{visual_note}|{run_id}"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)

    t0 = time.monotonic()
    backend_used    = "unknown"
    fallback_reason = ""

    # ── 1. Stable Diffusion (local) ──────────────────────────────────────
    probe = probe_sd_backend()
    if probe["available"]:
        _log(f"[VISUAL] Scene {scene_index+1}: SD ({probe['model_id']})")
        try:
            ok = _generate_sd(
                prompt=prompt, negative_prompt=neg_p, seed=seed,
                width=width, height=height,
                steps=steps, guidance=guidance, output=output_path,
            )
            if ok:
                backend_used = "stable-diffusion"
                _log(f"[VISUAL] Scene {scene_index+1}: SD OK ({time.monotonic()-t0:.1f}s)")
            else:
                fallback_reason = "SD produced empty output"
                _log(f"[VISUAL][WARNING] Scene {scene_index+1}: SD failed — {fallback_reason}")
        except Exception as exc:
            fallback_reason = str(exc)
            _log(f"[VISUAL][WARNING] Scene {scene_index+1}: SD exception — {fallback_reason}")
    else:
        fallback_reason = probe["error"]
        _log(f"[VISUAL] Scene {scene_index+1}: SD unavailable — {fallback_reason}")

    # ── 2. Cloud API (Pollinations.ai FLUX free → Together → Replicate → FAL) ─
    if backend_used != "stable-diffusion":
        from .visual_api import generate_via_api
        _log(f"[VISUAL] Scene {scene_index+1}: trying cloud API...")
        api_ok, api_backend = generate_via_api(
            prompt=prompt, seed=seed, width=width, height=height,
            output_path=output_path, logger=_log,
        )
        if api_ok:
            backend_used = f"cloud-api/{api_backend}"
            _log(
                f"[VISUAL] Scene {scene_index+1}: cloud OK via {api_backend}"
                f" ({time.monotonic()-t0:.1f}s)"
            )
        else:
            if not fallback_reason:
                fallback_reason = "all cloud API backends unavailable or timed out"
            _log(
                f"[VISUAL][FALLBACK] Scene {scene_index+1}: cloud API failed — "
                f"{fallback_reason}"
            )

    # ── 3. Pillow procedural (guaranteed fallback) ────────────────────────
    if not backend_used.startswith(("stable-diffusion", "cloud-api")):
        _log(f"[VISUAL][FALLBACK] Scene {scene_index+1}: Pillow procedural")
        _generate_pillow(scene_index, title, text, output_path, direction, width, height)
        backend_used = "pillow-fallback"

    if not output_path.is_file() or output_path.stat().st_size < 500:
        raise RuntimeError(
            f"All visual backends failed for scene {scene_index+1}: {output_path}"
        )

    sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
    is_fallback = backend_used == "pillow-fallback"
    return {
        "backend":        backend_used,
        "fallback":       is_fallback,
        "fallback_reason": fallback_reason if is_fallback else "",
        "prompt":         prompt,
        "seed":           seed,
        "width":          width,
        "height":         height,
        "steps":          steps,
        "guidance_scale": guidance,
        "elapsed_s":      round(time.monotonic() - t0, 2),
        "sha256":         sha,
        "path":           str(output_path.resolve()),
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "scene_index":    scene_index,
        "run_id":         run_id,
    }


def backend_status() -> dict[str, Any]:
    """Return current backend availability for /api/status."""
    from .visual_api import api_status
    probe  = probe_sd_backend()
    api_st = api_status()
    return {
        "sd_available":  probe["available"],
        "sd_model":      probe["model_id"],
        "sd_error":      probe["error"],
        "cloud_api":     api_st,
        "pillow":        True,
        "primary":       (
            "stable-diffusion" if probe["available"]
            else f"cloud-api/{api_st.get('forced_backend','pollinations')}"
            if not os.environ.get("AURELIA_FORCE_FALLBACK")
            else "pillow-fallback"
        ),
        "tts_backends":  _probe_tts(),
    }


def _probe_tts() -> list[str]:
    import shutil
    available = []
    try:
        import kokoro  # type: ignore # noqa: F401
        available.append("kokoro")
    except Exception:
        pass
    if shutil.which("piper") or shutil.which("piper-tts"):
        available.append("piper")
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        available.append("espeak-ng")
    try:
        import pyttsx3  # type: ignore # noqa: F401
        available.append("pyttsx3")
    except Exception:
        pass
    return available


__all__ = ["generate_visual", "probe_sd_backend", "backend_status"]
