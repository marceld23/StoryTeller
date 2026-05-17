"""Prozedurale, nahtlos loopende Wartesound-Ambiences pro Welt (offline, 0 Tokens).

Zwei Moods:
  - "space"  (Sci-Fi): tiefe Drone + Schwebung + leises Rauschen + Shimmer
  - "forest" (Fantasy): weicher Wind + warmer Pad-Akkord + sanftes LFO

Bewusst leise (Amplitude ~0.05). Die Datei ist durch eine End-zu-Anfang-
Überblendung in sich gapless loopbar.
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
    """Erzeugt eine in sich loopbare Datei: Ende in den Anfang überblenden."""
    x = int(sr * xfade)
    if len(buf) <= 2 * x:
        return buf
    extra = buf[len(buf) - x:]
    out = buf[: len(buf) - x].copy()
    fi = np.linspace(0.0, 1.0, x)
    out[:x] = out[:x] * fi + extra * (1.0 - fi)
    return out


def _space(dur: float, sr: int) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    # Drones: ganzzahlige Zyklen über dur => von sich aus periodisch
    sig = np.zeros(n)
    for f, a in ((55.0, 1.0), (110.0, 0.5), (164.0, 0.22)):
        f = round(f * dur) / dur
        sig += a * np.sin(2 * np.pi * f * t)
    # Schwebung
    fb = round(56.0 * dur) / dur
    sig += 0.4 * np.sin(2 * np.pi * fb * t)
    # langsames Amplituden-LFO
    lfo = 0.75 + 0.25 * np.sin(2 * np.pi * (1.0 / dur) * t)
    # leises gefiltertes Rauschen
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n)
    noise = np.convolve(noise, np.ones(220) / 220, mode="same")
    sig = sig * lfo + 0.15 * noise
    # zarter Shimmer
    sig += 0.04 * np.sin(2 * np.pi * (round(1320 * dur) / dur) * t) * lfo
    return _norm(sig, 0.05)


def _forest(dur: float, sr: int) -> np.ndarray:
    n = int(dur * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(7)
    # Wind: bandbegrenztes, langsam moduliertes Rauschen
    wind = rng.standard_normal(n)
    wind = np.convolve(wind, np.ones(400) / 400, mode="same")
    wind *= 0.6 + 0.4 * np.sin(2 * np.pi * (1.0 / dur) * t)
    # warmer Pad-Akkord (A / C# / E -> A-Dur, ganzzahlige Zyklen)
    pad = np.zeros(n)
    for f, a in ((110.0, 1.0), (138.59, 0.5), (164.81, 0.5), (220.0, 0.3)):
        f = round(f * dur) / dur
        pad += a * np.sin(2 * np.pi * f * t)
    lfo = 0.7 + 0.3 * np.sin(2 * np.pi * (2.0 / dur) * t)
    sig = 0.5 * pad * lfo + 0.5 * wind
    return _norm(sig, 0.05)


_MOODS = {"space": _space, "forest": _forest}

# Welt-Genre/-Id -> Mood
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
