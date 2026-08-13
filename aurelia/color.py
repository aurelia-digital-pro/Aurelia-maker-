"""AURELIA Maker — professional color grading and finishing domain."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class ColorGrade:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    shot_id: str = ""
    name: str = "cinematic"
    look: str = "natural"
    exposure: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    temperature: float = 6500.0
    gamma: float = 1.0

    def validate(self) -> dict[str, Any]:
        errors = []
        if self.contrast < 0:
            errors.append("contrast must be greater than zero")
        if self.saturation < 0:
            errors.append("saturation must not be negative")
        if self.gamma <= 0:
            errors.append("gamma must be greater than zero")
        if self.temperature <= 0:
            errors.append("temperature must be greater than zero")
        return {"passed": not errors, "errors": errors}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColorGrade":
        return cls(**data)


class ColorFinishingEngine:
    """Deterministic finishing validation and grade application plan."""

    def __init__(self, grade: ColorGrade):
        if not isinstance(grade, ColorGrade):
            raise TypeError("grade must be a ColorGrade")
        self.grade = grade

    def validate(self) -> dict[str, Any]:
        checks = {
            "grade_present": self.grade is not None,
            "grade_id_present": bool(getattr(self.grade, "id", "")),
        }

        try:
            grade_result = self.grade.validate()
            checks["grade_valid"] = bool(
                grade_result.get("passed", False)
            )
        except Exception:
            checks["grade_valid"] = False

        return {
            "passed": all(checks.values()),
            "checks": checks,
        }

    def build_finishing_plan(
        self,
        timeline_id: str,
        resolution: str = "1920x1080",
        pixel_format: str = "yuv420p",
    ) -> dict[str, Any]:
        if not timeline_id:
            raise ValueError("timeline_id is required")

        validation = self.validate()

        return {
            "timeline_id": timeline_id,
            "grade": asdict(self.grade),
            "resolution": resolution,
            "pixel_format": pixel_format,
            "validation": validation,
        }


@dataclass
class ColorPlan:
    project_id: str = ""
    timeline_id: str = ""
    grades: list[ColorGrade] = field(default_factory=list)
    output_profile: str = "rec709"
    validation: dict[str, Any] = field(default_factory=dict)

    def add_grade(self, grade: ColorGrade) -> None:
        self.grades.append(grade)

    def validate(self) -> dict[str, Any]:
        checks = {
            "project_present": bool(self.project_id),
            "profile_present": bool(self.output_profile),
            "grades_valid": all(
                grade.validate()["passed"] for grade in self.grades
            ),
            "grade_shots_unique": len(
                [grade.shot_id for grade in self.grades]
            ) == len(
                {grade.shot_id for grade in self.grades}
            ),
            "grade_shots_present": all(
                bool(grade.shot_id) for grade in self.grades
            ),
        }
        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColorPlan":
        data = dict(data)
        data["grades"] = [
            ColorGrade(**grade)
            for grade in data.get("grades", [])
        ]
        return cls(**data)


def process_color(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("COLOR requires output path")

    source = data.get("input") or data.get("master") or data.get("video")
    if source is None:
        raise ValueError("COLOR requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "COLOR",
        "artifact": str(output_path),
    }
