"""TTS-Provider-Abstraktion.

OpenAITTS (Default, PCM 24 kHz mono -> ideal für Reverb) implementiert;
LocalTTS = Phase 10 (Pi 5 + AI HAT). Hinweis: Whisper kann KEIN TTS.
Auswahl über config.tts.provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..config import Config
from ..oai import get_client

OPENAI_TTS_SR = 24000  # response_format="pcm" => 24 kHz, s16le, mono


class TTS(ABC):
    @abstractmethod
    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        """Liefert (float32 mono [-1,1], sample_rate)."""
        ...


class OpenAITTS(TTS):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        client = get_client(self.cfg)
        voice = self.cfg.models.tts_voice
        buf = bytearray()
        kw = dict(
            model=self.cfg.models.tts,
            voice=voice,
            input=text,
            response_format="pcm",
        )
        if instructions:
            kw["instructions"] = instructions
        with client.audio.speech.with_streaming_response.create(**kw) as resp:
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
        pcm = np.frombuffer(bytes(buf), dtype="<i2").astype(np.float32) / 32768.0
        return pcm, OPENAI_TTS_SR


class LocalTTS(TTS):
    """Phase 10 (optional): lokales TTS — NUR Pi 5 + AI HAT."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        raise NotImplementedError("Phase 10: lokales TTS (Pi 5 + AI HAT).")


def get_tts(cfg: Config) -> TTS:
    return {"openai": OpenAITTS, "local": LocalTTS}[cfg.tts.provider](cfg)
