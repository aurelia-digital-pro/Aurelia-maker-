"""AURELIA Maker — research and source provenance domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import hashlib
import json
import uuid


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
