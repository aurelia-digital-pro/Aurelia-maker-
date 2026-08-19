from __future__ import annotations
from pathlib import Path
"""AURELIA Maker — production visual pipeline domain."""


from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class VisualAsset:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    source_ref: str = ""
    asset_type: str = "image"
    width: int = 0
    height: int = 0
    frame_rate: float = 24.0
    duration: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "source_present": bool(self.source_ref),
            "dimensions_valid": self.width > 0 and self.height > 0,
            "frame_rate_valid": self.frame_rate > 0,
            "duration_valid": self.duration >= 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class VisualPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    animatic_id: str = ""
    version: int = 1
    assets: list[VisualAsset] = field(default_factory=list)
    style: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)

    def add_asset(self, asset: VisualAsset) -> None:
        self.assets.append(asset)

    def validate(self) -> dict[str, Any]:
        checks = {
            "animatic_present": bool(self.animatic_id),
            "version_valid": self.version > 0,
            "assets_valid": all(
                asset.validate()["passed"] for asset in self.assets
            ),
            "asset_ids_unique": len(
                {asset.id for asset in self.assets}
            ) == len(self.assets),
            "shot_ids_present": all(
                bool(asset.shot_id) for asset in self.assets
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualPlan":
        data = dict(data)
        data["assets"] = [
            VisualAsset(**asset)
            for asset in data.get("assets", [])
        ]
        return cls(**data)


VisualPipeline = VisualAsset


def process_visual(data: dict) -> dict:
    from .visuals import render_cinematic_shot

    output = data.get("output")
    if output is None:
        raise ValueError("VISUAL requires output path")

    shot = data.get("shot")
    if not shot:
        raise ValueError("VISUAL requires SHOT output")

    source = data.get("visual_source") or data.get("source")
    if source is None:
        raise ValueError("VISUAL requires a visual source; SCRIPT is not a visual source")

    source = Path(source)
    if not source.exists():
        raise ValueError(f"VISUAL source does not exist: {source}")

    if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError(f"VISUAL source must be an image: {source}")

    result = render_cinematic_shot(
        source,
        Path(output),
        shot,
        data.get("cinematography"),
        data.get("lighting"),
        data.get("vfx"),
    )

    return {
        "stage": "VISUAL",
        "artifact": str(result),
    }
