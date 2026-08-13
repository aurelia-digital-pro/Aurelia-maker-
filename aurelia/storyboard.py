"""AURELIA Maker — production storyboard domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class StoryboardFrame:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    frame_number: int = 1
    image_ref: str = ""
    composition: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    dialogue: str = ""
    notes: str = ""

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "frame_number_valid": self.frame_number > 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class Storyboard:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    directing_plan_id: str = ""
    version: int = 1
    frames: list[StoryboardFrame] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def add_frame(self, frame: StoryboardFrame) -> None:
        self.frames.append(frame)

    def validate(self) -> dict[str, Any]:
        checks = {
            "directing_plan_present": bool(self.directing_plan_id),
            "version_valid": self.version > 0,
            "frames_valid": all(frame.validate()["passed"] for frame in self.frames),
            "frame_numbers_unique_per_shot": self._unique_frame_numbers(),
        }
        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def _unique_frame_numbers(self) -> bool:
        groups: dict[str, set[int]] = {}
        for frame in self.frames:
            groups.setdefault(frame.shot_id, set())
            if frame.frame_number in groups[frame.shot_id]:
                return False
            groups[frame.shot_id].add(frame.frame_number)
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Storyboard":
        data = dict(data)
        data["frames"] = [
            StoryboardFrame(**frame)
            for frame in data.get("frames", [])
        ]
        return cls(**data)
