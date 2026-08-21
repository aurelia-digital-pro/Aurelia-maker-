"""AURELIA — AI layer for local intelligence (no API key, no SaaS).

This module provides lightweight local AI capabilities:

1. StoryUnderstanding   — keyword + regex NLP for script analysis
2. CharacterExtractor   — extract named characters + dialogue speakers
3. SentimentAnalyzer    — lexicon-based sentiment/emotion (Arabic + English)
4. KeywordExtractor     — TF-IDF style extraction without external libs
5. LocalNLPRouter       — single entry point; routes to best available backend:
     priority: spaCy → NLTK → built-in fallback

All operations are SYNCHRONOUS and OFFLINE.
No API key, no network call, no paid service.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


# ── Sentiment / Emotion lexicons ────────────────────────────────────────────

_AR_POSITIVE = {
    "\u062d\u0628", "\u0623\u0645\u0644", "\u0641\u0631\u062d", "\u0633\u0639\u0627\u062f\u0629", "\u0646\u062c\u0627\u062d", "\u062c\u0645\u0627\u0644", "\u062e\u064a\u0631",
    "\u0636\u0648\u0621", "\u0633\u0644\u0627\u0645", "\u0639\u062f\u0627\u0644\u0629", "\u062d\u0631\u064a\u0629", "\u0625\u0628\u062f\u0627\u0639", "\u0634\u062c\u0627\u0639\u0629", "\u0627\u0646\u062a\u0635\u0627\u0631",
}
_AR_NEGATIVE = {
    "\u062e\u0648\u0641", "\u062d\u0632\u0646", "\u0645\u0648\u062a", "\u062f\u0645\u0627\u0631", "\u0638\u0644\u0645", "\u0623\u0644\u0645", "\u062e\u0633\u0627\u0631\u0629", "\u062d\u0631\u0628",
    "\u0643\u0631\u0627\u0647\u064a\u0629", "\u0641\u0634\u0644", "\u0647\u0632\u064a\u0645\u0629", "\u0638\u0644\u0627\u0645", "\u0639\u0646\u0641",
}
_EN_POSITIVE = {
    "love", "hope", "joy", "beauty", "peace", "light", "freedom",
    "victory", "courage", "truth", "justice", "creation", "win", "success",
}
_EN_NEGATIVE = {
    "fear", "death", "war", "pain", "loss", "hate", "dark", "evil",
    "destroy", "fail", "terror", "violence", "chaos",
}


def _sentiment(text: str) -> str:
    words = set(re.findall(r'\b\w+\b', text.lower()))
    ar_words = set(re.findall(r'[\u0600-\u06FF]+', text))
    pos = len(words & _EN_POSITIVE) + len(ar_words & _AR_POSITIVE)
    neg = len(words & _EN_NEGATIVE) + len(ar_words & _AR_NEGATIVE)
    if pos > neg + 1:
        return "positive"
    if neg > pos + 1:
        return "negative"
    return "neutral"


# ── Character extraction ──────────────────────────────────────────────────

_SPEAKER_RE = re.compile(
    r'^(?P<speaker>[A-Z\u0600-\u06FF][A-Z\u0600-\u06FFa-z_\- ]{0,30})\s*:\s*(?P<line>.+)',
    re.MULTILINE,
)
_PRONOUN_SKIP = {"THE", "A", "AN", "AND", "OR", "BUT", "IN", "ON", "AT", "TO",
                 "INT", "EXT", "CUT", "FADE"}


def extract_characters(text: str) -> list[dict[str, Any]]:
    """Extract named characters and their dialogue line counts."""
    found: Counter = Counter()
    for m in _SPEAKER_RE.finditer(text):
        speaker = m.group("speaker").strip().upper()
        if speaker not in _PRONOUN_SKIP and len(speaker) > 1:
            found[speaker] += 1
    return [
        {"name": name, "line_count": count}
        for name, count in found.most_common()
    ]


# ── Keyword extraction (TF-IDF-like, no external libs) ──────────────────

_STOPWORDS_EN = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "on", "at",
    "for", "with", "as", "by", "from", "that", "this", "it", "its", "and",
    "or", "but", "not", "no", "nor", "so", "yet", "both", "either", "neither",
    "he", "she", "they", "we", "you", "i", "me", "him", "her", "us", "them",
    "his", "their", "our", "your", "my", "its",
}
_STOPWORDS_AR = {
    "\u0641\u064a", "\u0645\u0646", "\u0625\u0644\u0649", "\u0639\u0644\u0649", "\u0639\u0646", "\u0645\u0639", "\u0647\u0630\u0627", "\u0647\u0630\u0647", "\u0627\u0644\u0630\u064a", "\u0627\u0644\u062a\u064a",
    "\u0643\u0627\u0646", "\u0643\u0627\u0646\u062a", "\u064a\u0643\u0648\u0646", "\u0647\u0648", "\u0647\u064a", "\u0646\u062d\u0646", "\u0623\u0646\u062a\u0645", "\u0623\u0646\u0627", "\u0644\u0643\u0646",
    "\u0648\u0644\u0643\u0646", "\u0623\u0646", "\u0644\u0627", "\u0648", "\u0623\u0648", "\u062b\u0645", "\u0642\u062f", "\u0644\u0642\u062f", "\u0647\u0644", "\u0645\u0627",
}


def extract_keywords(text: str, top_n: int = 12) -> list[str]:
    """Extract most distinctive words (TF-IDF approximation)."""
    tokens = re.findall(r'[\u0600-\u06FF]{3,}|[a-zA-Z]{4,}', text)
    filtered = [
        t.lower() for t in tokens
        if t.lower() not in _STOPWORDS_EN
        and t not in _STOPWORDS_AR
        and len(t) >= 3
    ]
    return [w for w, _ in Counter(filtered).most_common(top_n)]


# ── Story understanding ──────────────────────────────────────────────────

_BEAT_PATTERNS: dict[str, list[str]] = {
    "opening": ["begin", "start", "once", "\u0643\u0627\u0646 \u0647\u0646\u0627\u0643", "\u0628\u062f\u0623", "\u062a\u0628\u062f\u0623", "introduction", "intro"],
    "rising_action": ["then", "suddenly", "\u062b\u0645", "\u0641\u062c\u0623\u0629", "conflict", "challenge", "\u062a\u062d\u062f\u064a"],
    "climax": ["finally", "at last", "\u0623\u062e\u064a\u0631\u0627\u064b", "\u0641\u064a \u0627\u0644\u0646\u0647\u0627\u064a\u0629", "peak", "crisis", "\u0623\u0632\u0645\u0629"],
    "falling_action": ["after", "following", "\u0628\u0639\u062f", "\u0625\u062b\u0631", "resolution", "\u062d\u0644"],
    "resolution": ["end", "conclude", "finally", "\u062e\u062a\u0627\u0645", "\u0646\u0647\u0627\u064a\u0629", "result", "\u0646\u062a\u064a\u062c\u0629"],
    "exposition": ["background", "context", "\u062e\u0644\u0641\u064a\u0629", "\u0633\u064a\u0627\u0642", "history", "\u062a\u0627\u0631\u064a\u062e"],
}


def classify_beat(text: str) -> str:
    lowered = text.lower()
    scores: dict[str, int] = {}
    for beat, keywords in _BEAT_PATTERNS.items():
        scores[beat] = sum(1 for kw in keywords if kw in lowered)
    return max(scores, key=lambda k: scores[k]) if any(scores.values()) else "development"


# ── LocalNLPRouter ────────────────────────────────────────────────────────────

class LocalNLPRouter:
    """Route NLP tasks to best available local backend.

    Priority: spaCy → NLTK → built-in fallback.
    Probes availability once at construction.
    """

    def __init__(self) -> None:
        self._spacy_nlp = None
        self._nltk_available = False
        self._backend = "builtin"
        self._probe()

    def _probe(self) -> None:
        # Try spaCy first
        try:
            import spacy  # type: ignore
            # Try multilingual or English model
            for model in ("xx_ent_wiki_sm", "en_core_web_sm"):
                try:
                    self._spacy_nlp = spacy.load(model)
                    self._backend = f"spacy/{model}"
                    return
                except Exception:
                    pass
        except ImportError:
            pass
        # Try NLTK
        try:
            import nltk  # type: ignore
            nltk.data.find("tokenizers/punkt")
            self._nltk_available = True
            self._backend = "nltk"
            return
        except Exception:
            pass
        # Built-in regex fallback
        self._backend = "builtin"

    @property
    def backend(self) -> str:
        return self._backend

    def analyze(self, text: str) -> dict[str, Any]:
        """Full NLP analysis of a text block."""
        result: dict[str, Any] = {
            "backend":    self._backend,
            "sentiment":  _sentiment(text),
            "beat":       classify_beat(text),
            "keywords":   extract_keywords(text),
            "characters": extract_characters(text),
            "entities":   [],
        }

        if self._spacy_nlp is not None:
            try:
                doc = self._spacy_nlp(text[:2000])
                result["entities"] = [
                    {"text": ent.text, "label": ent.label_}
                    for ent in doc.ents
                ]
                # Use spaCy tokens for better keyword quality
                content_tokens = [
                    token.lemma_.lower()
                    for token in doc
                    if not token.is_stop and not token.is_punct
                    and len(token.text) > 3
                ]
                if content_tokens:
                    result["keywords"] = [
                        w for w, _ in Counter(content_tokens).most_common(12)
                    ]
            except Exception:
                pass

        elif self._nltk_available:
            try:
                import nltk
                tokens = nltk.word_tokenize(text)
                # POS-tag; keep nouns + verbs
                tagged = nltk.pos_tag(tokens)
                content = [
                    w.lower() for w, pos in tagged
                    if pos.startswith(("NN", "VB"))
                    and w.lower() not in _STOPWORDS_EN
                    and len(w) > 3
                ]
                if content:
                    result["keywords"] = [
                        w for w, _ in Counter(content).most_common(12)
                    ]
            except Exception:
                pass

        return result

    def is_arabic(self, text: str) -> bool:
        ar = len(re.findall(r'[\u0600-\u06FF]', text))
        return ar > len(text) * 0.15


# Module-level singleton (lazy, probed once)
_router: LocalNLPRouter | None = None


def get_router() -> LocalNLPRouter:
    global _router
    if _router is None:
        _router = LocalNLPRouter()
    return _router


def analyze_text(text: str) -> dict[str, Any]:
    """Convenience: full analysis via singleton router."""
    return get_router().analyze(text)


__all__ = [
    "LocalNLPRouter", "get_router", "analyze_text",
    "extract_characters", "extract_keywords", "classify_beat",
]
