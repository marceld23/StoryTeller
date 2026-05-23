"""Playback through the (volume-safe) audio backend.

TTS PCM -> optional reverb -> temp WAV -> backend.play_wav.
On the Pi this respects the ALSA softvol volume; on PC it is software gain.

Two paths:
- `play_array(backend, audio, sr, stop=...)` — one-shot, the legacy path.
- `play_stream(backend, chunks, fx=…, stop=…)` — consumes a generator of
  `(audio, sr)` chunks and plays them in order as each becomes ready.
  Lets the player start the first chunk while later ones are still being
  synthesised (latency masking).
"""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Iterable

import numpy as np
import soundfile as sf

from .backend import AudioBackend


def play_array(backend: AudioBackend, audio: np.ndarray, sample_rate: int,
               stop: threading.Event | None = None) -> None:
    """Play a float32 mono array. If `stop` is given, playback aborts as soon
    as the event is set (barge-in / button interrupt)."""
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    sf.write(path, audio, sample_rate, subtype="PCM_16")
    if stop is not None:
        backend.play_wav_interruptible(path, stop)
    else:
        backend.play_wav(path)


def play_stream(
    backend: AudioBackend,
    chunks: Iterable[tuple[np.ndarray, int]],
    fx=None,                                  # VoiceFX | None
    stop: threading.Event | None = None,
) -> None:
    """Play an iterator of `(audio, sr)` chunks sequentially. The chunks are
    consumed lazily, so a streaming TTS producer can keep working while the
    earlier chunks play. FX (if given) is applied per chunk — reverb tails
    cannot bleed across chunks, which is the price for low first-audio
    latency.

    Stops cleanly as soon as `stop` is set (between or during chunks)."""
    for audio, sr in chunks:
        if stop is not None and stop.is_set():
            return
        if fx is not None:
            audio = fx.process(audio, sr)
        if audio is None or len(audio) == 0:
            continue
        play_array(backend, audio, sr, stop=stop)
