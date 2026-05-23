"""Procedural, seamlessly looping per-world wait ambiences (offline, 0 tokens).

Two moods:
  - "space"  (Sci-Fi): deep drone + beating + faint noise + shimmer
  - "forest" (Fantasy): soft wind + warm pad chord + gentle LFO

Deliberately quiet (amplitude ~0.05). An end-to-start crossfade makes the
file gapless-loopable on its own.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 24000


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m) * peak


def _seamless(buf: np.ndarray, sr: int, xfade: float = 0.4) -> np.ndarray:
    """Produces a self-loopable file: crossfade the end into the beginning."""
    x = int(sr * xfade)
    if len(buf) <= 2 * x:
        return buf
    extra = buf[len(buf) - x:]
    out = buf[: len(buf) - x].copy()
    fi = np.linspace(0.0, 1.0, x)
    out[:x] = out[:x] * fi + extra * (1.0 - fi)
    return out


def _bandpass_noise(n: int, sr: int, lo_hz: float, hi_hz: float,
                    rng: np.random.Generator) -> np.ndarray:
    """Quick FFT-based band-pass — much cleaner than a box-filter average,
    and lets us shape noise into the AUDIBLE band (hundreds of Hz) instead
    of leaving it at sub-bass."""
    noise = rng.standard_normal(n).astype(np.float32)
    fft = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    mask = (freqs >= lo_hz) & (freqs <= hi_hz)
    fft[~mask] = 0
    return np.fft.irfft(fft, n=n).astype(np.float32)


def _space(dur: float, sr: int) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    # Deep drone foundation: integer number of cycles over dur so the loop
    # joins seamlessly without a click.
    sig = np.zeros(n)
    for f, a in ((55.0, 1.0), (110.0, 0.5), (164.0, 0.22)):
        f = round(f * dur) / dur
        sig += a * np.sin(2 * np.pi * f * t)
    # Slow beating partial near the second drone for sci-fi life.
    fb = round(56.0 * dur) / dur
    sig += 0.4 * np.sin(2 * np.pi * fb * t)
    # Mid-range harmonics so it's not just sub-bass mud on small speakers.
    for f, a in ((220.0, 0.18), (330.0, 0.12), (440.0, 0.08), (660.0, 0.06)):
        f = round(f * dur) / dur
        sig += a * np.sin(2 * np.pi * f * t)
    # Slow amplitude LFO
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * (1.0 / dur) * t)
    # Air / hiss in the mids (band-passed noise — was previously a 220-tap
    # box filter, which is ~LP @ 50 Hz so contributed almost nothing).
    rng = np.random.default_rng(42)
    air = _bandpass_noise(n, sr, 400.0, 3000.0, rng)
    sig = sig * lfo + 0.20 * (air / (np.max(np.abs(air)) or 1.0))
    # Distinct shimmer well above the speech band.
    sig += 0.10 * np.sin(2 * np.pi * (round(1320 * dur) / dur) * t) * lfo
    return _norm(sig, 0.20)


def _forest(dur: float, sr: int) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)
    # Real wind: band-passed broadband noise in the 200–3000 Hz region
    # plus a slow amplitude LFO. The OLD code used a 400-tap box filter
    # which is essentially LP @ 30 Hz — i.e. the "wind" had no audible
    # content at all and the file sounded like a sub-bass drone.
    wind = _bandpass_noise(n, sr, 200.0, 3000.0, rng)
    wind = wind / (np.max(np.abs(wind)) or 1.0)
    wind *= 0.6 + 0.4 * np.sin(2 * np.pi * (1.0 / dur) * t)
    # Warm pad chord (A / C# / E + octave) — integer cycles for the loop.
    pad = np.zeros(n)
    for f, a in ((110.0, 1.0), (138.59, 0.5), (164.81, 0.5), (220.0, 0.3),
                 (329.63, 0.2), (440.0, 0.12)):
        f = round(f * dur) / dur
        pad += a * np.sin(2 * np.pi * f * t)
    lfo = 0.7 + 0.3 * np.sin(2 * np.pi * (2.0 / dur) * t)
    sig = 0.5 * pad * lfo + 0.5 * wind
    return _norm(sig, 0.20)


_MOODS = {"space": _space, "forest": _forest}

# world genre/id -> mood
GENRE_MOOD = {
    "science-fiction": "space", "sci-fi": "space", "scifi": "space",
    "high-fantasy": "forest", "fantasy": "forest",
}


def mood_for(world) -> str:
    g = (world.genre or "").strip().lower()
    return GENRE_MOOD.get(g, "space" if "fi" in g else "forest")


def write_ambient(path: Path, mood: str, dur: float = 20.0,
                   sr: int = SR) -> Path:
    gen = _MOODS.get(mood, _space)
    buf = _seamless(gen(dur + 0.5, sr), sr)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), buf.astype(np.float32), sr, subtype="PCM_16")
    return path
