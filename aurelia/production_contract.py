"""Canonical stage order and payload contracts for AURELIA Maker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


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
            errors.append(f"Unknown production stage: {self.stage}")
        for field_name, fields in (
            ("required_inputs", self.required_inputs),
            ("required_outputs", self.required_outputs),
        ):
            if any(not isinstance(value, str) or not value for value in fields):
                errors.append(f"{field_name} must contain non-empty strings")
            if len(set(fields)) != len(fields):
                errors.append(f"{field_name} contains duplicates")
        return {"valid": not errors, "stage": self.stage, "errors": errors}

    def validate_inputs(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        missing = [key for key in self.required_inputs if key not in payload]
        return {
            "valid": not missing,
            "stage": self.stage,
            "missing": missing,
            "errors": [f"{self.stage} missing required input: {key}" for key in missing],
        }

    def validate_outputs(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        missing = [key for key in self.required_outputs if key not in payload]
        return {
            "valid": not missing,
            "stage": self.stage,
            "missing": missing,
            "errors": [f"{self.stage} missing required output: {key}" for key in missing],
        }


def build_production_contracts() -> dict[str, ProductionContract]:
    contracts: dict[str, ProductionContract] = {}

    def add(stage: str, inputs: tuple[str, ...], outputs: tuple[str, ...]) -> None:
        contracts[stage] = ProductionContract(
            stage=stage,
            required_inputs=inputs,
            required_outputs=outputs,
        )

    add("SCRIPT", ("episode_id", "title", "language", "profile", "source_text_sha256"), ("text", "script_chars", "script_words"))
    add("DEVELOPMENT", ("text",), ("genre", "theme", "logline"))
    add("STORY", ("text",), ("acts", "turning_points"))
    add("WORLD", ("text",), ("setting", "time_period", "atmosphere"))
    add("CHARACTER", ("text",), ("character_count", "characters"))
    add("SERIES_BIBLE", ("text", "episode_id", "title", "language", "profile"), ("series_title", "episode_number"))
    add("RESEARCH", ("text",), ("fact_count", "facts"))
    add("PRE_PRODUCTION", ("text",), ("scene_count", "total_planned_duration"))
    add("SEQUENCE", ("scene_count",), ("total_shots",))
    add("SCENE", ("total_shots",), ("scenes",))
    add("SHOT", ("scenes",), ("shot_summary",))
    add("STORYBOARD", ("shot_summary",), ("storyboard_scenes",))
    add("ANIMATIC", ("storyboard_scenes",), ("animatic_duration",))
    add("VISUAL", ("animatic_duration",), ("visual_count", "visual_scene_keys"))
    add("ASSET", ("visual_count",), ("asset_count",))
    add("CAMERA", ("asset_count",), ("movements",))
    add("DEPTH", ("movements",), ("dof_values",))
    add("MOTION", ("dof_values",), ("motions",))
    add("LIGHT", ("motions",), ("lighting_count",))
    add("ATMOSPHERE", ("lighting_count",), ("atmosphere",))
    add("VFX", ("atmosphere",), ("vfx",))
    add("NARRATION", ("vfx",), ("narration_duration", "narration_language", "audio_provenance"))
    add("DIALOGUE", ("audio_provenance",), ("dialogue",))
    add("SOUND", ("dialogue",), ("sound_design_path", "sound_design_boundaries", "ambient_path", "ambient_provenance"))
    add("MUSIC", ("sound_design_path", "ambient_path"), ("music_duration", "music_path", "music_provenance"))
    add("EDIT", ("music_path", "sound_design_path"), ("clip_count", "edit_path"))
    add("COLOR", ("edit_path",), ("graded_path",))
    add("SUBTITLE", ("graded_path",), ("subtitle_path",))
    add("MASTER", ("graded_path", "subtitle_path"), ("master_path",))
    add("QC", ("master_path",), ("qc", "qc_passed", "qc_fatals", "qc_warnings"))
    add("DELIVERY", ("master_path", "qc"), ("artifact", "manifest", "delivery_artifact"))

    if tuple(contracts) != PRODUCTION_STAGES:
        raise RuntimeError("Canonical production contract definition is incomplete")
    return contracts


def validate_production_contracts(
    contracts: dict[str, ProductionContract],
) -> dict[str, Any]:
    errors: list[str] = []
    if tuple(contracts.keys()) != PRODUCTION_STAGES:
        errors.append("Production contract order does not match PRODUCTION_STAGES")
    for stage, contract in contracts.items():
        result = contract.validate()
        if not result["valid"]:
            errors.extend(result["errors"])
        if contract.stage != stage:
            errors.append(f"Contract key mismatch: {stage}")
    return {"valid": not errors, "count": len(contracts), "errors": errors}


__all__ = [
    "PRODUCTION_STAGES",
    "ProductionContract",
    "build_production_contracts",
    "validate_production_contracts",
]
