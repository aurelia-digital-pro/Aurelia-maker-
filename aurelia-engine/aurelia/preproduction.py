"""AURELIA Maker — production-grade pre-production planning domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class LocationPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    environment: str = ""
    requirements: list[str] = field(default_factory=list)
    continuity_notes: list[str] = field(default_factory=list)


@dataclass
class CastingPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    character_id: str = ""
    performer: str = ""
    voice: str = ""
    notes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductionRequirement:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: str = ""
    item: str = ""
    source: str = ""
    required: bool = True
    status: str = "PLANNED"


@dataclass
class PreProductionPlan:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    version: int = 1
    locations: list[LocationPlan] = field(default_factory=list)
    casting: list[CastingPlan] = field(default_factory=list)
    requirements: list[ProductionRequirement] = field(default_factory=list)
    schedule: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)

    def add_location(self, location: LocationPlan) -> None:
        self.locations.append(location)

    def add_casting(self, casting: CastingPlan) -> None:
        self.casting.append(casting)

    def add_requirement(self, requirement: ProductionRequirement) -> None:
        self.requirements.append(requirement)

    def validate(self) -> dict[str, Any]:
        checks = {
            "project_present": bool(self.project_id),
            "version_valid": self.version > 0,
            "locations_valid": all(bool(x.name) for x in self.locations),
            "casting_valid": all(bool(x.character_id) for x in self.casting),
            "requirements_valid": all(bool(x.item) for x in self.requirements),
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
    def from_dict(cls, data: dict[str, Any]) -> "PreProductionPlan":
        data = dict(data)
        data["locations"] = [
            LocationPlan(**item) for item in data.get("locations", [])
        ]
        data["casting"] = [
            CastingPlan(**item) for item in data.get("casting", [])
        ]
        data["requirements"] = [
            ProductionRequirement(**item)
            for item in data.get("requirements", [])
        ]
        return cls(**data)
