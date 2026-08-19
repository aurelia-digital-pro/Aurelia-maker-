"""AURELIA Maker — subtitle and localization engine."""

from __future__ import annotations
from pathlib import Path

from dataclasses import asdict, dataclass, field
from typing import Any
import json
import uuid


@dataclass
class SubtitleCue:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    start: float = 0.0
    end: float = 0.0
    text: str = ""
    language: str = "en"
    speaker: str = ""

    def validate(self) -> dict[str, Any]:
        checks = {
            "start_valid": self.start >= 0,
            "end_valid": self.end > self.start,
            "text_present": bool(self.text.strip()),
            "language_valid": self.language in {"ar", "en"},
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class SubtitleTrack:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    language: str = "en"
    rtl: bool = False
    cues: list[SubtitleCue] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_cue(self, cue: SubtitleCue) -> None:
        self.cues.append(cue)

    def validate(self) -> dict[str, Any]:
        language_valid = self.language in {"ar", "en"}
        rtl_valid = self.rtl == (self.language == "ar")
        cues_valid = all(cue.validate()["passed"] for cue in self.cues)

        ordered = all(
            self.cues[index].start >= self.cues[index - 1].end
            for index in range(1, len(self.cues))
        )

        checks = {
            "language_valid": language_valid,
            "rtl_valid": rtl_valid,
            "cues_valid": cues_valid,
            "cues_ordered": ordered,
            "version_valid": self.version > 0,
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SubtitleTrack":
        data = dict(data)
        data["cues"] = [
            SubtitleCue(**cue)
            for cue in data.get("cues", [])
        ]
        return cls(**data)


class SubtitleLocalizationEngine:
    """Deterministic subtitle timing and localization validation."""

    SUPPORTED_LANGUAGES = {"ar", "en"}

    def create_track(
        self,
        language: str,
        cues: list[SubtitleCue] | None = None,
    ) -> SubtitleTrack:
        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported subtitle language: {language}")

        track = SubtitleTrack(
            language=language,
            rtl=language == "ar",
            cues=list(cues or []),
        )
        track.validate()
        return track

    def validate_track(self, track: SubtitleTrack) -> dict[str, Any]:
        return track.validate()

    def build_localization_plan(
        self,
        subtitle_id: str,
        languages: list[str],
    ) -> dict[str, Any]:
        languages = list(dict.fromkeys(languages))

        checks = {
            "subtitle_id_present": bool(subtitle_id),
            "languages_present": bool(languages),
            "languages_supported": all(
                language in self.SUPPORTED_LANGUAGES
                for language in languages
            ),
            "languages_unique": len(languages) == len(set(languages)),
        }

        return {
            "subtitle_id": subtitle_id,
            "languages": languages,
            "rtl_languages": [
                language for language in languages
                if language == "ar"
            ],
            "validation": {
                "passed": all(checks.values()),
                "checks": checks,
            },
        }


def process_subtitle(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("SUBTITLE requires output path")

    source = data.get("input") or data.get("video") or data.get("master")
    subtitles = data.get("subtitles")

    if source is None:
        raise ValueError("SUBTITLE requires an input artifact")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "SUBTITLE",
        "artifact": str(output_path),
        "subtitles": subtitles,
    }
