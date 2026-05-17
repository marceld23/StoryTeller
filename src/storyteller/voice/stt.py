"""STT-Provider-Abstraktion.

OpenAISTT (Default) implementiert; LocalWhisperSTT = Phase 10 (Pi 5 + AI HAT).
Auswahl über config.stt.provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import Config
from ..oai import get_client


class STT(ABC):
    @abstractmethod
    def transcribe(self, wav_path: str) -> str: ...


class OpenAISTT(STT):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def transcribe(self, wav_path: str) -> str:
        client = get_client(self.cfg)
        with open(wav_path, "rb") as f:
            r = client.audio.transcriptions.create(
                model=self.cfg.models.stt,
                file=f,
                language=self.cfg.stt.language,
            )
        return (r.text or "").strip()


class LocalWhisperSTT(STT):
    """Phase 10 (optional): lokales Whisper — NUR Pi 5 + AI HAT."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def transcribe(self, wav_path: str) -> str:
        raise NotImplementedError("Phase 10: lokales Whisper (Pi 5 + AI HAT).")


def get_stt(cfg: Config) -> STT:
    return {"openai": OpenAISTT, "local_whisper": LocalWhisperSTT}[
        cfg.stt.provider
    ](cfg)
