"""AURELIA Maker — offline TTS backend.

Priority order (all free / local):
1. Kokoro TTS  — high quality neural, ~80 MB model, local inference
2. espeak-ng   — fast, robotic but reliable, supports Arabic
3. pyttsx3     — system TTS fallback

Arabic: uses espeak-ng 'ar' voice or pyttsx3 Arabic voice when available.
English: uses Kokoro (en-us female) → espeak-ng en-us+f3 → pyttsx3.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


_AR_RE = re.compile(r'[\u0600-\u06FF]')


def _is_arabic(text: str) -> bool:
    return len(_AR_RE.findall(text)) > len(text) * 0.15


def _try_kokoro(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt Kokoro TTS. Returns True on success."""
    try:
        import kokoro  # type: ignore
        voice = "af_heart" if lang == "en" else "af_heart"  # Kokoro en only for now
        if lang == "ar":
            return False  # Kokoro has no Arabic model yet
        pipeline = kokoro.KPipeline(lang_code="a")  # American English
        audio_data = b""
        for _, _, audio in pipeline(text, voice=voice, speed=0.95, split_pattern=r'\n+'):
            import io
            import soundfile as sf  # type: ignore
            buf = io.BytesIO()
            sf.write(buf, audio, 24000, format="WAV")
            audio_data += buf.getvalue()
        if audio_data:
            out_wav.write_bytes(audio_data)
            return out_wav.stat().st_size > 1000
    except Exception:
        pass
    return False


def _try_espeak(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt espeak-ng or espeak. Returns True on success."""
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        return False
    try:
        if lang == "ar":
            voice = "ar"
            speed = "130"
            pitch = "40"
        else:
            voice = "en-us+f3"  # female voice, more natural
            speed = "145"
            pitch = "50"
        result = subprocess.run(
            [espeak, "-s", speed, "-p", pitch, "-v", voice, "-w", str(out_wav), text],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            # fallback voice
            voice2 = "ar" if lang == "ar" else "en"
            result = subprocess.run(
                [espeak, "-s", speed, "-v", voice2, "-w", str(out_wav), text],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return out_wav.exists() and out_wav.stat().st_size > 500
    except Exception:
        return False


def _try_pyttsx3(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt pyttsx3 system TTS. Returns True on success."""
    try:
        import time
        import pyttsx3  # type: ignore
        engine = pyttsx3.init()
        engine.setProperty("rate", 145)
        engine.setProperty("volume", 0.95)
        # Try to set Arabic voice if available
        if lang == "ar":
            voices = engine.getProperty("voices")
            ar_voice = next(
                (v for v in voices if "arabic" in v.name.lower() or "ar" in v.id.lower()),
                None,
            )
            if ar_voice:
                engine.setProperty("voice", ar_voice.id)
        engine.save_to_file(text, str(out_wav))
        engine.runAndWait()
        time.sleep(0.3)
        return out_wav.exists() and out_wav.stat().st_size > 500
    except Exception:
        return False


def synthesize_script(text: str, out_wav: Path) -> None:
    """Synthesize narration text to WAV using best available offline TTS."""
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    if not text or not text.strip():
        raise ValueError("TTS: empty narration text")

    lang = "ar" if _is_arabic(text) else "en"

    # Try each backend in priority order
    for backend in (_try_kokoro, _try_espeak, _try_pyttsx3):
        if out_wav.exists():
            out_wav.unlink()  # clear any partial file
        try:
            if backend(text, out_wav, lang):
                return
        except Exception:
            pass

    raise RuntimeError(
        "Offline TTS: all backends failed. "
        "Install espeak-ng: sudo apt-get install -y espeak-ng"
    )
