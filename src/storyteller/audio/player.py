"""Wiedergabe über das (lautstärke-sichere) Audio-Backend.

TTS-PCM -> optional Reverb -> temporäre WAV -> backend.play_wav
(aplay durch `plug:respeaker_softvol`, respektiert die softvol-Lautstärke).
Streaming-Optimierung später hinter gleicher Schnittstelle.
"""

from __future__ import annotations

import tempfile

import numpy as np
import soundfile as sf

from .backend import AudioBackend


def play_array(backend: AudioBackend, audio: np.ndarray, sample_rate: int) -> None:
    audio = np.clip(audio, -1.0, 1.0).astype(np.float32)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        path = tmp.name
    sf.write(path, audio, sample_rate, subtype="PCM_16")
    backend.play_wav(path)
