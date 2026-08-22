from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

from aurelia.media import assemble_cinematic_clips, probe_duration
from aurelia.tts import synthesize_script
from aurelia.visuals import CinematicVisualEngine


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="aurelia-smoke-"))
    try:
        sources = [root / "visual-a.png", root / "visual-b.png"]
        clips = [root / "cinematic-shot-a.mp4", root / "cinematic-shot-b.mp4"]
        final = root / "cinematic-edit.mp4"
        audio = root / "narration.wav"

        for index, color in enumerate(((18, 44, 80), (70, 28, 55))):
            image = Image.new("RGB", (640, 360), color)
            draw = ImageDraw.Draw(image)
            draw.ellipse((120 + index * 90, 70, 400 + index * 90, 300), fill=(212, 136, 52), outline=(255, 255, 255), width=5)
            image.save(sources[index])

        engine = CinematicVisualEngine(width=320, height=180, fps=12)
        for source, video, movement in zip(sources, clips, ("dolly_in", "pan_right")):
            engine.render_motion(
                source, video, duration=2.5,
                camera={"movement": movement, "zoom_start": 1.0, "zoom_end": 1.12},
                lighting={"brightness": 1.02, "contrast": 1.06, "saturation": 1.05},
                atmosphere={"haze": 0.15},
                vfx={"grain": 0.02, "vignette": 0.2, "bloom": 0.08},
            )
        assemble_cinematic_clips(clips, ["dissolve"], final, transition_duration=0.4)
        synthesize_script("AURELIA Maker current production path smoke test.", audio)

        assert final.stat().st_size > 1000
        assert audio.stat().st_size > 1000
        assert probe_duration(final) >= 4.0
        print(f"CINEMATIC RENDER PASS: {final}")
        print("DISSOLVE TRANSITION PASS")
        print(f"TTS PASS: {audio}")
        print(f"VIDEO VALIDATION: PASS (duration={probe_duration(final):.2f}s, non_empty={final.stat().st_size > 1000})")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
