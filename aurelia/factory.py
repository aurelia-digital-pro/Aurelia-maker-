"""AURELIA Maker — production-grade deterministic Factory Core."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable
import hashlib
import json
import logging
import os
import shutil
import time


Processor = Callable[[dict[str, Any]], dict[str, Any]]
Validator = Callable[[dict[str, Any]], bool]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def fingerprint(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ExecutionContext:
    project: str
    unit_type: str
    unit_id: str
    stage: str
    configuration: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return fingerprint(
            {
                "project": self.project,
                "unit_type": self.unit_type,
                "unit_id": self.unit_id,
                "stage": self.stage,
                "configuration": self.configuration,
            }
        )


@dataclass
class ArtifactRecord:
    artifact_id: str
    path: str
    kind: str
    stage: str
    sha256: str
    size: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionRecord:
    execution_id: str
    cache_key: str
    stage: str
    unit_type: str
    unit_id: str
    status: str
    attempts: int = 0
    input_fingerprint: str = ""
    output_fingerprint: str = ""
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class FactoryStore:
    """Persistent state, cache and provenance store."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

        self.state_path = self.root / "factory-state.json"
        self.cache_dir = self.root / "cache"
        self.artifact_dir = self.root / "artifacts"
        self.log_dir = self.root / "logs"

        self.cache_dir.mkdir(exist_ok=True)
        self.artifact_dir.mkdir(exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)

        self.logger = logging.getLogger("aurelia.factory")
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_dir / "factory.log")
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(message)s"
                )
            )
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        if not self.state_path.exists():
            self._write_state({"schema_version": "1.0", "executions": {}})

    def _read_state(self) -> dict[str, Any]:
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def _write_state(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                state,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)

    def get(self, cache_key: str) -> ExecutionRecord | None:
        state = self._read_state()
        raw = state["executions"].get(cache_key)
        if raw is None:
            return None

        artifacts = [
            ArtifactRecord(**item)
            for item in raw.get("artifacts", [])
        ]
        raw["artifacts"] = artifacts
        return ExecutionRecord(**raw)

    def put(self, record: ExecutionRecord) -> None:
        state = self._read_state()
        data = asdict(record)
        state["executions"][record.cache_key] = data
        self._write_state(state)

    def clear_failed(self, cache_key: str) -> None:
        state = self._read_state()
        raw = state["executions"].get(cache_key)
        if raw and raw.get("status") == "FAILED":
            del state["executions"][cache_key]
            self._write_state(state)


class FactoryExecutor:
    """Executes real processors with validation, retry, cache and recovery."""

    def __init__(
        self,
        store: FactoryStore,
        max_retries: int = 2,
    ):
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        self.store = store
        self.max_retries = max_retries

    def _validate_processor(
        self,
        processor: Processor | None,
    ) -> None:
        if not callable(processor):
            raise TypeError(
                "A real callable processor is required; "
                "placeholder processors are not permitted"
            )

    def _validate_validator(
        self,
        validator: Validator | None,
    ) -> None:
        if not callable(validator):
            raise TypeError(
                "A real callable validator is required"
            )

    def _record_artifact(
        self,
        path: Path,
        stage: str,
        artifact_id: str,
    ) -> ArtifactRecord:
        if not path.exists():
            raise FileNotFoundError(str(path))

        return ArtifactRecord(
            artifact_id=artifact_id,
            path=str(path),
            kind=path.suffix.lstrip(".") or "file",
            stage=stage,
            sha256=file_hash(path),
            size=path.stat().st_size,
        )

    def execute(
        self,
        context: ExecutionContext,
        input_data: dict[str, Any],
        processor: Processor,
        validator: Validator,
        *,
        artifact_paths: list[Path] | None = None,
        force: bool = False,
    ) -> ExecutionRecord:
        self._validate_processor(processor)
        self._validate_validator(validator)

        if not isinstance(input_data, dict):
            raise TypeError("input_data must be a dict")

        cache_key = fingerprint(
            {
                "context": context.key(),
                "input": input_data,
            }
        )

        cached = self.store.get(cache_key)
        if (
            not force
            and cached is not None
            and cached.status == "COMPLETED"
            and all(Path(a.path).exists() for a in cached.artifacts)
        ):
            self.store.logger.info(
                "CACHE HIT stage=%s unit=%s/%s key=%s",
                context.stage,
                context.unit_type,
                context.unit_id,
                cache_key,
            )
            return cached

        execution = ExecutionRecord(
            execution_id=cache_key[:16],
            cache_key=cache_key,
            stage=context.stage,
            unit_type=context.unit_type,
            unit_id=context.unit_id,
            status="RUNNING",
            input_fingerprint=fingerprint(input_data),
        )

        last_error = ""

        for attempt in range(1, self.max_retries + 2):
            execution.attempts = attempt

            try:
                self.store.logger.info(
                    "EXECUTE stage=%s unit=%s/%s attempt=%s",
                    context.stage,
                    context.unit_type,
                    context.unit_id,
                    attempt,
                )

                output = processor(dict(input_data))

                if not isinstance(output, dict):
                    raise TypeError(
                        "Processor must return a dict"
                    )

                if not validator(output):
                    raise ValueError(
                        "Stage validation failed"
                    )

                records: list[ArtifactRecord] = []

                for index, path in enumerate(artifact_paths or []):
                    records.append(
                        self._record_artifact(
                            Path(path),
                            context.stage,
                            f"{execution.execution_id}-{index + 1}",
                        )
                    )

                execution.status = "COMPLETED"
                execution.output_fingerprint = fingerprint(output)
                execution.artifacts = records
                execution.metadata = {
                    "output": output,
                    "deterministic_key": cache_key,
                }

                self.store.put(execution)

                self.store.logger.info(
                    "COMPLETED stage=%s unit=%s/%s",
                    context.stage,
                    context.unit_type,
                    context.unit_id,
                )

                return execution

            except Exception as exc:
                last_error = str(exc)
                execution.error = last_error
                execution.status = "FAILED"

                self.store.logger.error(
                    "FAILED stage=%s unit=%s/%s attempt=%s error=%s",
                    context.stage,
                    context.unit_type,
                    context.unit_id,
                    attempt,
                    last_error,
                )

                if attempt <= self.max_retries:
                    time.sleep(0.05 * attempt)
                    continue

        self.store.put(execution)
        return execution

    def recover(
        self,
        context: ExecutionContext,
    ) -> ExecutionRecord | None:
        record = self.store.get(
            fingerprint(
                {
                    "context": context.key(),
                    "input": {},
                }
            )
        )
        return record


def deterministic_build_key(
    project: str,
    unit_type: str,
    unit_id: str,
    stage: str,
    input_data: dict[str, Any],
    configuration: dict[str, Any],
) -> str:
    return fingerprint(
        {
            "project": project,
            "unit_type": unit_type,
            "unit_id": unit_id,
            "stage": stage,
            "input": input_data,
            "configuration": configuration,
        }
    )


__all__ = [
    "ArtifactRecord",
    "ExecutionContext",
    "ExecutionRecord",
    "FactoryExecutor",
    "FactoryStore",
    "canonical_json",
    "deterministic_build_key",
    "file_hash",
    "fingerprint",
    "sha256_bytes",
]




class ProductionFactory(FactoryStore):

    def create_manifest(self, episode_id="", title=""):
        from .production import ProductionManifest

        manifest = ProductionManifest()
        if hasattr(manifest, "episode_id"):
            manifest.episode_id = episode_id
        if hasattr(manifest, "title"):
            manifest.title = title

        self.manifest = manifest
        return manifest

    def save(self):
        if hasattr(self, "_save"):
            return self._save()

        if hasattr(self, "state"):
            state = self.state
            if hasattr(state, "save"):
                return state.save()

        root = Path(self.root)
        root.mkdir(parents=True, exist_ok=True)

        state_path = root / "factory-state.json"
        state_path.write_text(
            "{}",
            encoding="utf-8",
        )
        return state_path
    """Unified production factory entry point."""

    def __init__(self, root="."):
        super().__init__(root)


def create_production_orchestrator(
    root: str | Path,
    max_retries: int = 2,
):
    """Create the canonical production orchestrator."""

    from .orchestrator import ProductionOrchestrator

    return ProductionOrchestrator(
        root=root,
        max_retries=max_retries,
    )


__all__ = [
    "ExecutionContext",
    "ArtifactRecord",
    "ExecutionRecord",
    "FactoryStore",
    "FactoryExecutor",
    "deterministic_build_key",
    "create_production_orchestrator",
]


def production_contracts():
    """Return the canonical validated production contracts."""

    from .production_contract import (
        build_production_contracts,
        validate_production_contracts,
    )

    contracts = build_production_contracts()
    result = validate_production_contracts(contracts)

    if not result["valid"]:
        raise RuntimeError(
            "Invalid production contracts: "
            + "; ".join(result["errors"])
        )

    return contracts


__all__.append("production_contracts")


def build_canonical_production_pipeline(
    root: str | Path,
    max_retries: int = 2,
):
    """Build the canonical end-to-end production pipeline."""

    from .production_pipeline import build_production_pipeline

    return build_production_pipeline(
        root=Path(root),
        max_retries=max_retries,
    )


__all__ = [
    "ArtifactRecord",
    "ExecutionContext",
    "ExecutionRecord",
    "FactoryStore",
    "FactoryExecutor",
    "deterministic_build_key",
    "build_canonical_production_pipeline",
]
