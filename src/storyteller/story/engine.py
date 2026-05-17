"""Story-Engine v2.

Der Erzähler weiß: Er erzählt NICHT für sich, sondern um den Spieler aktiv
einzubinden — dessen Aktionen werden mitgedacht, aufgegriffen und wirken auf
die Welt. Er folgt einem MAKRO-Spannungsbogen (Blueprint) und einer dynamisch
geplanten SUBSTORY (Mini-Bogen).

Statusmaschine (siehe substory.NarrativeState):
- IN_SUBSTORY: Substory vorantreiben, Spieler einbinden.
- SUBSTORY_COMPLETE: Erzähler hat complete_substory aufgerufen.
- PLANNING: Architekt (SubstoryPlanner) "überlegt" via RAG+Kontext eine neue
  Substory; sie wird per Prompt-Injection eingespeist und ist über Tools
  abfragbar/anpassbar (get_/adjust_substory_plan).
"""

from __future__ import annotations

import json

from ..config import Config
from ..oai import get_client
import random

from .blueprint import BlueprintTracker
from .cost import CostTracker
from .dynamics import INTEGRATION_RULE, StoryDynamics
from .knowledge import KnownFacts
from .random_events import RandomEvents
from .substory import NarrativeState, SubstoryPlan, SubstoryPlanner

TOOLS = [
    {"type": "function", "function": {
        "name": "retrieve_world_fact",
        "description": "Semantische Suche in der Weltbeschreibung. fact_type "
                       "optional filtern.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "fact_type": {"type": "string",
                          "enum": ["place", "person", "item", "fragment",
                                   "glossary", "history", "system"]}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "lookup_glossary",
        "description": "Schlage einen Welt-Begriff im Glossar nach (für "
                       "konsistente Terminologie).",
        "parameters": {"type": "object", "properties": {
            "term": {"type": "string"}}, "required": ["term"]}}},
    {"type": "function", "function": {
        "name": "get_world_overview",
        "description": "Liefert Beschreibung, Ausgangssituation, Stimmung, "
                       "Ambiente, Physik/Magie und die Namen der Zufallslisten.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "roll_random_event",
        "description": "Würfle ein welt-spezifisches Zufallsereignis.",
        "parameters": {"type": "object", "properties": {
            "table_name": {"type": "string"}}, "required": ["table_name"]}}},
    {"type": "function", "function": {
        "name": "roll_story_dynamic",
        "description": "Würfle eine abstrakte Story-Wendung (z.B. weiterer "
                       "Antagonist, Unvorhergesehenes). Subtil einweben, NICHT "
                       "den Bogen kippen.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "remember_fact",
        "description": "Merke dauerhaft, was der Spieler nun kennt.",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string"}, "name": {"type": "string"},
            "note": {"type": "string"}}, "required": ["kind", "name"]}}},
    {"type": "function", "function": {
        "name": "advance_beat",
        "description": "Schalte einen Sub-Beat der aktuellen Substory weiter.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "complete_substory",
        "description": "Rufe auf, wenn die aktuelle Substory befriedigend "
                       "aufgelöst ist. Übergib eine kurze Zusammenfassung.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string"}}, "required": ["summary"]}}},
    {"type": "function", "function": {
        "name": "get_substory_plan",
        "description": "Lies den aktuellen Substory-Plan (Beats/Auflösung).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "adjust_substory_plan",
        "description": "Passe den Substory-Plan an, wenn der Spieler die "
                       "Richtung deutlich ändert (Notiz wird mitgeführt).",
        "parameters": {"type": "object", "properties": {
            "change": {"type": "string"}}, "required": ["change"]}}},
]

CO_CREATION = (
    "GRUNDHALTUNG: Du bist Erzähler, aber der eigentliche Sinn ist, den "
    "SPIELER aktiv einzubinden. Denke seine Aktionen, Absichten und Ideen "
    "konsequent mit, greife sie auf, baue darauf auf und lass sie die Welt "
    "verändern. Niemals Multiple-Choice, niemals auf Schienen. Schaffe "
    "lebendige, offene Situationen, auf die er frei reagieren kann."
)

_Q_PREFIXES = (
    "was ", "wer ", "wo ", "wie ", "warum", "wieso", "welche", "welcher",
    "welches", "wann", "wozu", "kann ich", "darf ich", "habe ich", "hab ich",
    "gibt es", "gibt's", "wisst ihr", "weißt du", "weisst du", "erinner",
)


def _is_query(text: str) -> bool:
    """Heuristik: stellt der Spieler eine Rückfrage (statt zu handeln)?"""
    t = text.strip().lower()
    return t.endswith("?") or t.startswith(_Q_PREFIXES)


BRIEF_RULE = (
    "\nDER SPIELER STELLT EINE RÜCKFRAGE: Antworte SEHR KURZ (1–2 Sätze), "
    "kläre nur die Frage sachlich. KEINE neue Szene, Handlung NICHT "
    "vorantreiben, keinen Beat wechseln, keine Story-Dynamik."
)


class StoryEngine:
    def __init__(self, cfg: Config, world, rag=None,
                 known: KnownFacts | None = None,
                 macro: BlueprintTracker | None = None,
                 memory: list[dict] | None = None,
                 cost: CostTracker | None = None):
        self.cfg = cfg
        self.world = world
        self.rag = rag
        self.known = known or KnownFacts()
        self.macro = macro or BlueprintTracker(world.blueprint)
        self.random = RandomEvents(world)
        self.memory: list[dict] = memory or []
        self.cost = cost or CostTracker(cfg)
        self.planner = SubstoryPlanner(cfg, self.cost)
        self.substory: SubstoryPlan | None = None
        self._rng = random.Random()
        self.dynamics = StoryDynamics(self._rng)
        self._transition = False
        self._wrap_up = False

    # --- Zustand ---
    def state(self) -> NarrativeState:
        if self.substory is None:
            return NarrativeState.PLANNING
        if self.substory.status == "complete":
            return NarrativeState.SUBSTORY_COMPLETE
        return NarrativeState.IN_SUBSTORY

    def _recent(self) -> str:
        tail = [m["content"] for m in self.memory[-4:]
                if m["role"] in ("user", "assistant")]
        return " ".join(tail)[:600]

    def _ensure_substory(self) -> None:
        if self.substory is not None and self.substory.status != "complete":
            return
        prev = self.substory.closing_summary if self.substory else ""
        if self.substory is not None:           # vorige abgeschlossen
            self.macro.advance()                # Makro-Bogen weiterschalten
        dyn_hint = ""
        if self.cfg.story.dynamics_in_planning:
            dyn_hint = self.dynamics.roll()
        self.substory = self.planner.plan_next(
            self.world, self.rag, self.macro.guidance(),
            self.known.summary(), self._recent(), prev, dyn_hint)
        self._transition = bool(prev)

    # --- Prompt ---
    def _system(self, retrieved: list[dict], dynamic: str | None = None,
                brief: bool = False) -> str:
        w = self.world
        facts = "\n".join(f"- [{r['fact_type']}] {r['content']}"
                          for r in retrieved)
        cap = ("\nWICHTIG: Das Sitzungsbudget ist erschöpft — führe die "
               "Geschichte jetzt zu einem ruhigen, runden Abschluss."
               if self._wrap_up else "")
        dyn = (f"\n\nMÖGLICHE STORY-DYNAMIK (optional einweben): {dynamic}\n"
               f"{INTEGRATION_RULE}" if dynamic else "")
        gloss = "; ".join(f"{g.term}={g.definition}"
                          for g in getattr(w, "glossary", [])[:12])
        rtables = ", ".join(t.name for t in w.random_tables)
        return (
            f"Du bist der ERZÄHLER der Welt {w.name} ({w.genre}).\n"
            f"{w.description}\nSpielerrolle: {w.player_role}\n"
            f"Erzählstil: {w.narration_style}\n"
            f"STIMMUNG: {w.mood or '–'}\nAMBIENTE: {w.ambience or '–'}\n"
            f"PHYSIK/MAGIE: {w.magic_physics or '–'}\n"
            f"AUSGANGSSITUATION: {w.starting_situation or '–'}\n"
            f"GLOSSAR (Begriffe konsistent verwenden; vollständig via "
            f"lookup_glossary): {gloss or '–'}\n"
            f"ZUFALLSLISTEN (konkret, bei passender Gelegenheit via "
            f"roll_random_event ziehen): {rtables or '–'}\n\n"
            f"{CO_CREATION}\n\n"
            f"MAKRO-SPANNUNGSBOGEN:\n{self.macro.guidance()}\n\n"
            f"{self.substory.as_prompt_block(self._transition)}\n\n"
            f"Dem Spieler bereits bekannt: {self.known.summary()}\n\n"
            f"Hintergrundwissen (nur einbauen, wenn es JETZT zur Szene passt; "
            f"NICHT aufzählen):\n{facts or '(keine Treffer)'}{cap}{dyn}\n\n"
            f"{self.cfg.story.narration_guidance}\n"
            "Tools bei Bedarf still nutzen (get_world_overview, "
            "retrieve_world_fact, lookup_glossary, roll_random_event, "
            "roll_story_dynamic) — das Ergebnis IMMER in einfache, kurze "
            "Erzählung verwandeln, niemals Fakten oder Listen vorlesen."
            + (BRIEF_RULE if brief else "")
        )

    def _exec_tool(self, name: str, args: dict) -> str:
        s = self.substory
        if name == "retrieve_world_fact" and self.rag:
            rows = self.rag.retrieve(self.world.id, args.get("query", ""),
                                     fact_type=args.get("fact_type"))
            return json.dumps([r["content"] for r in rows], ensure_ascii=False)
        if name == "lookup_glossary":
            term = (args.get("term") or "").strip().lower()
            for g in getattr(self.world, "glossary", []):
                if term and term in g.term.lower():
                    return f"{g.term}: {g.definition}"
            if self.rag:
                rows = self.rag.retrieve(self.world.id, args.get("term", ""),
                                         fact_type="glossary")
                if rows:
                    return rows[0]["content"]
            return "(kein Glossareintrag gefunden)"
        if name == "get_world_overview":
            w = self.world
            return json.dumps({
                "beschreibung": w.description,
                "ausgangssituation": w.starting_situation,
                "stimmung": w.mood,
                "ambiente": w.ambience,
                "physik_magie": w.magic_physics,
                "zufallslisten": [t.name for t in w.random_tables],
            }, ensure_ascii=False)
        if name == "roll_random_event":
            return self.random.roll(args.get("table_name", ""))
        if name == "roll_story_dynamic":
            return f"{self.dynamics.roll()} — {INTEGRATION_RULE}"
        if name == "remember_fact":
            return self.known.remember(args.get("kind", "fakt"),
                                       args.get("name", ""),
                                       args.get("note", ""))
        if name == "advance_beat" and s:
            s.advance()
            b = s.current_beat()
            return f"Sub-Beat -> {b.name if b else '?'}"
        if name == "complete_substory" and s:
            s.status = "complete"
            s.closing_summary = args.get("summary", "")
            return "Substory abgeschlossen — der Architekt plant die nächste."
        if name == "get_substory_plan" and s:
            return json.dumps(s.model_dump(include={
                "title", "premise", "beats", "cursor", "resolution_hint",
                "adjustments"}), ensure_ascii=False)
        if name == "adjust_substory_plan" and s:
            s.adjustments.append(args.get("change", ""))
            return "Substory-Plan angepasst (wird weiter berücksichtigt)."
        return "(Tool nicht verfügbar)"

    def _complete(self, user_text: str) -> str:
        self._ensure_substory()
        if self.cost.over_cap:
            self._wrap_up = True
        client = get_client(self.cfg)
        retrieved: list[dict] = []
        if self.rag:
            try:
                retrieved = self.rag.retrieve(self.world.id, user_text)
            except Exception:
                retrieved = []
        brief = _is_query(user_text)
        dyn = None if brief else self.dynamics.maybe(
            self.cfg.story.dynamic_event_prob)
        self.memory.append({"role": "user", "content": user_text})
        working = [{"role": "system",
                    "content": self._system(retrieved, dyn, brief)}]
        working += self.memory

        max_tool_rounds = 8
        try:
            for i in range(max_tool_rounds + 1):
                # Letzte Runde: Tools weglassen -> erzwingt Text (nie leer)
                use_tools = i < max_tool_rounds
                kw = {"model": self.cfg.models.story_llm, "messages": working,
                      "temperature": self.cfg.models.llm_temperature}
                if use_tools:
                    kw["tools"] = TOOLS
                resp = client.chat.completions.create(**kw)
                self.cost.record_chat(resp.usage)
                msg = resp.choices[0].message
                if use_tools and msg.tool_calls:
                    working.append(msg.model_dump(exclude_none=True))
                    for tc in msg.tool_calls:
                        try:
                            a = json.loads(tc.function.arguments or "{}")
                        except json.JSONDecodeError:
                            a = {}
                        working.append({"role": "tool",
                                        "tool_call_id": tc.id,
                                        "content": str(self._exec_tool(
                                            tc.function.name, a))})
                    continue
                text = (msg.content or "").strip()
                if text:
                    self.memory.append({"role": "assistant",
                                        "content": text})
                    self._transition = False
                    self._trim()
                    return text
            return "…"
        except Exception as exc:
            import logging

            logging.getLogger("storyteller").warning(
                "LLM/Verbindung gestört: %r", exc)
            self._transition = False
            # letzten User-Eintrag entfernen, damit kein Loch im Verlauf bleibt
            if self.memory and self.memory[-1].get("role") == "user":
                self.memory.pop()
            return ("Einen Augenblick — die Verbindung stockt gerade. "
                    "Sag es bitte gleich noch einmal.")

    def _trim(self) -> None:
        keep = self.cfg.story.short_term_memory_turns * 2
        if len(self.memory) > keep:
            self.memory = self.memory[-keep:]

    # --- API ---
    def opening(self) -> str:
        return self._complete(
            "[Beginne EINFACH und kurz: 3–5 kurze Sätze zur Ausgangslage, "
            "höchstens ein, zwei konkrete Dinge nennen, keine Infoflut. Ende "
            "mit EINER klaren, offenen Lage oder Frage, auf die der Spieler "
            "direkt reagieren kann.]")

    def turn(self, player_utterance: str) -> str:
        return self._complete(player_utterance)

    # --- Persistenz ---
    def snapshot(self) -> dict:
        return {
            "world_id": self.world.id,
            "memory": self.memory,
            "macro_index": self.macro.index,
            "substory": self.substory.model_dump() if self.substory else None,
            "known": self.known.to_list(),
            "cost": self.cost.snapshot(),
        }

    def restore(self, state: dict) -> None:
        self.memory = state.get("memory", [])
        self.macro.index = state.get("macro_index", 0)
        sub = state.get("substory")
        self.substory = SubstoryPlan(**sub) if sub else None
        self.known = KnownFacts(state.get("known", []))
        self.cost = CostTracker.restore(self.cfg, state.get("cost", {}))
        self.planner.cost = self.cost
