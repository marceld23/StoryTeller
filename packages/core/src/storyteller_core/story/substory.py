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
import logging
import time as _time

from pydantic import BaseModel, Field

from ..config import Config
from ..oai import chat_extras, get_chat_client
from ..worlds.schema import Beat
from .dynamics import INTEGRATION_RULE

log = logging.getLogger("storyteller.planner")


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
        # 400 chars covers ~3 short sentences — the variant-pick reasoning
        # is the most-useful planner note for understanding session arc
        # choices, and 160 chars truncated mid-word ("...zwei para").
        why = (data.get("why") or "").strip()[:400]
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

    # Suffixes that, when attached to an existing region's stem, look
    # like a top-level region the planner invented (e.g. "Aurelion-
    # Korridor" off the canonical "Aurelion-System"). Matched case-
    # insensitively. Pattern: <token>-<suffix>.
    _REGION_LIKE_SUFFIXES: tuple[str, ...] = (
        "system", "sektor", "korridor", "korridoren", "korridors",
        "bahn", "reich", "raum", "zone", "sphäre", "spähre",
        "achse", "sector",
    )

    def _warn_coined_region_names(self, world, *,
                                   title: str,
                                   premise: str, hook: str,
                                   involved_places: list[str],
                                   beat_names: list[str],
                                   beat_goals: list[str]) -> None:
        """Surface planner-coined region-like names as a transcript
        warning. No-op if no transcript is attached (callers outside
        the engine path)."""
        if not self.transcript:
            return
        import re
        existing_lower: set[str] = set()
        for collection in ("regions", "places", "factions",
                             "persons", "items", "glossary"):
            for entry in (getattr(world, collection, None) or []):
                n = (getattr(entry, "name", None)
                     or getattr(entry, "term", None) or "")
                if isinstance(n, str) and n.strip():
                    existing_lower.add(n.strip().lower())
        # Region stems: tokens BEFORE the "-System"/"-Sektor" suffix in
        # actual region names. If those stems appear in the plan with
        # a *different* suffix, that's the coin we want to flag.
        region_stems: set[str] = set()
        for r in (getattr(world, "regions", []) or []):
            rname = (getattr(r, "name", "") or "").strip()
            if not rname:
                continue
            # Split on "-" / whitespace; first part is usually the stem
            # ("Aurelion-System" → "Aurelion"). Keep all parts to be
            # tolerant; short generic tokens get filtered below.
            parts = re.split(r"[-\s]+", rname)
            for p in parts:
                if len(p) >= 4 and p.lower() not in {"system", "sektor",
                                                       "sector", "the"}:
                    region_stems.add(p.lower())

        suffix_pattern = re.compile(
            r"\b([A-ZÄÖÜ][\wÄÖÜäöüß]{2,})-(" +
            "|".join(self._REGION_LIKE_SUFFIXES) + r")\w*\b",
            flags=re.IGNORECASE)
        haystack = " ".join([
            title, premise, hook,
            " ".join(involved_places or []),
            " ".join(beat_names or []),
            " ".join(beat_goals or []),
        ])
        coined: dict[str, str] = {}     # coined-name -> closest stem
        for match in suffix_pattern.finditer(haystack):
            full = match.group(0)
            stem = match.group(1).lower()
            full_low = full.lower()
            if full_low in existing_lower:
                continue                # already in the world, fine
            if stem in region_stems:
                # E.g. world has region "Aurelion-System", plan says
                # "Aurelion-Korridor" → flag with the canonical name.
                coined[full] = next(
                    (r.name for r in (getattr(world, "regions", []) or [])
                     if (getattr(r, "name", "") or "").lower().split(
                         "-")[0] == stem), stem)
        if coined:
            details = "; ".join(
                f"'{name}' (kanonisch: '{canon}')"
                for name, canon in list(coined.items())[:5])
            self.transcript.note(
                f"[planner] coined region-like names not in world: {details}")
            log.warning("planner coined region-like names: %s", coined)

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
        # Canonical names the planner MUST stay consistent with. Without
        # this block the planner only saw a free-text world.description
        # and improvised compound names like "Aurelion-Korridor" when it
        # needed a sub-spatial term — the narrator then took those as
        # canon for the rest of the session. Surface the structured
        # lists exactly the way the narrator's system prompt does.
        regions_names = "; ".join(
            r.name for r in (getattr(world, "regions", []) or [])[:12]) \
            or "(keine)"
        factions_names = "; ".join(
            f.name for f in (getattr(world, "factions", []) or [])[:8]) \
            or "(keine)"
        places_names = "; ".join(
            p.name for p in (getattr(world, "places", []) or [])[:20]) \
            or "(keine)"
        persons_names = "; ".join(
            p.name for p in (getattr(world, "persons", []) or [])[:12]) \
            or "(keine)"
        user = (
            f"WELT: {world.name} ({world.genre}). {world.description}\n"
            f"Spielerrolle: {world.player_role}\n"
            f"{world_tone_line(world)}\n\n"
            f"KANONISCHE NAMEN (WÖRTLICH verwenden, NICHT verändern):\n"
            f"  Regionen: {regions_names}\n"
            f"  Fraktionen: {factions_names}\n"
            f"  Orte (Top 20): {places_names}\n"
            f"  Personen (Top 12): {persons_names}\n"
            f"NAMENS-REGEL: Wenn die Substory in einer Region spielt, "
            f"nutze deren Namen WÖRTLICH (z.B. 'Aurelion-System', NICHT "
            f"'Aurelion-Korridor' oder 'Aurelion-Sektor'). Neue Mikro-"
            f"Orte (eine Brücke, eine Wartungsluke, ein Korridor IN "
            f"einem existierenden Ort) sind ok — aber NIE neue Top-"
            f"Level-Regionen oder System-/Sektor-/Korridor-Namen "
            f"erfinden. `involved_places` SOLL bevorzugt Namen aus der "
            f"Orte-Liste oben nutzen; neue Orte beschreibe als 'in "
            f"<Region>' oder 'innerhalb <Ort>'.\n\n"
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
        # are intermittent. Each attempt is bookended with a Python log
        # AND a transcript note so the admin can see the planner is
        # working (heavy planning calls can take 30-90 s on frontier
        # reasoning models — without an "in progress" marker the silence
        # between attempts looked like a hang).
        last_err: Exception | None = None
        prompt_chars = len(_PLANNER_SYS) + len(user)
        for attempt in (1, 2):
            log.info("plan_next attempt %d/2 model=%s n_beats=%d prompt=%d chars",
                     attempt, self.cfg.models.planner,
                     _cap_n, prompt_chars)
            if self.transcript:
                self.transcript.note(
                    f"[planner] planning new substory "
                    f"(attempt {attempt}/2, model={self.cfg.models.planner}, "
                    f"target {_cap_n} beats)…")
            t0 = _time.perf_counter()
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
                dt = _time.perf_counter() - t0
                log.info("plan_next attempt %d/2 OK in %.1fs title=%r "
                         "beats=%d persons=%d places=%d",
                         attempt, dt, title, len(beats),
                         len(data.get("involved_persons") or []),
                         len(data.get("involved_places") or []))
                involved_places = list(
                    data.get("involved_places") or [])[:8]
                involved_persons = list(
                    data.get("involved_persons") or [])[:8]
                # Post-hoc consistency check: flag any planner-coined
                # region-/sector-/corridor-shaped names that don't exist
                # in the world. Doesn't reject the plan (sometimes a
                # newly-coined micro-location IS the right call) — just
                # makes the drift visible as a [planner] transcript
                # note so the operator can see WHY a future synopsis
                # talks about an "Aurelion-Korridor" that's nowhere in
                # the world data.
                self._warn_coined_region_names(
                    world, title=title,
                    premise=(data.get("premise") or ""),
                    hook=(data.get("hook") or ""),
                    involved_places=involved_places,
                    beat_names=[b.name for b in beats],
                    beat_goals=[b.goal for b in beats])
                return SubstoryPlan(
                    title=title,
                    premise=(data.get("premise") or "").strip(),
                    hook=(data.get("hook") or "").strip(),
                    beats=beats,
                    involved_places=involved_places,
                    involved_persons=involved_persons,
                    resolution_hint=(data.get("resolution_hint") or "").strip(),
                )
            except Exception as exc:
                dt = _time.perf_counter() - t0
                last_err = exc
                log.warning("plan_next attempt %d/2 FAILED after %.1fs: "
                            "%s: %s", attempt, dt,
                            type(exc).__name__, str(exc)[:200])
                if self.transcript:
                    self.transcript.note(
                        f"[planner] FAILED attempt {attempt}/2 "
                        f"after {dt:.0f}s: "
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
