"""AURELIA Maker — production sound and music domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class SoundTrack:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source: str = ""
    track_type: str = "sfx"
    start: float = 0.0
    duration: float = 0.0
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "name_present": bool(self.name),
            "source_present": bool(self.source),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration >= 0,
            "volume_valid": self.volume >= 0,
            "fade_in_valid": self.fade_in >= 0,
            "fade_out_valid": self.fade_out >= 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class MusicCue:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source: str = ""
    start: float = 0.0
    duration: float = 0.0
    volume: float = 1.0
    tempo: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "name_present": bool(self.name),
            "source_present": bool(self.source),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration >= 0,
            "volume_valid": self.volume >= 0,
            "tempo_valid": self.tempo >= 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class SoundPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    dialogue_tracks: list[SoundTrack] = field(default_factory=list)
    sound_effects: list[SoundTrack] = field(default_factory=list)
    ambience: list[SoundTrack] = field(default_factory=list)
    music: list[MusicCue] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        all_sound = (
            self.dialogue_tracks
            + self.sound_effects
            + self.ambience
        )

        checks = {
            "shot_present": bool(self.shot_id),
            "version_valid": self.version > 0,
            "sound_valid": all(
                track.validate()["passed"] for track in all_sound
            ),
            "music_valid": all(
                cue.validate()["passed"] for cue in self.music
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
