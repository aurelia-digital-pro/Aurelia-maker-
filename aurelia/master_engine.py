"""AURELIA Maker — professional mastering engine."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class MasterProfile:
    name: str = "streaming"
    resolution: str = "1920x1080"
    fps: float = 30.0
    codec: str = "h264"
    container: str = "mp4"
    audio_codec: str = "aac"
    audio_channels: int = 2
    pixel_format: str = "yuv420p"
    bitrate_kbps: int = 8000

    def validate(self) -> dict[str, Any]:
        width, height = self.resolution.split("x")
        checks = {
            "name_present": bool(self.name),
            "resolution_valid": int(width) > 0 and int(height) > 0,
            "fps_valid": self.fps > 0,
            "codec_valid": bool(self.codec),
            "container_valid": bool(self.container),
            "audio_codec_valid": bool(self.audio_codec),
            "channels_valid": self.audio_channels in {1, 2, 6, 8},
            "pixel_format_valid": bool(self.pixel_format),
            "bitrate_valid": self.bitrate_kbps > 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class MasterPackage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timeline_id: str = ""
    profile: MasterProfile = field(default_factory=MasterProfile)
    duration: float = 0.0
    source_hash: str = ""
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        profile_result = self.profile.validate()

        checks = {
            "timeline_present": bool(self.timeline_id),
            "duration_valid": self.duration >= 0,
            "source_hash_present": bool(self.source_hash),
            "profile_valid": profile_result["passed"],
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
            "profile": profile_result,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


class MasteringEngine:
    """Deterministic master specification and validation engine."""

    def __init__(self, profile: MasterProfile | None = None):
        self.profile = profile or MasterProfile()

    def validate(self) -> dict[str, Any]:
        return self.profile.validate()

    def build_master(
        self,
        timeline_id: str,
        duration: float,
        source_hash: str,
    ) -> MasterPackage:
        master = MasterPackage(
            timeline_id=timeline_id,
            profile=self.profile,
            duration=duration,
            source_hash=source_hash,
        )
        master.validate()
        return master

    def build_master_plan(
        self,
        timeline_id: str,
        duration: float,
        source_hash: str,
    ) -> dict[str, Any]:
        master = self.build_master(
            timeline_id=timeline_id,
            duration=duration,
            source_hash=source_hash,
        )
        return master.to_dict()


def process_master(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("MASTER requires output path")

    source = data.get("input") or data.get("video") or data.get("master")
    if source is None:
        raise ValueError("MASTER requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "MASTER",
        "artifact": str(output_path),
    }
