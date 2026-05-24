"""Voice-mode interview that collects a world brief from the player.

The Pi voice loop calls this when the player says "Hey Jarvis" → "Ja"
→ "Neue Welt". The interview is a short Q&A loop driven by a small
``gen``-LLM-Call per turn:

    System: "You moderate a world design interview. Ask ONE concrete,
             vivid question at a time. Keep it short — the player
             hears you read it aloud."
    History: [{assistant: question1}, {user: answer1}, …]
    → Next question

The player ends the interview with a "Generieren" voice command. The
collected history is then assembled into a single dense brief that
``generate_world`` consumes (the same multi-step pipeline the admin
uses for the typed prompt).

Cost: each turn is one chat completion against the ``gen`` endpoint
(local Ollama is free; OpenAI is billed and cap-checked).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from ..config import Config
from ..oai import get_chat_client, reasoning_kwargs
from .cost import DailyCapExceeded
from .ledger import CostLedger

log = logging.getLogger("storyteller.world_design")


_SYS_DE = (
    "Du moderierst eine kurze, lebendige Welt-Gestaltung für ein "
    "interaktives Audio-Storyteller-Spiel. Der Spieler hört dich "
    "vorlesen — halte deine Fragen daher KURZ (1–2 Sätze) und stelle "
    "GENAU EINE Frage pro Runde.\n"
    "\n"
    "Sammle nach und nach die nötigen Bausteine, ohne starr durch eine "
    "Checkliste zu gehen: Genre/Setting, Spieler-Rolle, "
    "Grundstimmung/Ton (düster, hoffnungsvoll …), eine zentrale "
    "Spannung/Konfliktidee, den Ausgangsmoment der ersten Szene und "
    "evtl. 1–2 markante Personen oder Orte.\n"
    "\n"
    "Greife die Antworten des Spielers konkret auf. Frage nach Details, "
    "wenn etwas vage bleibt. Wenn schon eine Antwort sehr reich ist, "
    "schiebe nur eine vertiefende Folgefrage hinterher. Wenn dir das "
    "Gesamtbild dicht genug erscheint, kannst du den Spieler darauf "
    "hinweisen, dass er Generieren sagen kann — aber du brichst nicht "
    "selbst ab. Schreibe in einfachem, fließendem Deutsch."
)

_SYS_EN = (
    "You moderate a short, vivid world-design conversation for an "
    "interactive audio storyteller. The player HEARS you read your "
    "questions — so keep them SHORT (1–2 sentences) and ask EXACTLY "
    "ONE question per turn.\n"
    "\n"
    "Gather the building blocks gradually, not by ticking a rigid "
    "checklist: setting/genre, player role, overall tone (grim, "
    "hopeful …), a central tension or conflict, the opening moment of "
    "the first scene, maybe 1–2 striking characters or places.\n"
    "\n"
    "Build directly on the player's answers. Probe for detail when "
    "something stays vague. If an answer is already rich, follow up "
    "with one deepening question. Once the picture feels dense enough, "
    "you may remind the player that they can say Generate — but don't "
    "stop the interview yourself. Write in simple flowing English."
)

_OPENING_QUESTION_DE = (
    "Lass uns deine Welt entwerfen. Erzähl mir zuerst grob: in welchem "
    "Setting soll deine Geschichte spielen?"
)
_OPENING_QUESTION_EN = (
    "Let's design your world. To start: what kind of setting do you "
    "want your story to take place in?"
)


class WorldDesignInterview:
    """One-instance-per-design conversation. Thread-unsafe — only used
    from the single voice loop thread."""

    def __init__(self, cfg: Config, locale: str = "de"):
        self.cfg = cfg
        self.locale = locale if locale in ("de", "en") else "de"
        # Chat history in OpenAI shape, but WITHOUT the system role
        # (rebuilt per call so the latest sys-prompt always applies).
        self.history: list[dict] = []

    # ---------------- turn helpers -----------------------------------

    def opening_question(self) -> str:
        return (_OPENING_QUESTION_DE if self.locale == "de"
                else _OPENING_QUESTION_EN)

    def add_question(self, text: str) -> None:
        self.history.append({"role": "assistant",
                             "content": (text or "").strip()})

    def add_user(self, text: str) -> None:
        self.history.append({"role": "user",
                             "content": (text or "").strip()})

    def next_question(self) -> str:
        """Generate the LLM's next question given the running history.

        Cap-checked (raises DailyCapExceeded if the daily budget is hit
        BEFORE the call). On any LLM/JSON error we fall back to a generic
        "Erzähl mir mehr."-style prompt so the interview never deadlocks.
        """
        ledger = CostLedger(self.cfg)
        ledger.assert_under_cap()
        sys_prompt = _SYS_DE if self.locale == "de" else _SYS_EN
        messages = [{"role": "system", "content": sys_prompt},
                    *self.history]
        try:
            r = get_chat_client(self.cfg, "gen").chat.completions.create(
                model=self.cfg.models.gen,
                temperature=0.7,
                messages=messages,
                **reasoning_kwargs(self.cfg, "gen"),
            )
            ledger.record_chat_usage(
                role="gen", model=self.cfg.models.gen, usage=r.usage)
            text = (r.choices[0].message.content or "").strip()
        except DailyCapExceeded:
            raise
        except Exception as exc:
            log.warning("design interview LLM call failed: %r", exc)
            text = ""
        if not text:
            from ..i18n import DESIGN_PROMPTS
            text = DESIGN_PROMPTS[self.locale]["interview_fallback_question"]
        return text

    # ---------------- brief assembly ---------------------------------

    def as_brief(self) -> str:
        """Render the full chat as a single dense prompt for
        ``generate_world``. Both sides of the conversation are kept so
        the generator can see WHAT was asked, not just WHAT was
        answered."""
        if self.locale == "de":
            head = ("Welt-Brief aus dem Voice-Mode-Interview mit dem "
                    "Spieler. Nutze diese Informationen, um eine "
                    "vollständige, in sich stimmige Welt zu entwerfen:\n")
            qlabel, alabel = "Frage", "Antwort des Spielers"
        else:
            head = ("World brief from the voice-mode interview with the "
                    "player. Use this to design a complete, internally "
                    "consistent world:\n")
            qlabel, alabel = "Question", "Player answer"
        lines = [head]
        for m in self.history:
            label = qlabel if m["role"] == "assistant" else alabel
            lines.append(f"{label}: {m['content']}")
        return "\n".join(lines).strip()

    # ---------------- persistence ------------------------------------

    def save_transcript(self) -> Path:
        """Persist a JSONL transcript under
        ``data/transcripts/_world_design-<utc-ts>.jsonl``. Returns the
        written path."""
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = self.cfg.path(f"data/transcripts/_world_design-{ts}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": datetime.now(UTC).isoformat(
                        timespec="seconds"),
                    "kind": "world_design.meta",
                    "locale": self.locale,
                    "model_gen": self.cfg.models.gen,
                }, ensure_ascii=False) + "\n")
                for m in self.history:
                    f.write(json.dumps(m, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            log.warning("world-design transcript write failed: %r", exc)
        return path
