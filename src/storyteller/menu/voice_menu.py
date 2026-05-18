"""Voice-controlled system menu.

Uses the locale voice-prompt cache (no TTS tokens for fixed prompts) and STT
for the player's input. World selection is done by the LLM (robust, natural —
e.g. "something in space" -> starfaring); keyword matching + a default are
only fallbacks if the LLM is unavailable.
Returns: {action: 'play'|'load', world_id, save_name}.
"""

from __future__ import annotations

import json
import tempfile

from ..config import Config
from ..i18n import norm, world_keywords


def _match_keyword(text: str, keywords: dict[str, list[str]]) -> str | None:
    t = text.lower()
    for wid, kws in keywords.items():
        if any(k in t for k in kws):
            return wid
    return None


class VoiceMenu:
    def __init__(self, cfg: Config, backend, prompts, stt, leds=None,
                 ww=None, speak: bool = True):
        self.cfg = cfg
        self.backend = backend
        self.prompts = prompts
        self.stt = stt
        self.leds = leds
        self.ww = ww          # optional WakeWord (gate the menu like the loop)
        self.speak = speak
        self.locale = norm(cfg.general.locale)
        self.keywords = world_keywords(self.locale)
        self._load_kw = (("laden", "spielstand") if self.locale == "de"
                         else ("load", "save game", "saved game"))

    # --- world catalog (id, name, genre, short description) ---
    def _worlds(self) -> list[dict]:
        from ..worlds.registry import all_world_ids, load_world

        out = []
        for wid in all_world_ids(self.cfg):
            try:
                w = load_world(self.cfg, wid)
                out.append({"id": w.id, "name": w.name, "genre": w.genre,
                            "desc": (w.description or "")[:160]})
            except Exception:
                continue
        return out

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

    # --- LLM intent classification ---
    def _classify_llm(self, said: str, worlds: list[dict]) -> str:
        """Returns a world id, 'load', or 'unknown'. Fails soft -> 'unknown'."""
        try:
            from ..oai import get_client

            ids = [w["id"] for w in worlds]
            catalog = "\n".join(
                f'- id="{w["id"]}" name="{w["name"]}" genre="{w["genre"]}": '
                f'{w["desc"]}' for w in worlds)
            sys = (
                "Map the user's spoken menu choice to exactly one option. "
                "Options are the world ids below, or 'load' (resume a saved "
                "game), or 'unknown' if unclear. Consider meaning, not exact "
                "words (e.g. 'something in space' -> the sci-fi world). "
                f"Answer JSON only: {{\"choice\": \"<one of: "
                f"{', '.join(ids)}, load, unknown>\"}}\n\nWORLDS:\n{catalog}")
            r = get_client(self.cfg).chat.completions.create(
                model=self.cfg.models.story_llm,
                messages=[{"role": "system", "content": sys},
                          {"role": "user", "content": said}],
                response_format={"type": "json_object"},
            )
            choice = json.loads(r.choices[0].message.content or "{}") \
                .get("choice", "unknown").strip()
            if choice in ids or choice in ("load", "unknown"):
                return choice
        except Exception:
            pass
        return "unknown"

    def run(self) -> dict:
        worlds = self._worlds()
        self.prompts.play("welcome", self.backend)
        active = True  # first listen is active (like other steps); only
        for _ in range(6):  # after no answer do we gate on the wake word
            self.prompts.play("choose_world", self.backend)
            if self.ww is not None and not active:
                if self.speak:
                    self.prompts.play("wake_hint", self.backend)
                if self.leds:
                    self.leds.idle()
                if not self.ww.listen_blocking():
                    import time
                    time.sleep(2)
                    continue
            said = self._ask()
            active = False  # next round requires the wake word
            if not said.strip():
                # silence: no "not understood" — wake word next round
                continue

            choice = self._classify_llm(said, worlds)
            if choice == "unknown":  # fallback: keyword, then load-keyword
                low = said.lower()
                if any(k in low for k in self._load_kw):
                    choice = "load"
                else:
                    choice = _match_keyword(said, self.keywords) or "unknown"

            if choice == "load":
                return {"action": "load", "world_id": None,
                        "save_name": None}
            if choice != "unknown":
                self.prompts.play(f"world_{choice}", self.backend)
                self.prompts.play("starting", self.backend)
                return {"action": "play", "world_id": choice,
                        "save_name": None}
            self.prompts.play("not_understood", self.backend)

        default = worlds[0]["id"] if worlds else "sternenfahrt"
        return {"action": "play", "world_id": default, "save_name": None}
