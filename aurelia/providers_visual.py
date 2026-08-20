"""Visual provider adapter for canonical AURELIA production.

This module provides a single entrypoint `generate_scene_image_with_provenance`
that is used by the canonical EpisodeProduction. It wraps the repository's
`aurelia.ai_visual` backend and records provenance next to generated assets.

Behavior:
- Production (canonical) will call this provider. Any raised exception is
  considered a production failure (FAIL-CLOSED).
- A test-only stub can be enabled by setting AURELIA_TEST_STUB=1 in the
  environment; this is only for CI cheap-gates and MUST NOT be enabled in
  production runs.

The provider reads ai_config.json for model metadata used in provenance.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from . import ai_visual

CONFIG_PATH = Path(__file__).resolve().parents[0] / "ai_config.json"


class VisualGenerationError(RuntimeError):
    pass


def _read_config() -> Dict[str, Any]:
    try:
        # prefer aurelia/ai_config.json next to package root
        cfg_path = Path(__file__).resolve().parents[1] / "ai_config.json"
        if not cfg_path.exists():
            cfg_path = CONFIG_PATH
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _write_provenance(asset_path: Path, provenance: Dict[str, Any]) -> None:
    prov_path = asset_path.with_suffix(asset_path.suffix + ".prov.json")
    prov_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_scene_image_with_provenance(
    scene_index: int,
    title: str,
    text: str,
    output: str | Path,
    direction: dict | None = None,
) -> Tuple[Path, Dict[str, Any]]:
    """Generate a scene image and return (path, provenance).

    Production default: call the repository ai_visual.generate_scene_image which
    uses an open-source local pipeline. If that code raises, treat as fatal.

    In CI/test only: if AURELIA_TEST_STUB=1 is present, produce a tiny PNG stub
    (deterministic) and record provenance as stubbed.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # allow explicit test stub but DEFAULT is real AI backend
    if os.environ.get("AURELIA_TEST_STUB") == "1":
        # test stub: write a 16x16 PNG using PIL (bundled in repo requirements)
        try:
            from PIL import Image, ImageDraw
        except Exception as e:
            raise VisualGenerationError(f"Test stub requires Pillow: {e}")
        img = Image.new("RGB", (64, 36), (16 + (scene_index % 200), 32, 48))
        draw = ImageDraw.Draw(img)
        draw.text((4, 14), f"S{scene_index+1}", fill=(255, 255, 255))
        img.save(output_path, format="PNG")
        sha = _sha256(output_path)
        prov = {
            "backend": "test-stub",
            "model_id": None,
            "model_source": None,
            "model_revision": None,
            "prompt": f"TEST-STUB: {title} -- {text}",
            "negative_prompt": None,
            "seed": 0,
            "width": 64,
            "height": 36,
            "steps": 0,
            "guidance_scale": None,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "sha256": sha,
            "path": str(output_path),
            "scene_index": scene_index,
        }
        _write_provenance(output_path, prov)
        return output_path, prov

    # Real backend path
    cfg = _read_config()
    model_info = cfg.get("model", {})
    image_cfg = cfg.get("image", {})

    # Build prompt via ai_visual helper if available
    try:
        prompt = ai_visual.build_scene_prompt(title, text, direction)
    except Exception:
        # fallback to a simple content-derived prompt
        prompt = f"{title} — {text}"

    negative = image_cfg.get("negative_prompt") if image_cfg else None

    # Attempt generation — any error is fatal (fail-closed)
    try:
        # ai_visual.generate_scene_image returns a Path.
        # We call with direction to let AI include cinematic cues.
        generated = ai_visual.generate_scene_image(
            scene_index=scene_index,
            title=title,
            description=text,
            output=output_path,
            direction=direction,
            width=int(image_cfg.get("width", 512)),
            height=int(image_cfg.get("height", 512)),
        )
    except Exception as exc:  # pragma: no cover - real backend may fail in runtime
        raise VisualGenerationError(f"AI visual backend failed: {exc}") from exc

    if not Path(generated).is_file():
        raise VisualGenerationError(f"AI visual backend produced no file: {generated}")

    sha = _sha256(Path(generated))
    prov = {
        "backend": model_info.get("source") or "diffusers",
        "model_id": model_info.get("id") or "unknown",
        "model_source": model_info.get("source") or "unknown",
        "model_revision": model_info.get("recommended_revision") or None,
        "prompt": prompt,
        "negative_prompt": negative,
        "seed": None,  # unknown unless ai_visual exposes it
        "width": int(image_cfg.get("width", 512)),
        "height": int(image_cfg.get("height", 512)),
        "steps": int(image_cfg.get("steps", 20)),
        "guidance_scale": float(image_cfg.get("guidance_scale", 7.5)),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sha256": sha,
        "path": str(Path(generated).resolve()),
        "scene_index": scene_index,
    }
    _write_provenance(Path(generated), prov)
    return Path(generated), prov
