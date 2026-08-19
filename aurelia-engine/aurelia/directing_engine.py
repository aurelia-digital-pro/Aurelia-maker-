"""Content-driven cinematic direction for AURELIA Maker.

Scene direction is derived from the meaning of the scene text, never from
scene index arithmetic. The engine produces deterministic camera, depth,
motion and lighting plans that can be consumed by the local renderer.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .cinematography import CameraPlan, DepthPlan, MotionPlan
from .lighting import AtmospherePlan, LightSource, LightingPlan


ENVIRONMENTS: dict[str, dict[str, Any]] = {
    "space": {
        "keywords": ["فضاء", "كون", "نجمة", "مجرة", "كوكب", "الكون", "space", "cosmos", "star", "galaxy", "planet"],
        "lens": 24.0,
        "framing": "wide",
        "movement": "slow_drift",
        "easing": "ease_in_out",
        "dof": 0.0,
        "key": (0.65, "#9BB8FF"),
        "fill": (0.18, "#263A66"),
        "rim": (0.85, "#C9A86A"),
        "atmosphere": (0.0, 0.05, 0.08, 0.0),
    },
    "laboratory": {
        "keywords": ["مختبر", "تجربة", "علم", "علمي", "مجهر", "ذرة", "معادلة", "laboratory", "experiment", "science", "microscope", "atom", "equation"],
        "lens": 50.0,
        "framing": "medium",
        "movement": "dolly_in",
        "easing": "ease_in",
        "dof": 0.65,
        "key": (1.0, "#E8F0FF"),
        "fill": (0.35, "#6F86A8"),
        "rim": (0.65, "#C9A86A"),
        "atmosphere": (0.02, 0.08, 0.02, 0.0),
    },
    "city": {
        "keywords": ["مدينة", "شارع", "حضارة", "مجتمع", "مدينة", "city", "street", "civilization", "society", "urban"],
        "lens": 35.0,
        "framing": "wide",
        "movement": "tracking",
        "easing": "ease_in_out",
        "dof": 0.35,
        "key": (0.9, "#C9A86A"),
        "fill": (0.28, "#33435C"),
        "rim": (0.55, "#8FA9FF"),
        "atmosphere": (0.08, 0.22, 0.08, 0.1),
    },
    "human": {
        "keywords": ["إنسان", "بشر", "عقل", "وعي", "ذاكرة", "لغة", "طفل", "شخص", "human", "mind", "consciousness", "memory", "language", "person", "child"],
        "lens": 85.0,
        "framing": "close_up",
        "movement": "slow_push",
        "easing": "ease_in_out",
        "dof": 0.85,
        "key": (0.95, "#F2D5B0"),
        "fill": (0.22, "#4A4050"),
        "rim": (0.72, "#C9A86A"),
        "atmosphere": (0.03, 0.12, 0.03, 0.0),
    },
    "abstract": {
        "keywords": ["فكرة", "معنى", "مفهوم", "سؤال", "معلومة", "معرفة", "فكر", "idea", "meaning", "concept", "question", "knowledge", "thought"],
        "lens": 50.0,
        "framing": "medium",
        "movement": "orbit",
        "easing": "linear",
        "dof": 0.45,
        "key": (0.75, "#C9A86A"),
        "fill": (0.2, "#18233A"),
        "rim": (0.65, "#6EA0FF"),
        "atmosphere": (0.04, 0.18, 0.05, 0.0),
    },
}


class DirectingEngine:
    """Derive a stable cinematic plan from scene semantics."""

    def classify(self, title: str, text: str) -> str:
        haystack = f"{title} {text}".casefold()
        scores = {
            name: sum(1 for keyword in spec["keywords"] if keyword.casefold() in haystack)
            for name, spec in ENVIRONMENTS.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] else "abstract"

    def direct(self, scene_id: str, title: str, text: str, duration: float) -> dict[str, Any]:
        environment = self.classify(title, text)
        spec = ENVIRONMENTS[environment]

        camera = CameraPlan(
            shot_id=scene_id,
            lens_mm=spec["lens"],
            aperture=2.2 if spec["dof"] >= 0.65 else 3.5,
            distance=1.0,
            height=0.5,
            angle=0.0,
            framing=spec["framing"],
            movement=spec["movement"],
        )
        depth = DepthPlan(
            shot_id=scene_id,
            foreground={"role": "semantic foreground"},
            midground={"role": environment},
            background={"role": "contextual environment"},
            depth_of_field=spec["dof"],
        )
        motion = MotionPlan(
            shot_id=scene_id,
            type=spec["movement"],
            duration=duration,
            start={"zoom": 1.0},
            end={"zoom": 1.08 if spec["movement"] != "tracking" else 1.03},
            easing=spec["easing"],
        )

        key_i, key_c = spec["key"]
        fill_i, fill_c = spec["fill"]
        rim_i, rim_c = spec["rim"]
        fog, haze, dust, humidity = spec["atmosphere"]
        atmosphere = AtmospherePlan(
            shot_id=scene_id,
            fog=fog,
            haze=haze,
            dust=dust,
            humidity=humidity,
            temperature=0.0,
        )
        lighting = LightingPlan(
            shot_id=scene_id,
            key=LightSource(name="key", type="area", intensity=key_i, color=key_c),
            fill=LightSource(name="fill", type="area", intensity=fill_i, color=fill_c),
            rim=LightSource(name="rim", type="area", intensity=rim_i, color=rim_c),
            atmosphere=atmosphere,
        )

        for plan in (camera, depth, motion, lighting):
            if not plan.validate()["passed"]:
                raise ValueError(f"Invalid directing plan for {scene_id}")

        return {
            "environment": environment,
            "camera": asdict(camera),
            "depth": asdict(depth),
            "motion": asdict(motion),
            "lighting": asdict(lighting),
        }


__all__ = ["DirectingEngine"]
