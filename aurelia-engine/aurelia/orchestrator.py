"""AURELIA Maker — canonical production orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .execution import ProductionExecutor, StageExecution
from .production_run import ProductionRunRegistry


Processor = Callable[[dict[str, Any]], dict[str, Any]]
Validator = Callable[[dict[str, Any]], bool]


class ProductionOrchestrator:
    """Canonical controller for complete production-stage execution."""

    def __init__(
        self,
        root: str | Path,
        max_retries: int = 2,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

        self.executor = ProductionExecutor(
            root=self.root,
            max_retries=max_retries,
        )
        self.runs = ProductionRunRegistry(self.root)

    def validate_stage(self, stage: str) -> None:
        from .production_contract import PRODUCTION_STAGES

        if stage not in PRODUCTION_STAGES:
            raise ValueError(
                f"Unknown production stage: {stage}"
            )

    def create_run(
        self,
        project: str,
        metadata: dict[str, Any] | None = None,
    ):
        from .production_contract import PRODUCTION_STAGES

        return self.runs.create(
            project=project,
            stages=PRODUCTION_STAGES,
            metadata=metadata,
        )

    def run_production_stage(
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
    ) -> StageExecution:
        self.validate_stage(stage)

        execution = self.executor.execute_stage(
            project=project,
            stage=stage,
            unit_type=unit_type,
            unit_id=unit_id,
            input_data=input_data,
            processor=processor,
            validator=validator,
            artifact_paths=artifact_paths,
            force=force,
        )

        if run_id is not None:
            run = self.runs.get(run_id)
            if run is None:
                raise ValueError(
                    f"Unknown production run: {run_id}"
                )

            if execution.status == "COMPLETED":
                run.mark_stage_completed(stage)
            else:
                run.mark_stage_failed(stage)

            self.runs.save(run)

        return execution

    def complete_run(self, run_id: str):
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError(
                f"Unknown production run: {run_id}"
            )

        run.mark_completed()
        return self.runs.save(run)

    def fail_run(self, run_id: str):
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError(
                f"Unknown production run: {run_id}"
            )

        run.mark_failed()
        return self.runs.save(run)


def build_production_orchestrator(
    root: str | Path,
    max_retries: int = 2,
) -> ProductionOrchestrator:
    return ProductionOrchestrator(
        root=root,
        max_retries=max_retries,
    )


__all__ = [
    "ProductionOrchestrator",
    "build_production_orchestrator",
]
