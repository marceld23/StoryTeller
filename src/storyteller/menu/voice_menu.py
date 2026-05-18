"""Voice-controlled system menu.

Uses the locale voice-prompt cache (no TTS tokens for fixed prompts), STT for
the player's input and simple keyword matching. Returns a selection:
{action: 'play'|'load'|'quit', world_id, save_name}.
"""

from __future__ import annotations

import tempfile

from ..config import Config
from ..i18n import norm, world_keywords


def _match_world(text: str, keywords: dict[str, list[str]]) -> str | None:
    t = text.lower()
    for wid, kws in keywords.items():
        if any(k in t for k in kws):
            return wid
    return None


class VoiceMenu:
    def __init__(self, cfg: Config, backend, prompts, stt, leds=None):
        self.cfg = cfg
        self.backend = backend
        self.prompts = prompts
        self.stt = stt
        self.leds = leds
        self.locale = norm(cfg.general.locale)
        self.keywords = world_keywords(self.locale)
        # locale-spezifische "laden"-Trigger
        self._load_kw = (("laden", "spielstand") if self.locale == "de"
                         else ("load", "save game", "saved game"))

    def _ask(self, seconds: float = 4.0) -> str:
        if self.leds:
            self.leds.listen()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            path = t.name
        self.backend.record_wav(path, seconds)
        try:
            return self.stt.transcribe(path)
        except Exception:
            return ""

    def run(self) -> dict:
        self.prompts.play("welcome", self.backend)
        for _ in range(3):
            self.prompts.play("choose_world", self.backend)
            said = self._ask()
            low = said.lower()
            if any(k in low for k in self._load_kw):
                return {"action": "load", "world_id": None,
                        "save_name": None}
            wid = _match_world(said, self.keywords)
            if wid:
                self.prompts.play(f"world_{wid}", self.backend)
                self.prompts.play("starting", self.backend)
                return {"action": "play", "world_id": wid,
                        "save_name": None}
            self.prompts.play("not_understood", self.backend)
        return {"action": "play", "world_id": "sternenfahrt",
                "save_name": None}
