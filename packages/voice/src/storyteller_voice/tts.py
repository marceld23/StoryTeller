"""TTS provider abstraction.

OpenAITTS (default, PCM 24 kHz mono -> ideal for reverb) implemented;
LocalTTS = Phase 10 (Pi 5 + AI HAT). Note: Whisper is NOT TTS.
Selected via config.tts.provider.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np
from storyteller_core.config import Config
from storyteller_core.oai import get_tts_client

log = logging.getLogger("storyteller.tts")

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
        client = get_tts_client(self.cfg)
        log.info("TTS: model=%s voice=%s endpoint=%s", self.cfg.models.tts,
                 self.cfg.models.tts_voice,
                 self.cfg.models.tts_endpoint.base_url or "OpenAI")
        voice = self.cfg.models.tts_voice
        buf = bytearray()
        # WAV is self-describing (carries the real sample rate + channels), so
        # it works across servers — OpenAI returns 24 kHz mono, but others
        # (e.g. kokoro) may use a different rate or stereo PCM. Decoding raw
        # "pcm" with a fixed 24 kHz mono assumption garbles those.
        kw = dict(
            model=self.cfg.models.tts,
            voice=voice,
            input=text,
            response_format="wav",
        )
        if instructions:
            kw["instructions"] = instructions
        with client.audio.speech.with_streaming_response.create(**kw) as resp:
            for chunk in resp.iter_bytes():
                buf.extend(chunk)
        import io

        import soundfile as sf

        data, sr = sf.read(io.BytesIO(bytes(buf)), dtype="float32",
                           always_2d=False)
        if getattr(data, "ndim", 1) > 1:        # downmix to mono
            data = data.mean(axis=1)
        return np.ascontiguousarray(data, dtype=np.float32), int(sr)


class LocalTTS(TTS):
    """Phase 10 (optional): lokales TTS — NUR Pi 5 + AI HAT."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        raise NotImplementedError("Phase 10: lokales TTS (Pi 5 + AI HAT).")


def get_tts(cfg: Config) -> TTS:
    return {"openai": OpenAITTS, "local": LocalTTS}[cfg.tts.provider](cfg)
