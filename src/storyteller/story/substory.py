"""Substory system: a dynamic mini arc inside the macro arc.

NarrativeState:
  IN_SUBSTORY       – the narrator is mid-substory
  SUBSTORY_COMPLETE – the current substory is resolved -> architect replans
  PLANNING          – the architect "thinks up" a new substory (RAG + context)

The SubstoryPlan is prompt-injected into the narrator system prompt and is
queryable/adjustable via tools (get_/adjust_substory_plan).
"""

from __future__ import annotations

import enum
import json

from pydantic import BaseModel, Field

from ..config import Config
from ..oai import get_client
from ..worlds.schema import Beat
from .dynamics import INTEGRATION_RULE


class NarrativeState(str, enum.Enum):
    IN_SUBSTORY = "in_substory"
    SUBSTORY_COMPLETE = "substory_complete"
    PLANNING = "planning"


class SubstoryPlan(BaseModel):
    title: str
    premise: str
    hook: str
    beats: list[Beat] = Field(default_factory=list)
    involved_places: list[str] = Field(default_factory=list)
    involved_persons: list[str] = Field(default_factory=list)
    resolution_hint: str = ""
    status: str = "active"          # active | complete
    cursor: int = 0                 # aktueller Sub-Beat
    adjustments: list[str] = Field(default_factory=list)
    closing_summary: str = ""

    # --- Beat-Navigation ---
    def current_beat(self) -> Beat | None:
        if not self.beats:
            return None
        return self.beats[min(self.cursor, len(self.beats) - 1)]

    def advance(self) -> None:
        self.cursor = min(self.cursor + 1, max(0, len(self.beats) - 1))

    @property
    def near_end(self) -> bool:
        return bool(self.beats) and self.cursor >= len(self.beats) - 1

    def as_prompt_block(self, transition: bool) -> str:
        b = self.current_beat()
        beat_txt = (f"{b.name} — Ziel: {b.goal} (Spannung {b.tension}/10)"
                    if b else "(keine Beats)")
        adj = ("\nANPASSUNGEN (beachten): " + " | ".join(self.adjustments)
               if self.adjustments else "")
        head = ("ÜBERGANG: Die vorige Substory ist aufgelöst — leite jetzt "
                "weich in DIESE neue Substory über.\n" if transition else "")
        return (
            f"{head}AKTUELLE SUBSTORY: {self.title}\n"
            f"Prämisse: {self.premise}\nAufhänger: {self.hook}\n"
            f"Sub-Beat {self.cursor + 1}/{len(self.beats) or 1}: {beat_txt}\n"
            f"Beteiligte Orte: {', '.join(self.involved_places) or '–'}; "
            f"Personen: {', '.join(self.involved_persons) or '–'}\n"
            f"Auflösung anstreben: {self.resolution_hint}{adj}\n"
            "Treibe DIESE Substory voran, bis sie befriedigend aufgelöst ist; "
            "ist sie aufgelöst, rufe das Tool complete_substory auf (erfinde "
            "NICHT selbst einen komplett neuen Bogen — der Architekt plant ihn)."
        )


_PLANNER_SYS = (
    "Du bist Story-Architekt. Entwirf die NÄCHSTE Substory als eigenständigen "
    "kleinen Spannungsbogen, konsistent mit den etablierten Weltfakten und dem "
    "Makro-Spannungsbogen. Sie muss Raum für die freie Mitgestaltung des "
    "Spielers lassen (keine Schienen). Antworte AUSSCHLIESSLICH als JSON mit "
    "den Schlüsseln: title, premise, hook, beats (Liste aus "
    "{name, goal, tension(0-10)}), involved_places (Liste), "
    "involved_persons (Liste), resolution_hint."
)


class SubstoryPlanner:
    """Der "Überleg- und Planungsschritt" für eine neue Substory (eigener LLM-Call)."""

    def __init__(self, cfg: Config, cost=None):
        self.cfg = cfg
        self.cost = cost

    def plan_next(self, world, rag, macro_guidance: str, known_summary: str,
                  recent: str, previous_summary: str = "",
                  dynamic_hint: str = "", locale: str = "de") -> SubstoryPlan:
        from ..i18n import LANG_INSTRUCTION, norm

        loc = norm(locale)
        grounding = ""
        if rag is not None:
            try:
                q = f"{macro_guidance} {recent} {previous_summary}".strip()
                hits = rag.retrieve(world.id, q or world.description,
                                    locale=loc)
                grounding = "\n".join(f"- [{h['fact_type']}] {h['content']}"
                                      for h in hits)
            except Exception:
                grounding = ""

        user = (
            f"WELT: {world.name} ({world.genre}). {world.description}\n"
            f"Spielerrolle: {world.player_role}\n\n"
            f"MAKRO-BOGEN:\n{macro_guidance}\n\n"
            f"Dem Spieler bekannt: {known_summary}\n"
            f"Vorige Substory (Abschluss): {previous_summary or '–'}\n"
            f"Letzte Spieler-/Erzähl-Signale: {recent or '–'}\n\n"
            f"Etablierte Weltfakten (nutzen, nicht widersprechen):\n"
            f"{grounding or '(keine)'}\n\n"
            + (f"OPTIONALE ABSTRAKTE WENDUNG (dezent einplanen, z.B. in einem "
               f"Beat oder im resolution_hint): {dynamic_hint}. {INTEGRATION_RULE}\n\n"
               if dynamic_hint else "")
            + f"Plane jetzt die nächste Substory "
            f"(max. {self.cfg.story.max_substory_beats} Beats).\n"
            f"{LANG_INSTRUCTION[loc]}"
        )
        client = get_client(self.cfg)
        try:
            resp = client.chat.completions.create(
                model=self.cfg.models.story_llm,
                messages=[{"role": "system", "content": _PLANNER_SYS},
                          {"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
            if self.cost is not None:
                self.cost.record_chat(resp.usage)
            data = json.loads(resp.choices[0].message.content or "{}")
            beats = [Beat(name=b.get("name", f"Beat {i+1}"),
                          goal=b.get("goal", ""),
                          tension=max(0, min(10, int(b.get("tension", 5)))))
                     for i, b in enumerate(data.get("beats", [])[
                         : self.cfg.story.max_substory_beats])]
            if not beats:
                beats = [Beat(name="Aufhänger", goal=data.get("hook", ""),
                              tension=3),
                         Beat(name="Höhepunkt", goal="Zuspitzung", tension=8),
                         Beat(name="Auflösung", goal="Abschluss", tension=3)]
            return SubstoryPlan(
                title=data.get("title", "Eine neue Wendung"),
                premise=data.get("premise", ""),
                hook=data.get("hook", ""),
                beats=beats,
                involved_places=list(data.get("involved_places", []))[:8],
                involved_persons=list(data.get("involved_persons", []))[:8],
                resolution_hint=data.get("resolution_hint", ""),
            )
        except Exception:
            # Robuster Fallback, falls JSON/Modell zickt
            return SubstoryPlan(
                title="Eine unerwartete Wendung",
                premise=f"Eine neue Herausforderung in {world.name}.",
                hook="Etwas zwingt zum Handeln.",
                beats=[Beat(name="Aufhänger", goal="Lage etablieren", tension=3),
                       Beat(name="Zuspitzung", goal="Eskalation", tension=7),
                       Beat(name="Auflösung", goal="Abschluss", tension=3)],
                resolution_hint="Eine Entscheidung des Spielers löst es auf.",
            )
