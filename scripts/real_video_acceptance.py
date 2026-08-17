"""Generate and verify Episode 0013 through the canonical AURELIA Factory."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import traceback
from pathlib import Path


SCRIPT = Path("scripts/episode-0013.txt")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="runs/acceptance/final.mp4")
    args = parser.parse_args()

    final = Path(args.output).resolve()
    root = final.parent
    root.mkdir(parents=True, exist_ok=True)
    error_file = root / "error.txt"

    try:
        from aurelia.episode_engine import produce_episode
        from aurelia.media import validate_master

        if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
            raise RuntimeError("FFmpeg/ffprobe are required for real acceptance")
        if not SCRIPT.exists():
            raise RuntimeError(f"Missing Episode 0013 script: {SCRIPT}")

        factory_root = root / "factory"
        result = produce_episode(
            "0013",
            SCRIPT,
            factory_root,
            profile="youtube",
            log=lambda message: print(f"[FACTORY] {message}", flush=True),
        )
        produced = Path(result["final_mp4"]).resolve()
        if not produced.exists() or produced.stat().st_size < 100_000:
            raise RuntimeError(f"Factory did not produce a valid FINAL MP4: {produced}")

        shutil.copy2(produced, final)
        qc_result = validate_master(final, min_duration=30.0)
        if not qc_result["passed"]:
            raise RuntimeError(f"QC rejected Episode 0013: {qc_result}")

        probe = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,format_name",
                "-of", "json", str(final),
            ],
            text=True,
        )
        metadata = json.loads(probe)["format"]
        duration = float(metadata["duration"])
        size = int(metadata["size"])
        sha = hashlib.sha256(final.read_bytes()).hexdigest()

        qc = {
            "accepted": True,
            "episode_id": "0013",
            "artifact": str(final),
            "sha256": sha,
            "duration_seconds": duration,
            "size_bytes": size,
            "format": metadata.get("format_name"),
            "scenes": result.get("scenes"),
            "ai_visual_backend": "stable-diffusion-v1-5/stable-diffusion-v1-5",
            "execution": "canonical_episode_engine -> local CPU Stable Diffusion -> cinematic FFmpeg motion -> offline espeak-ng TTS -> music -> subtitles -> color grade -> master encode -> QC",
            "factory_output": str(produced),
            "qc_checks": qc_result["checks"],
        }
        (root / "qc.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")

        visuals = produced.parent.parent.parent / "visuals"
        acceptance_visuals = root / "visuals"
        if visuals.exists():
            shutil.copytree(visuals, acceptance_visuals, dirs_exist_ok=True)
        print(json.dumps(qc, indent=2))
    except Exception as exc:
        error_file.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
