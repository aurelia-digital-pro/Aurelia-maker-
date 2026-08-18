from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from aurelia.asset_generator import generate_scene_image, generate_title_card
from aurelia.ffmpeg_util import ffmpeg_binary, ffprobe_binary
from aurelia.tts import synthesize_script


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="aurelia-smoke-"))
    try:
        visual = root / "visual.png"
        title = root / "title.png"
        audio = root / "narration.wav"
        generate_title_card("AURELIA MAKER", "Repair Smoke Test", title)
        generate_scene_image(0, "Smoke", "Real local visual generation", visual)
        synthesize_script("AURELIA Maker local narration smoke test.", audio)
        assert title.stat().st_size > 1000
        assert visual.stat().st_size > 1000
        assert audio.stat().st_size > 1000
        ffmpeg = ffmpeg_binary()
        ffprobe = ffprobe_binary()
        print(f"FFMPEG PASS: {ffmpeg}")
        print(f"FFPROBE PASS: {ffprobe}")
        print("VISUAL PASS")
        print("TTS PASS")
        print("STAGE 1/10 PASS")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
