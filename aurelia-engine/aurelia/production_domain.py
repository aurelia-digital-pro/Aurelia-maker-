"""AURELIA Maker — scalable cinematic production domain model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
import json
import uuid


class UnitType(str, Enum):
    SHOT = "SHOT"
    SCENE = "SCENE"
    SEQUENCE = "SEQUENCE"
    EPISODE = "EPISODE"
    SEASON = "SEASON"
    SERIES = "SERIES"
    FILM = "FILM"


UNIT_PARENT = {
    UnitType.SHOT: UnitType.SCENE,
    UnitType.SCENE: UnitType.SEQUENCE,
    UnitType.SEQUENCE: UnitType.EPISODE,
    UnitType.EPISODE: UnitType.SEASON,
    UnitType.SEASON: UnitType.SERIES,
}


@dataclass
class ProductionUnit:
    id: str
    type: UnitType
    name: str
    parent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        unit_type: UnitType,
        name: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ProductionUnit":
        return cls(
            id=f"{unit_type.value.lower()}-{uuid.uuid4().hex[:12]}",
            type=unit_type,
            name=name,
            parent_id=parent_id,
            metadata=dict(metadata or {}),
        )


@dataclass
class ProductionProject:
    project_id: str
    name: str
    units: dict[str, ProductionUnit] = field(default_factory=dict)

    def add_unit(self, unit: ProductionUnit) -> ProductionUnit:
        if unit.id in self.units:
            raise ValueError(f"Production unit already exists: {unit.id}")

        if unit.parent_id is not None:
            parent = self.units.get(unit.parent_id)

            if parent is None:
                raise ValueError(
                    f"Parent production unit does not exist: {unit.parent_id}"
                )

            expected_parent = UNIT_PARENT.get(unit.type)

            if expected_parent is not None and parent.type != expected_parent:
                raise ValueError(
                    f"{unit.type.value} requires parent "
                    f"{expected_parent.value}, got {parent.type.value}"
                )

            parent.children.append(unit.id)

        self.units[unit.id] = unit
        return unit

    def get_unit(self, unit_id: str) -> ProductionUnit:
        try:
            return self.units[unit_id]
        except KeyError:
            raise KeyError(f"Production unit not found: {unit_id}") from None

    def children_of(self, unit_id: str) -> list[ProductionUnit]:
        unit = self.get_unit(unit_id)
        return [self.units[child_id] for child_id in unit.children]

    def ancestors(self, unit_id: str) -> list[ProductionUnit]:
        result = []
        current = self.get_unit(unit_id)

        while current.parent_id is not None:
            current = self.get_unit(current.parent_id)
            result.append(current)

        return result

    def validate(self) -> None:
        for unit in self.units.values():
            if unit.parent_id is None:
                continue

            parent = self.get_unit(unit.parent_id)
            expected = UNIT_PARENT.get(unit.type)

            if expected is not None and parent.type != expected:
                raise ValueError(
                    f"Invalid hierarchy: {unit.type.value} "
                    f"{unit.id} -> {parent.type.value}"
                )

            if unit.id not in parent.children:
                raise ValueError(
                    f"Broken child relationship: {unit.id}"
                )

        for unit in self.units.values():
            for child_id in unit.children:
                child = self.get_unit(child_id)

                if child.parent_id != unit.id:
                    raise ValueError(
                        f"Broken parent relationship: {child.id}"
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "units": {
                unit_id: {
                    **asdict(unit),
                    "type": unit.type.value,
                }
                for unit_id, unit in self.units.items()
            },
        }

    def save(self, path: str) -> None:
        self.validate()

        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                self.to_dict(),
                handle,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )

    @classmethod
    def load(cls, path: str) -> "ProductionProject":
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)

        project = cls(
            project_id=data["project_id"],
            name=data["name"],
        )

        for unit_id, raw in data["units"].items():
            project.units[unit_id] = ProductionUnit(
                id=raw["id"],
                type=UnitType(raw["type"]),
                name=raw["name"],
                parent_id=raw.get("parent_id"),
                metadata=raw.get("metadata", {}),
                children=raw.get("children", []),
            )

        project.validate()
        return project


def validate_unit_type(value: str) -> UnitType:
    try:
        return UnitType(value.upper())
    except ValueError:
        raise ValueError(f"Unknown production unit type: {value}") from None


__all__ = [
    "ProductionProject",
    "ProductionUnit",
    "UNIT_PARENT",
    "UnitType",
    "validate_unit_type",
]
