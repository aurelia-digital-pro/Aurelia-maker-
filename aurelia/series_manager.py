"""AURELIA — Series / Season / Episode / Act continuity manager.

Manages the full narrative hierarchy:
  Series
    Season
      Episode
        Act
          Scene

Continuity state is persisted to JSON on disk so it survives between runs.
This module handles:
  - series/season/episode/act creation and metadata
  - character, location, object identity registers
  - visual language (palette, style) continuity per series
  - voice identity per character
  - timeline and story-state tracking between episodes
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ── domain dataclasses ────────────────────────────────────────────────────────

@dataclass
class CharacterIdentity:
    id: str
    name: str
    description: str = ""
    voice_profile: str = ""     # TTS speaker key
    visual_profile: str = ""    # visual style hint for SD prompt
    first_episode: str = ""
    last_episode: str = ""
    active: bool = True


@dataclass
class LocationIdentity:
    id: str
    name: str
    description: str = ""
    visual_profile: str = ""
    first_episode: str = ""
    time_of_day: str = ""        # day / night / golden_hour
    active: bool = True


@dataclass
class VisualLanguage:
    palette: str = ""            # hex colors or style description
    grade: str = ""              # color grade style
    aspect_ratio: str = "16:9"
    font_style: str = ""
    title_card_style: str = ""


@dataclass
class Act:
    id: str
    number: int
    title: str = ""
    description: str = ""
    scene_ids: list[str] = field(default_factory=list)


@dataclass
class Episode:
    id: str
    number: int
    season_id: str
    title: str = ""
    language: str = "ar"
    script_path: str = ""
    acts: list[Act] = field(default_factory=list)
    status: str = "pending"     # pending / in_progress / completed / failed
    final_mp4: str = ""
    run_id: str = ""
    story_state: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0


@dataclass
class Season:
    id: str
    number: int
    series_id: str
    title: str = ""
    episodes: list[Episode] = field(default_factory=list)


@dataclass
class Series:
    id: str
    title: str
    description: str = ""
    language: str = "ar"
    seasons: list[Season] = field(default_factory=list)
    characters: list[CharacterIdentity] = field(default_factory=list)
    locations: list[LocationIdentity] = field(default_factory=list)
    visual_language: VisualLanguage = field(default_factory=VisualLanguage)
    story_state: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


# ── manager ───────────────────────────────────────────────────────────────────

class SeriesManager:
    """Persist and manage the full Series hierarchy."""

    def __init__(self, storage_dir: Path | str) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._series: dict[str, Series] = {}
        self._load_all()

    # ── persistence ───────────────────────────────────────────────────────

    def _path(self, series_id: str) -> Path:
        return self.storage_dir / f"series_{series_id}.json"

    def _load_all(self) -> None:
        for p in self.storage_dir.glob("series_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                s = self._from_dict(data)
                self._series[s.id] = s
            except Exception:
                pass

    def _save(self, series: Series) -> None:
        self._path(series.id).write_text(
            json.dumps(asdict(series), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── series CRUD ───────────────────────────────────────────────────────

    def create_series(
        self,
        series_id: str,
        title: str,
        language: str = "ar",
        description: str = "",
    ) -> Series:
        s = Series(id=series_id, title=title, language=language, description=description)
        self._series[series_id] = s
        self._save(s)
        return s

    def get_series(self, series_id: str) -> Series | None:
        return self._series.get(series_id)

    def list_series(self) -> list[Series]:
        return list(self._series.values())

    # ── season / episode ──────────────────────────────────────────────────

    def add_season(
        self,
        series_id: str,
        season_number: int,
        title: str = "",
    ) -> Season:
        s = self._series[series_id]
        season_id = f"{series_id}_s{season_number:02d}"
        season = Season(id=season_id, number=season_number, series_id=series_id, title=title)
        s.seasons.append(season)
        self._save(s)
        return season

    def add_episode(
        self,
        series_id: str,
        season_number: int,
        episode_number: int,
        title: str = "",
        language: str = "",
        script_path: str = "",
    ) -> Episode:
        s = self._series[series_id]
        season = next((x for x in s.seasons if x.number == season_number), None)
        if season is None:
            season = self.add_season(series_id, season_number)
        ep_id   = f"{season.id}_ep{episode_number:03d}"
        ep_lang = language or s.language
        ep = Episode(
            id=ep_id,
            number=episode_number,
            season_id=season.id,
            title=title,
            language=ep_lang,
            script_path=script_path,
        )
        season.episodes.append(ep)
        self._save(s)
        return ep

    def update_episode_status(
        self,
        series_id: str,
        episode_id: str,
        status: str,
        final_mp4: str = "",
        run_id: str = "",
        story_state: dict[str, Any] | None = None,
    ) -> None:
        s = self._series.get(series_id)
        if s is None:
            return
        for season in s.seasons:
            for ep in season.episodes:
                if ep.id == episode_id:
                    ep.status = status
                    if final_mp4:
                        ep.final_mp4  = final_mp4
                        ep.completed_at = time.time()
                    if run_id:
                        ep.run_id = run_id
                    if story_state:
                        ep.story_state.update(story_state)
                    self._save(s)
                    return

    # ── identity registers ────────────────────────────────────────────────

    def add_character(
        self,
        series_id: str,
        character_id: str,
        name: str,
        description: str = "",
        voice_profile: str = "",
        visual_profile: str = "",
        first_episode: str = "",
    ) -> CharacterIdentity:
        s = self._series[series_id]
        char = CharacterIdentity(
            id=character_id, name=name, description=description,
            voice_profile=voice_profile, visual_profile=visual_profile,
            first_episode=first_episode,
        )
        s.characters.append(char)
        self._save(s)
        return char

    def add_location(
        self,
        series_id: str,
        location_id: str,
        name: str,
        description: str = "",
        visual_profile: str = "",
        first_episode: str = "",
    ) -> LocationIdentity:
        s = self._series[series_id]
        loc = LocationIdentity(
            id=location_id, name=name, description=description,
            visual_profile=visual_profile, first_episode=first_episode,
        )
        s.locations.append(loc)
        self._save(s)
        return loc

    def set_visual_language(
        self,
        series_id: str,
        palette: str = "",
        grade: str = "",
        aspect_ratio: str = "16:9",
        font_style: str = "",
        title_card_style: str = "",
    ) -> None:
        s = self._series[series_id]
        s.visual_language = VisualLanguage(
            palette=palette, grade=grade, aspect_ratio=aspect_ratio,
            font_style=font_style, title_card_style=title_card_style,
        )
        self._save(s)

    def get_continuity_context(
        self,
        series_id: str,
        current_episode_id: str | None = None,
    ) -> dict[str, Any]:
        """Return a context dict for injection into the directing/visual pipeline."""
        s = self._series.get(series_id)
        if s is None:
            return {}
        return {
            "series_id":      s.id,
            "series_title":   s.title,
            "visual_language": asdict(s.visual_language),
            "characters":     [asdict(c) for c in s.characters if c.active],
            "locations":      [asdict(l) for l in s.locations if l.active],
            "story_state":    dict(s.story_state),
        }

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> Series:
        """Deserialize a Series from dict (handles nested dataclasses)."""
        data = dict(data)

        if "visual_language" in data and isinstance(data["visual_language"], dict):
            data["visual_language"] = VisualLanguage(**data["visual_language"])

        seasons_raw = data.pop("seasons", [])
        seasons: list[Season] = []
        for sr in seasons_raw:
            sr = dict(sr)
            episodes_raw = sr.pop("episodes", [])
            episodes: list[Episode] = []
            for er in episodes_raw:
                er = dict(er)
                acts_raw = er.pop("acts", [])
                acts = [Act(**ar) for ar in acts_raw]
                er["acts"] = acts
                episodes.append(Episode(**er))
            sr["episodes"] = episodes
            seasons.append(Season(**sr))
        data["seasons"] = seasons

        chars_raw = data.pop("characters", [])
        data["characters"] = [CharacterIdentity(**c) for c in chars_raw]

        locs_raw = data.pop("locations", [])
        data["locations"] = [LocationIdentity(**l) for l in locs_raw]

        return Series(**data)


__all__ = [
    "SeriesManager", "Series", "Season", "Episode", "Act",
    "CharacterIdentity", "LocationIdentity", "VisualLanguage",
]
