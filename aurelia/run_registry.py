"""AURELIA Maker — persistent production run registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import json
import time
import uuid


@dataclass
class ProductionRun:
    run_id: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )
    project: str = ""
    status: str = "CREATED"
    stages: list[str] = field(default_factory=list)
    completed_stages: list[str] = field(default_factory=list)
    failed_stages: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(
        default_factory=time.time
    )
    updated_at: float = field(
        default_factory=time.time
    )

    def mark_stage_completed(self, stage: str) -> None:
        if stage not in self.stages:
            self.stages.append(stage)

        if stage not in self.completed_stages:
            self.completed_stages.append(stage)

        if stage in self.failed_stages:
            self.failed_stages.remove(stage)

        self.status = "RUNNING"
        self.updated_at = time.time()

    def mark_stage_failed(self, stage: str) -> None:
        if stage not in self.stages:
            self.stages.append(stage)

        if stage not in self.failed_stages:
            self.failed_stages.append(stage)

        self.status = "FAILED"
        self.updated_at = time.time()

    def complete(self) -> None:
        if self.failed_stages:
            raise RuntimeError(
                "Cannot complete a run with failed stages"
            )

        self.status = "COMPLETED"
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunRegistry:
    """Durable registry for factory production runs."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

        self.path = self.root / "production-runs.json"

        if not self.path.exists():
            self._write({})

    def _read(self) -> dict[str, Any]:
        return json.loads(
            self.path.read_text(encoding="utf-8")
        )

    def _write(self, data: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(".tmp")

        temporary.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        temporary.replace(self.path)

    def create(
        self,
        project: str,
        stages: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> ProductionRun:
        run = ProductionRun(
            project=project,
            stages=list(stages),
            metadata=metadata or {},
        )

        data = self._read()
        data[run.run_id] = run.to_dict()
        self._write(data)

        return run

    def save(self, run: ProductionRun) -> None:
        run.updated_at = time.time()

        data = self._read()
        data[run.run_id] = run.to_dict()
        self._write(data)

    def get(self, run_id: str) -> ProductionRun | None:
        data = self._read()
        raw = data.get(run_id)

        if raw is None:
            return None

        return ProductionRun(**raw)


__all__ = [
    "ProductionRun",
    "RunRegistry",
]
