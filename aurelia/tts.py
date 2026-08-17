"""Offline TTS backend with espeak-ng as the deterministic system fallback."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess


def synthesize_script(text: str, out_wav: Path) -> None:
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        subprocess.run(
            [espeak, "-s", "150", "-v", "en", "-w", str(out_wav), text],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 150)
        engine.setProperty("volume", 0.95)
        engine.save_to_file(text, str(out_wav))
        engine.runAndWait()

    if not out_wav.exists() or out_wav.stat().st_size == 0:
        raise RuntimeError("Offline TTS produced no audio artifact")
