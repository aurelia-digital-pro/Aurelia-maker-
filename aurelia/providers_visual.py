from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from . import ai_visual

CONFIG_PATH = Path(__file__).resolve().parents[0] / "ai_config.json"


class VisualGenerationError(RuntimeError):
    pass


def _read_config() -> Dict[str, Any]:
    try:
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

    cfg = _read_config()
    model_info = cfg.get("model", {})
    image_cfg = cfg.get("image", {})

    try:
        prompt = ai_visual.build_scene_prompt(title, text, direction)
    except Exception:
        prompt = f"{title} — {text}"

    negative = image_cfg.get("negative_prompt") if image_cfg else None

    # Attempt generation — prefer ai_visual to write its own prov.json if possible
    try:
        generated = ai_visual.generate_scene_image(
            scene_index=scene_index,
            title=title,
            description=text,
            output=output_path,
            direction=direction,
            width=int(image_cfg.get("width", 512)),
            height=int(image_cfg.get("height", 512)),
        )
    except Exception as exc:
        raise VisualGenerationError(f"AI visual backend failed: {exc}") from exc

    if not Path(generated).is_file():
        raise VisualGenerationError(f"AI visual backend produced no file: {generated}")

    # Read any prov.json created by ai_visual
    prov_path = Path(generated).with_suffix(Path(generated).suffix + ".prov.json")
    prov: Dict[str, Any] = {}
    if prov_path.is_file():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
        except Exception:
            prov = {}

    # Ensure canonical provenance fields exist
    sha = _sha256(Path(generated))
    prov.setdefault("backend", model_info.get("source") or "diffusers")
    prov.setdefault("model_id", model_info.get("id") or None)
    prov.setdefault("model_source", model_info.get("source") or None)
    prov.setdefault("model_revision", model_info.get("recommended_revision") or None)
    prov.setdefault("prompt", prompt)
    prov.setdefault("negative_prompt", negative)
    prov.setdefault("seed", None)
    prov.setdefault("width", int(image_cfg.get("width", 512)))
    prov.setdefault("height", int(image_cfg.get("height", 512)))
    prov.setdefault("steps", int(image_cfg.get("steps", 20)))
    prov.setdefault("guidance_scale", float(image_cfg.get("guidance_scale", 7.5)))
    prov.setdefault("generated_at", datetime.utcnow().isoformat() + "Z")
    prov.setdefault("sha256", sha)
    prov.setdefault("path", str(Path(generated).resolve()))
    prov.setdefault("scene_index", scene_index)

    # If no explicit fallback recorded, assert fallback=False
    prov.setdefault("fallback", False)
    prov.setdefault("fallback_reason", "")

    # Write merged provenance back next to asset
    _write_provenance(Path(generated), prov)
    return Path(generated), prov
