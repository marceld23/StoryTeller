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
from ..oai import chat_extras, get_chat_client
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
    cursor: int = 0                 # current sub-beat
    adjustments: list[str] = Field(default_factory=list)
    closing_summary: str = ""

    # --- beat navigation ---
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
        # `resolution_hint` is intentionally NOT exposed in the prompt block
        # — the narrator must not know the resolution in advance. It stays
        # on the SubstoryPlan for the planner/curator and tools that need
        # it. The narrator just plays the current sub-beat.
        return (
            f"{head}AKTUELLE SUBSTORY: {self.title}\n"
            f"Prämisse: {self.premise}\nAufhänger: {self.hook}\n"
            f"Sub-Beat {self.cursor + 1}/{len(self.beats) or 1}: {beat_txt}\n"
            f"Beteiligte Orte: {', '.join(self.involved_places) or '–'}; "
            f"Personen: {', '.join(self.involved_persons) or '–'}{adj}\n"
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


def choose_blueprint_variant(cfg: Config, world, *, known_summary: str = "",
                              recent: str = "", previous_summary: str = "",
                              locale: str = "de",
                              cost=None, ledger=None,
                              thread_id: str | None = None,
                              world_id: str | None = None,
                              transcript=None) -> int:
    """Pick which of `world.blueprints` should drive the NEXT substory
    arc. Returns 0 for legacy single-arc worlds (no LLM call). For
    multi-variant worlds: one small `planner` chat call with the
    variant catalog + recent player context, returns the chosen
    index. Falls back to 0 on any error so the engine always has a
    valid choice — the engine clamps invalid indices in
    World.active_blueprint anyway."""
    variants = list(getattr(world, "blueprints", None) or [])
    if len(variants) <= 1:
        return 0
    from ..i18n import LANG_INSTRUCTION, norm

    loc = norm(locale)
    catalog = "\n".join(
        f"{i}: \"{v.name}\" — länge={v.length}, struktur={v.structure}, "
        f"twist={v.twist_kind or 'kein'}; trigger={v.trigger_hints}\n"
        f"   {v.description or v.blueprint.premise}"
        for i, v in enumerate(variants))
    sys_msg = (
        "Du wählst aus mehreren Story-Bogen-Varianten einer Welt EINEN "
        "Bogen für die kommende Substory aus. Wäge ab: was passt zum "
        "bisherigen Spielverlauf, was würde sich frisch und passend "
        "anfühlen — vermeide den gleichen Bogen wie im vorigen Stück, "
        "wenn der Spieler schon Welt-Erfahrung hat. Antworte JSON: "
        "{\"choice\": <index>, \"why\": \"<knapp>\"}. Index MUSS einer "
        "der angebotenen sein."
    )
    user = (
        f"WELT: {world.name} ({world.genre}).\n"
        f"Dem Spieler bereits bekannt: {known_summary or '(neu)'}\n"
        f"Vorige Substory (Abschluss): {previous_summary or '–'}\n"
        f"Letzte Signale: {recent or '–'}\n\n"
        f"VERFÜGBARE STORY-BÖGEN:\n{catalog}\n\n"
        f"Wähle JETZT einen Index.\n{LANG_INSTRUCTION[loc]}"
    )
    try:
        resp = get_chat_client(cfg, "planner").chat.completions.create(
            model=cfg.models.planner,
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            **chat_extras(cfg, "planner",
                          temperature=cfg.models.planner_temperature),
        )
        if cost is not None:
            usd = cost.record_chat(resp.usage, role="planner",
                                    model=cfg.models.planner)
            if ledger is not None and resp.usage is not None:
                ledger.record(
                    kind="chat", usd=usd,
                    thread_id=thread_id, world_id=world_id,
                    model=cfg.models.planner,
                    chat_in=getattr(resp.usage, "prompt_tokens", 0) or 0,
                    chat_out=getattr(resp.usage,
                                     "completion_tokens", 0) or 0)
        data = json.loads(resp.choices[0].message.content or "{}")
        choice = int(data.get("choice", 0))
        why = (data.get("why") or "").strip()[:160]
        if 0 <= choice < len(variants):
            if transcript:
                transcript.note(
                    f"[planner] variant pick: #{choice} "
                    f"'{variants[choice].name}'"
                    + (f" — {why}" if why else ""))
            return choice
    except Exception as exc:
        if transcript:
            transcript.note(
                f"[planner] variant pick FAILED — "
                f"{type(exc).__name__}: {str(exc)[:160]}")
    return 0


class SubstoryPlanner:
    """The "think-and-plan step" for a new substory (its own LLM call)."""

    def __init__(self, cfg: Config, cost=None, *, ledger=None,
                 thread_id: str | None = None, world_id: str | None = None,
                 transcript=None):
        self.cfg = cfg
        self.cost = cost
        self.ledger = ledger
        self.thread_id = thread_id
        self.world_id = world_id
        # Optional transcript handle — when present, planning failures land
        # as `[planner] FAILED` notes in the session transcript instead of
        # vanishing into the engine log.
        self.transcript = transcript

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

        from .patterns import choose_pattern, world_tone_line

        pat = choose_pattern(world, self.cfg)
        skeleton = "\n".join(
            f"  {i+1}. {a} (Ziel: {g}, ~Spannung {t})"
            for i, (a, g, t) in enumerate(pat["beats"]))
        user = (
            f"WELT: {world.name} ({world.genre}). {world.description}\n"
            f"Spielerrolle: {world.player_role}\n"
            f"{world_tone_line(world)}\n\n"
            f"MAKRO-BOGEN:\n{macro_guidance}\n\n"
            f"Dem Spieler bekannt: {known_summary}\n"
            f"Vorige Substory (Abschluss): {previous_summary or '–'}\n"
            f"Letzte Spieler-/Erzähl-Signale: {recent or '–'}\n\n"
            f"Etablierte Weltfakten (nutzen, nicht widersprechen):\n"
            f"{grounding or '(keine)'}\n\n"
            f"STRUKTUR {pat['name']} — {pat['shape']}\n"
            f"Instanziiere GENAU dieses Beat-Gerüst weltkonkret "
            f"({pat['n_beats']} Beats, Spannung der Kurve folgend, max "
            f"{pat['tension_cap']}):\n{skeleton}\n\n"
            + (f"OPTIONALE ABSTRAKTE WENDUNG (dezent einplanen, z.B. in einem "
               f"Beat oder im resolution_hint): {dynamic_hint}. "
               f"{INTEGRATION_RULE}\n\n" if dynamic_hint else "")
            + f"Plane jetzt die nächste Substory ({pat['n_beats']} Beats, "
            f"passend zu Ton & Zielgruppe).\n{LANG_INSTRUCTION[loc]}"
        )
        _cap_n = pat["n_beats"]
        _cap_t = pat["tension_cap"]
        client = get_chat_client(self.cfg, "planner")

        # Try the planner LLM up to twice. The second try is a slightly
        # stricter retry with the same prompt — most JSON-shape failures
        # are intermittent. Each failure lands a `[planner] FAILED` line
        # in the transcript so the admin can see what happened instead
        # of an opaque "Eine unerwartete Wendung" fallback.
        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                resp = client.chat.completions.create(
                    model=self.cfg.models.planner,
                    messages=[{"role": "system", "content": _PLANNER_SYS},
                              {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                    **chat_extras(self.cfg, "planner",
                                  temperature=self.cfg.models.planner_temperature),
                )
                if self.cost is not None:
                    _usd = self.cost.record_chat(
                        resp.usage, role="planner",
                        model=self.cfg.models.planner)
                    if self.ledger is not None and resp.usage is not None:
                        self.ledger.record(
                            kind="chat", usd=_usd,
                            thread_id=self.thread_id, world_id=self.world_id,
                            model=self.cfg.models.planner,
                            chat_in=getattr(resp.usage, "prompt_tokens", 0) or 0,
                            chat_out=getattr(resp.usage,
                                             "completion_tokens", 0) or 0)
                data = json.loads(resp.choices[0].message.content or "{}")
                beats = [Beat(name=b.get("name", f"Beat {i+1}"),
                              goal=b.get("goal", ""),
                              tension=max(0, min(_cap_t,
                                                 int(b.get("tension", 5)))))
                         for i, b in enumerate(
                             data.get("beats", [])[:_cap_n])]
                if not beats:
                    raise ValueError(
                        "planner JSON had no usable `beats` array")
                title = (data.get("title") or "").strip() \
                    or "Eine neue Wendung"
                return SubstoryPlan(
                    title=title,
                    premise=(data.get("premise") or "").strip(),
                    hook=(data.get("hook") or "").strip(),
                    beats=beats,
                    involved_places=list(data.get("involved_places") or [])[:8],
                    involved_persons=list(data.get("involved_persons") or [])[:8],
                    resolution_hint=(data.get("resolution_hint") or "").strip(),
                )
            except Exception as exc:
                last_err = exc
                if self.transcript:
                    self.transcript.note(
                        f"[planner] FAILED attempt {attempt}/2: "
                        f"{type(exc).__name__}: {str(exc)[:160]}")

        # Both attempts failed. Surface as a notable, loud transcript line
        # AND return a marked-fallback substory so the next ensure_substory
        # call will retry from scratch instead of letting the engine cement
        # this stub for the entire session (which was the bug in
        # 'pi-justus_scify' — 18 turns on a stub with empty involved_*).
        if self.transcript:
            self.transcript.note(
                f"[planner] FAILED both attempts — using marked stub. "
                f"last_err={type(last_err).__name__ if last_err else 'unknown'}")
        return SubstoryPlan(
            title="(planning failed — temporary)",
            premise=f"Planung für {world.name} ist gerade fehlgeschlagen.",
            hook="Etwas zwingt zum Handeln.",
            beats=[Beat(name="Aufhänger", goal="Lage etablieren", tension=3),
                   Beat(name="Zuspitzung", goal="Eskalation", tension=7),
                   Beat(name="Auflösung", goal="Abschluss", tension=3)],
            resolution_hint="Eine Entscheidung des Spielers löst es auf.",
            # The status="planning_failed" is recognised by ensure_substory
            # so the next turn re-attempts the plan instead of treating
            # this as an active arc to stay on for hours.
            status="planning_failed",
        )
