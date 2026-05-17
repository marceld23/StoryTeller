"""Sprachgesteuertes Systemmenü.

Nutzt den Voice-Prompt-Cache (keine TTS-Tokens für feste Ansagen), STT für
die Spieler-Eingabe und einfaches Keyword-Matching. Liefert eine Auswahl:
{action: 'play'|'load'|'quit', world_id, save_name}.
"""

from __future__ import annotations

import json
import tempfile

from ..config import Config

WORLD_KEYWORDS = {
    "sternenfahrt": ["sternenfahrt", "scifi", "science", "raumschiff", "weltraum",
                     "kapitän", "all"],
    "immerwald": ["immerwald", "fantasy", "wald", "waldläufer", "magie", "epos"],
}


def _match_world(text: str) -> str | None:
    t = text.lower()
    for wid, kws in WORLD_KEYWORDS.items():
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
            wid = _match_world(said)
            if "laden" in said.lower() or "spielstand" in said.lower():
                return {"action": "load", "world_id": None, "save_name": None}
            if wid:
                self.prompts.play(f"world_{wid}", self.backend)
                self.prompts.play("starting", self.backend)
                return {"action": "play", "world_id": wid, "save_name": None}
            self.prompts.play("not_understood", self.backend)
        return {"action": "play", "world_id": "sternenfahrt", "save_name": None}
