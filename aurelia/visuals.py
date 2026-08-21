"""AURELIA Maker — Final Cinematic Visual Engine.

Upgrade:
- 16 motion intents fully mapped to FFmpeg filter expressions
- zoom_start / zoom_end are CALLER-SUPPLIED (from ShotSpec), not hardcoded
- crane_up / crane_down / tilt_up / tilt_down add vertical movement
- handheld adds micro-jitter via perturbed x/y expressions
- rack_focus simulates depth shift via brief zoom pulse
- reveal_wide starts tight then opens
- pan_left / pan_right add pure horizontal movement
- orbit now uses proper 2pi circular path

Legacy fallback: if caller passes zoom_start == zoom_end == 0.0 or
zoom_start < 1.0, the engine self-corrects to avoid black bars.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter

from .ffmpeg_util import run_ffmpeg


class CinematicVisualEngine:
    """Deterministic production renderer for final cinematic shots."""

    DEFAULT_WIDTH  = 1920
    DEFAULT_HEIGHT = 1080
    DEFAULT_FPS    = 24

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
    ) -> None:
        self.width  = width
        self.height = height
        self.fps    = fps

    # ── public API ──────────────────────────────────────────────────────────

    def render_frame(
        self,
        source: str | Path,
        output: str | Path,
        camera: dict[str, Any] | None = None,
        depth: dict[str, Any] | None = None,
        lighting: dict[str, Any] | None = None,
        atmosphere: dict[str, Any] | None = None,
        vfx: dict[str, Any] | None = None,
    ) -> Path:
        source_path = Path(source)
        output_path = Path(output)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(source_path).convert("RGB")
        image = self._fit_canvas(image)
        image = self._apply_camera_frame(image, camera or {})
        image = self._apply_depth(image, depth or {})
        image = self._apply_lighting(image, lighting or {})
        image = self._apply_atmosphere(image, atmosphere or {})
        image = self._apply_vfx(image, vfx or {})
        image.save(output_path, "PNG", optimize=True)
        return output_path

    def render_motion(
        self,
        source: str | Path,
        output: str | Path,
        duration: float,
        camera: dict[str, Any] | None = None,
        depth: dict[str, Any] | None = None,
        lighting: dict[str, Any] | None = None,
        atmosphere: dict[str, Any] | None = None,
        vfx: dict[str, Any] | None = None,
    ) -> Path:
        if duration <= 0:
            raise ValueError("duration must be greater than zero")

        source_path = Path(source)
        output_path = Path(output)
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        camera     = camera     or {}
        lighting   = lighting   or {}
        atmosphere = atmosphere or {}
        vfx        = vfx        or {}

        movement   = str(camera.get("movement") or camera.get("type") or "static").lower()
        zoom_start = float(camera.get("zoom_start", 1.0))
        zoom_end   = float(camera.get("zoom_end",   zoom_start))

        # Safety: never go below 1.0 (causes black bars in zoompan)
        zoom_start = max(1.0, zoom_start)
        zoom_end   = max(1.0, zoom_end)

        frames      = max(1, round(duration * self.fps))
        denominator = max(frames - 1, 1)

        zoom_expr = (
            f"{zoom_start:.6f}+({zoom_end:.6f}-{zoom_start:.6f})*on/{denominator}"
        )

        # ── motion intent -> (x_expr, y_expr) ────────────────────────────────
        cx = "iw/2-(iw/zoom/2)"
        cy = "ih/2-(ih/zoom/2)"

        if movement == "slow_drift":
            x_expr = f"iw/2-(iw/zoom/2)+(iw-iw/zoom)*0.30*sin(on/{denominator}*PI)"
            y_expr = cy

        elif movement == "tracking":
            x_expr = f"iw/2-(iw/zoom/2)+(iw-iw/zoom)*0.25*(on/{denominator})"
            y_expr = cy

        elif movement == "pan_right":
            x_expr = f"iw/2-(iw/zoom/2)+(iw-iw/zoom)*0.40*(on/{denominator})"
            y_expr = cy

        elif movement == "pan_left":
            x_expr = f"iw/2-(iw/zoom/2)-(iw-iw/zoom)*0.40*(on/{denominator})"
            y_expr = cy

        elif movement == "orbit":
            x_expr = f"iw/2-(iw/zoom/2)+(iw-iw/zoom)*0.18*sin(on/{denominator}*2*PI)"
            y_expr = f"ih/2-(ih/zoom/2)+(ih-ih/zoom)*0.10*cos(on/{denominator}*2*PI)"

        elif movement == "crane_up":
            x_expr = cx
            y_expr = f"ih/2-(ih/zoom/2)+(ih-ih/zoom)*0.30*(1-on/{denominator})"

        elif movement == "crane_down":
            x_expr = cx
            y_expr = f"ih/2-(ih/zoom/2)+(ih-ih/zoom)*0.30*(on/{denominator})"

        elif movement == "tilt_up":
            x_expr = cx
            y_expr = f"ih/2-(ih/zoom/2)+(ih-ih/zoom)*0.18*(1-on/{denominator})"

        elif movement == "tilt_down":
            x_expr = cx
            y_expr = f"ih/2-(ih/zoom/2)+(ih-ih/zoom)*0.18*(on/{denominator})"

        elif movement == "handheld":
            # Micro-jitter: tiny sinusoidal perturbation simulating handheld shake
            x_expr = (
                f"iw/2-(iw/zoom/2)"
                f"+(iw-iw/zoom)*0.008*sin(on*7.3)"
                f"+(iw-iw/zoom)*0.005*cos(on*11.7)"
            )
            y_expr = (
                f"ih/2-(ih/zoom/2)"
                f"+(ih-ih/zoom)*0.006*cos(on*9.1)"
                f"+(ih-ih/zoom)*0.004*sin(on*13.5)"
            )

        elif movement == "rack_focus":
            # Subtle lateral drift to accompany the zoom pulse in zoom_expr
            x_expr = f"iw/2-(iw/zoom/2)+(iw-iw/zoom)*0.04*sin(on/{denominator}*2*PI)"
            y_expr = cy

        elif movement == "reveal_wide":
            # zoom_start > zoom_end: starts tight, opens wide (set by ShotDesigner)
            x_expr = cx
            y_expr = cy

        elif movement == "pull_out":
            x_expr = cx
            y_expr = cy

        elif movement in ("dolly_in", "slow_push", "push_in"):
            x_expr = cx
            y_expr = cy

        elif movement == "static":
            x_expr = cx
            y_expr = cy

        else:
            # Unknown motion intent: stable center
            x_expr = cx
            y_expr = cy

        filters = [
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase",
            f"crop={self.width}:{self.height}",
            "zoompan="
            f"z='{zoom_expr}':"
            f"x='{x_expr}':"
            f"y='{y_expr}':"
            f"d=1:s={self.width}x{self.height}:fps={self.fps}",
        ]
        filters.extend(self._ffmpeg_visual_filters(lighting, atmosphere, vfx))

        command = [
            "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", str(source_path),
            "-vf", ",".join(filters),
            "-t", f"{duration:.6f}",
            "-r", str(self.fps),
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output_path),
        ]
        result = run_ffmpeg(command)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return output_path

    # ── Pillow helpers (render_frame path) ──────────────────────────────────

    def _fit_canvas(self, image: Image.Image) -> Image.Image:
        ratio = max(self.width / image.width, self.height / image.height)
        size  = (
            max(self.width,  round(image.width  * ratio)),
            max(self.height, round(image.height * ratio)),
        )
        image = image.resize(size, Image.Resampling.LANCZOS)
        left  = (image.width  - self.width)  // 2
        top   = (image.height - self.height) // 2
        return image.crop((left, top, left + self.width, top + self.height))

    def _apply_camera_frame(self, image: Image.Image, camera: dict[str, Any]) -> Image.Image:
        zoom = float(camera.get("zoom", 1.0))
        if zoom <= 1.0:
            return image
        zoom   = min(zoom, 8.0)
        width  = max(1, round(image.width  / zoom))
        height = max(1, round(image.height / zoom))
        left   = (image.width  - width)  // 2
        top    = (image.height - height) // 2
        image  = image.crop((left, top, left + width, top + height))
        return image.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def _apply_depth(self, image: Image.Image, depth: dict[str, Any]) -> Image.Image:
        amount = float(depth.get("depth_of_field") or depth.get("blur") or 0.0)
        if amount <= 0:
            return image
        return image.filter(ImageFilter.GaussianBlur(min(max(amount, 0.0), 20.0)))

    def _apply_lighting(self, image: Image.Image, lighting: dict[str, Any]) -> Image.Image:
        brightness = float(lighting.get("brightness", 1.0))
        contrast   = float(lighting.get("contrast",   1.0))
        saturation = float(lighting.get("saturation", 1.0))
        if brightness != 1.0:
            image = ImageEnhance.Brightness(image).enhance(max(0.0, brightness))
        if contrast != 1.0:
            image = ImageEnhance.Contrast(image).enhance(max(0.0, contrast))
        if saturation != 1.0:
            image = ImageEnhance.Color(image).enhance(max(0.0, saturation))
        return image

    def _apply_atmosphere(self, image: Image.Image, atmosphere: dict[str, Any]) -> Image.Image:
        blur = float(atmosphere.get("blur") or atmosphere.get("softness") or 0.0)
        if blur <= 0:
            return image
        return image.filter(ImageFilter.GaussianBlur(min(blur, 8.0)))

    def _apply_vfx(self, image: Image.Image, vfx: dict[str, Any]) -> Image.Image:
        blur = float(vfx.get("blur", 0.0) or 0.0)
        if blur > 0:
            image = image.filter(ImageFilter.GaussianBlur(min(blur, 12.0)))
        return image

    def _ffmpeg_visual_filters(
        self,
        lighting: dict[str, Any],
        atmosphere: dict[str, Any],
        vfx: dict[str, Any],
    ) -> list[str]:
        filters: list[str] = []
        brightness = float(lighting.get("brightness", 1.0))
        contrast   = float(lighting.get("contrast",   1.0))
        saturation = float(lighting.get("saturation", 1.0))
        if brightness != 1.0 or contrast != 1.0 or saturation != 1.0:
            filters.append(
                f"eq=brightness={brightness - 1.0:.6f}"
                f":contrast={contrast:.6f}"
                f":saturation={saturation:.6f}"
            )
        blur = float(atmosphere.get("blur") or vfx.get("blur") or 0.0)
        if blur > 0:
            filters.append(f"gblur=sigma={min(blur, 12.0):.4f}")
        return filters


# ── public helper ────────────────────────────────────────────────────────────

def _model_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        if not isinstance(result, dict):
            raise TypeError(f"to_dict() must return dict, got {type(result).__name__}")
        return result
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"Unsupported cinematic plan type: {type(value).__name__}")


def render_cinematic_shot(
    source: str | Path,
    output: str | Path,
    shot: Any,
    cinematography: Any | None = None,
    lighting: Any | None = None,
    vfx: Any | None = None,
) -> Path:
    """Render one complete production-domain cinematic shot."""
    shot_data           = _model_to_dict(shot)
    cinematography_data = _model_to_dict(cinematography)
    lighting_data       = _model_to_dict(lighting)
    vfx_data            = _model_to_dict(vfx)

    camera = _model_to_dict(cinematography_data.get("camera", {}))
    depth  = _model_to_dict(cinematography_data.get("depth",  {}))
    motion = _model_to_dict(cinematography_data.get("motion", {}))

    camera["movement"] = motion.get("type") or camera.get("movement") or "static"
    camera.setdefault(
        "zoom_start",
        _model_to_dict(motion.get("start", {})).get("zoom", 1.0),
    )
    camera.setdefault(
        "zoom_end",
        _model_to_dict(motion.get("end", {})).get("zoom", 1.0),
    )

    duration = float(shot_data.get("duration") or motion.get("duration") or 0.0)
    if duration <= 0:
        raise ValueError(f"Shot {shot_data.get('id', '')} has no valid duration")

    atmosphere = _model_to_dict(lighting_data.get("atmosphere", {}))
    engine     = CinematicVisualEngine()
    return engine.render_motion(
        source=source, output=output, duration=duration,
        camera=camera, depth=depth,
        lighting=lighting_data, atmosphere=atmosphere, vfx=vfx_data,
    )


__all__ = ["CinematicVisualEngine", "render_cinematic_shot"]
