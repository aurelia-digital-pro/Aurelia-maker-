"""AURELIA Maker — canonical production contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PRODUCTION_STAGES: tuple[str, ...] = (
    "SCRIPT",
    "DEVELOPMENT",
    "STORY",
    "WORLD",
    "CHARACTER",
    "SERIES_BIBLE",
    "RESEARCH",
    "PRE_PRODUCTION",
    "SEQUENCE",
    "SCENE",
    "SHOT",
    "STORYBOARD",
    "ANIMATIC",
    "VISUAL",
    "ASSET",
    "CAMERA",
    "DEPTH",
    "MOTION",
    "LIGHT",
    "ATMOSPHERE",
    "VFX",
    "NARRATION",
    "DIALOGUE",
    "SOUND",
    "MUSIC",
    "EDIT",
    "COLOR",
    "SUBTITLE",
    "MASTER",
    "QC",
    "DELIVERY",
)


@dataclass(frozen=True)
class ProductionContract:
    stage: str
    required_inputs: tuple[str, ...] = ()
    required_outputs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        errors: list[str] = []

        if not self.stage:
            errors.append("stage is required")

        if self.stage not in PRODUCTION_STAGES:
            errors.append(
                f"Unknown production stage: {self.stage}"
            )

        return {
            "valid": not errors,
            "stage": self.stage,
            "errors": errors,
        }


def build_production_contracts() -> dict[str, ProductionContract]:
    return {
        stage: ProductionContract(stage=stage)
        for stage in PRODUCTION_STAGES
    }


def validate_production_contracts(
    contracts: dict[str, ProductionContract],
) -> dict[str, Any]:
    errors: list[str] = []

    if tuple(contracts.keys()) != PRODUCTION_STAGES:
        errors.append(
            "Production contract order does not match "
            "PRODUCTION_STAGES"
        )

    for stage, contract in contracts.items():
        result = contract.validate()

        if not result["valid"]:
            errors.extend(result["errors"])

        if contract.stage != stage:
            errors.append(
                f"Contract key mismatch: {stage}"
            )

    return {
        "valid": not errors,
        "count": len(contracts),
        "errors": errors,
    }


__all__ = [
    "PRODUCTION_STAGES",
    "ProductionContract",
    "build_production_contracts",
    "validate_production_contracts",
]
