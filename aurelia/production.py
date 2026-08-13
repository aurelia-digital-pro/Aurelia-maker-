from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
"""AURELIA Maker — unified production factory facade."""


from .factory import ProductionFactory as _ProductionFactory


class ProductionFactory(_ProductionFactory):
    """Unified public production factory."""
    pass

        
@dataclass
class ProductionManifest:
    episode_id: str = ""
    title: str = ""
    schema_version: str = "1.0"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def validate(self) -> dict[str, Any]:
        checks = {
            "episode_present": bool(self.episode_id),
            "title_present": bool(self.title),
            "schema_present": bool(self.schema_version),
        }
        return {"passed": all(checks.values()), "checks": checks}
