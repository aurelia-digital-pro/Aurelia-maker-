"""AURELIA Maker — final delivery packaging and release domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class DeliveryPackage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    master_id: str = ""
    qc_report_id: str = ""
    output_path: str = ""
    format: str = "mp4"
    resolution: str = "1920x1080"
    status: str = "PENDING"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        checks = {
            "project_present": bool(self.project_id),
            "master_present": bool(self.master_id),
            "qc_report_present": bool(self.qc_report_id),
            "output_present": bool(self.output_path),
            "format_valid": self.format.lower() in {"mp4", "mov", "mkv"},
            "resolution_valid": "x" in self.resolution.lower(),
            "status_valid": self.status in {"PENDING", "READY", "DELIVERED", "FAILED"},
        }

        return {
            "passed": all(checks.values()),
            "checks": checks,
        }

    def mark_ready(self) -> None:
        result = self.validate()
        if not result["passed"]:
            raise ValueError("Delivery package failed validation")
        self.status = "READY"

    def mark_delivered(self) -> None:
        if self.status != "READY":
            raise ValueError("Delivery package must be READY before delivery")
        self.status = "DELIVERED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeliveryPackage":
        return cls(**data)


def process_delivery(data: dict) -> dict:
    source = data.get("input") or data.get("master") or data.get("video")
    output = data.get("output")

    if source is None:
        raise ValueError("DELIVERY requires a final artifact")
    if output is None:
        raise ValueError("DELIVERY requires output path")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    if source_path.stat().st_size == 0:
        raise ValueError("DELIVERY rejected empty artifact")

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "DELIVERY",
        "artifact": str(output_path),
    }
