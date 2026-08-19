"""AURELIA Maker — unified production execution layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .factory import (
    ArtifactRecord,
    ExecutionContext,
    ExecutionRecord,
    FactoryExecutor,
    FactoryStore,
)


Processor = Callable[[dict[str, Any]], dict[str, Any]]
Validator = Callable[[dict[str, Any]], bool]


@dataclass
class StageExecution:
    stage: str
    unit_type: str
    unit_id: str
    status: str
    attempts: int
    output: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    error: str = ""
    execution_id: str = ""

    @classmethod
    def from_record(
        cls,
        record: ExecutionRecord,
    ) -> "StageExecution":
        output = record.metadata.get("output", {})
        if not isinstance(output, dict):
            output = {}

        return cls(
            stage=record.stage,
            unit_type=record.unit_type,
            unit_id=record.unit_id,
            status=record.status,
            attempts=record.attempts,
            output=output,
            artifacts=list(record.artifacts),
            error=record.error,
            execution_id=record.execution_id,
        )

    @property
    def completed(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def failed(self) -> bool:
        return self.status == "FAILED"


class ProductionExecutor:
    """Canonical executor used by the Cinematic Production Factory."""

    def __init__(
        self,
        root: str | Path,
        max_retries: int = 2,
    ) -> None:
        self.store = FactoryStore(Path(root))
        self.executor = FactoryExecutor(
            self.store,
            max_retries=max_retries,
        )

    def execute_stage(
        self,
        *,
        project: str,
        unit_type: str,
        unit_id: str,
        stage: str,
        input_data: dict[str, Any],
        processor: Processor,
        validator: Validator,
        configuration: dict[str, Any] | None = None,
        artifact_paths: list[str | Path] | None = None,
        force: bool = False,
    ) -> StageExecution:
        context = ExecutionContext(
            project=project,
            unit_type=unit_type,
            unit_id=unit_id,
            stage=stage,
            configuration=configuration or {},
        )

        paths = (
            [Path(path) for path in artifact_paths]
            if artifact_paths
            else None
        )

        record = self.executor.execute(
            context=context,
            input_data=input_data,
            processor=processor,
            validator=validator,
            artifact_paths=paths,
            force=force,
        )

        return StageExecution.from_record(record)


__all__ = [
    "Processor",
    "Validator",
    "StageExecution",
    "ProductionExecutor",
]
