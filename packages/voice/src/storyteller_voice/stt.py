"""STT provider abstraction.

OpenAISTT (default) implemented; LocalWhisperSTT = Phase 10 (Pi 5 + AI HAT).
Selected via config.stt.provider. Language follows the locale.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from storyteller_core.config import Config
from storyteller_core.oai import get_stt_client

log = logging.getLogger("storyteller.stt")


class STT(ABC):
    @abstractmethod
    def transcribe(self, wav_path: str) -> str: ...


class OpenAISTT(STT):
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def transcribe(self, wav_path: str) -> str:
        from storyteller_core.i18n import norm

        client = get_stt_client(self.cfg)
        log.info("STT: model=%s endpoint=%s", self.cfg.models.stt,
                 self.cfg.models.stt_endpoint.base_url or "OpenAI")
        # STT-Sprache folgt der Locale (de/en); überschreibt stt.language.
        lang = norm(self.cfg.general.locale)
        with open(wav_path, "rb") as f:
            r = client.audio.transcriptions.create(
                model=self.cfg.models.stt,
                file=f,
                language=lang,
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
