"""Narration gate ("curator"): a per-turn LLM call that picks which
pre-authored plot reveals the narrator MAY use this turn, and which
authored topics must stay hidden.

This is a *guardrail against premature spoilers* — NOT a creative cage.
The narrator stays free to react to the player, to improvise, and to
invent harmless new details. Only AUTHORED material (world fragments,
history events, glossary specifics, substory resolution, future beats)
is curated.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from ..config import Config
from ..i18n import GATE_SYS, norm
from ..oai import chat_extras, get_chat_client

log = logging.getLogger("storyteller.curator")


class NarrationGate(BaseModel):
    scene_intent: str = ""
    permitted_reveals: list[str] = Field(default_factory=list)
    forbidden_topics: list[str] = Field(default_factory=list)
    tone_nudge: str = ""


def _truncate(items: list[str], n: int) -> list[str]:
    return [s.strip() for s in items if isinstance(s, str) and s.strip()][:n]


class Curator:
    """One small LLM call per turn — decides what's allowed to be revealed.

    Failure-tolerant: any error returns an empty `NarrationGate`, which the
    narrator treats as "no extra restrictions, no permitted reveals" —
    matches the algorithmic-only Phase-1 behaviour.
    """

    def __init__(self, cfg: Config, cost=None, *, ledger=None,
                 thread_id: str | None = None, world_id: str | None = None):
        self.cfg = cfg
        self.cost = cost
        self.ledger = ledger
        self.thread_id = thread_id
        self.world_id = world_id

    def gate(
        self,
        world,
        substory_dict: dict | None,
        macro_beats_remaining: list,   # [Beat], future beats still ahead
        retrieved_hits: list[dict],
        known_facts_summary: str,
        recent_text: str,
        user_text: str,
        beat_turns: int,
        locale: str = "de",
        max_reveals: int | None = None,
    ) -> NarrationGate:
        loc = norm(locale)
        # `max_reveals` is overridable per call so the pressure controller
        # can scale the gate's strictness with the current plot-pressure
        # (more reveals = more permissive). Falls back to the config cap.
        if max_reveals is None:
            max_reveals = int(getattr(self.cfg.story,
                                       "narration_gate_max_reveals", 3))
        max_reveals = max(1, int(max_reveals))

        # Build the curator's input. It sees EVERYTHING — including the
        # substory.resolution_hint — because IT is the one keeping it
        # secret from the narrator.
        sub_block = ""
        if substory_dict:
            beats = substory_dict.get("beats") or []
            cur = int(substory_dict.get("cursor", 0))
            beat_lines = "\n".join(
                f"  {i+1}. {b.get('name','?')} (Ziel: {b.get('goal','')}, "
                f"Spannung {b.get('tension','?')})"
                for i, b in enumerate(beats))
            sub_block = (
                f"AKTUELLE SUBSTORY: {substory_dict.get('title','')}\n"
                f"Prämisse: {substory_dict.get('premise','')}\n"
                f"Aufhänger: {substory_dict.get('hook','')}\n"
                f"Aktueller Sub-Beat {cur + 1}/{max(1, len(beats))}\n"
                f"Beats:\n{beat_lines or '(keine)'}\n"
                f"VOR-GEPLANTE AUFLÖSUNG (geheim halten!): "
                f"{substory_dict.get('resolution_hint','(unbekannt)')}\n"
            )
        future_beats = "; ".join(getattr(b, "name", "?")
                                 for b in macro_beats_remaining) or "(keine)"
        hits_block = "\n".join(
            f"- [{r.get('fact_type','fact')}] {r.get('content','')[:200]}"
            for r in (retrieved_hits or [])[:8]) or "(keine)"

        user_msg = (
            f"WELT: {world.name} ({world.genre})\n"
            f"{world.description}\n\n"
            f"{sub_block}\n"
            f"KÜNFTIGE MAKRO-BEATS (noch ausstehend, dürfen heute NICHT "
            f"vorgegriffen werden): {future_beats}\n\n"
            f"DEM SPIELER SCHON BEKANNT: "
            f"{known_facts_summary or '(nichts Besonderes)'}\n"
            f"AKTUELLE EINGABE DES SPIELERS: {user_text or '(stumm)'}\n"
            f"LETZTE ERZÄHL-/SPIELER-SCHRITTE: {recent_text or '(noch nichts)'}\n"
            f"SUB-BEAT LÄUFT SEIT {beat_turns} ZÜGEN auf demselben Beat — "
            f"je länger, desto eher darfst du einen Reveal/Fortschritt "
            f"freischalten.\n\n"
            f"AUTHORED WELT-FAKTEN (semantisch passend abgerufen — wähle "
            f"daraus passende Reveals oder benenne ähnliche; ungeöffnete "
            f"Geheimnisse bleiben in forbidden_topics):\n{hits_block}\n\n"
            f"Wähle JETZT die Kurator-Entscheidung. Höchstens {max_reveals} "
            f"permitted_reveals."
        )

        try:
            client = get_chat_client(self.cfg, "gate")
            resp = client.chat.completions.create(
                model=self.cfg.models.gate,
                messages=[{"role": "system", "content": GATE_SYS[loc]},
                          {"role": "user", "content": user_msg}],
                response_format={"type": "json_object"},
                **chat_extras(self.cfg, "gate",
                              temperature=self.cfg.models.gate_temperature),
            )
            if self.cost is not None:
                _usd = self.cost.record_chat(resp.usage, role="gate",
                                              model=self.cfg.models.gate)
                if self.ledger is not None and resp.usage is not None:
                    self.ledger.record(
                        kind="chat", usd=_usd,
                        thread_id=self.thread_id, world_id=self.world_id,
                        model=self.cfg.models.gate,
                        chat_in=getattr(resp.usage, "prompt_tokens", 0) or 0,
                        chat_out=getattr(resp.usage,
                                         "completion_tokens", 0) or 0)
            data = json.loads(resp.choices[0].message.content or "{}")
            return NarrationGate(
                scene_intent=str(data.get("scene_intent", "")).strip()[:300],
                permitted_reveals=_truncate(
                    list(data.get("permitted_reveals") or []), max_reveals),
                forbidden_topics=_truncate(
                    list(data.get("forbidden_topics") or []), 12),
                tone_nudge=str(data.get("tone_nudge", "")).strip()[:160],
            )
        except Exception as exc:
            # Be loud about it — the previous silent fallback let the gate
            # quietly time out every turn and made it look like the curator
            # was just always permissive. INFO with the exception name lets
            # ops grep for it without drowning the rest of the logs.
            log.warning("XTTS gate fell back to empty: %s: %s",
                        type(exc).__name__, exc)
            return NarrationGate()
