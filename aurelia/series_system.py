"""AURELIA Maker — series, continuity, and delivery domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class ContinuityRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    entity_id: str = ""
    entity_type: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def validate(self) -> dict[str, Any]:
        checks = {
            "entity_present": bool(self.entity_id),
            "type_present": bool(self.entity_type),
            "version_valid": self.version > 0,
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class EpisodeRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    season_id: str = ""
    number: int = 0
    title: str = ""
    continuity_ids: list[str] = field(default_factory=list)

    def validate(self) -> dict[str, Any]:
        checks = {
            "season_present": bool(self.season_id),
            "number_valid": self.number > 0,
            "title_present": bool(self.title),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class SeasonRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    series_id: str = ""
    number: int = 0
    title: str = ""
    episodes: list[EpisodeRecord] = field(default_factory=list)

    def validate(self) -> dict[str, Any]:
        checks = {
            "series_present": bool(self.series_id),
            "number_valid": self.number > 0,
            "episodes_unique": len(
                [episode.number for episode in self.episodes]
            ) == len({episode.number for episode in self.episodes}),
            "episodes_valid": all(
                episode.validate()["passed"] for episode in self.episodes
            ),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class SeriesRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    seasons: list[SeasonRecord] = field(default_factory=list)
    continuity: list[ContinuityRecord] = field(default_factory=list)
    version: int = 1

    def add_season(self, season: SeasonRecord) -> None:
        self.seasons.append(season)

    def add_continuity(self, record: ContinuityRecord) -> None:
        self.continuity.append(record)

    def validate(self) -> dict[str, Any]:
        season_numbers = [season.number for season in self.seasons]
        checks = {
            "title_present": bool(self.title),
            "version_valid": self.version > 0,
            "seasons_unique": len(season_numbers) == len(set(season_numbers)),
            "seasons_valid": all(
                season.validate()["passed"] for season in self.seasons
            ),
            "continuity_valid": all(
                record.validate()["passed"] for record in self.continuity
            ),
        }
        return {"passed": all(checks.values()), "checks": checks}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SeriesRecord":
        data = dict(data)
        data["seasons"] = [
            SeasonRecord(
                **{
                    **season,
                    "episodes": [
                        EpisodeRecord(**episode)
                        for episode in season.get("episodes", [])
                    ],
                }
            )
            for season in data.get("seasons", [])
        ]
        data["continuity"] = [
            ContinuityRecord(**record)
            for record in data.get("continuity", [])
        ]
        return cls(**data)
