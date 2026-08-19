"""AURELIA Maker — production VFX and compositing domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class VFXLayer:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    effect_type: str = ""
    enabled: bool = True
    parameters: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "name_present": bool(self.name),
            "effect_type_present": bool(self.effect_type),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class CompositeLayer:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source: str = ""
    blend_mode: str = "normal"
    opacity: float = 1.0
    z_index: int = 0

    def validate(self) -> dict[str, Any]:
        checks = {
            "name_present": bool(self.name),
            "source_present": bool(self.source),
            "opacity_valid": 0.0 <= self.opacity <= 1.0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class VFXCompositePlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    vfx_layers: list[VFXLayer] = field(default_factory=list)
    composite_layers: list[CompositeLayer] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "shot_present": bool(self.shot_id),
            "version_valid": self.version > 0,
            "vfx_valid": all(
                layer.validate()["passed"] for layer in self.vfx_layers
            ),
            "composite_valid": all(
                layer.validate()["passed"]
                for layer in self.composite_layers
            ),
            "z_order_unique": len(
                {layer.z_index for layer in self.composite_layers}
            ) == len(self.composite_layers),
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


VFXPlan = VFXLayer
