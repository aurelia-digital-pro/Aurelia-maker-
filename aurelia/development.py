"""AURELIA Maker — development domain for series and film production."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class DevelopmentProject:
    id: str
    title: str
    format: str
    premise: str
    logline: str = ""
    genre: str = ""
    language: str = ""
    status: str = "DEVELOPMENT"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DevelopmentVersion:
    id: str
    project_id: str
    version: int
    content: dict[str, Any]
    parent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DevelopmentRepository:
    projects: dict[str, DevelopmentProject] = field(default_factory=dict)
    versions: dict[str, DevelopmentVersion] = field(default_factory=dict)

    def create_project(
        self,
        title: str,
        format: str,
        premise: str,
        logline: str = "",
        genre: str = "",
        language: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> DevelopmentProject:
        if not title.strip():
            raise ValueError("Project title is required")
        if not format.strip():
            raise ValueError("Project format is required")
        if not premise.strip():
            raise ValueError("Project premise is required")

        project = DevelopmentProject(
            id=str(uuid.uuid4()),
            title=title.strip(),
            format=format.strip().upper(),
            premise=premise.strip(),
            logline=logline.strip(),
            genre=genre.strip(),
            language=language.strip(),
            metadata={} if metadata is None else dict(metadata),
        )
        self.projects[project.id] = project
        return project

    def create_version(
        self,
        project_id: str,
        content: dict[str, Any],
        parent_id: str | None = None,
    ) -> DevelopmentVersion:
        if project_id not in self.projects:
            raise KeyError(f"Unknown development project: {project_id}")
        if not isinstance(content, dict) or not content:
            raise ValueError("Development content must be a non-empty dict")

        existing = [
            v.version
            for v in self.versions.values()
            if v.project_id == project_id
        ]
        version_number = max(existing, default=0) + 1

        if parent_id is not None:
            parent = self.versions.get(parent_id)
            if parent is None:
                raise KeyError(f"Unknown parent version: {parent_id}")
            if parent.project_id != project_id:
                raise ValueError("Parent version belongs to another project")

        version = DevelopmentVersion(
            id=str(uuid.uuid4()),
            project_id=project_id,
            version=version_number,
            content=dict(content),
            parent_id=parent_id,
        )
        self.versions[version.id] = version
        return version

    def latest_version(self, project_id: str) -> DevelopmentVersion | None:
        versions = [
            v for v in self.versions.values()
            if v.project_id == project_id
        ]
        return max(versions, key=lambda v: v.version, default=None)

    def validate(self) -> None:
        for project in self.projects.values():
            if not project.title or not project.format or not project.premise:
                raise ValueError(
                    f"Invalid development project: {project.id}"
                )

        for version in self.versions.values():
            if version.project_id not in self.projects:
                raise ValueError(
                    f"Version references unknown project: {version.id}"
                )
            if version.parent_id is not None:
                parent = self.versions.get(version.parent_id)
                if parent is None:
                    raise ValueError(
                        f"Version references unknown parent: {version.id}"
                    )
                if parent.project_id != version.project_id:
                    raise ValueError(
                        f"Version parent crosses project boundary: {version.id}"
                    )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "projects": {
                key: value.to_dict()
                for key, value in self.projects.items()
            },
            "versions": {
                key: value.to_dict()
                for key, value in self.versions.items()
            },
        }

    def save(self, path: str) -> None:
        from pathlib import Path

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str) -> "DevelopmentRepository":
        from pathlib import Path

        data = json.loads(
            Path(path).read_text(encoding="utf-8")
        )

        repository = cls()

        for key, value in data.get("projects", {}).items():
            repository.projects[key] = DevelopmentProject(**value)

        for key, value in data.get("versions", {}).items():
            repository.versions[key] = DevelopmentVersion(**value)

        repository.validate()
        return repository


def validate_development_repository(
    repository: DevelopmentRepository,
) -> None:
    repository.validate()
