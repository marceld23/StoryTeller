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
        from storyteller_core.health import HealthRegistry, wrap
        from storyteller_core.i18n import norm

        client = get_stt_client(self.cfg)
        base = self.cfg.models.stt_endpoint.base_url or ""
        log.info("STT: model=%s endpoint=%s", self.cfg.models.stt,
                 base or "OpenAI")
        # STT language follows the locale (de/en); overrides stt.language.
        lang = norm(self.cfg.general.locale)
        try:
            with open(wav_path, "rb") as f:
                r = client.audio.transcriptions.create(
                    model=self.cfg.models.stt,
                    file=f,
                    language=lang,
                )
        except Exception as exc:
            err = wrap("stt", base_url=base,
                       model=self.cfg.models.stt)(exc)
            HealthRegistry.get(self.cfg).record_error(err)
            raise err from exc
        HealthRegistry.get(self.cfg).record_ok(
            "stt", base_url=base, model=self.cfg.models.stt)
        return (r.text or "").strip()


class LocalWhisperSTT(STT):
    """Phase 10 (optional): local Whisper — Pi 5 + AI HAT ONLY."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def transcribe(self, wav_path: str) -> str:
        raise NotImplementedError("Phase 10: lokales Whisper (Pi 5 + AI HAT).")


class _TrackingSTT(STT):
    """Wraps a real STT backend; logs audio-seconds to the cost ledger
    after each transcription. Local endpoints (faster-whisper / local
    Whisper) end up at usd=0 and are skipped by the ledger."""

    def __init__(self, inner: STT, cfg: Config):
        self.inner = inner
        self.cfg = cfg

    def transcribe(self, wav_path: str) -> str:
        text = self.inner.transcribe(wav_path)
        self._log(wav_path)
        return text

    def _log(self, wav_path: str) -> None:
        try:
            from storyteller_core.story.cost import is_local_role
            from storyteller_core.story.ledger import CostLedger
            if is_local_role(self.cfg, "stt"):
                return
            import wave
            with wave.open(wav_path, "rb") as w:
                seconds = w.getnframes() / float(w.getframerate() or 1)
            usd = seconds / 60.0 * self.cfg.cost.usd_per_minute_stt
            CostLedger(self.cfg).record(
                kind="stt", usd=usd, model=self.cfg.models.stt,
                stt_sec=float(seconds))
        except Exception:
            pass


def get_stt(cfg: Config) -> STT:
    inner = {"openai": OpenAISTT, "local_whisper": LocalWhisperSTT}[
        cfg.stt.provider
    ](cfg)
    return _TrackingSTT(inner, cfg)
