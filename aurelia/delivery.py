"""AURELIA Maker — final delivery packaging and release domain."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json
import uuid

from .ffmpeg_util import run_ffprobe


@dataclass
class DeliveryPackage:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    master_id: str = ""
    qc_report_id: str = ""
    output_path: str = ""
    format: str = "mp4"
    resolution: str = "1920x1080"
    status: str = "PENDING"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> dict[str, Any]:
        output = Path(self.output_path) if self.output_path else None
        artifact_checks = validate_video_artifact(output) if output else {"passed": False, "checks": {}}
        checks = {
            "project_present": bool(self.project_id),
            "master_present": bool(self.master_id),
            "qc_report_present": bool(self.qc_report_id),
            "output_present": bool(self.output_path),
            "format_valid": self.format.lower() == "mp4",
            "resolution_valid": "x" in self.resolution.lower(),
            "status_valid": self.status in {"PENDING", "READY", "DELIVERED", "FAILED"},
            "artifact_valid": artifact_checks["passed"],
        }
        return {"passed": all(checks.values()), "checks": checks, "artifact": artifact_checks}

    def mark_ready(self) -> None:
        result = self.validate()
        if not result["passed"]:
            raise ValueError(f"Delivery package failed validation: {result}")
        self.status = "READY"

    def mark_delivered(self) -> None:
        if self.status != "READY":
            raise ValueError("Delivery package must be READY before delivery")
        self.status = "DELIVERED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeliveryPackage":
        return cls(**data)


def validate_video_artifact(path: Path | None, min_duration: float = 1.0) -> dict[str, Any]:
    checks = {
        "exists": bool(path and path.is_file()),
        "non_empty": bool(path and path.is_file() and path.stat().st_size > 1000),
        "mp4_extension": bool(path and path.suffix.lower() == ".mp4"),
        "ffprobe_readable": False,
        "has_video": False,
        "duration_valid": False,
        "has_audio": False,
    }
    if not checks["exists"] or not checks["non_empty"] or not checks["mp4_extension"]:
        return {"passed": False, "checks": checks, "sha256": ""}

    probe = run_ffprobe([
        "-v", "error", "-show_entries", "format=format_name,duration",
        "-show_entries", "stream=codec_type,codec_name,width,height",
        "-of", "json", str(path),
    ])
    if probe.returncode != 0:
        return {"passed": False, "checks": checks, "sha256": ""}
    try:
        payload = json.loads(probe.stdout)
        streams = payload.get("streams", [])
        fmt = payload.get("format", {})
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(fmt.get("duration") or 0)
        checks["ffprobe_readable"] = True
        checks["has_video"] = bool(video and video.get("codec_name") in {"h264", "hevc", "mpeg4"} and int(video.get("width", 0)) > 0 and int(video.get("height", 0)) > 0)
        checks["duration_valid"] = duration >= min_duration
        checks["has_audio"] = audio is not None
    except (ValueError, TypeError, json.JSONDecodeError):
        pass

    digest = hashlib.sha256(path.read_bytes()).hexdigest() if checks["ffprobe_readable"] else ""
    return {"passed": all(checks.values()), "checks": checks, "sha256": digest}


def process_delivery(data: dict) -> dict:
    source = data.get("input") or data.get("master") or data.get("video")
    output = data.get("output")
    if source is None:
        raise ValueError("DELIVERY requires a final artifact")
    if output is None:
        raise ValueError("DELIVERY requires output path")

    source_path = Path(source).resolve()
    output_path = Path(output).resolve()
    if source_path == output_path:
        raise ValueError("DELIVERY source and output must be different artifacts")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    source_validation = validate_video_artifact(source_path, min_duration=float(data.get("min_duration", 1.0)))
    if not source_validation["passed"]:
        raise ValueError(f"DELIVERY rejected invalid final artifact: {source_validation}")

    expected_sha256 = data.get("expected_sha256")
    if expected_sha256 and source_validation["sha256"] != expected_sha256:
        raise ValueError("DELIVERY rejected artifact with unexpected content hash")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(source_path.read_bytes())
    output_validation = validate_video_artifact(output_path, min_duration=float(data.get("min_duration", 1.0)))
    if not output_validation["passed"] or output_validation["sha256"] != source_validation["sha256"]:
        raise ValueError("DELIVERY output validation failed")

    return {
        "stage": "DELIVERY",
        "artifact": str(output_path),
        "source": str(source_path),
        "sha256": output_validation["sha256"],
        "validation": output_validation,
    }
