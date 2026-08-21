"""AURELIA Maker — research and source provenance domain.

Compatibility adapter: provide research_topic(text: str) -> list of structured findings
expected by factory_runner.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import hashlib
import json
import uuid
import re
from collections import Counter


@dataclass
class ResearchSource:
    id: str
    title: str
    source_type: str
    locator: str
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResearchFinding:
    id: str
    source_id: str
    claim: str
    evidence: str
    confidence: float
    tags: list[str] = field(default_factory=list)


@dataclass
class ResearchRepository:
    sources: dict[str, ResearchSource] = field(default_factory=dict)
    findings: dict[str, ResearchFinding] = field(default_factory=dict)

    def add_source(
        self,
        title: str,
        source_type: str,
        locator: str,
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ResearchSource:
        if not title.strip():
            raise ValueError("Research source title is required")
        if not source_type.strip():
            raise ValueError("Research source type is required")
        if not locator.strip():
            raise ValueError("Research source locator is required")

        content_hash = (
            hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content
            else ""
        )

        source = ResearchSource(
            id=str(uuid.uuid4()),
            title=title.strip(),
            source_type=source_type.strip(),
            locator=locator.strip(),
            content_hash=content_hash,
            metadata={} if metadata is None else dict(metadata),
        )
        self.sources[source.id] = source
        return source

    def add_finding(
        self,
        source_id: str,
        claim: str,
        evidence: str,
        confidence: float,
        tags: list[str] | None = None,
    ) -> ResearchFinding:
        if source_id not in self.sources:
            raise KeyError(f"Unknown research source: {source_id}")
        if not claim.strip():
            raise ValueError("Research claim is required")
        if not evidence.strip():
            raise ValueError("Research evidence is required")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Research confidence must be between 0 and 1")

        finding = ResearchFinding(
            id=str(uuid.uuid4()),
            source_id=source_id,
            claim=claim.strip(),
            evidence=evidence.strip(),
            confidence=float(confidence),
            tags=[] if tags is None else list(tags),
        )
        self.findings[finding.id] = finding
        return finding

    def findings_for_source(
        self,
        source_id: str,
    ) -> list[ResearchFinding]:
        if source_id not in self.sources:
            raise KeyError(f"Unknown research source: {source_id}")

        return [
            finding
            for finding in self.findings.values()
            if finding.source_id == source_id
        ]

    def validate(self) -> None:
        for source_id, source in self.sources.items():
            if source_id != source.id:
                raise ValueError("Research source key/id mismatch")
            if not source.title or not source.source_type or not source.locator:
                raise ValueError(f"Invalid research source: {source.id}")

        for finding_id, finding in self.findings.items():
            if finding_id != finding.id:
                raise ValueError("Research finding key/id mismatch")
            if finding.source_id not in self.sources:
                raise ValueError(
                    f"Finding references unknown source: {finding.id}"
                )
            if not finding.claim or not finding.evidence:
                raise ValueError(f"Invalid research finding: {finding.id}")
            if not 0.0 <= finding.confidence <= 1.0:
                raise ValueError(
                    f"Invalid research confidence: {finding.id}"
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "sources": {
                key: asdict(value)
                for key, value in self.sources.items()
            },
            "findings": {
                key: asdict(value)
                for key, value in self.findings.items()
            },
        }

    def save(self, path: str) -> None:
        from pathlib import Path

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                self.to_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str) -> "ResearchRepository":
        from pathlib import Path

        data = json.loads(
            Path(path).read_text(encoding="utf-8")
        )

        repository = cls()

        for key, value in data.get("sources", {}).items():
            repository.sources[key] = ResearchSource(**value)

        for key, value in data.get("findings", {}).items():
            repository.findings[key] = ResearchFinding(**value)

        repository.validate()
        return repository


# ---------------------------------------------------------------------------
# Compatibility function required by factory_runner
# research_topic(text: str) -> list[dict]
# Each dict should be JSON-serializable and include at least:
#   - claim (str)
#   - evidence (str)
#   - confidence (float between 0.0 and 1.0)
#   - tags (list[str])
# The implementation uses deterministic heuristics to extract factual claims from
# the provided text. It does not call external services.
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # Simple sentence splitter using punctuation and newlines
    parts = re.split(r'(?<=[.!?\n])\s+', text)
    parts = [p.strip() for p in parts if p.strip()]
    return parts


def _score_confidence(sentence: str, keywords: list[str]) -> float:
    s = sentence.lower()
    hits = sum(1 for k in keywords if k in s)
    if hits == 0:
        return 0.3
    # cap confidence between 0.45 and 0.95
    conf = min(0.95, 0.45 + 0.2 * hits)
    return round(conf, 2)


def research_topic(text: str) -> list:
    """Derive structured research findings from input text.

    This is deterministic and local: it finds sentences that look like
    factual claims, assembles supporting evidence (nearby sentences), and
    returns a list of findings.
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return []

    keywords = [
        "ai", "artificial intelligence", "machine learning", "neural", "model",
        "dataset", "training", "algorithm", "intelligence", "deep learning",
        "ذكاء", "اصطناعي", "تعلم", "شبكة", "نموذج", "بيانات", "تدريب",
    ]

    findings: list[dict] = []
    # Find candidate sentences containing keywords
    for idx, s in enumerate(sentences):
        low = s.lower()
        if any(k in low for k in keywords):
            # evidence = surrounding sentences
            prev_sent = sentences[idx - 1] if idx > 0 else ""
            next_sent = sentences[idx + 1] if idx + 1 < len(sentences) else ""
            evidence = " ".join(p for p in (prev_sent, s, next_sent) if p).strip()
            confidence = _score_confidence(s, keywords)
            tags = [k for k in ["ai", "research", "tech"] if k in low or any(word in low for word in ["intelligence", "ذكاء"])]
            finding = {
                "claim": s.strip(),
                "evidence": evidence,
                "confidence": confidence,
                "tags": tags,
            }
            findings.append(finding)

    # Fallback: if no keyword hits, return top frequent nouns/phrases as low-confidence findings
    if not findings:
        tokens = re.findall(r"[\w\u0600-\u06FF']{3,}", text)
        stopwords = {"the", "and", "for", "with", "that", "this", "from", "have", "are", "was", "were", "his", "her", "their", "our", "you", "في", "من", "على", "عن", "هو", "هي"}
        words = [t.lower() for t in tokens if t.lower() not in stopwords]
        common = [w for w, _ in Counter(words).most_common(5)]
        for w in common[:3]:
            findings.append({
                "claim": f"Topic term: {w}",
                "evidence": f"Term '{w}' appears frequently in the input.",
                "confidence": 0.35,
                "tags": ["topic"],
            })

    # Deduplicate by claim
    seen = set()
    unique: list[dict] = []
    for f in findings:
        c = f["claim"]
        if c not in seen:
            seen.add(c)
            unique.append(f)

    return unique
