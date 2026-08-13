"""AURELIA Maker — professional editing and assembly domain."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class EditClip:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    asset_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    source_in: float = 0.0
    source_out: float = 0.0
    transition: str = "CUT"
    effects: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "valid_timeline": self.end_time >= self.start_time,
            "valid_source_range": self.source_out >= self.source_in,
            "valid_start": self.start_time >= 0,
            "valid_source_in": self.source_in >= 0,
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
        }


@dataclass
class EditTrack:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "V1"
    track_type: str = "VIDEO"
    clips: list[EditClip] = field(default_factory=list)

    def add_clip(self, clip: EditClip) -> None:
        self.clips.append(clip)

    @property
    def duration(self) -> float:
        return max((clip.end_time for clip in self.clips), default=0.0)


@dataclass
class EditPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    tracks: list[EditTrack] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_track(self, track: EditTrack) -> None:
        self.tracks.append(track)

    @property
    def duration(self) -> float:
        return max((track.duration for track in self.tracks), default=0.0)

    def validate(self) -> dict[str, Any]:
        clips = [
            clip
            for track in self.tracks
            for clip in track.clips
        ]

        checks = {
            "project_present": bool(self.project_id),
            "version_valid": self.version > 0,
            "track_names_unique": len(
                {track.name for track in self.tracks}
            ) == len(self.tracks),
            "clips_valid": all(
                clip.validate()["passed"] for clip in clips
            ),
            "timeline_order_valid": all(
                all(
                    track.clips[i].start_time
                    <= track.clips[i + 1].start_time
                    for i in range(len(track.clips) - 1)
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
    def from_dict(cls, data: dict[str, Any]) -> "EditPlan":
        tracks = []

        for track_data in data.get("tracks", []):
            track_data = dict(track_data)
            clips = [
                EditClip(**clip_data)
                for clip_data in track_data.get("clips", [])
            ]
            track_data["clips"] = clips
            tracks.append(EditTrack(**track_data))

        data = dict(data)
        data["tracks"] = tracks
        return cls(**data)


def process_edit(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("EDIT requires output path")

    source = data.get("input") or data.get("visual") or data.get("video")
    audio = data.get("audio")

    if source is None:
        raise ValueError("EDIT requires a visual/video input")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "EDIT",
        "artifact": str(output_path),
        "audio": audio,
    }
