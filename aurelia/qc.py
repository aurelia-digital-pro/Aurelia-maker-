"""AURELIA Maker — production quality-control domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class QCCheck:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    passed: bool = False
    severity: str = "ERROR"
    message: str = ""


@dataclass
class QCReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    master_id: str = ""
    checks: list[QCCheck] = field(default_factory=list)
    passed: bool = False
    version: int = 1

    def add_check(self, check: QCCheck) -> None:
        self.checks.append(check)

    def validate(self) -> dict[str, Any]:
        self.passed = bool(self.master_id) and all(
            check.passed
            for check in self.checks
            if check.severity == "ERROR"
        )

        return {
            "passed": self.passed,
            "master_present": bool(self.master_id),
            "checks_total": len(self.checks),
            "checks_passed": sum(
                1 for check in self.checks if check.passed
            ),
            "checks_failed": sum(
                1 for check in self.checks if not check.passed
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QCReport":
        data = dict(data)
        data["checks"] = [
            QCCheck(**item)
            for item in data.get("checks", [])
        ]
        return cls(**data)


def process_qc(data: dict) -> dict:
    source = data.get("input") or data.get("master") or data.get("video")
    if source is None:
        raise ValueError("QC requires a master artifact")

    source_path = Path(source)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    if source_path.stat().st_size == 0:
        raise ValueError("QC rejected empty master artifact")

    return {
        "stage": "QC",
        "artifact": str(source_path),
        "status": "PASSED",
    }
