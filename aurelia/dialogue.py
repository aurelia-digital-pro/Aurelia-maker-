"""AURELIA Maker — narration and dialogue production domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class DialogueLine:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character: str = ""
    text: str = ""
    start: float = 0.0
    duration: float = 0.0
    language: str = "en"
    voice: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "character_present": bool(self.character),
            "text_present": bool(self.text.strip()),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration >= 0,
            "language_present": bool(self.language),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class NarrationSegment:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    start: float = 0.0
    duration: float = 0.0
    language: str = "en"
    voice: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "text_present": bool(self.text.strip()),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration >= 0,
            "language_present": bool(self.language),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class DialoguePlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    narration: list[NarrationSegment] = field(default_factory=list)
    dialogue: list[DialogueLine] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "version_valid": self.version > 0,
            "narration_valid": all(
                segment.validate()["passed"]
                for segment in self.narration
            ),
            "dialogue_valid": all(
                line.validate()["passed"]
                for line in self.dialogue
            ),
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


DialogueTrack = DialogueLine
