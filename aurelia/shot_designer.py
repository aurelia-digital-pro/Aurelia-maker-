"""AURELIA Maker — cinematic shot designer.

Converts a SceneAnalysis into a concrete list of ShotSpec objects.
Each scene gets 2-5 shots based on narrative beat, action level,
and emotional register.

PRIMARY replacement for the single-shot-per-paragraph pattern.
Every scene becomes a mini-sequence with a clear editorial rhythm.

Shot design is CONTENT-DRIVEN, not template-driven:
- Beat determines shot sequence structure
- Emotion modifies motion intent and magnitude
- Action level sets number of shots and zoom range
- No hardcoded 1.0->1.08 for all shots
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from .scene_analyzer import SceneAnalysis


# ---------------------------------------------------------------------------
# Shot function vocabulary
# ---------------------------------------------------------------------------

SHOT_FUNCTION = {
    "establishing": "Establishes context — wide, reveals location/scale",
    "development":  "Carries narrative — medium or tracking, subject in action",
    "detail":       "Emphasises specific element — close-up, focused",
    "reaction":     "Captures response/emotion — close-up or medium, slower",
    "transition":   "Bridges to next scene — pull-out or dissolve setup",
}

# All supported motion intents with semantic descriptions
MOTION_INTENTS: dict[str, str] = {
    "push_in":     "Slow zoom toward subject — intimacy or revelation",
    "pull_out":    "Zoom away from subject — context reveal or distance",
    "tracking":    "Horizontal follow — subject movement, narrative drive",
    "slow_drift":  "Gentle lateral float — contemplative, atmospheric",
    "orbit":       "Circular movement — emphasis on subject/object",
    "dolly_in":    "Zoom + slight drift — depth, immersion",
    "crane_up":    "Vertical upward pan — scale, elevation, transcendence",
    "crane_down":  "Vertical downward pan — landing, descent, focus",
    "static":      "No movement — maximum stability, observation",
    "handheld":    "Micro-jitter + slow push — rawness, immediacy",
    "reveal_wide": "Starts tight, opens wide — contextual reveal",
    "rack_focus":  "Simulated rack focus — depth shift, attention redirect",
    "pan_right":   "Rightward horizontal pan — revealing, following",
    "pan_left":    "Leftward horizontal pan — retrospective, following",
    "tilt_up":     "Upward vertical pan — scale, aspiration",
    "tilt_down":   "Downward vertical pan — weight, consequence",
}

FRAMING_TYPES = [
    "extreme_wide", "wide", "medium_wide", "medium",
    "medium_close", "close_up", "extreme_close_up", "over_shoulder",
]


# ---------------------------------------------------------------------------
# ShotSpec
# ---------------------------------------------------------------------------

@dataclass
class ShotSpec:
    """Complete specification for a single cinematic shot."""

    shot_index: int
    shot_function: str       # from SHOT_FUNCTION keys
    framing: str             # from FRAMING_TYPES
    motion_intent: str       # from MOTION_INTENTS keys
    motion_magnitude: float  # 0.0 (none) to 1.0 (maximum)
    zoom_start: float
    zoom_end: float
    duration: float
    transition_in: str       # cut / dissolve / fade / fade_in
    transition_out: str      # cut / dissolve / fade
    visual_note: str         # short description for image generation enrichment
    depth_of_field: float    # 0.0 (infinite) to 1.0 (very shallow bokeh)
    is_first: bool = False
    is_last: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_index": self.shot_index,
            "shot_function": self.shot_function,
            "framing": self.framing,
            "motion_intent": self.motion_intent,
            "motion_magnitude": self.motion_magnitude,
            "zoom_start": self.zoom_start,
            "zoom_end": self.zoom_end,
            "duration": self.duration,
            "transition_in": self.transition_in,
            "transition_out": self.transition_out,
            "visual_note": self.visual_note,
            "depth_of_field": self.depth_of_field,
            "is_first": self.is_first,
            "is_last": self.is_last,
        }


# ---------------------------------------------------------------------------
# Shot design templates per narrative beat
# duration_ratio values in each template must sum to 1.0
# ---------------------------------------------------------------------------

_BEAT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "exposition": [
        {"function": "establishing", "framing": "wide",
         "motion": "slow_drift", "magnitude": 0.30, "dof": 0.0,  "ratio": 0.40},
        {"function": "development", "framing": "medium",
         "motion": "push_in",    "magnitude": 0.40, "dof": 0.40, "ratio": 0.35},
        {"function": "detail",     "framing": "close_up",
         "motion": "static",     "magnitude": 0.00, "dof": 0.70, "ratio": 0.25},
    ],
    "rising_action": [
        {"function": "establishing", "framing": "medium_wide",
         "motion": "tracking",   "magnitude": 0.50, "dof": 0.20, "ratio": 0.30},
        {"function": "development", "framing": "medium",
         "motion": "dolly_in",   "magnitude": 0.50, "dof": 0.40, "ratio": 0.40},
        {"function": "detail",     "framing": "close_up",
         "motion": "push_in",    "magnitude": 0.60, "dof": 0.75, "ratio": 0.30},
    ],
    "climax": [
        {"function": "establishing", "framing": "wide",
         "motion": "reveal_wide","magnitude": 0.70, "dof": 0.10, "ratio": 0.20},
        {"function": "development", "framing": "medium",
         "motion": "tracking",   "magnitude": 0.70, "dof": 0.30, "ratio": 0.28},
        {"function": "detail",     "framing": "close_up",
         "motion": "handheld",   "magnitude": 0.60, "dof": 0.65, "ratio": 0.27},
        {"function": "reaction",   "framing": "extreme_close_up",
         "motion": "static",     "magnitude": 0.00, "dof": 0.90, "ratio": 0.25},
    ],
    "falling_action": [
        {"function": "establishing", "framing": "wide",
         "motion": "pull_out",   "magnitude": 0.40, "dof": 0.00, "ratio": 0.35},
        {"function": "development", "framing": "medium",
         "motion": "slow_drift", "magnitude": 0.30, "dof": 0.40, "ratio": 0.35},
        {"function": "reaction",   "framing": "close_up",
         "motion": "static",     "magnitude": 0.00, "dof": 0.80, "ratio": 0.30},
    ],
    "resolution": [
        {"function": "establishing", "framing": "extreme_wide",
         "motion": "pull_out",   "magnitude": 0.50, "dof": 0.00, "ratio": 0.40},
        {"function": "development", "framing": "medium",
         "motion": "slow_drift", "magnitude": 0.25, "dof": 0.35, "ratio": 0.35},
        {"function": "transition",  "framing": "wide",
         "motion": "pull_out",   "magnitude": 0.40, "dof": 0.10, "ratio": 0.25},
    ],
    "transition": [
        {"function": "establishing", "framing": "medium_wide",
         "motion": "tracking",   "magnitude": 0.50, "dof": 0.20, "ratio": 0.50},
        {"function": "transition",  "framing": "wide",
         "motion": "pull_out",   "magnitude": 0.40, "dof": 0.10, "ratio": 0.50},
    ],
    "unknown": [
        {"function": "establishing", "framing": "medium_wide",
         "motion": "slow_drift", "magnitude": 0.30, "dof": 0.20, "ratio": 0.45},
        {"function": "development", "framing": "medium",
         "motion": "push_in",    "magnitude": 0.35, "dof": 0.45, "ratio": 0.55},
    ],
}

# Emotion modifiers — adjust motion intent and magnitude per shot function
_EMOTION_MODIFIERS: dict[str, dict[str, Any]] = {
    "tense":      {"boost": +0.15, "prefer": "tracking"},
    "melancholic": {"boost": -0.10, "prefer": "slow_drift"},
    "calm":       {"boost": -0.15, "prefer": "static"},
    "awe":        {"boost": +0.10, "prefer": "pull_out"},
    "wonder":     {"boost": +0.05, "prefer": "reveal_wide"},
    "joyful":     {"boost": +0.10, "prefer": "tracking"},
    "dread":      {"boost":  0.00, "prefer": "push_in"},
    "neutral":    {"boost":  0.00, "prefer": None},
}

_MIN_SHOT_DURATION = 2.0  # seconds


# ---------------------------------------------------------------------------
# Designer
# ---------------------------------------------------------------------------

class ShotDesigner:
    """Converts a SceneAnalysis into a sequence of ShotSpec objects."""

    def design(self, analysis: SceneAnalysis, scene_duration: float) -> list[ShotSpec]:
        beat = analysis.narrative_beat
        templates = list(_BEAT_TEMPLATES.get(beat, _BEAT_TEMPLATES["unknown"]))

        max_shots = self._max_shots(analysis.action_level, scene_duration)
        templates = templates[:max_shots]

        mod = _EMOTION_MODIFIERS.get(
            analysis.emotional_register,
            _EMOTION_MODIFIERS["neutral"],
        )
        mag_boost = float(mod.get("boost", 0.0))
        prefer_motion: str | None = mod.get("prefer")

        shots: list[ShotSpec] = []
        for i, tmpl in enumerate(templates):
            raw_dur = scene_duration * tmpl["ratio"]
            duration = max(_MIN_SHOT_DURATION, raw_dur)

            motion = str(tmpl["motion"])
            # Apply emotion preference to development/reaction shots
            if prefer_motion and tmpl["function"] in ("development", "reaction"):
                motion = prefer_motion

            magnitude = min(1.0, max(0.0, float(tmpl["magnitude"]) + mag_boost))
            dof = float(tmpl["dof"])

            # High action: reduce dof for wider focus
            if analysis.action_level > 0.7:
                dof = max(0.0, dof - 0.20)
            # Melancholic: add bokeh
            if analysis.emotional_register == "melancholic":
                dof = min(1.0, dof + 0.15)

            zoom_start, zoom_end = self._zoom_range(motion, magnitude)

            transition_in = self._transition_in(i, analysis)
            transition_out = self._transition_out(i, len(templates), analysis)
            visual_note = self._visual_note(tmpl, analysis)

            shots.append(ShotSpec(
                shot_index=i,
                shot_function=str(tmpl["function"]),
                framing=str(tmpl["framing"]),
                motion_intent=motion,
                motion_magnitude=magnitude,
                zoom_start=zoom_start,
                zoom_end=zoom_end,
                duration=duration,
                transition_in=transition_in,
                transition_out=transition_out,
                visual_note=visual_note,
                depth_of_field=dof,
                is_first=(i == 0),
                is_last=(i == len(templates) - 1),
            ))

        return shots

    # ── private ────────────────────────────────────────────────────────────

    def _max_shots(self, action_level: float, duration: float) -> int:
        if duration < 5.0:
            return 1
        if duration < 10.0:
            return 2
        if action_level > 0.7:
            return min(5, max(3, math.ceil(duration / 4)))
        if action_level > 0.4:
            return min(4, max(2, math.ceil(duration / 6)))
        return min(3, max(2, math.ceil(duration / 8)))

    def _zoom_range(self, motion: str, magnitude: float) -> tuple[float, float]:
        """Compute zoom_start and zoom_end from motion intent and magnitude.

        Delta is content-driven (0.0 to 0.20), not hardcoded.
        """
        delta = magnitude * 0.20

        if motion == "static":
            return 1.0, 1.0
        if motion in ("pull_out", "reveal_wide"):
            return 1.0 + delta, 1.0
        if motion in ("tracking", "slow_drift", "orbit", "pan_left", "pan_right"):
            return 1.0, 1.0 + delta * 0.15
        if motion in ("crane_up", "crane_down", "tilt_up", "tilt_down"):
            return 1.0, 1.0 + delta * 0.12
        if motion == "handheld":
            return 1.0, 1.0 + delta * 0.60
        if motion == "rack_focus":
            return 1.0, 1.0 + delta * 0.10
        # push_in, dolly_in, slow_push
        return 1.0, 1.0 + delta

    def _transition_in(self, shot_index: int, a: SceneAnalysis) -> str:
        if shot_index == 0:
            return a.transition_hint
        if a.narrative_beat == "climax":
            return "cut"
        if a.emotional_register in ("calm", "melancholic"):
            return "dissolve"
        return "cut"

    def _transition_out(self, shot_index: int, total: int, a: SceneAnalysis) -> str:
        if shot_index == total - 1:
            if a.scene_purpose == "conclude":
                return "fade"
            if a.emotional_register in ("calm", "wonder"):
                return "dissolve"
        return "cut"

    def _visual_note(self, tmpl: dict[str, Any], a: SceneAnalysis) -> str:
        framing = str(tmpl["framing"]).replace("_", " ")
        function = str(tmpl["function"]).replace("_", " ")
        parts = [f"{framing} {function}"]
        if a.emotional_register != "neutral":
            parts.append(a.emotional_register)
        if a.primary_subject:
            parts.append(a.primary_subject[:30])
        if a.location_type != "unknown":
            parts.append(a.location_type)
        if a.time_of_day != "unknown":
            parts.append(a.time_of_day)
        return ", ".join(parts)


__all__ = ["ShotDesigner", "ShotSpec", "MOTION_INTENTS", "SHOT_FUNCTION"]
