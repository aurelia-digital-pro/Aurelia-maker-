"""AURELIA Maker — content-driven cinematic direction engine.

Upgrade in this revision:
- DirectingEngine.direct() now accepts an optional scene_analysis dict
  (from SceneAnalyzer). When provided, the analysis takes priority over
  pure keyword matching for motion selection.
- _MOVEMENT_POOL is preserved as LEGACY FALLBACK only (used when
  scene_analysis is absent or when scene_index cycling is needed).
- Movement is no longer the PRIMARY cinematic decision from this module.
  ShotDesigner (shot_designer.py) owns motion at the shot level.
  DirectingEngine owns environment classification, lighting, and camera
  metadata that inform ShotDesigner.
- Zoom range is no longer set here (hardcoded 1.0→1.08 removed).
  zoom_start and zoom_end in MotionPlan are set by ShotDesigner per shot.
- Environment classification retained — it informs lighting and color,
  not shot structure.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .cinematography import CameraPlan, DepthPlan, MotionPlan
from .lighting import AtmospherePlan, LightSource, LightingPlan


# ---------------------------------------------------------------------------
# Environment catalogue — retained for lighting/color/depth metadata.
# NOT the source of shot structure or motion patterns.
# ---------------------------------------------------------------------------

ENVIRONMENTS: dict[str, dict[str, Any]] = {

    "space": {
        "keywords": [
            "فضاء", "كون", "نجمة", "نجوم", "مجرة", "كوكب", "الكون", "كوكب",
            "مجال", "نيوترون", "ثقب أسود", "ثقب اسود", "مدار", "نيازك",
            "space", "cosmos", "star", "stars", "galaxy", "planet", "orbit",
            "nebula", "asteroid", "black hole", "universe", "milky way",
        ],
        "lens": 24.0, "framing": "wide",
        "movement": "slow_drift", "easing": "ease_in_out", "dof": 0.0,
        "key": (0.65, "#9BB8FF"), "fill": (0.18, "#263A66"), "rim": (0.85, "#C9A86A"),
        "atmosphere": (0.0, 0.05, 0.08, 0.0),
    },
    "desert": {
        "keywords": [
            "صحراء", "رمال", "واحة", "كثيب", "رمل", "جفاف", "سراب",
            "desert", "sand", "dunes", "arid", "mirage", "sahara", "oasis",
        ],
        "lens": 35.0, "framing": "wide",
        "movement": "slow_drift", "easing": "ease_in_out", "dof": 0.1,
        "key": (1.1, "#FFD580"), "fill": (0.35, "#C97A20"), "rim": (0.4, "#FF9940"),
        "atmosphere": (0.0, 0.30, 0.15, 0.0),
    },
    "ocean": {
        "keywords": [
            "بحر", "محيط", "موج", "عمق", "بحار", "شاطئ", "ساحل",
            "ocean", "sea", "wave", "waves", "depth", "underwater", "coast",
            "shore", "marine", "water", "river", "lake", "tide",
        ],
        "lens": 28.0, "framing": "wide",
        "movement": "slow_drift", "easing": "ease_in_out", "dof": 0.2,
        "key": (0.85, "#5DB4E0"), "fill": (0.30, "#0A3A5C"), "rim": (0.6, "#B0E8FF"),
        "atmosphere": (0.0, 0.20, 0.0, 0.35),
    },
    "forest": {
        "keywords": [
            "غابة", "شجر", "أشجار", "طبيعة", "أخضر", "نبات", "حديقة",
            "forest", "jungle", "trees", "nature", "green", "woods",
            "foliage", "wilderness", "garden", "botanical",
        ],
        "lens": 50.0, "framing": "medium",
        "movement": "slow_push", "easing": "ease_in_out", "dof": 0.55,
        "key": (0.90, "#8FD47A"), "fill": (0.28, "#1E4A18"), "rim": (0.55, "#C9FF80"),
        "atmosphere": (0.05, 0.18, 0.05, 0.10),
    },
    "mountain": {
        "keywords": [
            "جبل", "جبال", "قمة", "تل", "هضبة", "وادي",
            "mountain", "mountains", "peak", "summit", "hill", "valley",
            "cliff", "highlands", "alpine",
        ],
        "lens": 24.0, "framing": "wide",
        "movement": "pull_out", "easing": "ease_out", "dof": 0.0,
        "key": (0.95, "#D0E8FF"), "fill": (0.25, "#3A5A7A"), "rim": (0.45, "#FFEECC"),
        "atmosphere": (0.0, 0.12, 0.04, 0.15),
    },
    "city": {
        "keywords": [
            "مدينة", "شارع", "حضارة", "مجتمع", "ناطحة", "برج", "طريق",
            "city", "street", "civilization", "society", "urban", "downtown",
            "skyscraper", "buildings", "traffic", "metropolis",
        ],
        "lens": 35.0, "framing": "wide",
        "movement": "tracking", "easing": "ease_in_out", "dof": 0.35,
        "key": (0.9, "#C9A86A"), "fill": (0.28, "#33435C"), "rim": (0.55, "#8FA9FF"),
        "atmosphere": (0.08, 0.22, 0.08, 0.1),
    },
    "home": {
        "keywords": [
            "منزل", "بيت", "غرفة", "داخل", "أسرة", "عائلة", "مطبخ",
            "home", "house", "room", "interior", "family", "living room",
            "kitchen", "bedroom", "indoor", "domestic",
        ],
        "lens": 35.0, "framing": "medium",
        "movement": "slow_push", "easing": "ease_in", "dof": 0.5,
        "key": (1.0, "#FFDD99"), "fill": (0.45, "#7A5A30"), "rim": (0.3, "#FFB050"),
        "atmosphere": (0.02, 0.06, 0.02, 0.0),
    },
    "laboratory": {
        "keywords": [
            "مختبر", "تجربة", "علم", "علمي", "مجهر", "ذرة", "معادلة",
            "بحث", "كيمياء", "فيزياء", "تحليل",
            "laboratory", "experiment", "science", "microscope", "atom",
            "equation", "research", "chemistry", "physics", "analysis",
        ],
        "lens": 50.0, "framing": "medium",
        "movement": "dolly_in", "easing": "ease_in", "dof": 0.65,
        "key": (1.0, "#E8F0FF"), "fill": (0.35, "#6F86A8"), "rim": (0.65, "#C9A86A"),
        "atmosphere": (0.02, 0.08, 0.02, 0.0),
    },
    "battle": {
        "keywords": [
            "معركة", "حرب", "قتال", "مواجهة", "انفجار", "جيش", "جندي",
            "battle", "war", "fight", "conflict", "explosion", "army",
            "soldier", "combat", "attack", "warrior",
        ],
        "lens": 24.0, "framing": "wide",
        "movement": "tracking", "easing": "ease_in_out", "dof": 0.2,
        "key": (1.0, "#FF8050"), "fill": (0.30, "#3A1008"), "rim": (0.6, "#FFCC40"),
        "atmosphere": (0.15, 0.35, 0.25, 0.0),
    },
    "machine": {
        "keywords": [
            "آلة", "آلات", "روبوت", "تقنية", "تكنولوجيا", "رقمي",
            "برمجة", "حاسوب", "ذكاء", "ذكاء اصطناعي", "شبكة",
            "machine", "robot", "technology", "digital", "code", "computer",
            "AI", "artificial intelligence", "network", "circuit", "cyber",
            "data", "algorithm",
        ],
        "lens": 50.0, "framing": "medium",
        "movement": "orbit", "easing": "linear", "dof": 0.4,
        "key": (0.8, "#40CCFF"), "fill": (0.20, "#102030"), "rim": (0.9, "#00FFCC"),
        "atmosphere": (0.0, 0.10, 0.0, 0.0),
    },
    "creature": {
        "keywords": [
            "حيوان", "حيوانات", "وحش", "مخلوق", "طائر", "أسد", "ذئب",
            "ديناصور", "أفعى", "تنين",
            "animal", "creature", "beast", "monster", "bird", "lion",
            "wolf", "dinosaur", "dragon", "reptile", "predator",
        ],
        "lens": 200.0, "framing": "close_up",
        "movement": "slow_push", "easing": "ease_in_out", "dof": 0.7,
        "key": (1.0, "#D4B06A"), "fill": (0.22, "#2A1A08"), "rim": (0.55, "#FF9A40"),
        "atmosphere": (0.03, 0.15, 0.08, 0.05),
    },
    "human": {
        "keywords": [
            "إنسان", "بشر", "عقل", "وعي", "ذاكرة", "لغة", "طفل",
            "شخص", "شخصية", "وجه", "امرأة", "رجل",
            "human", "mind", "consciousness", "memory", "language",
            "person", "child", "face", "woman", "man", "portrait",
        ],
        "lens": 85.0, "framing": "close_up",
        "movement": "slow_push", "easing": "ease_in_out", "dof": 0.85,
        "key": (0.95, "#F2D5B0"), "fill": (0.22, "#4A4050"), "rim": (0.72, "#C9A86A"),
        "atmosphere": (0.03, 0.12, 0.03, 0.0),
    },
    "ancient": {
        "keywords": [
            "قديم", "تاريخ", "حضارة", "أهرام", "فرعون", "مسجد", "قلعة",
            "معبد", "آثار", "تراث",
            "ancient", "history", "historical", "civilization", "pyramid",
            "pharaoh", "temple", "ruins", "heritage", "medieval",
            "monument", "castle",
        ],
        "lens": 28.0, "framing": "wide",
        "movement": "slow_drift", "easing": "ease_in_out", "dof": 0.1,
        "key": (1.0, "#FFCC80"), "fill": (0.30, "#402010"), "rim": (0.45, "#FFD060"),
        "atmosphere": (0.0, 0.20, 0.18, 0.0),
    },
    "fantasy": {
        "keywords": [
            "سحر", "خيال", "أسطورة", "ساحر", "جن", "سحري", "خيالي",
            "fantasy", "magic", "mythical", "wizard", "enchanted",
            "sorcery", "mystical", "fairy", "spell",
        ],
        "lens": 35.0, "framing": "wide",
        "movement": "orbit", "easing": "ease_in_out", "dof": 0.3,
        "key": (0.85, "#C080FF"), "fill": (0.25, "#200840"), "rim": (0.9, "#80FFCC"),
        "atmosphere": (0.0, 0.20, 0.0, 0.0),
    },
    "fire": {
        "keywords": [
            "نار", "حريق", "لهب", "دمار", "إحراق", "بركان",
            "fire", "flames", "burning", "inferno", "volcano", "explosion",
            "lava", "heat", "blaze",
        ],
        "lens": 35.0, "framing": "medium",
        "movement": "push_in", "easing": "ease_in", "dof": 0.2,
        "key": (1.2, "#FF4400"), "fill": (0.35, "#400800"), "rim": (1.0, "#FFAA00"),
        "atmosphere": (0.25, 0.40, 0.20, 0.0),
    },
    "dream": {
        "keywords": [
            "حلم", "أحلام", "خيال", "ذاكرة", "لاوعي", "وعي",
            "dream", "dreams", "surreal", "subconscious", "imagination",
            "vision", "hallucination", "ethereal",
        ],
        "lens": 50.0, "framing": "medium",
        "movement": "slow_drift", "easing": "ease_in_out", "dof": 0.9,
        "key": (0.70, "#DDA0FF"), "fill": (0.22, "#2A1040"), "rim": (0.60, "#80D0FF"),
        "atmosphere": (0.0, 0.35, 0.0, 0.2),
    },
    "industry": {
        "keywords": [
            "مصنع", "صناعة", "معدن", "حديد", "آلة", "محرك", "ميناء",
            "factory", "industry", "metal", "steel", "engine", "industrial",
            "warehouse", "port", "machinery",
        ],
        "lens": 28.0, "framing": "wide",
        "movement": "tracking", "easing": "linear", "dof": 0.25,
        "key": (1.0, "#FFCC80"), "fill": (0.28, "#303030"), "rim": (0.5, "#FF8800"),
        "atmosphere": (0.10, 0.25, 0.12, 0.0),
    },
    "abstract": {
        "keywords": [
            "فكرة", "معنى", "مفهوم", "سؤال", "معلومة", "معرفة", "فكر",
            "رمز", "مجرد",
            "idea", "meaning", "concept", "question", "knowledge",
            "thought", "symbol", "abstract",
        ],
        "lens": 50.0, "framing": "medium",
        "movement": "orbit", "easing": "linear", "dof": 0.45,
        "key": (0.75, "#C9A86A"), "fill": (0.2, "#18233A"), "rim": (0.65, "#6EA0FF"),
        "atmosphere": (0.04, 0.18, 0.05, 0.0),
    },
}

# LEGACY FALLBACK: movement variety pool.
# Used ONLY when scene_analysis is absent or for scene_index cycling.
# ShotDesigner is now the primary source of motion intent per shot.
_MOVEMENT_POOL: dict[str, list[str]] = {
    "space":      ["slow_drift", "orbit", "pull_out"],
    "desert":     ["slow_drift", "tracking", "push_in"],
    "ocean":      ["slow_drift", "pull_out", "tracking"],
    "forest":     ["slow_push", "dolly_in", "tracking"],
    "mountain":   ["pull_out", "slow_drift", "push_in"],
    "city":       ["tracking", "dolly_in", "pull_out"],
    "home":       ["slow_push", "dolly_in", "static"],
    "laboratory": ["dolly_in", "slow_push", "orbit"],
    "battle":     ["tracking", "push_in", "dolly_in"],
    "machine":    ["orbit", "dolly_in", "tracking"],
    "creature":   ["slow_push", "push_in", "tracking"],
    "human":      ["slow_push", "dolly_in", "static"],
    "ancient":    ["slow_drift", "pull_out", "tracking"],
    "fantasy":    ["orbit", "slow_drift", "push_in"],
    "fire":       ["push_in", "tracking", "dolly_in"],
    "dream":      ["slow_drift", "orbit", "pull_out"],
    "industry":   ["tracking", "dolly_in", "slow_drift"],
    "abstract":   ["orbit", "slow_drift", "push_in"],
}


class DirectingEngine:
    """Derive a stable, content-driven cinematic plan from scene semantics.

    Primary outputs used by EpisodeProduction:
    - environment classification (for lighting/color in ai_visual + episode_engine)
    - LightingPlan, CameraPlan, DepthPlan (metadata for render pipeline)

    Motion is now ADVISORY only: it feeds into episode_engine as a fallback
    when ShotDesigner is unavailable. ShotDesigner owns per-shot motion.
    """

    def classify(self, title: str, text: str) -> str:
        haystack = f"{title} {text}".casefold()
        scores = {
            name: sum(1 for kw in spec["keywords"] if kw.casefold() in haystack)
            for name, spec in ENVIRONMENTS.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "abstract"

    def _pick_movement(self, environment: str, scene_index: int) -> str:
        """LEGACY FALLBACK movement selection — used only when ShotDesigner is absent."""
        pool = _MOVEMENT_POOL.get(environment, ["slow_drift", "tracking", "push_in"])
        return pool[scene_index % len(pool)]

    def direct(
        self,
        scene_id: str,
        title: str,
        text: str,
        duration: float,
        scene_index: int = 0,
        scene_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return environment + lighting + camera metadata.

        scene_analysis (optional): output from SceneAnalyzer.analyze().to_dict().
        When provided, preferred_shots[0] is used as the advisory movement;
        otherwise legacy _MOVEMENT_POOL is used.
        """
        environment = self.classify(title, text)
        spec = ENVIRONMENTS[environment]

        # Movement: advisory only — ShotDesigner overrides at shot level
        if scene_analysis and scene_analysis.get("preferred_shots"):
            # Map shot type to a supported motion intent
            shot_to_motion = {
                "wide": "pull_out",
                "establishing": "slow_drift",
                "medium": "slow_push",
                "close_up": "push_in",
                "tracking": "tracking",
                "pull_out": "pull_out",
                "static": "static",
                "over_shoulder": "slow_push",
                "push_in": "push_in",
            }
            first_shot = scene_analysis["preferred_shots"][0]
            movement = shot_to_motion.get(first_shot, self._pick_movement(environment, scene_index))
        else:
            movement = self._pick_movement(environment, scene_index)

        camera = CameraPlan(
            shot_id=scene_id,
            lens_mm=spec["lens"],
            aperture=2.2 if spec["dof"] >= 0.65 else 3.5,
            distance=1.0,
            height=0.5,
            angle=0.0,
            framing=spec["framing"],
            movement=movement,
        )
        depth = DepthPlan(
            shot_id=scene_id,
            foreground={"role": "semantic foreground"},
            midground={"role": environment},
            background={"role": "contextual environment"},
            depth_of_field=spec["dof"],
        )
        # zoom_start / zoom_end are NOT set here — they are shot-level decisions
        # owned by ShotDesigner. MotionPlan records advisory movement only.
        motion = MotionPlan(
            shot_id=scene_id,
            type=movement,
            duration=duration,
            start={"zoom": 1.0},
            end={"zoom": 1.0},   # ShotDesigner will override
            easing=spec["easing"],
        )

        key_i,  key_c  = spec["key"]
        fill_i, fill_c = spec["fill"]
        rim_i,  rim_c  = spec["rim"]
        fog, haze, dust, humidity = spec["atmosphere"]
        atmosphere = AtmospherePlan(
            shot_id=scene_id,
            fog=fog, haze=haze, dust=dust, humidity=humidity,
            temperature=0.0,
        )
        lighting = LightingPlan(
            shot_id=scene_id,
            key=LightSource(name="key",  type="area", intensity=key_i,  color=key_c),
            fill=LightSource(name="fill", type="area", intensity=fill_i, color=fill_c),
            rim=LightSource(name="rim",  type="area", intensity=rim_i,  color=rim_c),
            atmosphere=atmosphere,
        )

        for plan in (camera, depth, motion, lighting):
            if not plan.validate()["passed"]:
                raise ValueError(f"Invalid directing plan for {scene_id}")

        return {
            "environment": environment,
            "camera":      asdict(camera),
            "depth":       asdict(depth),
            "motion":      asdict(motion),
            "lighting":    asdict(lighting),
        }


__all__ = ["DirectingEngine", "ENVIRONMENTS"]
