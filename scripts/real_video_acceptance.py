"""Generate and verify one explicitly selected episode through the canonical Chat path."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import traceback
from pathlib import Path


def _extract_representative_frames(video: Path, output_dir: Path, count: int = 5) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)], text=True).strip()
    duration = float(probe)
    evidence = []
    for index in range(count):
        timestamp = duration * ((index + 0.5) / count)
        frame = output_dir / f"final-frame-{index + 1:02d}.png"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1", str(frame)], check=True)
        evidence.append({"frame": str(frame), "timestamp_seconds": round(timestamp, 3), "sha256": hashlib.sha256(frame.read_bytes()).hexdigest()})
    if len({item["sha256"] for item in evidence}) < 2:
        raise RuntimeError("Representative final-video frames are unexpectedly identical")
    return evidence


def _wait_for_job(factory, job_id: str, timeout_seconds: int = 1800):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        job = factory.jobs.get(job_id)
        if job is None:
            raise RuntimeError(f"Chat-created job disappeared: {job_id}")
        if job.status in {"COMPLETED", "FAILED"}:
            return job
        time.sleep(1.0)
    raise TimeoutError(f"Timed out waiting for Chat-created job {job_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--output", default="runs/acceptance/final.mp4")
    args = parser.parse_args()

    episode_id = args.episode.strip()
    script = Path(args.script).resolve()
    final = Path(args.output).resolve()
    root = final.parent
    root.mkdir(parents=True, exist_ok=True)
    error_file = root / "error.txt"

    try:
        from aurelia.chat_entry import handle_chat_production
        from aurelia.factory_runner import FactoryRunner
        from aurelia.media import validate_master

        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise RuntimeError("FFmpeg/ffprobe are required for real acceptance")
        if not episode_id.isdigit() or len(episode_id) != 4:
            raise RuntimeError("Episode id must be an explicit four-digit value")
        if not script.is_file() or script.stat().st_size == 0:
            raise RuntimeError(f"Missing selected episode script: {script}")
        expected_name = f"episode-{episode_id}.txt"
        if script.name != expected_name:
            raise RuntimeError(f"Episode/script mismatch: --episode {episode_id} requires {expected_name}, got {script.name}")

        source_text = script.read_text(encoding="utf-8").strip()
        source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        factory = FactoryRunner(root / "factory")

        # Exercise the exact HTTP-equivalent Chat entry, not the legacy CLI
        # production path. The script remains acceptance input only; it is
        # copied into a unique .chat_inputs file by handle_chat_production.
        message = f"Create Episode {episode_id}\n{source_text}"
        accepted = handle_chat_production(factory, message)
        if not accepted.get("job_id") or accepted.get("script_source") != "chat":
            raise RuntimeError(f"Chat did not create a production job: {accepted}")

        job = _wait_for_job(factory, accepted["job_id"])
        if job.status != "COMPLETED":
            raise RuntimeError(f"Chat production did not complete Episode {episode_id}: {job.status} — {job.error}")

        produced = Path(job.final_mp4).resolve()
        if not produced.is_file() or produced.stat().st_size < 100_000:
            raise RuntimeError(f"Chat Factory did not produce a valid FINAL MP4: {produced}")

        canonical_evidence = "\n".join(job.logs)
        if "[FACTORY] SCRIPT" not in canonical_evidence or "[FACTORY] DELIVERY" not in canonical_evidence:
            raise RuntimeError("Acceptance could not prove the canonical production stages executed")
        if "produce_episode" in canonical_evidence or "TEST SERIALIZATION TRACE" in canonical_evidence:
            raise RuntimeError("Legacy/test production content appeared in canonical execution logs")

        shutil.copy2(produced, final)
        qc_result = validate_master(final, min_duration=30.0)
        if not qc_result["passed"]:
            raise RuntimeError(f"QC rejected Episode {episode_id}: {qc_result}")

        metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration,size,format_name", "-of", "json", str(final)], text=True))["format"]
        duration = float(metadata["duration"])
        size = int(metadata["size"])
        sha = hashlib.sha256(final.read_bytes()).hexdigest()
        production_root = produced.parents[1]
        manifest_path = production_root / "production_manifest.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"Canonical Factory manifest missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("episode_id") != episode_id:
            raise RuntimeError("Factory manifest episode id does not match acceptance target")
        if manifest.get("source") != "chat" or manifest.get("source_text_sha256") != source_sha256:
            raise RuntimeError("Factory manifest is not bound to the current Chat request")
        if manifest.get("job_id") != job.job_id:
            raise RuntimeError("Factory manifest job binding is incorrect")
        if manifest.get("title") not in source_text:
            raise RuntimeError("Factory manifest title is not derived from the current Chat request")

        frame_evidence = _extract_representative_frames(final, root / "final_frames")
        qc = {
            "accepted": True,
            "episode_id": episode_id,
            "job_id": job.job_id,
            "script": str(script),
            "source_text_sha256": source_sha256,
            "artifact": str(final),
            "sha256": sha,
            "duration_seconds": duration,
            "size_bytes": size,
            "format": metadata.get("format_name"),
            "scenes": job.metadata.get("result", {}).get("scenes"),
            "execution": "Chat -> FactoryRunner -> production stages -> visuals -> cinematic FFmpeg motion -> offline TTS -> music -> subtitles -> color grade -> master -> QC -> Delivery",
            "factory_output": str(produced),
            "canonical_path_verified": True,
            "legacy_produce_episode_used": False,
            "qc_checks": qc_result["checks"],
            "representative_frames": frame_evidence,
            "download_url": f"/api/jobs/{job.job_id}/video",
        }
        (root / "qc.json").write_text(json.dumps(qc, indent=2, ensure_ascii=False), encoding="utf-8")
        visuals = production_root / "visuals"
        acceptance_visuals = root / "visuals"
        if visuals.exists():
            shutil.copytree(visuals, acceptance_visuals, dirs_exist_ok=True)
        print(json.dumps(qc, indent=2))
    except Exception:
        error_file.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
