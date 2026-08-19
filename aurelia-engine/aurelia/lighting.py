"""AURELIA Maker — production lighting and atmosphere domain."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class LightSource:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: str = "area"
    intensity: float = 1.0
    color: str = "#FFFFFF"
    position: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def validate(self) -> dict[str, Any]:
        checks = {
            "name_present": bool(self.name),
            "type_present": bool(self.type),
            "intensity_valid": self.intensity >= 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class AtmospherePlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    fog: float = 0.0
    haze: float = 0.0
    dust: float = 0.0
    humidity: float = 0.0
    temperature: float = 0.0

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "fog_valid": 0 <= self.fog <= 1,
            "haze_valid": 0 <= self.haze <= 1,
            "dust_valid": 0 <= self.dust <= 1,
            "humidity_valid": 0 <= self.humidity <= 1,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class LightingPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    key: LightSource | None = None
    fill: LightSource | None = None
    rim: LightSource | None = None
    practicals: list[LightSource] = field(default_factory=list)
    atmosphere: AtmospherePlan | None = None
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "version_valid": self.version > 0,
            "key_valid": self.key is not None and self.key.validate()["passed"],
            "fill_valid": self.fill is not None and self.fill.validate()["passed"],
            "rim_valid": self.rim is not None and self.rim.validate()["passed"],
            "practicals_valid": all(
                light.validate()["passed"] for light in self.practicals
            ),
            "atmosphere_valid": (
                self.atmosphere is not None
                and self.atmosphere.validate()["passed"]
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

def process_light(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("LIGHT requires output path")

    source = data.get("input") or data.get("asset")
    if source is None:
        raise ValueError("LIGHT requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "LIGHT",
        "artifact": str(output_path),
        "lighting": data.get("lighting", {}),
    }
