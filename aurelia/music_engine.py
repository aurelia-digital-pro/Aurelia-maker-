"""AURELIA — Cinematic ambient music synthesis engine.

Generates rich multi-layer pentatonic minor ambient music using numpy.
No external music ML models required. Pure numpy + stdlib wave module.

Layers:
  - Deep bass: root + fifth, slow LFO amplitude modulation
  - String pad: pentatonic minor intervals, multiple harmonics, slow attack
  - High shimmer: upper octave whispers, sparse
  - Reverb: comb filter simulation (80ms / 160ms / 320ms delays)
  - Stereo: slight L/R offset for width
  - Fade: 3s in / 4s out
"""
from __future__ import annotations

import wave
from pathlib import Path


def generate_cinematic_music(duration_sec: float, output_path: Path) -> Path:
    """Generate cinematic ambient music and write to output_path as 16-bit stereo WAV.

    Works without pydub, scipy, or any ML model.
    Uses only numpy (already in requirements) and stdlib wave.
    """
    try:
        import numpy as np
    except ImportError:
        # numpy unavailable — write silence as a valid WAV
        _write_silence_wav(output_path, duration_sec)
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)

    SR = 44100
    duration = max(float(duration_sec), 5.0)
    n = int(SR * duration)
    t = np.linspace(0, duration, n, dtype=np.float64)

    # Pentatonic minor: A-based scale (Hz)
    # A2=110, C3=130.8, D3=146.8, E3=164.8, G3=196.0, A3=220.0
    SCALE = [55.0, 82.5, 110.0, 130.8, 146.8, 164.8, 196.0, 220.0, 261.6, 329.6]

    def sine(freq: float, amp: float = 1.0) -> np.ndarray:
        return amp * np.sin(2.0 * np.pi * freq * t)

    def slow_lfo(period: float, min_val: float = 0.5) -> np.ndarray:
        """Slow-breathing LFO envelope."""
        lfo = np.sin(2.0 * np.pi * (1.0 / period) * t) * 0.5 + 0.5
        return lfo * (1.0 - min_val) + min_val

    # ── Bass layer ─────────────────────────────────────────────────────────
    bass = (
        sine(SCALE[0],  0.32) +   # root A1
        sine(SCALE[1],  0.16) +   # fifth E2
        sine(SCALE[0] * 2, 0.10)  # octave
    ) * slow_lfo(9.0, 0.5)

    # ── String pad ─────────────────────────────────────────────────────────
    pad = np.zeros(n)
    weights = [0.14, 0.11, 0.09, 0.07, 0.06, 0.05, 0.04, 0.03]
    for i, freq in enumerate(SCALE[2:10]):
        w = weights[i] if i < len(weights) else 0.02
        pad += sine(freq, w)
        pad += sine(freq * 1.502, w * 0.35)   # slightly detuned fifth
        pad += sine(freq * 2.0,   w * 0.18)   # octave harmonic
        pad += sine(freq * 3.0,   w * 0.08)   # 3rd harmonic
    pad *= slow_lfo(7.0, 0.35)

    # ── High shimmer ──────────────────────────────────────────────────────
    shimmer = (
        sine(SCALE[-1] * 2, 0.035) +
        sine(SCALE[-2] * 2, 0.025)
    ) * slow_lfo(4.0, 0.1)

    # ── Mix ───────────────────────────────────────────────────────────────
    mix = bass + pad + shimmer

    # ── Reverb: comb filter simulation ───────────────────────────────────
    reverb = np.zeros(n)
    for delay_ms, decay in [(80, 0.22), (160, 0.14), (320, 0.08), (640, 0.04)]:
        d = int(SR * delay_ms / 1000)
        if d < n:
            reverb[d:] += mix[:n - d] * decay
    mix = mix + reverb

    # ── Stereo widening ───────────────────────────────────────────────────
    stereo_delay = int(SR * 0.009)  # 9ms L/R offset
    L = mix.copy()
    R = np.empty(n)
    R[:n - stereo_delay] = mix[stereo_delay:]
    R[n - stereo_delay:] = mix[-stereo_delay:]

    # ── Fade in / out ─────────────────────────────────────────────────────
    fade_in_n  = min(int(SR * 3.0), n // 4)
    fade_out_n = min(int(SR * 4.0), n // 4)
    env = np.ones(n)
    env[:fade_in_n]  = np.linspace(0.0, 1.0, fade_in_n)
    env[n - fade_out_n:] = np.linspace(1.0, 0.0, fade_out_n)
    L *= env
    R *= env

    # ── Normalize to -3 dBFS ──────────────────────────────────────────────
    peak = max(float(np.abs(L).max()), float(np.abs(R).max()), 1e-9)
    gain = 0.707 / peak
    L = L * gain
    R = R * gain

    # ── Write 16-bit stereo WAV ───────────────────────────────────────────
    L_i = np.clip(L * 32767.0, -32768.0, 32767.0).astype(np.int16)
    R_i = np.clip(R * 32767.0, -32768.0, 32767.0).astype(np.int16)

    stereo = np.empty(n * 2, dtype=np.int16)
    stereo[0::2] = L_i
    stereo[1::2] = R_i

    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())

    return output_path


def _write_silence_wav(output_path: Path, duration_sec: float) -> None:
    """Write a valid silent stereo WAV when numpy is unavailable."""
    SR = 44100
    n  = int(SR * max(float(duration_sec), 5.0))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(b"\x00\x00\x00\x00" * n)  # 2 channels × 2 bytes


__all__ = ["generate_cinematic_music", "_write_silence_wav"]
