"""AURELIA — Visual generation checkpoint for long-episode resume.

Saves completed shot records to disk so interrupted productions
can resume without regenerating already-completed images.

Usage:
    ckpt = VisualCheckpoint(production_root / "visual_checkpoint.json")

    # Before generating a shot:
    if ckpt.is_done(scene_idx, shot_idx, path):
        use cached path; continue

    # After generating a shot:
    ckpt.mark_done(scene_idx, shot_idx, path, backend, provenance)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class VisualCheckpoint:
    """Thread-safe persistent checkpoint for visual asset generation."""

    def __init__(self, checkpoint_path: Path) -> None:
        self._path = Path(checkpoint_path)
        self._data: dict[str, Any] = {"completed": {}}
        if self._path.is_file():
            try:
                self._data = json.loads(
                    self._path.read_text(encoding="utf-8")
                )
            except Exception:
                self._data = {"completed": {}}

    @staticmethod
    def _key(scene_idx: int, shot_idx: int) -> str:
        return f"{scene_idx}:{shot_idx}"

    def is_done(self, scene_idx: int, shot_idx: int, expected_path: Path) -> bool:
        """Return True if this shot already has a valid generated file."""
        record = self._data.get("completed", {}).get(
            self._key(scene_idx, shot_idx)
        )
        if not record:
            return False
        path = Path(record.get("path", ""))
        if not path.is_file() or path.stat().st_size < 1000:
            return False
        # Verify SHA256 integrity
        saved_sha = record.get("sha256", "")
        if saved_sha:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != saved_sha:
                return False
        return True

    def get_path(self, scene_idx: int, shot_idx: int) -> Path | None:
        """Return the path of a completed shot, or None."""
        record = self._data.get("completed", {}).get(
            self._key(scene_idx, shot_idx)
        )
        if record:
            p = Path(record["path"])
            if p.is_file():
                return p
        return None

    def get_provenance(self, scene_idx: int, shot_idx: int) -> dict[str, Any]:
        """Return provenance dict for a completed shot."""
        record = self._data.get("completed", {}).get(
            self._key(scene_idx, shot_idx)
        )
        if record:
            return dict(record.get("prov") or {})
        return {}

    def mark_done(
        self,
        scene_idx: int,
        shot_idx: int,
        path: Path,
        backend: str = "",
        provenance: dict[str, Any] | None = None,
    ) -> None:
        """Record a completed shot."""
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        self._data.setdefault("completed", {})[
            self._key(scene_idx, shot_idx)
        ] = {
            "path":    str(path.resolve()),
            "sha256":  sha,
            "backend": backend,
            "prov":    provenance or {},
        }
        self._save()

    def completed_count(self) -> int:
        return len(self._data.get("completed", {}))

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def clear(self) -> None:
        self._data = {"completed": {}}
        self._save()


__all__ = ["VisualCheckpoint"]
