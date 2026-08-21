"""AURELIA Maker — content-aware narrative scene analyzer.

PRIMARY scene understanding layer. Replaces paragraph-splitting as the
primary way AURELIA interprets a script.

planner.py paragraph splitting is kept as structural FALLBACK.
This module adds rich semantic understanding on top of those segments.

Output per scene:
  narrative_beat     — exposition / rising_action / climax / falling_action /
                       resolution / transition / unknown
  scene_purpose      — establish / develop / reveal / confront / reflect /
                       conclude / describe / unknown
  emotional_register — calm / tense / joyful / melancholic / awe / dread /
                       wonder / neutral
  action_level       — 0.0 (static) to 1.0 (maximum action)
  location_type      — interior / exterior / abstract / unknown
  time_of_day        — day / night / dawn / dusk / unknown
  primary_subject    — extracted text fragment describing the subject
  visual_objective   — short description for image generation
  preferred_shots    — ordered list of recommended shot types
  continuity_tags    — set of tags to maintain across shots/scenes
  transition_hint    — recommended transition from the previous scene
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Keyword maps for semantic classification
# ---------------------------------------------------------------------------

_BEAT_KEYWORDS: dict[str, list[str]] = {
    "exposition": [
        "في البداية", "كان يا ما كان", "منذ القدم", "في عالم", "يُعرَّف",
        "يبدأ", "in the beginning", "once", "long ago", "in a world", "it was",
        "there was", "the story begins", "introduction", "overview",
    ],
    "rising_action": [
        "ثم", "بعد ذلك", "فجأة", "لكن", "غير أن", "بينما", "في هذه الأثناء",
        "then", "suddenly", "but", "however", "meanwhile", "as", "while",
        "escalat", "intensif", "grows", "builds",
    ],
    "climax": [
        "في اللحظة الحاسمة", "ذروة", "أخيرًا", "الآن", "قرر", "واجه",
        "at last", "finally", "the moment", "peak", "crisis", "confronted",
        "decisive", "breakthrough", "revelation", "ultimate",
    ],
    "falling_action": [
        "بعد المعركة", "في أعقاب", "عاد", "تراجع", "خف",
        "after", "aftermath", "returned", "receded", "calmed", "resolved",
        "in the wake",
    ],
    "resolution": [
        "في النهاية", "وهكذا", "وبذلك", "الخلاصة", "اليوم", "الآن نعلم",
        "in the end", "thus", "so", "conclusion", "today", "now we know",
        "ultimately", "the result",
    ],
    "transition": [
        "انتقل", "سافر", "ذهب إلى", "عبر", "من هناك",
        "moved to", "traveled to", "went to", "crossed", "from there",
        "cut to", "meanwhile in",
    ],
}

_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "awe": [
        "عجيب", "رائع", "مذهل", "ساحر", "هائل", "لا يُصدَّق",
        "amazing", "wonder", "awe", "breathtaking", "magnificent", "stunning",
        "vast", "immense", "infinite",
    ],
    "tense": [
        "خطر", "تهديد", "خوف", "قلق", "ضغط", "صراع", "توتر",
        "danger", "threat", "fear", "anxiety", "pressure", "conflict", "tense",
        "urgent", "crisis", "alarm",
    ],
    "joyful": [
        "فرح", "سعادة", "احتفال", "نصر", "ابتسامة", "ضحك",
        "joy", "happiness", "celebration", "victory", "smile", "laugh",
        "delight", "triumph", "success",
    ],
    "melancholic": [
        "حزن", "فقدان", "وحدة", "ذكرى", "ماضٍ", "دموع",
        "sadness", "loss", "loneliness", "memory", "past", "tears",
        "mourning", "grief", "nostalgia", "regret",
    ],
    "dread": [
        "كابوس", "ظلام", "رعب", "هلاك", "دمار", "نهاية",
        "nightmare", "darkness", "horror", "doom", "destruction", "end",
        "apocalypse", "terror", "shadow",
    ],
    "wonder": [
        "اكتشاف", "استكشاف", "جديد", "مجهول", "كنز", "أسرار",
        "discovery", "exploration", "new", "unknown", "treasure", "secrets",
        "mystery", "curiosity", "potential",
    ],
    "calm": [
        "هدوء", "سكينة", "راحة", "سلام", "استقرار",
        "calm", "peace", "rest", "tranquil", "serene", "quiet", "gentle",
        "still", "harmony",
    ],
}

_ACTION_WEIGHTS: dict[str, float] = {
    "انفجار": 1.0, "معركة": 0.9, "ركض": 0.8, "هجوم": 0.9,
    "explosion": 1.0, "battle": 0.9, "running": 0.8, "attack": 0.9,
    "chase": 0.85, "fight": 0.9, "crash": 0.95,
    "حركة": 0.5, "يمشي": 0.4, "يتحرك": 0.5, "يبني": 0.4,
    "walk": 0.4, "move": 0.5, "build": 0.4, "work": 0.4,
    "يفكر": 0.15, "يتأمل": 0.1, "ينظر": 0.2, "يسمع": 0.15,
    "think": 0.15, "reflect": 0.1, "observe": 0.2, "listen": 0.15,
}

_INTERIOR_KW = [
    "منزل", "غرفة", "داخل", "مطبخ", "مكتب", "مختبر", "قاعة",
    "home", "room", "inside", "interior", "kitchen", "office", "lab",
    "hall", "laboratory", "building", "church", "temple", "cave",
]
_EXTERIOR_KW = [
    "خارج", "شارع", "طريق", "غابة", "جبل", "صحراء", "بحر", "سماء",
    "outside", "street", "road", "forest", "mountain", "desert", "sea",
    "sky", "outdoor", "landscape", "field", "ocean", "space", "city",
]

_TIME_KEYWORDS: dict[str, list[str]] = {
    "night": ["ليل", "ظلام", "نجوم", "قمر", "night", "dark", "stars", "moon", "midnight"],
    "dawn":  ["فجر", "شروق", "dawn", "sunrise", "early morning"],
    "dusk":  ["غروب", "مساء", "twilight", "dusk", "sunset", "evening"],
    "day":   ["نهار", "ضوء", "شمس", "day", "daylight", "sun", "afternoon", "morning"],
}


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class SceneAnalysis:
    """Rich semantic understanding of a single scene."""

    scene_id: str
    text: str
    title: str

    narrative_beat: str = "unknown"
    scene_purpose: str = "describe"
    emotional_register: str = "neutral"
    action_level: float = 0.3
    location_type: str = "unknown"
    time_of_day: str = "unknown"
    primary_subject: str = ""
    visual_objective: str = ""
    preferred_shots: list[str] = field(default_factory=list)
    continuity_tags: set[str] = field(default_factory=set)
    transition_hint: str = "cut"

    scene_index: int = 0
    total_scenes: int = 1
    is_opening: bool = False
    is_closing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "title": self.title,
            "narrative_beat": self.narrative_beat,
            "scene_purpose": self.scene_purpose,
            "emotional_register": self.emotional_register,
            "action_level": self.action_level,
            "location_type": self.location_type,
            "time_of_day": self.time_of_day,
            "primary_subject": self.primary_subject,
            "visual_objective": self.visual_objective,
            "preferred_shots": self.preferred_shots,
            "continuity_tags": list(self.continuity_tags),
            "transition_hint": self.transition_hint,
            "scene_index": self.scene_index,
            "is_opening": self.is_opening,
            "is_closing": self.is_closing,
        }


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class SceneAnalyzer:
    """Derives semantic scene understanding from text without calling any AI API."""

    def analyze(
        self,
        scene_id: str,
        title: str,
        text: str,
        scene_index: int = 0,
        total_scenes: int = 1,
        prev_analysis: "SceneAnalysis | None" = None,
    ) -> SceneAnalysis:
        haystack = f"{title} {text}".casefold()

        a = SceneAnalysis(
            scene_id=scene_id, text=text, title=title,
            scene_index=scene_index, total_scenes=total_scenes,
            is_opening=(scene_index == 0),
            is_closing=(scene_index == total_scenes - 1),
        )

        a.narrative_beat = self._detect_beat(haystack, scene_index, total_scenes)
        a.emotional_register = self._detect_emotion(haystack)
        a.action_level = self._measure_action(haystack)
        a.location_type = self._detect_location(haystack)
        a.time_of_day = self._detect_time(haystack)
        a.primary_subject = self._extract_subject(title, text)
        a.scene_purpose = self._infer_purpose(
            a.narrative_beat, a.action_level, scene_index, total_scenes
        )
        a.visual_objective = self._compose_visual_objective(a)
        a.preferred_shots = self._recommend_shots(a)
        a.continuity_tags = self._extract_continuity(text, prev_analysis)
        a.transition_hint = self._suggest_transition(a, prev_analysis)

        return a

    def analyze_sequence(self, raw_scenes: list[dict[str, str]]) -> list[SceneAnalysis]:
        """Analyze a full sequence, threading context between scenes."""
        total = len(raw_scenes)
        results: list[SceneAnalysis] = []
        prev: SceneAnalysis | None = None
        for i, scene in enumerate(raw_scenes):
            a = self.analyze(
                scene_id=str(scene.get("id", i)),
                title=scene.get("title", ""),
                text=scene.get("text", ""),
                scene_index=i,
                total_scenes=total,
                prev_analysis=prev,
            )
            results.append(a)
            prev = a
        return results

    # ── private ────────────────────────────────────────────────────────────

    def _detect_beat(self, haystack: str, index: int, total: int) -> str:
        position = index / max(total - 1, 1)
        if total <= 3:
            structural = ["exposition", "climax", "resolution"][min(index, 2)]
        elif position < 0.15:
            structural = "exposition"
        elif position < 0.35:
            structural = "rising_action"
        elif position < 0.60:
            structural = "climax"
        elif position < 0.80:
            structural = "falling_action"
        else:
            structural = "resolution"

        best_beat, best_score = structural, 0
        for beat, keywords in _BEAT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in haystack)
            if score > best_score:
                best_score = score
                best_beat = beat

        return best_beat if best_score >= 2 else structural

    def _detect_emotion(self, haystack: str) -> str:
        scores = {
            em: sum(1 for kw in kws if kw in haystack)
            for em, kws in _EMOTION_KEYWORDS.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "neutral"

    def _measure_action(self, haystack: str) -> float:
        hits = [(w, v) for w, v in _ACTION_WEIGHTS.items() if w.lower() in haystack]
        if not hits:
            return 0.3
        avg = sum(v for _, v in hits) / len(hits)
        return min(1.0, avg + len(hits) * 0.05)

    def _detect_location(self, haystack: str) -> str:
        i_score = sum(1 for kw in _INTERIOR_KW if kw.lower() in haystack)
        e_score = sum(1 for kw in _EXTERIOR_KW if kw.lower() in haystack)
        if i_score > e_score:
            return "interior"
        if e_score > i_score:
            return "exterior"
        return "unknown"

    def _detect_time(self, haystack: str) -> str:
        for label, kws in _TIME_KEYWORDS.items():
            if any(kw in haystack for kw in kws):
                return label
        return "unknown"

    def _extract_subject(self, title: str, text: str) -> str:
        clean = re.sub(r'^[#*_>\-]+\s*', '', title.strip())
        words = clean.split()
        return " ".join(words[:6]) if words else text.split(".")[0][:60]

    def _infer_purpose(self, beat: str, action: float, index: int, total: int) -> str:
        if index == 0:
            return "establish"
        if index == total - 1:
            return "conclude"
        if beat == "climax":
            return "confront" if action > 0.5 else "reveal"
        if beat == "exposition":
            return "establish"
        if beat == "falling_action":
            return "reflect"
        if beat == "resolution":
            return "conclude"
        if action > 0.6:
            return "develop"
        return "describe"

    def _compose_visual_objective(self, a: SceneAnalysis) -> str:
        parts = []
        if a.is_opening:
            parts.append("cinematic establishing")
        elif a.is_closing:
            parts.append("conclusive wide")
        else:
            parts.append("narrative")
        if a.location_type != "unknown":
            parts.append(a.location_type)
        if a.time_of_day != "unknown":
            parts.append(a.time_of_day)
        parts.append(a.emotional_register)
        parts.append(f"subject: {a.primary_subject[:40]}")
        return " | ".join(parts)

    def _recommend_shots(self, a: SceneAnalysis) -> list[str]:
        if a.scene_purpose == "establish":
            shots = ["wide", "establishing", "medium"]
        elif a.scene_purpose == "confront":
            shots = ["medium", "close_up", "tracking", "over_shoulder"]
        elif a.scene_purpose == "reveal":
            shots = ["close_up", "push_in", "wide"]
        elif a.scene_purpose == "reflect":
            shots = ["medium", "close_up", "static"]
        elif a.scene_purpose == "conclude":
            shots = ["wide", "pull_out", "dissolve_out"]
        elif a.action_level > 0.7:
            shots = ["tracking", "medium", "close_up", "wide"]
        else:
            shots = ["medium", "establishing", "close_up"]

        if a.emotional_register in ("awe", "wonder") and "wide" not in shots:
            shots.insert(0, "wide")
        if a.emotional_register == "tense" and "close_up" not in shots:
            shots.append("close_up")
        if a.emotional_register == "melancholic":
            shots = [s for s in shots if s != "tracking"]
            if "static" not in shots:
                shots.append("static")

        return shots[:5]

    def _extract_continuity(
        self, text: str, prev: "SceneAnalysis | None"
    ) -> set[str]:
        tags: set[str] = set()
        if prev is None:
            return tags
        if prev.location_type == "interior":
            tags.add("interior_continuity")
        prev_words = set(prev.primary_subject.lower().split())
        curr_words = set(text.lower().split())
        if len(prev_words & curr_words) >= 2:
            tags.add("character_continuity")
        if prev.emotional_register not in ("neutral", "unknown"):
            tags.add(f"emotion_{prev.emotional_register}")
        return tags

    def _suggest_transition(
        self,
        current: SceneAnalysis,
        prev: "SceneAnalysis | None",
    ) -> str:
        if prev is None:
            return "fade_in"
        if current.narrative_beat in ("climax", "transition"):
            return "cut"
        if (
            prev.emotional_register == current.emotional_register
            and current.emotional_register in ("calm", "melancholic", "wonder")
        ):
            return "dissolve"
        if current.scene_purpose == "conclude":
            return "fade"
        return "cut"


__all__ = ["SceneAnalyzer", "SceneAnalysis"]
