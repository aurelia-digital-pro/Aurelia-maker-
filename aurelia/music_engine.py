"""AURELIA — structured cinematic music synthesis."""
from __future__ import annotations

import wave
from pathlib import Path


def generate_cinematic_music(
    duration_sec: float,
    output_path: str | Path,
    emotional_arc: list[str] | None = None,
) -> Path:
    """Write a multi-layer 48 kHz stereo score with a narrative envelope."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        import numpy as np
    except ImportError:
        _write_silence_wav(output, duration_sec)
        return output

    sr = 48_000
    duration = max(float(duration_sec), 5.0)
    n = int(sr * duration)
    t = np.arange(n, dtype=np.float64) / sr
    phase = np.clip(t / duration, 0.0, 1.0)
    arc = [str(x).lower() for x in (emotional_arc or [])]
    tension = 1.0 + 0.12 * sum(x in {"climax", "tension", "rising_action", "awe"} for x in arc)
    root = 55.0 if not any(x in {"bright", "wonder", "hope"} for x in arc) else 65.41

    def sine(freq: float, amp: float = 1.0) -> np.ndarray:
        return amp * np.sin(2.0 * np.pi * freq * t)

    # Intro → build → climax → resolution envelope; all layers use it.
    envelope = np.piecewise(
        phase,
        [phase < 0.10, (phase >= 0.10) & (phase < 0.40), (phase >= 0.40) & (phase < 0.70), phase >= 0.70],
        [lambda x: 0.18 + 0.82 * x / 0.10,
         lambda x: 1.0 + 0.18 * (x - 0.10) / 0.30,
         lambda x: 1.18,
         lambda x: 1.18 - 0.72 * (x - 0.70) / 0.30],
    )
    breathe = 0.82 + 0.18 * np.sin(2 * np.pi * t / 8.0)

    bass = (sine(root, 0.32) + sine(root * 1.5, 0.13) + sine(root * 2.0, 0.08)) * breathe
    pad = np.zeros(n)
    for idx, ratio in enumerate((2.0, 2.4, 3.0, 4.0, 4.8, 6.0)):
        tone = sine(root * ratio, 0.08 / (1 + idx * 0.22))
        pad += tone * (0.85 + 0.15 * np.sin(2 * np.pi * t / (5.0 + idx)))

    # A sparse melodic line and a low rhythmic pulse make the structure audible.
    melody_freqs = [root * 4, root * 4.8, root * 6, root * 7.2, root * 8]
    melody = np.zeros(n)
    note_len = max(1, int(sr * 1.6))
    for idx, start in enumerate(range(0, n, note_len)):
        end = min(n, start + int(note_len * 0.72))
        freq = melody_freqs[idx % len(melody_freqs)]
        local = np.arange(end - start) / sr
        melody[start:end] += np.sin(2 * np.pi * freq * local) * (0.025 + 0.03 * (phase[start:end] > 0.4))

    pulse = np.sin(2 * np.pi * root * 2.0 * t) * (0.025 + 0.025 * (phase > 0.4))
    pulse *= (np.sin(2 * np.pi * 0.5 * t) > -0.1).astype(np.float64)
    mix = (bass * 0.52 + pad * 0.80 + melody + pulse) * envelope * tension

    reverb = np.zeros(n)
    for delay_ms, decay in ((80, 0.20), (160, 0.13), (320, 0.07), (640, 0.035)):
        d = int(sr * delay_ms / 1000)
        if d < n:
            reverb[d:] += mix[:-d] * decay
    mix += reverb

    delay = int(sr * 0.009)
    left = mix.copy()
    right = np.roll(mix, -delay)
    right[-delay:] = mix[-1]
    fade = np.minimum(1.0, np.minimum(t / 3.0, (duration - t) / 4.0).clip(min=0.0))
    left *= fade
    right *= fade
    peak = max(float(np.max(np.abs(left))), float(np.max(np.abs(right))), 1e-9)
    gain = 0.62 / peak
    interleaved = np.empty(n * 2, dtype=np.int16)
    interleaved[0::2] = np.clip(left * gain * 32767, -32768, 32767).astype(np.int16)
    interleaved[1::2] = np.clip(right * gain * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(interleaved.tobytes())
    return output


def _write_silence_wav(output_path: str | Path, duration_sec: float) -> None:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sr = 48_000
    n = int(sr * max(float(duration_sec), 5.0))
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(b"\x00\x00\x00\x00" * n)


__all__ = ["generate_cinematic_music", "_write_silence_wav"]
