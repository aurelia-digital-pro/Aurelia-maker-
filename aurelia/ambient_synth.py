"""Environment-aware ambient sound synthesis using NumPy."""
from __future__ import annotations

import hashlib
import wave
from pathlib import Path
from typing import Any

import numpy as np

SAMPLE_RATE = 48_000

PROFILES: dict[str, dict[str, Any]] = {
    "machine": {"tones": (58, 116, 233), "noise": 0.20, "lfo": 0.08},
    "desert": {"tones": (74,), "noise": 0.34, "lfo": 0.15},
    "ocean": {"tones": (48, 96), "noise": 0.38, "lfo": 0.22},
    "forest": {"tones": (180, 360), "noise": 0.24, "lfo": 0.18},
    "city": {"tones": (62, 124, 248), "noise": 0.27, "lfo": 0.11},
    "space": {"tones": (36, 72), "noise": 0.10, "lfo": 0.05},
    "ancient": {"tones": (55, 110, 165), "noise": 0.16, "lfo": 0.08},
    "abstract": {"tones": (90, 207, 311), "noise": 0.29, "lfo": 0.31},
    "urban": {"tones": (68, 136, 272), "noise": 0.30, "lfo": 0.12},
    "mountain": {"tones": (42, 84), "noise": 0.25, "lfo": 0.09},
}


def _filtered_noise(rng: np.random.Generator, count: int, profile: dict[str, Any]) -> np.ndarray:
    raw = rng.normal(0.0, 1.0, count).astype(np.float32)
    # A cheap low-pass integrator produces wind/water-like correlated texture.
    alpha = 0.012 + float(profile["lfo"]) * 0.025
    out = np.empty_like(raw)
    out[0] = raw[0]
    for i in range(1, count):
        out[i] = (1.0 - alpha) * out[i - 1] + alpha * raw[i]
    return out / max(1e-6, float(np.max(np.abs(out))))


def synthesize_ambient(environment: str, duration_sec: float, output: str | Path, seed: int | None = None) -> Path:
    """Generate a distinct stereo environmental bed with gentle LFO movement."""
    key = str(environment or "abstract").lower()
    profile = PROFILES.get(key, PROFILES["abstract"])
    seconds = max(0.5, float(duration_sec))
    count = int(round(seconds * SAMPLE_RATE))
    digest = hashlib.sha256(f"{key}:{seed if seed is not None else 0}".encode()).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "big"))
    t = np.arange(count, dtype=np.float32) / SAMPLE_RATE
    left = np.zeros(count, dtype=np.float32)
    right = np.zeros(count, dtype=np.float32)
    for idx, frequency in enumerate(profile["tones"]):
        phase = (idx + 1) * 0.37
        lfo = 1.0 + 0.22 * np.sin(2 * np.pi * float(profile["lfo"]) * t + phase)
        tone = np.sin(2 * np.pi * float(frequency) * t + phase) * lfo
        left += tone * (0.035 / (idx + 1))
        right += np.sin(2 * np.pi * float(frequency) * t + phase + 0.17) * lfo * (0.033 / (idx + 1))
    noise = _filtered_noise(rng, count, profile) * float(profile["noise"]) * 0.12
    left += noise
    right += np.roll(noise, min(97, count - 1))
    fade = np.minimum(1.0, np.minimum(t / 1.5, (seconds - t) / 1.5).clip(min=0.0))
    stereo = np.stack([left * fade, right * fade], axis=1)
    peak = float(np.max(np.abs(stereo))) or 1.0
    stereo = np.clip(stereo / max(1.0, peak * 2.5), -1.0, 1.0)
    pcm = (stereo * 32767.0).astype(np.int16)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    return out


AmbientSynthesizer = synthesize_ambient
__all__ = ["PROFILES", "SAMPLE_RATE", "synthesize_ambient", "AmbientSynthesizer"]
