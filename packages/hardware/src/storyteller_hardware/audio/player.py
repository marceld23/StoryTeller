"""Playback through the (volume-safe) audio backend.

TTS PCM -> optional reverb -> temp WAV -> backend.play_wav.
On the Pi this respects the ALSA softvol volume; on PC it is software gain.
Streaming optimization later behind the same interface.
"""

from __future__ import annotations

import tempfile
import threading

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
