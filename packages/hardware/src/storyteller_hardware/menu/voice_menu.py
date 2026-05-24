"""Voice-controlled system menu.

Uses the locale voice-prompt cache (no TTS tokens for fixed prompts) and STT
for the player's input. World selection is done by the LLM (robust, natural —
e.g. "something in space" -> starfaring); keyword matching + a default are
only fallbacks if the LLM is unavailable.
Returns: {action: 'play'|'load', world_id, save_name}.
"""

from __future__ import annotations

import json
import logging
import tempfile

from storyteller_core.config import Config
from storyteller_core.i18n import norm, world_keywords

log = logging.getLogger("storyteller.voice_menu")


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

    def _play_world_pick(self, world_id: str, worlds: list[dict]) -> None:
        """Confirm the player's pick aloud. Uses the baked `world_<id>`
        voice prompt if available, otherwise live-synthesises a short
        "Du wählst {display_name}" line so runtime-generated worlds also
        get spoken confirmation. Any TTS failure is swallowed — the
        subsequent "starting" prompt is the load-bearing announcement."""
        pid = f"world_{world_id}"
        if pid in self.prompts.prompts:
            self.prompts.play(pid, self.backend)
            return
        disp = next((w["display_name"] for w in worlds
                     if w["id"] == world_id), world_id)
        text = (f"Du wählst {disp}." if self.locale == "de"
                else f"You picked {disp}.")
        try:
            import numpy as np
            import soundfile as sf
            from storyteller_voice.tts import get_tts

            audio, sr = get_tts(self.cfg).synthesize(text)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as t:
                path = t.name
            sf.write(path, np.clip(audio, -1, 1).astype(np.float32), sr,
                     subtype="PCM_16")
            self.backend.play_wav(path)
        except Exception as exc:
            log.warning("live world-pick TTS failed: %r", exc)

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
            said = self.stt.transcribe(path) or ""
        except Exception as exc:
            log.warning("STT failed in voice menu: %r", exc)
            said = ""
        # Surface the transcript in the journal so a misclassified menu
        # answer can be debugged from logs (otherwise we only see the
        # final "Welt: …" line and have no idea what the player said).
        if said.strip():
            log.info("[Menu/Du] %s", said.strip())
        else:
            log.info("[Menu/Du] (Stille)")
        return said

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
            # NAME-FIRST: prior wording was too genre-friendly and could
            # pick a popular sci-fi world when the player clearly named a
            # different one ("Justus Scify" -> "Sternenfahrt"). Now: match
            # the spoken phrase against id / name / short / phonetic
            # variants first; genre is only the last resort when nothing
            # else fits.
            sys = (
                "Map the user's spoken menu choice to exactly one option.\n"
                "Options are: the world ids below, 'load' (resume a saved "
                "game), or 'unknown'.\n\n"
                "MATCHING RULES (strict order — stop at the first that "
                "fires):\n"
                "1. NAME MATCH: if the user's phrase clearly contains the "
                "short name, the full name, the id (with spaces/hyphens "
                "ignored), or a recognisable phonetic variant of any "
                "world, return THAT world's id. Treat STT artefacts "
                "liberally (Justus / Justice / Jüstus, Scify / Sci-Fi / "
                "Sai-Fai, Sternenfahrt / Sternfahrt are all valid "
                "matches if they refer to one of the listed worlds).\n"
                "2. LOAD: if the user wants to resume / load / continue / "
                "weiter / spielstand a saved game, return 'load'.\n"
                "3. GENRE FALLBACK: only if NO name match plausibly "
                "applies, and the user clearly described a genre or "
                "vibe ('something in space', 'eine Fantasy-Welt'), pick "
                "the best-matching world by genre.\n"
                "4. Otherwise return 'unknown'.\n\n"
                "Do NOT prefer a popular genre over an explicit name. "
                "If the user said a name, the matching world wins even "
                "if another world has a more dominant genre.\n\n"
                f"Answer JSON only: {{\"choice\": \"<one of: "
                f"{', '.join(ids)}, load, unknown>\"}}\n\n"
                f"WORLDS:\n{catalog}")
            r = get_chat_client(self.cfg, "story").chat.completions.create(
                model=self.cfg.models.story_llm,
                messages=[{"role": "system", "content": sys},
                          {"role": "user", "content": said}],
                response_format={"type": "json_object"},
                **chat_extras(self.cfg, "story"),
            )
            choice = json.loads(r.choices[0].message.content or "{}") \
                .get("choice", "unknown").strip()
            log.info("[Menu/LLM] said=%r -> choice=%r", said, choice)
            if choice in ids or choice in ("load", "unknown"):
                return choice
        except Exception as exc:
            log.warning("classify_llm failed: %r", exc)
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
                # Per-world prompt is only baked for the canonical demo
                # worlds. For worlds the admin generated at runtime (no
                # `world_<id>` in the voice-prompts cache) synthesise a
                # short confirmation live so the player hears the name
                # they picked. Falls through to the generic "starting"
                # prompt either way.
                self._play_world_pick(choice, worlds)
                self.prompts.play("starting", self.backend)
                return {"action": "play", "world_id": choice,
                        "save_name": None}
            self.prompts.play("not_understood", self.backend)

        default = worlds[0]["id"] if worlds else "sternenfahrt"
        return {"action": "play", "world_id": default, "save_name": None}
