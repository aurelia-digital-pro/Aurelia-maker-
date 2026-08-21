"""AURELIA — structured per-job production trace logger.

Every production run gets a ProductionLogger bound to its job_id.
The logger emits structured records to:
  1. In-memory log list (streamed to WebSocket / UI)
  2. Per-job NDJSON file (persistent, survives restart)

Record schema:
  job_id, episode_id, stage, scene, shot, backend,
  input, output, duration_s, status, retry, fallback,
  fallback_reason, error, ts
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ProductionLogger:
    """Emit structured + human-readable log lines for one production job."""

    def __init__(
        self,
        job_id: str,
        episode_id: str,
        log_dir: Path | None = None,
    ) -> None:
        self.job_id     = job_id
        self.episode_id = episode_id
        self._records: list[dict[str, Any]] = []
        self._lines:   list[str]             = []
        self._lock = threading.Lock()
        self._log_file: Path | None = None
        if log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            self._log_file = log_dir / f"production_{job_id}.ndjson"

    # ── internal ──────────────────────────────────────────────────────────

    def _write(self, record: dict[str, Any], line: str) -> None:
        with self._lock:
            self._records.append(record)
            self._lines.append(line)
            if self._log_file:
                try:
                    with self._log_file.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception:
                    pass

    def _rec(
        self,
        stage: str,
        status: str,
        *,
        scene: int | None = None,
        shot: int | None = None,
        backend: str = "",
        input_ref: str = "",
        output_ref: str = "",
        duration_s: float = 0.0,
        retry: int = 0,
        fallback: bool = False,
        fallback_reason: str = "",
        error: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rec = {
            "job_id":         self.job_id,
            "episode_id":     self.episode_id,
            "stage":          stage,
            "scene":          scene,
            "shot":           shot,
            "backend":        backend,
            "input":          input_ref,
            "output":         output_ref,
            "duration_s":     round(duration_s, 3),
            "status":         status,
            "retry":          retry,
            "fallback":       fallback,
            "fallback_reason": fallback_reason,
            "error":          error,
            "ts":             datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            rec.update(extra)
        return rec

    # ── public emitters ───────────────────────────────────────────────────

    def stage_start(self, stage: str, detail: str = "") -> float:
        """Mark stage start. Returns start timestamp for elapsed tracking."""
        line = f"[{stage}] START {detail}".strip()
        self._write(self._rec(stage, "START", input_ref=detail), line)
        return time.monotonic()

    def stage_ok(self, stage: str, t0: float, detail: str = "", output_ref: str = "") -> None:
        elapsed = time.monotonic() - t0
        line = f"[{stage}] OK {detail} ({elapsed:.1f}s)".strip()
        self._write(
            self._rec(stage, "OK", output_ref=output_ref, duration_s=elapsed, input_ref=detail),
            line,
        )

    def stage_fail(self, stage: str, t0: float, error: str, retry: int = 0) -> None:
        elapsed = time.monotonic() - t0
        line = f"[{stage}][FATAL] FAILED — {error} ({elapsed:.1f}s)"
        self._write(
            self._rec(stage, "FATAL", duration_s=elapsed, error=error, retry=retry),
            line,
        )

    def stage_warn(self, stage: str, message: str) -> None:
        line = f"[{stage}][WARNING] {message}"
        self._write(self._rec(stage, "WARNING", error=message), line)

    def visual(
        self,
        scene: int,
        shot: int,
        backend: str,
        output_ref: str,
        elapsed: float,
        fallback: bool = False,
        fallback_reason: str = "",
    ) -> None:
        status = "FALLBACK" if fallback else "OK"
        flag   = "[FALLBACK]" if fallback else ""
        line   = f"[VISUAL]{flag} Scene {scene+1} Shot {shot}: {backend} → {Path(output_ref).name} ({elapsed:.1f}s)"
        self._write(
            self._rec(
                "VISUAL", status,
                scene=scene, shot=shot,
                backend=backend, output_ref=output_ref, duration_s=elapsed,
                fallback=fallback, fallback_reason=fallback_reason,
            ),
            line,
        )

    def tts(
        self,
        backend: str,
        output_ref: str,
        elapsed: float,
        fallback: bool = False,
        fallback_reason: str = "",
    ) -> None:
        status = "FALLBACK" if fallback else "OK"
        flag   = "[FALLBACK]" if fallback else ""
        line   = f"[TTS]{flag} {backend} → {Path(output_ref).name} ({elapsed:.1f}s)"
        self._write(
            self._rec(
                "TTS", status,
                backend=backend, output_ref=output_ref, duration_s=elapsed,
                fallback=fallback, fallback_reason=fallback_reason,
            ),
            line,
        )

    def qc_result(
        self,
        passed: bool,
        checks: list[dict[str, Any]],
        output_ref: str = "",
    ) -> None:
        fatals   = [c for c in checks if not c["passed"] and c.get("severity") == "FATAL"]
        warnings = [c for c in checks if not c["passed"] and c.get("severity") == "WARNING"]
        status   = "OK" if passed else "FATAL"
        line     = (
            f"[QC] {'PASS' if passed else 'FAIL'} — "
            f"{len(fatals)} fatal, {len(warnings)} warnings"
        )
        self._write(
            self._rec(
                "QC", status,
                output_ref=output_ref,
                error="\n".join(c["message"] for c in fatals) if fatals else "",
                extra={"qc_checks": checks, "warnings": [c["message"] for c in warnings]},
            ),
            line,
        )

    def info(self, message: str) -> None:
        """Freeform log line (status INFO, no stage tracking)."""
        with self._lock:
            self._lines.append(message)
        if self._log_file:
            rec = {"job_id": self.job_id, "status": "INFO", "message": message,
                   "ts": datetime.now(timezone.utc).isoformat()}
            try:
                with self._log_file.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def __call__(self, message: str) -> None:
        """Allow use as a plain LogFn callable."""
        self.info(message)

    # ── accessors ─────────────────────────────────────────────────────────

    @property
    def lines(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    @property
    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def fallback_summary(self) -> list[dict[str, Any]]:
        """Return all records where fallback=True."""
        return [r for r in self.records if r.get("fallback")]

    def fatal_summary(self) -> list[dict[str, Any]]:
        """Return all records where status=FATAL."""
        return [r for r in self.records if r.get("status") == "FATAL"]


__all__ = ["ProductionLogger"]
