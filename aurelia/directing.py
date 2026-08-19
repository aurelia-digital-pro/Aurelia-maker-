"""AURELIA Maker — cinematic directing hierarchy: sequence, scene, shot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class Shot:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    number: int = 1
    description: str = ""
    duration: float = 0.0
    camera: dict[str, Any] = field(default_factory=dict)
    motion: dict[str, Any] = field(default_factory=dict)
    visual: dict[str, Any] = field(default_factory=dict)
    audio: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scene:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    number: int = 1
    title: str = ""
    purpose: str = ""
    shots: list[Shot] = field(default_factory=list)

    def add_shot(self, shot: Shot) -> None:
        self.shots.append(shot)

    @property
    def duration(self) -> float:
        return sum(shot.duration for shot in self.shots)


@dataclass
class Sequence:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    number: int = 1
    title: str = ""
    purpose: str = ""
    scenes: list[Scene] = field(default_factory=list)

    def add_scene(self, scene: Scene) -> None:
        self.scenes.append(scene)

    @property
    def duration(self) -> float:
        return sum(scene.duration for scene in self.scenes)


@dataclass
class DirectingPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    sequences: list[Sequence] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_sequence(self, sequence: Sequence) -> None:
        self.sequences.append(sequence)

    def validate(self) -> dict[str, Any]:
        checks = {
            "project_present": bool(self.project_id),
            "version_valid": self.version > 0,
            "sequence_numbers_unique": len(
                {x.number for x in self.sequences}
            ) == len(self.sequences),
            "scene_numbers_valid": all(
                scene.number > 0
                for sequence in self.sequences
                for scene in sequence.scenes
            ),
            "shot_numbers_valid": all(
                shot.number > 0
                for sequence in self.sequences
                for scene in sequence.scenes
                for shot in scene.shots
            ),
            "durations_valid": all(
                shot.duration >= 0
                for sequence in self.sequences
                for scene in sequence.scenes
                for shot in scene.shots
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DirectingPlan":
        sequences = []

        for sequence_data in data.get("sequences", []):
            scenes = []

            for scene_data in sequence_data.get("scenes", []):
                shots = [
                    Shot(**shot_data)
                    for shot_data in scene_data.get("shots", [])
                ]

                scene_data = dict(scene_data)
                scene_data["shots"] = shots
                scenes.append(Scene(**scene_data))

            sequence_data = dict(sequence_data)
            sequence_data["scenes"] = scenes
            sequences.append(Sequence(**sequence_data))

        data = dict(data)
        data["sequences"] = sequences
        return cls(**data)
