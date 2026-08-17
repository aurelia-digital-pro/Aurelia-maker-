"""Generate and verify a real AI-backed AURELIA MP4 end-to-end."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from aurelia.ai_visual import generate_scene_image


SCENES = [
    ("Landfall", "A lone AURELIA tower rises above a dark sea as dawn breaks, with mist moving through the architecture."),
    ("Human Horizon", "A solitary observer stands before a vast luminous city while the first sunlight crosses the horizon."),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def narration(path: Path) -> None:
    import pyttsx3

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    if voices:
        engine.setProperty("voice", voices[0].id)
    engine.setProperty("rate", 145)
    engine.setProperty("volume", 1.0)
    text = (
        "AURELIA begins where observation becomes a question. "
        "A city appears at the edge of the human horizon. "
        "The machine does not merely assemble frames. It transforms a written intention into an image, motion, sound, and a finished film."
    )
    engine.save_to_file(text, str(path))
    engine.runAndWait()
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("Narration backend produced no audio artifact")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="runs/acceptance/final.mp4")
    args = parser.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("FFmpeg/ffprobe are required for real acceptance")

    root = Path(args.output).resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    visuals = root / "visuals"
    visuals.mkdir(exist_ok=True)
    audio = root / "narration.wav"
    clips: list[Path] = []

    for i, (title, description) in enumerate(SCENES):
        image = generate_scene_image(i, title, description, visuals / f"scene_{i+1:02d}.png", width=512, height=512)
        if not image.exists() or image.stat().st_size < 10_000:
            raise RuntimeError(f"AI scene generation failed: {image}")
        clip = root / f"clip_{i+1:02d}.mp4"
        run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", str(image), "-t", "4",
            "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,zoompan=z='min(zoom+0.0012,1.12)':d=120:s=1280x720:fps=30,fade=t=in:st=0:d=0.5,fade=t=out:st=3.5:d=0.5",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
        ])
        clips.append(clip)

    concat = root / "concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips) + "\n", encoding="utf-8")
    silent = root / "picture_edit.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)])

    narration(audio)
    final = Path(args.output).resolve()
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(silent), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart", str(final),
    ])

    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration,size,format_name", "-of", "json", str(final)
    ], text=True)
    metadata = json.loads(probe)["format"]
    duration = float(metadata["duration"])
    size = int(metadata["size"])
    if duration < 7.0 or size < 100_000:
        raise RuntimeError(f"QC rejected master: duration={duration}, size={size}")

    sha = hashlib.sha256(final.read_bytes()).hexdigest()
    qc = {
        "accepted": True,
        "artifact": str(final),
        "sha256": sha,
        "duration_seconds": duration,
        "size_bytes": size,
        "format": metadata.get("format_name"),
        "ai_visual_backend": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "execution": "real_local_cpu_inference -> ffmpeg motion -> narration -> final mp4",
    }
    (root / "qc.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
    print(json.dumps(qc, indent=2))


if __name__ == "__main__":
    main()
