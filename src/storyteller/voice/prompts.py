"""Voice-Prompt-Cache: feste Ansagen einmalig via TTS rendern, dann ohne API
abspielen (spart Tokens + Latenz). Cache neu bauen bei Stimm-/Textänderung.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from ..config import Config

# Fester Ansagen-Katalog (Inhalt = Daten, wie die Seed-Welten).
PROMPTS: dict[str, str] = {
    "welcome": "Willkommen beim Geschichtenerzähler.",
    "choose_world": "Welche Welt möchtest du spielen? Sage Sternenfahrt für "
                    "Science-Fiction, oder Immerwald für Fantasy.",
    "world_sternenfahrt": "Sternenfahrt. Du bist Raumschiffkapitän.",
    "world_immerwald": "Das Immerwald-Reich. Du bist Waldläufer.",
    "menu_hint": "Du kannst sagen: neue Geschichte, Spielstand laden, "
                 "oder Geschichte speichern.",
    "not_understood": "Das habe ich nicht verstanden. Bitte wiederhole es.",
    "listening": "Ich höre.",
    "starting": "Die Geschichte beginnt.",
    "saved": "Die Geschichte wurde gespeichert.",
    "no_saves": "Es gibt keine gespeicherten Spielstände.",
    "goodbye": "Bis zum nächsten Mal.",
    "error_retry": "Es gab gerade eine Störung. Sag es bitte noch einmal.",
}


class VoicePromptCache:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dir = cfg.path(cfg.paths.voice_prompts_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._manifest = self.dir / "manifest.json"

    def _voice(self) -> str:
        return self.cfg.voice_prompts.voice or self.cfg.models.tts_voice

    def _wav(self, pid: str) -> Path:
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
                or m.get("texts") != PROMPTS)

    def build(self, force: bool = False) -> list[str]:
        """Rendert fehlende (oder bei force/Änderung alle) Ansagen via TTS."""
        from .tts import get_tts

        rebuild = force or self._stale()
        tts = get_tts(self.cfg)
        built: list[str] = []
        for pid, text in PROMPTS.items():
            wav = self._wav(pid)
            if wav.exists() and not rebuild:
                continue
            audio, sr = tts.synthesize(text)
            sf.write(str(wav), np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
            built.append(pid)
        self._manifest.write_text(json.dumps(
            {"voice": self._voice(), "model": self.cfg.models.tts,
             "texts": PROMPTS}, ensure_ascii=False, indent=2))
        return built

    def play(self, pid: str, backend) -> None:
        wav = self._wav(pid)
        if not wav.exists():
            if not self.cfg.voice_prompts.allow_live_fallback:
                return
            from .tts import get_tts

            audio, sr = get_tts(self.cfg).synthesize(PROMPTS.get(pid, ""))
            sf.write(str(wav), np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
        backend.play_wav(str(wav))
