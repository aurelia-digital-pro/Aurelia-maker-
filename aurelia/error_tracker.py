from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

ERROR_STORE = Path("production_errors.json")


@dataclass
class ProductionError:
    job_id: str | None
    episode_id: str | None
    stage: str
    component: str
    error_type: str
    error_message: str
    root_cause: str | None = None
    first_seen: float = None
    last_seen: float = None
    attempt_count: int = 1
    fix_applied: str | None = None
    files_changed: list[str] | None = None
    status: str = "OPEN"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # ensure JSON-safe types
        if d["first_seen"] is None:
            d["first_seen"] = time.time()
        if d["last_seen"] is None:
            d["last_seen"] = d["first_seen"]
        return d


def _load_all() -> list[dict[str, Any]]:
    if not ERROR_STORE.exists():
        return []
    try:
        return json.loads(ERROR_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_all(items: list[dict[str, Any]]) -> None:
    ERROR_STORE.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def record_error(
    job_id: str | None,
    episode_id: str | None,
    stage: str,
    component: str,
    error_type: str,
    error_message: str,
    root_cause: str | None = None,
    fix_applied: str | None = None,
    files_changed: list[str] | None = None,
    status: str = "OPEN",
) -> None:
    items = _load_all()
    now = time.time()
    entry = ProductionError(
        job_id=job_id,
        episode_id=episode_id,
        stage=stage,
        component=component,
        error_type=error_type,
        error_message=error_message,
        root_cause=root_cause,
        first_seen=now,
        last_seen=now,
        attempt_count=1,
        fix_applied=fix_applied,
        files_changed=files_changed,
        status=status,
    )
    items.append(entry.to_dict())
    _save_all(items)


def mark_fixed(job_id: str | None, episode_id: str | None, stage: str, note: str | None = None) -> None:
    items = _load_all()
    changed = False
    for it in items:
        if it.get("job_id") == job_id and it.get("episode_id") == episode_id and it.get("stage") == stage and it.get("status") != "FIXED":
            it["status"] = "FIXED"
            it["fix_applied"] = note
            it["last_seen"] = time.time()
            changed = True
    if changed:
        _save_all(items)


def list_errors() -> list[dict[str, Any]]:
    return _load_all()
