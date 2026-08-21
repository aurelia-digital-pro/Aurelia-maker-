"""AURELIA — Cloud API visual generation backends.

Free tier (no API key required):
  pollinations  — Pollinations.ai FLUX.1, completely free, no account.
                  GET https://image.pollinations.ai/prompt/{prompt}?...
                  Returns real neural FLUX image. Works in CI and production.

Paid tiers (opt-in via environment variables):
  together      — Together.ai FLUX.1-schnell, TOGETHER_API_KEY
  replicate     — Replicate FLUX.1-schnell, REPLICATE_API_TOKEN
  fal           — FAL.ai FLUX.1-schnell, FAL_KEY

Priority (auto):
  pollinations → together → replicate → fal

Override with: AURELIA_VISUAL_BACKEND=pollinations|together|replicate|fal|pillow
Disable all cloud: AURELIA_FORCE_FALLBACK=1
"""
from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
from pathlib import Path


_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"
_POLLINATIONS_TIMEOUT = 90
_API_TIMEOUT = 90


def _via_pollinations(
    prompt: str, seed: int, width: int, height: int, output_path: Path
) -> bool:
    """Pollinations.ai FLUX.1 — free, no API key. Returns True on success."""
    try:
        encoded = urllib.parse.quote(prompt[:400], safe="")
        url = (
            f"{_POLLINATIONS_BASE}/{encoded}"
            f"?width={width}&height={height}&seed={seed % (2**31)}"
            f"&nologo=true&model=flux&enhance=false"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AURELIA-Maker/2.0", "Accept": "image/*"},
        )
        with urllib.request.urlopen(req, timeout=_POLLINATIONS_TIMEOUT) as resp:
            data = resp.read()
        if len(data) < 5000:
            return False
        output_path.write_bytes(data)
        # Normalize to PNG via PIL if available
        try:
            from PIL import Image
            with Image.open(output_path) as img:
                img.convert("RGB").save(output_path, format="PNG", optimize=True)
        except Exception:
            pass
        return output_path.is_file() and output_path.stat().st_size > 5000
    except Exception:
        return False


def _via_together(
    prompt: str, seed: int, width: int, height: int, output_path: Path
) -> bool:
    """Together.ai FLUX.1-schnell. Requires TOGETHER_API_KEY."""
    api_key = os.environ.get("TOGETHER_API_KEY", "")
    if not api_key:
        return False
    try:
        import base64
        import json as _json
        payload = _json.dumps({
            "model": "black-forest-labs/FLUX.1-schnell-Free",
            "prompt": prompt,
            "width": width,
            "height": height,
            "steps": 4,
            "n": 1,
            "seed": seed % (2**31),
            "response_format": "b64_json",
        }).encode()
        request = urllib.request.Request(
            "https://api.together.xyz/v1/images/generations",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=_API_TIMEOUT) as resp:
            result = _json.loads(resp.read())
        b64 = result["data"][0]["b64_json"]
        img_data = base64.b64decode(b64)
        if len(img_data) < 5000:
            return False
        output_path.write_bytes(img_data)
        return output_path.is_file() and output_path.stat().st_size > 5000
    except Exception:
        return False


def _via_replicate(
    prompt: str, seed: int, width: int, height: int, output_path: Path
) -> bool:
    """Replicate FLUX.1-schnell. Requires REPLICATE_API_TOKEN."""
    api_key = os.environ.get("REPLICATE_API_TOKEN", "")
    if not api_key:
        return False
    try:
        import json as _json
        payload = _json.dumps({
            "version": "black-forest-labs/flux-schnell",
            "input": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "num_inference_steps": 4,
                "seed": seed % (2**31),
                "output_format": "png",
                "output_quality": 85,
            },
        }).encode()
        request = urllib.request.Request(
            "https://api.replicate.com/v1/predictions",
            data=payload,
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            },
        )
        with urllib.request.urlopen(request, timeout=_API_TIMEOUT) as resp:
            result = _json.loads(resp.read())
        output_urls = result.get("output") or []
        if not output_urls:
            return False
        url = output_urls[0] if isinstance(output_urls, list) else output_urls
        img_req = urllib.request.Request(
            url, headers={"User-Agent": "AURELIA-Maker/2.0"}
        )
        with urllib.request.urlopen(img_req, timeout=60) as img_resp:
            img_data = img_resp.read()
        if len(img_data) < 5000:
            return False
        output_path.write_bytes(img_data)
        return output_path.is_file() and output_path.stat().st_size > 5000
    except Exception:
        return False


def _via_fal(
    prompt: str, seed: int, width: int, height: int, output_path: Path
) -> bool:
    """FAL.ai FLUX.1-schnell. Requires FAL_KEY."""
    api_key = os.environ.get("FAL_KEY", "")
    if not api_key:
        return False
    try:
        import json as _json
        payload = _json.dumps({
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_inference_steps": 4,
            "seed": seed % (2**31),
            "num_images": 1,
            "enable_safety_checker": False,
        }).encode()
        request = urllib.request.Request(
            "https://fal.run/fal-ai/flux/schnell",
            data=payload,
            headers={
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=_API_TIMEOUT) as resp:
            result = _json.loads(resp.read())
        images = result.get("images", [])
        if not images:
            return False
        url = images[0].get("url", "")
        if not url:
            return False
        img_req = urllib.request.Request(
            url, headers={"User-Agent": "AURELIA-Maker/2.0"}
        )
        with urllib.request.urlopen(img_req, timeout=60) as img_resp:
            img_data = img_resp.read()
        if len(img_data) < 5000:
            return False
        output_path.write_bytes(img_data)
        return output_path.is_file() and output_path.stat().st_size > 5000
    except Exception:
        return False


_BACKEND_FUNCTIONS: dict = {
    "pollinations": _via_pollinations,
    "together":     _via_together,
    "replicate":    _via_replicate,
    "fal":          _via_fal,
}

_DEFAULT_PRIORITY = ["pollinations", "together", "replicate", "fal"]


def generate_via_api(
    prompt: str,
    seed: int,
    width: int,
    height: int,
    output_path: Path,
    logger=None,
) -> tuple[bool, str]:
    """Try cloud API backends in priority order.

    Returns (success: bool, backend_name: str).
    Pollinations.ai is always tried first (free, no API key).
    """
    def _log(msg: str) -> None:
        if logger:
            logger(msg)

    if os.environ.get("AURELIA_FORCE_FALLBACK") == "1":
        return False, ""

    forced = os.environ.get("AURELIA_VISUAL_BACKEND", "").lower().strip()
    if forced and forced in _BACKEND_FUNCTIONS:
        priority = [forced]
    elif forced == "pillow":
        return False, ""
    else:
        priority = list(_DEFAULT_PRIORITY)

    for backend_name in priority:
        fn = _BACKEND_FUNCTIONS[backend_name]
        try:
            _log(f"[VISUAL_API] {backend_name}...")
            ok = fn(prompt, seed, width, height, output_path)
            if ok:
                _log(f"[VISUAL_API] {backend_name} OK")
                # Polite delay for free Pollinations.ai tier
                if backend_name == "pollinations":
                    time.sleep(0.6)
                return True, backend_name
            _log(f"[VISUAL_API] {backend_name}: empty response")
        except Exception as exc:
            _log(f"[VISUAL_API] {backend_name}: {exc}")

    return False, ""


def api_status() -> dict:
    """Return configured API backends for /api/status."""
    return {
        "pollinations": True,
        "together":  bool(os.environ.get("TOGETHER_API_KEY")),
        "replicate": bool(os.environ.get("REPLICATE_API_TOKEN")),
        "fal":       bool(os.environ.get("FAL_KEY")),
        "forced_backend": os.environ.get("AURELIA_VISUAL_BACKEND", "auto"),
    }


__all__ = ["generate_via_api", "api_status"]
