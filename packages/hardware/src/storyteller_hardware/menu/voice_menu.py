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

from storyteller_core.config import Config
from storyteller_core.i18n import norm, world_keywords


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
        self._menu_wav: str | None = None  # cached dynamic world-list audio
        self._load_kw = (("laden", "spielstand") if self.locale == "de"
                         else ("load", "save game", "saved game"))

    # --- world catalog (id, name, display_name, genre, short description) ---
    def _worlds(self) -> list[dict]:
        from storyteller_core.worlds.registry import all_world_ids, load_world

        out = []
        for wid in all_world_ids(self.cfg):
            try:
                w = load_world(self.cfg, wid)
                # `display_name` is the short, easy-to-pronounce form used in
                # the spoken menu (and what the player would actually say);
                # `name` is the full prose title for the LLM classifier.
                disp = (getattr(w, "display_name", "") or w.name).strip()
                out.append({"id": w.id, "name": w.name, "display_name": disp,
                            "genre": w.genre,
                            "desc": (w.description or "")[:160]})
            except Exception:
                continue
        return out

    def _play_choose(self, worlds: list[dict]) -> None:
        """Announce the available worlds by short name (synthesised once).
        Falls back to the static cached prompt if TTS is unavailable."""
        if self._menu_wav is None:
            names = ", ".join(w["display_name"] for w in worlds)
            text = (f"Welche Welt möchtest du spielen? Verfügbar sind: {names}."
                    if self.locale == "de"
                    else f"Which world would you like to play? Available: {names}.")
            try:
                import tempfile

                import numpy as np
                import soundfile as sf
                from storyteller_voice.tts import get_tts

                audio, sr = get_tts(self.cfg).synthesize(text)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
                    path = t.name
                sf.write(path, np.clip(audio, -1, 1).astype(np.float32), sr,
                         subtype="PCM_16")
                self._menu_wav = path
            except Exception:
                self._menu_wav = ""  # cache failure -> static fallback
        if self._menu_wav:
            self.backend.play_wav(self._menu_wav)
        else:
            self.prompts.play("choose_world", self.backend)

    def _ask(self, seconds: float = 4.0) -> str:
        if self.leds:
            self.leds.listen()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
            path = t.name
        self.backend.record_until_silence(path)
        try:
            return self.stt.transcribe(path)
        except Exception:
            return ""

    # --- LLM intent classification ---
    def _classify_llm(self, said: str, worlds: list[dict]) -> str:
        """Returns a world id, 'load', or 'unknown'. Fails soft -> 'unknown'."""
        try:
            from storyteller_core.oai import chat_extras, get_chat_client

            ids = [w["id"] for w in worlds]
            catalog = "\n".join(
                f'- id="{w["id"]}" name="{w["name"]}" '
                f'short="{w["display_name"]}" genre="{w["genre"]}": '
                f'{w["desc"]}' for w in worlds)
            sys = (
                "Map the user's spoken menu choice to exactly one option. "
                "Options are the world ids below, or 'load' (resume a saved "
                "game), or 'unknown' if unclear. Consider meaning AND "
                "pronunciation variants — the player may say the short name, "
                "the full name, a fuzzy phonetic version, or describe the "
                "genre (e.g. 'something in space' -> the sci-fi world; "
                "'Aquatika' -> a world with short name 'Aquatica'). "
                f"Answer JSON only: {{\"choice\": \"<one of: "
                f"{', '.join(ids)}, load, unknown>\"}}\n\nWORLDS:\n{catalog}")
            r = get_chat_client(self.cfg, "story").chat.completions.create(
                model=self.cfg.models.story_llm,
                messages=[{"role": "system", "content": sys},
                          {"role": "user", "content": said}],
                response_format={"type": "json_object"},
                **chat_extras(self.cfg, "story"),
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
        # At the start we LISTEN twice (ask, listen; if silent, ask + listen
        # again) before falling back to the wake-word gate + hint. So the
        # player isn't told "I'm no longer listening" after a single miss.
        active_listens = 2
        for _ in range(6):
            if self.ww is not None and active_listens <= 0:
                # No active listening left: play the wake hint and gate on the
                # wake word. Do NOT re-prompt "choose_world" here (that caused
                # an extra "which world?" right before the hint). After the
                # wake word fires we prompt + listen below.
                if self.speak:
                    self.prompts.play("wake_hint", self.backend)
                if self.leds:
                    self.leds.idle()
                if not self.ww.listen_blocking():
                    import time
                    time.sleep(2)
                    continue
            # Prompt + listen: for the active rounds, and again right after
            # the wake word wakes us. Announces all available worlds.
            self._play_choose(worlds)
            said = self._ask()
            if active_listens > 0:
                active_listens -= 1
            if not said.strip():
                # silence: no "not understood" — listen again, then wake word
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
