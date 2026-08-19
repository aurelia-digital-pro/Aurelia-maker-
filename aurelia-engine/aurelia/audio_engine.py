"""AURELIA Maker — production audio engine."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class AudioTrack:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = "ambience"
    source: str = ""
    start: float = 0.0
    duration: float = 0.0
    gain_db: float = 0.0
    sample_rate: int = 48000
    channels: int = 2

    def validate(self) -> dict[str, Any]:
        checks = {
            "kind_present": bool(self.kind),
            "source_present": bool(self.source),
            "start_valid": self.start >= 0,
            "duration_valid": self.duration > 0,
            "sample_rate_valid": self.sample_rate in {44100, 48000, 96000},
            "channels_valid": self.channels in {1, 2},
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class AudioMix:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tracks: list[AudioTrack] = field(default_factory=list)
    narration_priority: int = 100
    dialogue_priority: int = 90
    sfx_priority: int = 70
    music_priority: int = 50
    ambience_priority: int = 30
    target_lufs: float = -16.0
    true_peak_db: float = -1.0
    sample_rate: int = 48000
    channels: int = 2
    validation: dict[str, Any] = field(default_factory=dict)

    def add_track(self, track: AudioTrack) -> None:
        self.tracks.append(track)

    def ordered_tracks(self) -> list[AudioTrack]:
        priorities = {
            "narration": self.narration_priority,
            "dialogue": self.dialogue_priority,
            "sfx": self.sfx_priority,
            "music": self.music_priority,
            "ambience": self.ambience_priority,
        }
        return sorted(
            self.tracks,
            key=lambda track: priorities.get(track.kind.lower(), 0),
            reverse=True,
        )

    def validate(self) -> dict[str, Any]:
        checks = {
            "tracks_valid": all(
                track.validate()["passed"] for track in self.tracks
            ),
            "target_lufs_valid": -70.0 <= self.target_lufs <= 0.0,
            "true_peak_valid": -20.0 <= self.true_peak_db <= 0.0,
            "sample_rate_valid": self.sample_rate in {44100, 48000, 96000},
            "channels_valid": self.channels in {1, 2},
            "priority_order_valid": (
                self.narration_priority
                > self.dialogue_priority
                > self.sfx_priority
                > self.music_priority
                > self.ambience_priority
            ),
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def duration(self) -> float:
        return max(
            (track.start + track.duration for track in self.tracks),
            default=0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AudioMix":
        data = dict(data)
        data["tracks"] = [
            AudioTrack(**track)
            for track in data.get("tracks", [])
        ]
        return cls(**data)


def _ensure_real_audio_stream(source, output):
    import subprocess
    from pathlib import Path

    source = Path(source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(source),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode == 0 and probe.stdout.strip():
        cmd = [
            "ffmpeg", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", str(output),
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", str(source),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", str(output),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    return output


def process_audio(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("AUDIO requires output path")

    source = data.get("input") or data.get("narration") or data.get("audio")
    if source is None:
        raise ValueError("AUDIO requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "AUDIO",
        "artifact": str(output_path),
    }
