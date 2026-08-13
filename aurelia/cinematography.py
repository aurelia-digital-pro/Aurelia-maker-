"""AURELIA Maker — production cinematography domain: camera, depth, motion."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class CameraPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    lens_mm: float = 50.0
    aperture: float = 2.8
    distance: float = 0.0
    height: float = 0.0
    angle: float = 0.0
    framing: str = "medium"
    movement: str = "static"
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "lens_valid": self.lens_mm > 0,
            "aperture_valid": self.aperture > 0,
            "distance_valid": self.distance >= 0,
        }
        self.validation = {"passed": all(checks.values()), "checks": checks}
        return self.validation


@dataclass
class DepthPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    foreground: dict[str, Any] = field(default_factory=dict)
    midground: dict[str, Any] = field(default_factory=dict)
    background: dict[str, Any] = field(default_factory=dict)
    depth_of_field: float = 0.0

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "depth_valid": self.depth_of_field >= 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class MotionPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    type: str = "static"
    duration: float = 0.0
    start: dict[str, Any] = field(default_factory=dict)
    end: dict[str, Any] = field(default_factory=dict)
    easing: str = "linear"

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "duration_valid": self.duration >= 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class CinematographyPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    camera: CameraPlan | None = None
    depth: DepthPlan | None = None
    motion: MotionPlan | None = None
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "version_valid": self.version > 0,
            "camera_valid": self.camera is not None
            and self.camera.validate()["passed"],
            "depth_valid": self.depth is not None
            and self.depth.validate()["passed"],
            "motion_valid": self.motion is not None
            and self.motion.validate()["passed"],
        }
        self.validation = {"passed": all(checks.values()), "checks": checks}
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def process_camera(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("CAMERA requires output path")

    source = data.get("asset") or data.get("input")
    if source is None:
        raise ValueError("CAMERA requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "CAMERA",
        "artifact": str(output_path),
        "camera": data.get("camera", {}),
    }
