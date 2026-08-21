"""AURELIA Maker — offline TTS backend (Arabic + English, multi-voice).

Priority order (all free / local):

  ARABIC
  1. Piper TTS (ar model)    — neural, natural Arabic voice, ~80 MB model
  2. espeak-ng ar            — fast, acceptable for Arabic
  3. pyttsx3 Arabic voice    — system TTS fallback

  ENGLISH
  1. Kokoro TTS (en)         — high quality neural, ~80 MB model
  2. Piper TTS (en model)    — good neural quality
  3. espeak-ng en-us+f3      — fast, acceptable
  4. pyttsx3                 — system TTS fallback

Multi-speaker dialogue is supported: if the text contains lines prefixed with
  NARRATOR:, SPEAKER_A:, SPEAKER_B:, etc.
the engine splits by speaker and concatenates segments with inter-speaker pauses.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────────────

_AR_RE = re.compile(r'[\u0600-\u06FF]')


def _is_arabic(text: str) -> bool:
    return len(_AR_RE.findall(text)) > len(text) * 0.15


def _detect_lang(text: str) -> str:
    return "ar" if _is_arabic(text) else "en"


# ── speaker splitting ─────────────────────────────────────────────────────────

_SPEAKER_RE = re.compile(
    r'^\s*(?P<speaker>[A-Z\u0600-\u06FF][A-Z\u0600-\u06FFa-z_\- ]{0,20})\s*:\s*(?P<line>.+)',
    re.MULTILINE,
)


def _split_dialogue(text: str) -> list[tuple[str, str]]:
    """Return list of (speaker, line) tuples.  Falls back to single narrator."""
    matches = list(_SPEAKER_RE.finditer(text))
    if len(matches) < 2:
        return [("NARRATOR", text.strip())]
    segments = []
    for m in matches:
        segments.append((m.group("speaker").strip(), m.group("line").strip()))
    return segments


# ── Piper TTS ─────────────────────────────────────────────────────────────────

_PIPER_MODELS: dict[str, str] = {
    # Paths where piper Arabic model may live (downloaded separately)
    "ar": "ar_JO-kareem-medium.onnx",   # Jordanian Arabic — natural
    "en": "en_US-lessac-medium.onnx",   # US English — natural female
}

_PIPER_MODEL_DIRS = [
    Path.home() / ".local" / "share" / "piper-voices",
    Path("/usr/share/piper-voices"),
    Path("/opt/piper-voices"),
    Path("models") / "piper",
]


def _find_piper_model(lang: str) -> Path | None:
    filename = _PIPER_MODELS.get(lang, "")
    for d in _PIPER_MODEL_DIRS:
        p = d / filename
        if p.is_file():
            return p
    return None


def _try_piper(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt piper TTS. Returns True on success."""
    piper = shutil.which("piper") or shutil.which("piper-tts")
    if not piper:
        return False
    model = _find_piper_model(lang)
    if model is None:
        return False
    try:
        result = subprocess.run(
            [piper, "--model", str(model), "--output_file", str(out_wav)],
            input=text.encode("utf-8"),
            capture_output=True,
            check=False,
        )
        return (
            result.returncode == 0
            and out_wav.exists()
            and out_wav.stat().st_size > 500
        )
    except Exception:
        return False


# ── Kokoro TTS ────────────────────────────────────────────────────────────────

def _try_kokoro(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt Kokoro TTS (English only for now). Returns True on success."""
    if lang != "en":
        return False
    try:
        import io
        import kokoro  # type: ignore
        import soundfile as sf  # type: ignore

        pipeline = kokoro.KPipeline(lang_code="a")  # American English
        audio_data = b""
        for _, _, audio in pipeline(text, voice="af_heart", speed=0.95, split_pattern=r'\n+'):
            buf = io.BytesIO()
            sf.write(buf, audio, 24000, format="WAV")
            audio_data += buf.getvalue()
        if audio_data:
            out_wav.write_bytes(audio_data)
            return out_wav.stat().st_size > 1000
    except Exception:
        pass
    return False


# ── espeak-ng ─────────────────────────────────────────────────────────────────

def _try_espeak(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt espeak-ng or espeak. Returns True on success."""
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if not espeak:
        return False
    try:
        if lang == "ar":
            # ar+m1 is a male Arabic voice — try multiple voices
            for voice in ("ar+m1", "ar"):
                result = subprocess.run(
                    [espeak, "-s", "120", "-p", "45", "-v", voice, "-w", str(out_wav), text],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                if result.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 500:
                    return True
        else:
            for voice, speed, pitch in [
                ("en-us+f3", "148", "52"),
                ("en-gb+f4", "145", "50"),
                ("en", "145", "50"),
            ]:
                result = subprocess.run(
                    [espeak, "-s", speed, "-p", pitch, "-v", voice, "-w", str(out_wav), text],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                if result.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 500:
                    return True
    except Exception:
        pass
    return False


# ── pyttsx3 ───────────────────────────────────────────────────────────────────

def _try_pyttsx3(text: str, out_wav: Path, lang: str) -> bool:
    """Attempt pyttsx3 system TTS. Returns True on success."""
    try:
        import time
        import pyttsx3  # type: ignore

        engine = pyttsx3.init()
        engine.setProperty("rate", 145)
        engine.setProperty("volume", 0.95)
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
        time.sleep(0.4)
        return out_wav.exists() and out_wav.stat().st_size > 500
    except Exception:
        return False


# ── concatenation helper ──────────────────────────────────────────────────────

def _concat_wavs(parts: list[Path], output: Path, pause_ms: int = 500) -> None:
    """Concatenate WAV files with a silent pause between each."""
    try:
        from pydub import AudioSegment  # type: ignore
        pause = AudioSegment.silent(duration=pause_ms)
        combined = AudioSegment.empty()
        for i, p in enumerate(parts):
            seg = AudioSegment.from_wav(str(p))
            if i > 0:
                combined += pause
            combined += seg
        combined.export(str(output), format="wav")
        return
    except Exception:
        pass

    # Fallback: ffmpeg concat
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and len(parts) > 1:
        try:
            list_file = output.parent / "concat_list.txt"
            list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in parts))
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0",
                 "-i", str(list_file), str(output)],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            if output.exists() and output.stat().st_size > 500:
                return
        except Exception:
            pass

    # Last resort: copy first part only
    import shutil as _shutil
    _shutil.copy2(parts[0], output)


# ── public API ─────────────────────────────────────────────────────────────────

def synthesize_script(text: str, out_wav: Path) -> None:
    """Synthesize narration text to WAV using best available offline TTS.

    Handles:
    - Arabic and English detection
    - Multi-speaker dialogue (SPEAKER: line format)
    - Falls back gracefully through Piper → Kokoro → espeak-ng → pyttsx3
    """
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    if not text or not text.strip():
        raise ValueError("TTS: empty narration text")

    segments = _split_dialogue(text)
    lang = _detect_lang(text)

    if len(segments) == 1:
        # Single narrator — simple path
        _synthesize_single(segments[0][1], out_wav, lang)
        return

    # Multi-speaker dialogue: synthesize each segment separately then concat
    with tempfile.TemporaryDirectory(prefix="aurelia-tts-") as tmp:
        parts: list[Path] = []
        for idx, (speaker, line) in enumerate(segments):
            seg_wav = Path(tmp) / f"seg_{idx:04d}.wav"
            seg_lang = _detect_lang(line)
            try:
                _synthesize_single(line, seg_wav, seg_lang)
                if seg_wav.exists() and seg_wav.stat().st_size > 500:
                    parts.append(seg_wav)
            except Exception:
                pass

        if not parts:
            raise RuntimeError("TTS: all dialogue segments failed")

        _concat_wavs(parts, out_wav, pause_ms=600)

    if not out_wav.exists() or out_wav.stat().st_size < 500:
        raise RuntimeError("TTS: concatenated output is empty")


def _synthesize_single(text: str, out_wav: Path, lang: str) -> None:
    """Synthesize a single text segment using best available backend."""
    # Build backend priority based on language
    if lang == "ar":
        backends = [_try_piper, _try_espeak, _try_pyttsx3]
    else:
        backends = [_try_kokoro, _try_piper, _try_espeak, _try_pyttsx3]

    for backend in backends:
        if out_wav.exists():
            out_wav.unlink()
        try:
            if backend(text, out_wav, lang):
                return
        except Exception:
            pass

    raise RuntimeError(
        f"Offline TTS: all backends failed for lang={lang}. "
        "For Arabic: install piper-tts with ar_JO model or espeak-ng. "
        "For English: install kokoro or espeak-ng."
    )
