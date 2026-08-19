"""AURELIA Maker — production animatic domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class AnimaticClip:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    storyboard_frame_id: str = ""
    source_ref: str = ""
    start: float = 0.0
    duration: float = 0.0
    audio_ref: str = ""
    transition: str = "cut"

    @property
    def end(self) -> float:
        return self.start + self.duration

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "storyboard_frame_present": bool(self.storyboard_frame_id),
            "source_present": bool(self.source_ref),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration > 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class Animatic:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    storyboard_id: str = ""
    version: int = 1
    clips: list[AnimaticClip] = field(default_factory=list)
    frame_rate: float = 24.0
    validation: dict[str, Any] = field(default_factory=dict)

    def add_clip(self, clip: AnimaticClip) -> None:
        self.clips.append(clip)

    @property
    def duration(self) -> float:
        return max((clip.end for clip in self.clips), default=0.0)

    def validate(self) -> dict[str, Any]:
        checks = {
            "storyboard_present": bool(self.storyboard_id),
            "version_valid": self.version > 0,
            "frame_rate_valid": self.frame_rate > 0,
            "clips_valid": all(
                clip.validate()["passed"] for clip in self.clips
            ),
            "timeline_valid": self._timeline_valid(),
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def _timeline_valid(self) -> bool:
        ordered = sorted(self.clips, key=lambda clip: clip.start)
        previous_end = 0.0

        for clip in ordered:
            if clip.start < previous_end:
                return False
            previous_end = clip.end

        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Animatic":
        data = dict(data)
        data["clips"] = [
            AnimaticClip(**clip)
            for clip in data.get("clips", [])
        ]
        return cls(**data)
