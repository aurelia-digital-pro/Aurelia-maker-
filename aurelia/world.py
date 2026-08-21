"""AURELIA Maker — world, character, and series-bible domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid
import re


@dataclass
class WorldElement:
    id: str
    name: str
    category: str
    description: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class Character:
    id: str
    name: str
    role: str
    description: str
    traits: list[str] = field(default_factory=list)
    relationships: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SeriesBible:
    id: str
    project_id: str
    title: str
    premise: str
    themes: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    world_elements: dict[str, WorldElement] = field(default_factory=dict)
    characters: dict[str, Character] = field(default_factory=dict)
    continuity: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def add_world_element(
        self,
        name: str,
        category: str,
        description: str,
        attributes: dict[str, Any] | None = None,
    ) -> WorldElement:
        if not name.strip():
            raise ValueError("World element name is required")
        if not category.strip():
            raise ValueError("World element category is required")
        if not description.strip():
            raise ValueError("World element description is required")

        element = WorldElement(
            id=str(uuid.uuid4()),
            name=name.strip(),
            category=category.strip(),
            description=description.strip(),
            attributes={} if attributes is None else dict(attributes),
        )
        self.world_elements[element.id] = element
        return element

    def add_character(
        self,
        name: str,
        role: str,
        description: str,
        traits: list[str] | None = None,
        relationships: dict[str, str] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Character:
        if not name.strip():
            raise ValueError("Character name is required")
        if not role.strip():
            raise ValueError("Character role is required")
        if not description.strip():
            raise ValueError("Character description is required")

        character = Character(
            id=str(uuid.uuid4()),
            name=name.strip(),
            role=role.strip(),
            description=description.strip(),
            traits=[] if traits is None else list(traits),
            relationships={} if relationships is None else dict(relationships),
            attributes={} if attributes is None else dict(attributes),
        )
        self.characters[character.id] = character
        return character

    def validate(self) -> None:
        if not self.project_id.strip():
            raise ValueError("Series bible project_id is required")
        if not self.title.strip():
            raise ValueError("Series bible title is required")
        if not self.premise.strip():
            raise ValueError("Series bible premise is required")

        for element_id, element in self.world_elements.items():
            if element_id != element.id:
                raise ValueError("World element key/id mismatch")
            if not element.name or not element.category or not element.description:
                raise ValueError(f"Invalid world element: {element.id}")

        for character_id, character in self.characters.items():
            if character_id != character.id:
                raise ValueError("Character key/id mismatch")
            if not character.name or not character.role or not character.description:
                raise ValueError(f"Invalid character: {character.id}")

    def snapshot(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass
class WorldRepository:
    bibles: dict[str, SeriesBible] = field(default_factory=dict)

    def create_bible(
        self,
        project_id: str,
        title: str,
        premise: str,
        themes: list[str] | None = None,
        rules: list[str] | None = None,
    ) -> SeriesBible:
        if not project_id.strip():
            raise ValueError("Project id is required")
        if not title.strip():
            raise ValueError("Bible title is required")
        if not premise.strip():
            raise ValueError("Bible premise is required")

        bible = SeriesBible(
            id=str(uuid.uuid4()),
            project_id=project_id,
            title=title.strip(),
            premise=premise.strip(),
            themes=[] if themes is None else list(themes),
            rules=[] if rules is None else list(rules),
        )
        self.bibles[bible.id] = bible
        return bible

    def get_for_project(self, project_id: str) -> SeriesBible | None:
        matches = [
            bible
            for bible in self.bibles.values()
            if bible.project_id == project_id
        ]
        return matches[-1] if matches else None

    def validate(self) -> None:
        for bible in self.bibles.values():
            bible.validate()

    def save(self, path: str) -> None:
        from pathlib import Path

        self.validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "bibles": {
                        key: bible.snapshot()
                        for key, bible in self.bibles.items()
                    }
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str) -> "WorldRepository":
        from pathlib import Path

        data = json.loads(
            Path(path).read_text(encoding="utf-8")
        )

        repository = cls()

        for key, value in data.get("bibles", {}).items():
            bible = SeriesBible(
                id=value["id"],
                project_id=value["project_id"],
                title=value["title"],
                premise=value["premise"],
                themes=value.get("themes", []),
                rules=value.get("rules", []),
                continuity=value.get("continuity", {}),
                version=value.get("version", 1),
            )

            for element_id, element in value.get("world_elements", {}).items():
                bible.world_elements[element_id] = WorldElement(**element)

            for character_id, character in value.get("characters", {}).items():
                bible.characters[character_id] = Character(**character)

            repository.bibles[key] = bible

        repository.validate()
        return repository


# Compatibility: build_world_context required by factory_runner
def _detect_time_period(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(19|20)\d{2}\b", lower):
        m = re.search(r"\b(19|20)\d{2}\b", lower)
        if m:
            return f"{m.group(0)}s"
    if any(k in lower for k in ["ancient", "medieval", "renaissance", "future", "futuristic", "modern", "contemporary"]):
        if "ancient" in lower or "medieval" in lower:
            return "ancient"
        if "future" in lower or "futuristic" in lower:
            return "future"
        if "modern" in lower or "contemporary" in lower:
            return "modern"
    return "unspecified"


def _detect_setting(text: str) -> str:
    keywords = ["city", "desert", "ocean", "sea", "space", "lab", "laboratory", "forest", "village", "mountain", "island", "jungle", "subway", "airport"]
    lower = text.lower()
    for k in keywords:
        if k in lower:
            return k
    arabic_map = {"مدينة": "city", "صحراء": "desert", "بحر": "ocean", "فضاء": "space", "غابة": "forest"}
    for ar, en in arabic_map.items():
        if ar in text:
            return en
    return "unspecified"


def _detect_atmosphere(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["tense", "tension", "suspense", "mysterious", "mystery", "ominous"]):
        return "tense"
    if any(w in lower for w in ["peaceful", "calm", "serene", "tranquil"]):
        return "calm"
    if any(w in lower for w in ["dream", "surreal", "fantasy", "magical"]):
        return "surreal"
    if any(w in lower for w in ["documentary", "informative", "factual"]):
        return "informative"
    return "neutral"


def build_world_context(text: str) -> dict:
    """Return minimal world context: setting, time_period, atmosphere."""
    body = "\n".join(
        line for line in text.splitlines()
        if not re.match(r'^\s*(?:title|language|lang|العنوان|اللغة)\s*[:=]', line, re.IGNORECASE)
    ).strip()
    setting = _detect_setting(body)
    time_period = _detect_time_period(body)
    atmosphere = _detect_atmosphere(body)
    return {"setting": setting, "time_period": time_period, "atmosphere": atmosphere}
