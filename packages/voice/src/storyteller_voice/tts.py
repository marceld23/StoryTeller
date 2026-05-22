"""TTS provider abstraction.

OpenAITTS (default, OpenAI-compatible HTTP — incl. self-hosted kokoro);
WyomingTTS (Wyoming/TCP, e.g. a Piper server — NOT HTTP);
LocalTTS = Phase 10 (Pi 5 + AI HAT). Note: Whisper is NOT TTS.
Selected via config.tts.provider, or auto-detected from the tts endpoint
scheme (tcp://|wyoming:// -> Wyoming).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from urllib.parse import urlparse

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
        # `instructions` (style steering) is an OpenAI gpt-4o-mini-tts feature.
        # Self-hosted servers (Piper, kokoro, …) don't know it and may reject
        # unknown fields, so only send it on the default OpenAI endpoint.
        if instructions and not self.cfg.models.tts_endpoint.base_url:
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


class WyomingTTS(TTS):
    """TTS over the Wyoming protocol (raw TCP, not HTTP/OpenAI).

    A Wyoming voice server (e.g. Piper) is configured via the tts endpoint as
    ``tcp://host:port`` (or ``wyoming://host:port``). ``models.tts_voice`` (or
    ``models.tts``) selects the voice, e.g. ``de_DE-thorsten-high``. Piper
    returns 16-bit mono PCM, sample rate announced in the AudioStart event.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        u = urlparse(cfg.models.tts_endpoint.base_url)
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 10200

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        import asyncio

        voice = self.cfg.models.tts_voice or self.cfg.models.tts
        log.info("TTS: wyoming voice=%s endpoint=tcp://%s:%d",
                 voice, self.host, self.port)
        pcm, rate = asyncio.run(self._synthesize(text, voice))
        if not pcm:
            return np.zeros(0, dtype=np.float32), rate
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        return np.ascontiguousarray(audio, dtype=np.float32), rate

    async def _synthesize(self, text: str, voice: str) -> tuple[bytes, int]:
        from wyoming.audio import AudioChunk, AudioStop
        from wyoming.client import AsyncTcpClient
        from wyoming.tts import Synthesize, SynthesizeVoice

        buf = bytearray()
        rate = 22050
        async with AsyncTcpClient(self.host, self.port) as client:
            syn = Synthesize(text=text)
            if voice:
                syn.voice = SynthesizeVoice(name=voice)
            await client.write_event(syn.event())
            while True:
                event = await client.read_event()
                if event is None:
                    break
                if AudioChunk.is_type(event.type):
                    chunk = AudioChunk.from_event(event)
                    rate = chunk.rate or rate
                    buf.extend(chunk.audio)
                elif AudioStop.is_type(event.type):
                    break
        return bytes(buf), rate


class LocalTTS(TTS):
    """Phase 10 (optional): lokales TTS — NUR Pi 5 + AI HAT."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def synthesize(self, text: str, instructions: str = "") -> tuple[np.ndarray, int]:
        raise NotImplementedError("Phase 10: lokales TTS (Pi 5 + AI HAT).")


def get_tts(cfg: Config) -> TTS:
    # Auto-detect Wyoming from the endpoint scheme so it's admin-configurable
    # and hot-reloaded; OpenAI stays the default for everything else.
    ep = cfg.models.tts_endpoint.base_url or ""
    if cfg.tts.provider == "wyoming" or ep.startswith(("tcp://", "wyoming://")):
        return WyomingTTS(cfg)
    return {"openai": OpenAITTS, "local": LocalTTS}.get(
        cfg.tts.provider, OpenAITTS)(cfg)
