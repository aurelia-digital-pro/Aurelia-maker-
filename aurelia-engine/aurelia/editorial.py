"""AURELIA Maker — professional editorial and timeline engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class TimelineClip:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    start: float = 0.0
    duration: float = 0.0
    source: str = ""
    transition_in: str = ""
    transition_out: str = ""

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration > 0,
            "source_present": bool(self.source),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class Timeline:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    episode_id: str = ""
    fps: float = 24.0
    clips: list[TimelineClip] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_clip(self, clip: TimelineClip) -> None:
        self.clips.append(clip)

    @property
    def duration(self) -> float:
        if not self.clips:
            return 0.0
        return max(
            clip.start + clip.duration
            for clip in self.clips
        )

    def validate(self) -> dict[str, Any]:
        ordered = sorted(
            self.clips,
            key=lambda clip: (clip.start, clip.id),
        )

        overlap_free = all(
            ordered[index].start + ordered[index].duration
            <= ordered[index + 1].start
            for index in range(len(ordered) - 1)
        )

        checks = {
            "episode_present": bool(self.episode_id),
            "fps_valid": self.fps > 0,
            "version_valid": self.version > 0,
            "clips_valid": all(
                clip.validate()["passed"]
                for clip in self.clips
            ),
            "timeline_overlap_free": overlap_free,
            "clip_ids_unique": len(
                {clip.id for clip in self.clips}
            ) == len(self.clips),
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
            "duration": self.duration,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Timeline":
        data = dict(data)
        data["clips"] = [
            TimelineClip(**clip)
            for clip in data.get("clips", [])
        ]
        return cls(**data)


@dataclass
class EditorialPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timeline: Timeline | None = None
    pacing: str = "cinematic"
    transitions: list[str] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        timeline_result = (
            self.timeline.validate()
            if self.timeline is not None
            else {"passed": False, "checks": {"timeline_present": False}}
        )

        checks = {
            "timeline_present": self.timeline is not None,
            "pacing_present": bool(self.pacing),
            "version_valid": self.version > 0,
            "timeline_valid": timeline_result["passed"],
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditorialPlan":
        data = dict(data)
        timeline = data.get("timeline")
        if timeline is not None:
            data["timeline"] = Timeline.from_dict(timeline)
        return cls(**data)
