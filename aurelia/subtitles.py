"""AURELIA Maker — subtitle and caption production domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class SubtitleCue:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = 1
    start: float = 0.0
    end: float = 0.0
    text: str = ""
    speaker: str = ""
    style: str = "DEFAULT"

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def validate(self) -> dict[str, Any]:
        checks = {
            "sequence_valid": self.sequence > 0,
            "start_valid": self.start >= 0,
            "end_after_start": self.end >= self.start,
            "text_present": bool(self.text.strip()),
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
        }


@dataclass
class SubtitleTrack:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    language: str = "en"
    format: str = "SRT"
    cues: list[SubtitleCue] = field(default_factory=list)

    def add_cue(self, cue: SubtitleCue) -> None:
        self.cues.append(cue)

    @property
    def duration(self) -> float:
        return max((cue.end for cue in self.cues), default=0.0)


@dataclass
class SubtitlePlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    tracks: list[SubtitleTrack] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_track(self, track: SubtitleTrack) -> None:
        self.tracks.append(track)

    def validate(self) -> dict[str, Any]:
        all_cues = [
            cue
            for track in self.tracks
            for cue in track.cues
        ]

        checks = {
            "project_present": bool(self.project_id),
            "version_valid": self.version > 0,
            "languages_valid": all(
                bool(track.language.strip())
                for track in self.tracks
            ),
            "formats_valid": all(
                track.format.upper() in {"SRT", "VTT", "ASS"}
                for track in self.tracks
            ),
            "cues_valid": all(
                cue.validate()["passed"]
                for cue in all_cues
            ),
            "cue_order_valid": all(
                all(
                    track.cues[i].start <= track.cues[i + 1].start
                    for i in range(len(track.cues) - 1)
                )
                for track in self.tracks
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
        return json.dumps(
            self.to_dict(),
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubtitlePlan":
        data = dict(data)
        data["tracks"] = [
            SubtitleTrack(
                **{
                    **track,
                    "cues": [
                        SubtitleCue(**cue)
                        for cue in track.get("cues", [])
                    ],
                }
            )
            for track in data.get("tracks", [])
        ]
        return cls(**data)
