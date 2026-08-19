"""AURELIA Maker — canonical production pipeline integration.

There is one production path: FactoryRunner supplies the processors from the
current Chat request and this module only coordinates execution/persistence.
No demo, acceptance, fixture, or default episode content is resolved here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .orchestrator import ProductionOrchestrator
from .production_contract import PRODUCTION_STAGES

Processor = Callable[[dict[str, Any]], dict[str, Any]]
Validator = Callable[[dict[str, Any]], bool]


@dataclass
class ProductionPipeline:
    orchestrator: ProductionOrchestrator
    stages: tuple[str, ...] = PRODUCTION_STAGES
    executions: list[Any] = field(default_factory=list)

    def validate(self) -> None:
        if tuple(self.stages) != PRODUCTION_STAGES:
            raise ValueError("Production pipeline stages do not match canonical order")
        for stage in self.stages:
            self.orchestrator.validate_stage(stage)

    def execute_stage(
        self,
        *,
        project: str,
        stage: str,
        unit_type: str,
        unit_id: str,
        input_data: dict[str, Any],
        processor: Processor,
        validator: Validator,
        run_id: str | None = None,
        artifact_paths: list[Path] | None = None,
        force: bool = False,
    ) -> Any:
        execution = self.orchestrator.run_production_stage(
            project=project,
            stage=stage,
            unit_type=unit_type,
            unit_id=unit_id,
            input_data=input_data,
            processor=processor,
            validator=validator,
            run_id=run_id,
            artifact_paths=artifact_paths,
            force=force,
        )
        self.executions.append(execution)
        return execution

    def execute_production(
        self,
        *,
        project: str,
        input_data: dict[str, Any],
        processors: dict[str, Processor],
        validators: dict[str, Validator],
        run_id: str | None = None,
    ) -> list[Any]:
        current = dict(input_data)
        results: list[Any] = []
        for stage in self.stages:
            processor = processors.get(stage)
            validator = validators.get(stage)
            if processor is None:
                raise ValueError(f"Missing production processor for stage: {stage}")
            if validator is None:
                raise ValueError(f"Missing production validator for stage: {stage}")
            execution = self.execute_stage(
                project=project,
                stage=stage,
                unit_type="production_stage",
                unit_id=f"{project}:{stage}",
                input_data=current,
                processor=processor,
                validator=validator,
                run_id=run_id,
            )
            results.append(execution)
            if execution.status != "COMPLETED":
                raise RuntimeError(f"Production stage failed: {stage}: {execution.error}")
            if not isinstance(execution.output, dict):
                raise TypeError(f"Stage {stage} did not return a dictionary artifact payload")
            current.update(execution.output)
        return results


def build_production_pipeline(root: str | Path, max_retries: int = 2) -> ProductionPipeline:
    pipeline = ProductionPipeline(
        orchestrator=ProductionOrchestrator(root=root, max_retries=max_retries)
    )
    pipeline.validate()
    return pipeline


__all__ = ["ProductionPipeline", "build_production_pipeline"]
