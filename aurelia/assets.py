from __future__ import annotations
from pathlib import Path

"""AURELIA Maker — production asset management domain."""


from dataclasses import asdict, dataclass, field
from typing import Any
import hashlib
import json
import uuid


@dataclass
class Asset:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_type: str = ""
    source_ref: str = ""
    content_hash: str = ""
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        payload = {
            "asset_type": self.asset_type,
            "source_ref": self.source_ref,
            "metadata": self.metadata,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        self.content_hash = hashlib.sha256(encoded).hexdigest()
        return self.content_hash

    def validate(self) -> dict[str, Any]:
        checks = {
            "type_present": bool(self.asset_type),
            "source_present": bool(self.source_ref),
            "version_valid": self.version > 0,
            "hash_present": bool(self.content_hash),
        }
        return {"passed": all(checks.values()), "checks": checks}


@dataclass
class AssetManifest:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    visual_plan_id: str = ""
    assets: list[Asset] = field(default_factory=list)
    version: int = 1
    validation: dict[str, Any] = field(default_factory=dict)

    def add_asset(self, asset: Asset) -> None:
        if not asset.content_hash:
            asset.compute_hash()
        self.assets.append(asset)

    def validate(self) -> dict[str, Any]:
        checks = {
            "visual_plan_present": bool(self.visual_plan_id),
            "version_valid": self.version > 0,
            "assets_valid": all(
                asset.validate()["passed"] for asset in self.assets
            ),
            "asset_ids_unique": len(
                {asset.id for asset in self.assets}
            ) == len(self.assets),
            "content_hashes_unique": len(
                {asset.content_hash for asset in self.assets}
            ) == len(self.assets),
        }

        self.validation = {
            "passed": all(checks.values()),
            "checks": checks,
        }
        return self.validation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2,
            ensure_ascii=False,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetManifest":
        data = dict(data)
        data["assets"] = [
            Asset(**asset)
            for asset in data.get("assets", [])
        ]
        return cls(**data)


def process_asset(data: dict) -> dict:
    output = data.get("output")
    if output is None:
        raise ValueError("ASSET requires output path")

    source = data.get("asset")
    if source is None:
        raise ValueError("ASSET requires asset input")

    source_path = Path(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_path.exists():
        raise FileNotFoundError(source_path)

    output_path.write_bytes(source_path.read_bytes())

    return {
        "stage": "ASSET",
        "artifact": str(output_path),
    }
