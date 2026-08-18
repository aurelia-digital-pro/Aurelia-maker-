"""Generate and verify one explicitly selected episode through the AURELIA Factory."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, traceback
from pathlib import Path


def _extract_representative_frames(video: Path, output_dir: Path, count: int = 5) -> list[dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video)], text=True).strip()
    duration = float(probe); evidence = []
    for index in range(count):
        timestamp = duration * ((index + 0.5) / count); frame = output_dir / f"final-frame-{index + 1:02d}.png"
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1", str(frame)], check=True)
        evidence.append({"frame": str(frame), "timestamp_seconds": round(timestamp, 3), "sha256": hashlib.sha256(frame.read_bytes()).hexdigest()})
    if len({item["sha256"] for item in evidence}) < 2: raise RuntimeError("Representative final-video frames are unexpectedly identical")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--episode", required=True); parser.add_argument("--script", required=True); parser.add_argument("--output", default="runs/acceptance/final.mp4"); args = parser.parse_args()
    episode_id = args.episode.strip(); script = Path(args.script).resolve(); final = Path(args.output).resolve(); root = final.parent; root.mkdir(parents=True, exist_ok=True); error_file = root / "error.txt"
    try:
        from aurelia.factory_runner import FactoryRunner
        from aurelia.media import validate_master
        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None: raise RuntimeError("FFmpeg/ffprobe are required for real acceptance")
        if not episode_id.isdigit() or len(episode_id) != 4: raise RuntimeError("Episode id must be an explicit four-digit value")
        if not script.exists(): raise RuntimeError(f"Missing selected episode script: {script}")
        expected_name = f"episode-{episode_id}.txt"
        if script.name != expected_name: raise RuntimeError(f"Episode/script mismatch: --episode {episode_id} requires {expected_name}, got {script.name}")
        factory = FactoryRunner(root / "factory")
        job = factory.execute(episode_id, profile="youtube", script_path=script)
        if job.status != "COMPLETED": raise RuntimeError(f"Factory did not complete Episode {episode_id}: {job.status} — {job.error}")
        produced = Path(job.final_mp4).resolve()
        if not produced.exists() or produced.stat().st_size < 100_000: raise RuntimeError(f"Factory did not produce a valid FINAL MP4: {produced}")
        canonical_evidence = "\n".join(job.logs)
        if "Starting canonical production" not in canonical_evidence: raise RuntimeError("Acceptance could not prove canonical Factory production path")
        if "produce_episode" in canonical_evidence: raise RuntimeError("Legacy produce_episode path appeared in Factory execution logs")
        shutil.copy2(produced, final)
        qc_result = validate_master(final, min_duration=30.0)
        if not qc_result["passed"]: raise RuntimeError(f"QC rejected Episode {episode_id}: {qc_result}")
        metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration,size,format_name", "-of", "json", str(final)], text=True))["format"]
        duration = float(metadata["duration"]); size = int(metadata["size"]); sha = hashlib.sha256(final.read_bytes()).hexdigest()
        production_root = produced.parents[1]; manifest_path = production_root / "production_manifest.json"
        if not manifest_path.exists(): raise RuntimeError(f"Canonical Factory manifest missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("episode_id") != episode_id: raise RuntimeError("Factory manifest episode id does not match acceptance target")
        frame_evidence = _extract_representative_frames(final, root / "final_frames")
        qc = {"accepted": True, "episode_id": episode_id, "script": str(script), "artifact": str(final), "sha256": sha, "duration_seconds": duration, "size_bytes": size, "format": metadata.get("format_name"), "scenes": job.metadata.get("result", {}).get("scenes"), "execution": "FactoryRunner -> canonical production stages -> local visuals -> cinematic FFmpeg motion -> offline TTS -> music -> subtitles -> color grade -> master encode -> QC -> delivery", "factory_output": str(produced), "canonical_path_verified": True, "legacy_produce_episode_used": False, "qc_checks": qc_result["checks"], "representative_frames": frame_evidence}
        (root / "qc.json").write_text(json.dumps(qc, indent=2, ensure_ascii=False), encoding="utf-8")
        visuals = production_root / "visuals"; acceptance_visuals = root / "visuals"
        if visuals.exists(): shutil.copytree(visuals, acceptance_visuals, dirs_exist_ok=True)
        print(json.dumps(qc, indent=2))
    except Exception:
        error_file.write_text(traceback.format_exc(), encoding="utf-8"); raise

if __name__ == "__main__": main()
