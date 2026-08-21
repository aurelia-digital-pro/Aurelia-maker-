"""AURELIA Maker — development domain for series and film production."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid
import re
from collections import Counter


@dataclass
class DevelopmentProject:
    id: str
    title: str
    format: str
    premise: str
    logline: str = ""
    genre: str = ""
    language: str = ""
    status: str = "DEVELOPMENT"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DevelopmentVersion:
    id: str
    project_id: str
    version: int
    content: dict[str, Any]
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DevelopmentRepository:
    projects: dict[str, DevelopmentProject] = field(default_factory=dict)
    versions: dict[str, DevelopmentVersion] = field(default_factory=dict)

    def create_project(
        self,
        title: str,
        format: str,
        premise: str,
        logline: str = "",
        genre: str = "",
        language: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DevelopmentProject:
        if not title.strip():
            raise ValueError("Project title is required")
        if not format.strip():
            raise ValueError("Project format is required")
        if not premise.strip():
            raise ValueError("Project premise is required")

        project = DevelopmentProject(
            id=str(uuid.uuid4()),
            title=title.strip(),
            format=format.strip().upper(),
            premise=premise.strip(),
            logline=logline.strip(),
            genre=genre.strip(),
            language=language.strip(),
            metadata={} if metadata is None else dict(metadata),
        )
        self.projects[project.id] = project
        return project

    def create_version(
        self,
        project_id: str,
        content: dict[str, Any],
        parent_id: str | None = None,
    ) -> DevelopmentVersion:
        if project_id not in self.projects:
            raise KeyError(f"Unknown development project: {project_id}")
        if not isinstance(content, dict) or not content:
            raise ValueError("Development content must be a non-empty dict")

        existing = [
            v.version
            for v in self.versions.values()
            if v.project_id == project_id
        ]
        version_number = max(existing, default=0) + 1

        if parent_id is not None:
            parent = self.versions.get(parent_id)
            if parent is None:
                raise KeyError(f"Unknown parent version: {parent_id}")
            if parent.project_id != project_id:
                raise ValueError("Parent version belongs to another project")

        version = DevelopmentVersion(
            id=str(uuid.uuid4()),
            project_id=project_id,
            version=version_number,
            content=dict(content),
            parent_id=parent_id,
        )
        self.versions[version.id] = version
        return version

    def latest_version(self, project_id: str) -> DevelopmentVersion | None:
        versions = [
            v for v in self.versions.values()
            if v.project_id == project_id
        ]
        return max(versions, key=lambda v: v.version, default=None)

    def validate(self) -> None:
        for project in self.projects.values():
            if not project.title or not project.format or not project.premise:
                raise ValueError(
                    f"Invalid development project: {project.id}"
                )

        for version in self.versions.values():
            if version.project_id not in self.projects:
                raise ValueError(
                    f"Version references unknown project: {version.id}"
                )
            if version.parent_id is not None:
                parent = self.versions.get(version.parent_id)
                if parent is None:
                    raise ValueError(
                        f"Version references unknown parent: {version.id}"
                    )
                if parent.project_id != version.project_id:
                    raise ValueError(
                        f"Version parent crosses project boundary: {version.id}"
                    )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "projects": {
                key: value.to_dict()
                for key, value in self.projects.items()
            },
            "versions": {
                key: value.to_dict()
                for key, value in self.versions.items()
            },
        }

    def save(self, path: str) -> None:
        from pathlib import Path

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str) -> "DevelopmentRepository":
        from pathlib import Path

        data = json.loads(
            Path(path).read_text(encoding="utf-8")
        )

        repository = cls()

        for key, value in data.get("projects", {}).items():
            repository.projects[key] = DevelopmentProject(**value)

        for key, value in data.get("versions", {}).items():
            repository.versions[key] = DevelopmentVersion(**value)

        repository.validate()
        return repository


def validate_development_repository(
    repository: DevelopmentRepository,
) -> None:
    repository.validate()


# ---------------------------------------------------------------------------
# Functional compatibility layer
# The production path expects three functions with the following signatures:
#   develop_story_concept(text: str) -> dict
#   extract_story_structure(text: str) -> dict
#   extract_characters(text: str) -> list[dict]
# Implement deterministic, text-driven heuristics that produce JSON-serializable
# outputs derived from the input script. Avoid external AI services.
# ---------------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    # Split by sentence-ending punctuation
    m = re.split(r'[\r\n]+', text)
    # prefer the first non-empty paragraph's first sentence
    for para in m:
        para = para.strip()
        if not para:
            continue
        sents = re.split(r'(?<=[.!?])\s+', para)
        if sents:
            return sents[0].strip()
    return text.splitlines()[0].strip()


def develop_story_concept(text: str) -> dict:
    """Derive a story concept (genre, theme, logline) from the provided text.

    Uses keyword heuristics and simple frequency analysis to produce a
    deterministic, JSON-serializable dictionary. Result fields:
      - genre
      - theme
      - logline
    """
    body = "\n".join(
        line for line in text.splitlines()
        if not re.match(r'^\s*(?:title|language|lang|العنوان|اللغة)\s*[:=]', line, re.IGNORECASE)
    ).strip()

    # Genre keywords mapping (English + Arabic hints)
    genre_map = {
        "documentary": ["documentary", "documental", "وثائقي", "docu"],
        "drama": ["drama", "dramatic", "درامي", "قصة"],
        "comedy": ["comedy", "humor", "مضحك", "كوميدي"],
        "sci-fi": ["science fiction", "sci-fi", "sci fi", "خيال علمي"],
        "thriller": ["thriller", "suspense", "مثير", "تشويق"],
        "animation": ["animation", "animated", "رسوم", "متحرك"],
        "fantasy": ["fantasy", "رمزي", "خيال"],
    }

    lower = body.lower()
    genre_scores = Counter()
    for g, keywords in genre_map.items():
        for kw in keywords:
            if kw in lower:
                genre_scores[g] += lower.count(kw)

    genre = genre_scores.most_common(1)[0][0] if genre_scores else "drama"

    # Theme: pick top frequent content words (exclude short/common stopwords)
    tokens = re.findall(r"[\w\u0600-\u06FF']{3,}", body)
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "have",
        "are", "was", "were", "his", "her", "their", "our", "you",
        "ي", "في", "من", "على", "عن", "هو", "هي",
    }
    words = [t.lower() for t in tokens if t.lower() not in stopwords]
    theme_terms = [w for w, _ in Counter(words).most_common(5)]
    theme = ", ".join(theme_terms[:3]) if theme_terms else "human experience"

    # Logline: use the first full sentence of the body or compose from title + premise
    first = _first_sentence(body)
    logline = first if len(first) > 10 else (body.strip().split("\n")[0][:200] if body else "")

    return {"genre": genre, "theme": theme, "logline": logline}


def extract_story_structure(text: str) -> dict:
    """Return a simple story structure derived from the text.

    Output fields:
      - acts: int
      - turning_points: list[str]
    """
    body = "\n".join(
        line for line in text.splitlines()
        if not re.match(r'^\s*(?:title|language|lang|العنوان|اللغة)\s*[:=]', line, re.IGNORECASE)
    ).strip()

    # Determine acts: prefer explicit markers (Act I/II/III), else split into 3
    acts = 3
    if re.search(r'\bact\s*[ivx]+\b', body, re.IGNORECASE):
        acts = len(re.findall(r'\bact\s*[ivx]+\b', body, re.IGNORECASE))
        acts = max(acts, 3)
    else:
        # if headings (###) present, use number of headings (bounded)
        headings = re.findall(r'^\s*#{1,6}\s+(.+)$', text, re.MULTILINE)
        if headings:
            acts = min(max(1, len(headings)), 6)

    # Turning points: sentences containing conflict markers or contrast words
    sentences = re.split(r'(?<=[.!?])\s+', body)
    tp_cues = ["but", "however", "until", "then", "when", "turns", "unexpected", "surprising", "yet", "nonetheless", "لكن", "ومع"]
    turning_points = []
    for s in sentences:
        low = s.lower()
        if any(cue in low for cue in tp_cues) and len(s.strip()) > 20:
            turning_points.append(s.strip())
    # Fallback: pick the last sentence of each third of the text
    if not turning_points:
        n = len(sentences)
        if n >= 3:
            turning_points = [sentences[max(0, i*n//3 - 1)].strip() for i in range(1, 3)]
        else:
            turning_points = [s.strip() for s in sentences[:2] if s.strip()]

    return {"acts": acts, "turning_points": turning_points}


def extract_characters(text: str) -> list[dict]:
    """Extract likely character names from script text.

    Returns list of dicts with at minimum 'name'. Heuristics:
      - Lines like NAME: dialogue
      - Proper nouns (capitalized sequences)
      - Arabic names detection by common name particles or capitalized-script heuristics
    """
    names = []
    seen = set()

    # 1) Speaker-prefixed lines (e.g., NARRATOR: ... or علي: ...)
    for m in re.finditer(r'^\s*([A-Z\u0600-\u06FF][A-Z\u0600-\u06FFa-z_\- ]{0,40})\s*:\s*', text, re.MULTILINE):
        candidate = m.group(1).strip()
        if candidate and candidate.lower() not in {"narrator", "voiceover", "voice"}:
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                names.append({"name": candidate})

    # 2) Proper noun sequences (English) — consecutive Capitalized words
    for m in re.finditer(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b', text):
        candidate = m.group(1).strip()
        if len(candidate) > 2 and candidate.lower() not in seen:
            seen.add(candidate.lower())
            names.append({"name": candidate})

    # 3) Arabic name heuristics: short sequences of Arabic letters (2-3 words)
    for m in re.finditer(r'([\u0600-\u06FF]{2,}\s+[\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,})?)', text):
        candidate = m.group(1).strip()
        if candidate and candidate.lower() not in seen:
            seen.add(candidate.lower())
            names.append({"name": candidate})

    # Limit results and ensure at least one entry
    if not names:
        # Try to create a narrator entry from the title or first non-empty line
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                name = stripped.split()[0][:32]
                names.append({"name": name})
                break
    # Deduplicate preserving order
    unique = []
    seen2 = set()
    for n in names:
        k = n["name"].lower()
        if k not in seen2:
            seen2.add(k)
            unique.append(n)
    return unique
