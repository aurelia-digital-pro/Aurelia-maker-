"""AURELIA Maker — master render and delivery preparation domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class MasterOutput:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    format: str = "MP4"
    codec: str = "H264"
    width: int = 1920
    height: int = 1080
    fps: float = 24.0
    duration: float = 0.0
    audio_channels: int = 2
    bitrate: int = 0
    checksum: str = ""

    def validate(self) -> dict[str, Any]:
        checks = {
            "path_present": bool(self.path),
            "format_valid": self.format.upper() in {"MP4", "MOV", "MKV"},
            "codec_present": bool(self.codec),
            "resolution_valid": self.width > 0 and self.height > 0,
            "fps_valid": self.fps > 0,
            "duration_valid": self.duration >= 0,
            "audio_channels_valid": self.audio_channels > 0,
        }
        return {
            "passed": all(checks.values()),
            "checks": checks,
        }


@dataclass
class MasterPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    outputs: list[MasterOutput] = field(default_factory=list)
    color_space: str = "Rec.709"
    audio_sample_rate: int = 48000
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_output(self, output: MasterOutput) -> None:
        self.outputs.append(output)

    def validate(self) -> dict[str, Any]:
        checks = {
            "project_present": bool(self.project_id),
            "version_valid": self.version > 0,
            "color_space_present": bool(self.color_space),
            "sample_rate_valid": self.audio_sample_rate > 0,
            "outputs_present": bool(self.outputs),
            "outputs_valid": all(
                output.validate()["passed"]
                for output in self.outputs
            ),
            "output_paths_unique": len(
                {output.path for output in self.outputs}
            ) == len(self.outputs),
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
    def from_dict(cls, data: dict[str, Any]) -> "MasterPlan":
        data = dict(data)
        data["outputs"] = [
            MasterOutput(**output)
            for output in data.get("outputs", [])
        ]
        return cls(**data)
