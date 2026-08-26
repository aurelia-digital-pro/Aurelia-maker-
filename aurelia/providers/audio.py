"""Provider-aware audio/TTS adapters for AURELIA Maker."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AudioProvider(ABC):
    name = "unknown"

    @abstractmethod
    def generate(self, text: str, output: str | Path, language: str = "en", **kwargs: Any) -> Path:
        raise NotImplementedError

    def validate(self, output: str | Path) -> bool:
        path = Path(output)
        return path.is_file() and path.stat().st_size > 0


class EdgeTTSProvider(AudioProvider):
    """Microsoft Edge Neural TTS adapter used by production narration.

    The provider is deliberately strict in production: if the network service or
    its executable is unavailable, generation fails instead of silently falling
    back to a robotic local voice. A degraded local path can be enabled only by
    explicitly setting ``AURELIA_ALLOW_DEGRADED_TTS=1`` outside production
    acceptance.
    """

    name = "edge-tts"
    DEFAULT_VOICES = {
        "ar": "ar-SA-HamedNeural",
        "en": "en-US-AriaNeural",
    }

    def __init__(
        self,
        *,
        voice: str | None = None,
        max_attempts: int = 3,
        timeout_seconds: int = 180,
        allow_degraded: bool | None = None,
    ) -> None:
        self.voice = voice
        self.max_attempts = max(1, int(max_attempts))
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.allow_degraded = (
            os.environ.get("AURELIA_ALLOW_DEGRADED_TTS", "0") == "1"
            if allow_degraded is None
            else bool(allow_degraded)
        )
        self.provenance: dict[str, Any] = {}

    @staticmethod
    def _normalise_language(language: str, text: str) -> str:
        if language and language.lower() not in {"auto", "und"}:
            return language.lower().split("-", 1)[0]
        from ..tts import _detect_lang
        return _detect_lang(text)

    def _voice_for(self, language: str, requested: str | None) -> str:
        return requested or self.voice or self.DEFAULT_VOICES.get(language, self.DEFAULT_VOICES["en"])

    @staticmethod
    def _probe_audio(path: Path) -> dict[str, Any]:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-select_streams", "a:0",
                    "-show_entries", "stream=codec_name,sample_rate,channels",
                    "-show_entries", "format=duration,size", "-of", "json", str(path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"TTS output probe timed out after 60s: {path}"
            ) from exc
        if result.returncode != 0:
            raise RuntimeError(f"TTS output probe failed: {result.stderr[-500:]}")
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            raise RuntimeError("TTS output contains no audio stream")
        stream = streams[0]
        duration = float(data.get("format", {}).get("duration") or 0.0)
        if duration <= 0:
            raise RuntimeError("TTS output has no measurable duration")
        return {
            "duration_s": duration,
            "sample_rate": int(stream.get("sample_rate") or 0),
            "channels": int(stream.get("channels") or 0),
            "codec": str(stream.get("codec_name") or ""),
            "size_bytes": int(data.get("format", {}).get("size") or path.stat().st_size),
        }

    def _degraded_espeak(self, text: str, output: Path, language: str, reason: str) -> Path:
        from ..tts import _try_espeak
        output.parent.mkdir(parents=True, exist_ok=True)
        if not _try_espeak(text, output, language):
            raise RuntimeError(f"Explicit degraded espeak TTS failed after Edge TTS failure: {reason}")
        metrics = self._probe_audio(output)
        self.provenance = {
            "provider": "espeak-ng",
            "voice": "ar+m1" if language == "ar" else "en-us+f3",
            "language": language,
            "model_or_voice_id": "ar+m1" if language == "ar" else "en-us+f3",
            "duration_s": metrics["duration_s"],
            "sample_rate": metrics["sample_rate"],
            "channels": metrics["channels"],
            "format": "wav",
            "fallback": True,
            "fallback_reason": reason,
            "degraded": True,
        }
        return output

    def generate(self, text: str, output: str | Path, language: str = "auto", **kwargs: Any) -> Path:
        if not text or not text.strip():
            raise ValueError("TTS: empty narration text")
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lang = self._normalise_language(language, text)
        voice = self._voice_for(lang, kwargs.get("voice"))
        segment_index = int(kwargs.get("segment_index", 0))
        text_fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
        diagnostic_prefix = (
            f"provider={self.name} voice={voice} language={lang} "
            f"segment={segment_index} text_sha256={text_fingerprint} "
            f"output={output_path}"
        )
        edge = shutil.which("edge-tts")
        if edge is None:
            reason = "edge-tts executable is not installed"
            if self.allow_degraded and os.environ.get("AURELIA_PRODUCTION_MODE", "0") != "1":
                return self._degraded_espeak(text, output_path, lang, reason)
            raise RuntimeError(
                f"Production TTS requires Edge Neural provider: {reason}; "
                f"{diagnostic_prefix} attempt=0 validation=not-run artifact_bytes=0"
            )

        last_error = ""
        attempt_errors: list[str] = []
        # Keep the temporary media on the same filesystem as the destination so
        # the final atomic replace cannot fail because /tmp and the output
        # volume are mounted separately.
        with tempfile.TemporaryDirectory(
            prefix=".aurelia-edge-tts-", dir=str(output_path.parent)
        ) as tmp:
            source_mp3 = Path(tmp) / "narration.mp3"
            converted_wav = Path(tmp) / "narration.wav"
            for attempt in range(1, self.max_attempts + 1):
                try:
                    if source_mp3.exists():
                        source_mp3.unlink()
                    result = subprocess.run(
                        [
                            edge, "--voice", voice, "--rate=-8%", "--pitch=-2Hz",
                            "--text", text, "--write-media", str(source_mp3),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout_seconds,
                        check=False,
                    )
                    if result.returncode != 0 or not source_mp3.is_file() or source_mp3.stat().st_size < 500:
                        detail = (result.stderr or result.stdout or "empty Edge TTS output").strip()
                        last_error = (
                            f"edge-tts subprocess exit={result.returncode}: {detail}"
                        )[-1000:]
                        raise RuntimeError(last_error)
                    convert = subprocess.run(
                        [
                            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-i", str(source_mp3), "-ar", "22050", "-ac", "1",
                            "-c:a", "pcm_s16le", str(converted_wav),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                        check=False,
                    )
                    if convert.returncode != 0 or not converted_wav.is_file() or converted_wav.stat().st_size < 500:
                        detail = (convert.stderr or "empty converted WAV output").strip()
                        last_error = (
                            f"ffmpeg WAV conversion exit={convert.returncode}: {detail}"
                        )[-1000:]
                        raise RuntimeError(last_error)
                    os.replace(converted_wav, output_path)
                    metrics = self._probe_audio(output_path)
                    self.provenance = {
                        "provider": self.name,
                        "voice": voice,
                        "language": lang,
                        "model_or_voice_id": voice,
                        "segment_index": segment_index,
                        "text_sha256": text_fingerprint,
                        "output_path": str(output_path),
                        "artifact_size_bytes": output_path.stat().st_size,
                        "artifact_validation": "passed",
                        "duration_s": metrics["duration_s"],
                        "sample_rate": metrics["sample_rate"],
                        "channels": metrics["channels"],
                        "format": "wav",
                        "fallback": False,
                        "fallback_reason": "",
                        "degraded": False,
                        "attempts": attempt,
                        "rate": "-8%",
                        "pitch": "-2Hz",
                    }
                    return output_path
                except subprocess.TimeoutExpired:
                    last_error = (
                        f"edge-tts subprocess timed out after {self.timeout_seconds}s"
                    )
                    attempt_errors.append(f"attempt {attempt}: {last_error}")
                    if attempt < self.max_attempts:
                        time.sleep(min(2.0 * attempt, 5.0))
                except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                    last_error = str(exc).strip() or exc.__class__.__name__
                    attempt_errors.append(f"attempt {attempt}: {last_error}")
                    if attempt < self.max_attempts:
                        time.sleep(min(2.0 * attempt, 5.0))

        history = "; ".join(attempt_errors[-self.max_attempts:])
        artifact_size = output_path.stat().st_size if output_path.is_file() else 0
        reason = (
            f"Edge TTS failed after {self.max_attempts} attempts: {last_error}"
            + (f" | attempts: {history}" if history else "")
            + f" | {diagnostic_prefix} attempt={self.max_attempts} "
              f"artifact_bytes={artifact_size} validation=failed"
        )
        if self.allow_degraded and os.environ.get("AURELIA_PRODUCTION_MODE", "0") != "1":
            return self._degraded_espeak(text, output_path, lang, reason)
        raise RuntimeError(reason)


class EspeakProvider(AudioProvider):
    """Explicit degraded/local espeak adapter; never selected by production default."""

    name = "espeak-ng"

    def __init__(self) -> None:
        self.provenance: dict[str, Any] = {}

    def generate(self, text: str, output: str | Path, language: str = "en", **kwargs: Any) -> Path:
        from ..tts import _detect_lang, _try_espeak
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lang = _detect_lang(text) if language in {"", "auto", "und"} else language.split("-", 1)[0]
        if not text or not text.strip() or not _try_espeak(text, destination, lang):
            raise RuntimeError("espeak-ng TTS failed to produce a WAV artifact")
        metrics = EdgeTTSProvider._probe_audio(destination)
        self.provenance = {
            "provider": self.name,
            "voice": "ar+m1" if lang == "ar" else "en-us+f3",
            "language": lang,
            "model_or_voice_id": "ar+m1" if lang == "ar" else "en-us+f3",
            "duration_s": metrics["duration_s"],
            "sample_rate": metrics["sample_rate"],
            "channels": metrics["channels"],
            "format": "wav",
            "fallback": False,
            "fallback_reason": "",
            "degraded": True,
        }
        return destination


def best_available() -> AudioProvider:
    return EdgeTTSProvider()


__all__ = ["AudioProvider", "EdgeTTSProvider", "EspeakProvider", "best_available"]
