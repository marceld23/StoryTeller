"""Voice-Prompt-Cache: feste Ansagen einmalig via TTS rendern, dann ohne API
abspielen (spart Tokens + Latenz). Pro Locale getrennt:
data/voice_prompts/<locale>/*.wav (+ manifest.json).
"""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf

from ..config import Config
from ..i18n import VOICE_PROMPTS, norm


class VoicePromptCache:
    def __init__(self, cfg: Config, locale: str | None = None):
        self.cfg = cfg
        self.locale = norm(locale or cfg.general.locale)
        self.prompts = VOICE_PROMPTS[self.locale]
        self.dir = cfg.path(cfg.paths.voice_prompts_dir) / self.locale
        self.dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self.dir / "manifest.json"

    def _voice(self) -> str:
        return self.cfg.voice_prompts.voice or self.cfg.models.tts_voice

    def _wav(self, pid: str):
        return self.dir / f"{pid}.wav"

    def _stale(self) -> bool:
        if not self._manifest.exists():
            return True
        try:
            m = json.loads(self._manifest.read_text())
        except Exception:
            return True
        return (m.get("voice") != self._voice()
                or m.get("model") != self.cfg.models.tts
                or m.get("texts") != self.prompts)

    def build(self, force: bool = False) -> list[str]:
        """Rendert fehlende (oder bei force/Änderung alle) Ansagen via TTS."""
        from .tts import get_tts

        rebuild = force or self._stale()
        tts = get_tts(self.cfg)
        built: list[str] = []
        for pid, text in self.prompts.items():
            wav = self._wav(pid)
            if wav.exists() and not rebuild:
                continue
            audio, sr = tts.synthesize(text)
            sf.write(str(wav), np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
            built.append(pid)
        self._manifest.write_text(json.dumps(
            {"locale": self.locale, "voice": self._voice(),
             "model": self.cfg.models.tts, "texts": self.prompts},
            ensure_ascii=False, indent=2))
        return built

    def play(self, pid: str, backend) -> None:
        wav = self._wav(pid)
        if not wav.exists():
            if not self.cfg.voice_prompts.allow_live_fallback:
                return
            from .tts import get_tts

            audio, sr = get_tts(self.cfg).synthesize(self.prompts.get(pid, ""))
            sf.write(str(wav), np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
        backend.play_wav(str(wav))
