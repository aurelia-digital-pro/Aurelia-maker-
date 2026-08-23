"""Real transition selection and FFmpeg xfade application."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .ffmpeg_util import run_ffmpeg
from .media import probe_duration


class TransitionType(str, Enum):
    HARD_CUT = "hard_cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    WIPE = "wipe"
    CROSSFADE = "crossfade"


@dataclass(frozen=True)
class TransitionSpec:
    kind: TransitionType
    duration: float


def select_transition(
    shot_a: dict[str, Any] | None,
    shot_b: dict[str, Any] | None,
    scene_change: bool = False,
) -> TransitionSpec:
    """Choose a motivated transition from semantic shot direction."""
    a = shot_a or {}
    b = shot_b or {}
    function = str(b.get("shot_function") or b.get("function") or "").lower()
    beat = str(b.get("narrative_beat") or a.get("narrative_beat") or "").lower()
    motion = str(b.get("motion_intent") or b.get("motion") or "").lower()
    if function == "action" or motion in {"handheld", "tracking"} and not scene_change:
        return TransitionSpec(TransitionType.HARD_CUT, 0.0)
    if scene_change:
        if function == "resolution" or beat in {"resolution", "conclude"}:
            return TransitionSpec(TransitionType.FADE, 0.4)
        if function in {"action", "climax"} or beat in {"climax", "rising_action"}:
            return TransitionSpec(TransitionType.WIPE, 0.25)
        return TransitionSpec(TransitionType.DISSOLVE, 0.5)
    if function == "resolution":
        return TransitionSpec(TransitionType.FADE, 0.4)
    return TransitionSpec(TransitionType.CROSSFADE, 0.3)


def apply_transition_ffmpeg(
    clip_a: str | Path,
    clip_b: str | Path,
    transition: TransitionSpec | TransitionType | str,
    output: str | Path,
) -> Path:
    """Apply a real xfade transition and encode the resulting video."""
    a, b = Path(clip_a), Path(clip_b)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(transition, TransitionSpec):
        spec = transition
    else:
        kind = TransitionType(str(transition))
        spec = TransitionSpec(kind, {TransitionType.FADE: 0.4, TransitionType.DISSOLVE: 0.5, TransitionType.WIPE: 0.25, TransitionType.CROSSFADE: 0.3}.get(kind, 0.0))
    if spec.kind == TransitionType.HARD_CUT or spec.duration <= 0:
        args = ["-y", "-hide_banner", "-loglevel", "error", "-i", str(a), "-i", str(b), "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    else:
        da, db = probe_duration(a), probe_duration(b)
        overlap = min(spec.duration, max(0.1, da / 3), max(0.1, db / 3))
        name = {TransitionType.FADE: "fadeblack", TransitionType.DISSOLVE: "fade", TransitionType.WIPE: "wiperight", TransitionType.CROSSFADE: "fade"}[spec.kind]
        graph = f"[0:v]settb=AVTB,setpts=PTS-STARTPTS[v0];[1:v]settb=AVTB,setpts=PTS-STARTPTS[v1];[v0][v1]xfade=transition={name}:duration={overlap:.4f}:offset={max(0.0, da-overlap):.4f},format=yuv420p[v]"
        args = ["-y", "-hide_banner", "-loglevel", "error", "-i", str(a), "-i", str(b), "-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(out)]
    result = run_ffmpeg(args)
    if result.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError(f"transition encoding failed: {result.stderr.decode(errors='replace')[-500:]}")
    return out


__all__ = ["TransitionType", "TransitionSpec", "select_transition", "apply_transition_ffmpeg"]
