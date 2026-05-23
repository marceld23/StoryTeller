"""OpenAI tool schemas + side-effect-aware dispatcher.

Tools fall into three classes; the dispatcher reports which class fired so
the graph can route accordingly (e.g. complete_substory triggers in-turn
replanning):

- KNOWLEDGE: retrieval / glossary / world overview / random rolls / dynamics
- MEMORY:    player-fact CRUD + character continuity
- NARRATIVE: substory-plan navigation (advance/complete/get/adjust)
"""

from __future__ import annotations

import json

from .dynamics import INTEGRATION_RULE, StoryDynamics
from .knowledge import KnownFacts
from .random_events import RandomEvents
from .substory import SubstoryPlan

TOOLS: list[dict] = [
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
        "description": "Würfle eine abstrakte Story-Wendung. Subtil einweben, "
                       "NICHT den Bogen kippen.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "remember_fact",
        "description": "Merke dauerhaft, was der Spieler nun kennt. Wenn "
                       "(kind, name) bereits existiert, wird note "
                       "aktualisiert. Bei Überlauf wird der älteste Eintrag "
                       "ohne note automatisch verdrängt.",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string"}, "name": {"type": "string"},
            "note": {"type": "string"}}, "required": ["kind", "name"]}}},
    {"type": "function", "function": {
        "name": "forget_fact",
        "description": "Lösche einen zuvor mit remember_fact gespeicherten "
                       "Fakt. kind ist optional zur Disambiguierung.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "list_known_facts",
        "description": "Gib die aktuell gespeicherten Spieler-Fakten als "
                       "JSON-Liste zurück (optional nach kind filtern).",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string"}}}}},
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
                       "Richtung deutlich ändert.",
        "parameters": {"type": "object", "properties": {
            "change": {"type": "string"}}, "required": ["change"]}}},
    {"type": "function", "function": {
        "name": "track_character",
        "description": "Merke/aktualisiere den Zustand einer Figur (Stimmung, "
                       "Status, offenes Versprechen) — für Konsistenz über "
                       "viele Züge. Kurz halten.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"},
            "state": {"type": "string"}}, "required": ["name", "state"]}}},
]


NARRATIVE_TOOLS: frozenset[str] = frozenset({
    "advance_beat", "complete_substory", "get_substory_plan",
    "adjust_substory_plan",
})
MEMORY_TOOLS: frozenset[str] = frozenset({
    "remember_fact", "forget_fact", "list_known_facts", "track_character",
})


def _gate_filter(
    rows: list[dict],
    gate: dict | None,
    known: KnownFacts,
) -> list[dict]:
    """Hide authored-spoiler categories (fragment / history) from tool
    results unless the curator has explicitly permitted them this turn
    or the player already knows the topic. Other categories pass through."""
    if not rows:
        return rows
    gate = gate or {}
    permits = [p.lower() for p in (gate.get("permitted_reveals") or [])]
    forbidden = [t.lower() for t in (gate.get("forbidden_topics") or [])]
    known_names = {(f.get("name") or "").lower() for f in known.to_list()
                   if isinstance(f.get("name"), str)}
    out: list[dict] = []
    for r in rows:
        text = (r.get("content") or "").lower()
        ft = (r.get("fact_type") or "").lower()
        # always drop hits that touch a forbidden topic
        if any(t and t in text for t in forbidden):
            continue
        if ft in ("fragment", "history"):
            if any(n and n in text for n in known_names):
                out.append(r)
                continue
            if any(p and p in text for p in permits):
                out.append(r)
                continue
            # otherwise: hidden (authored reveal not yet permitted)
            continue
        out.append(r)
    return out


def dispatch_tool(
    name: str,
    args: dict,
    ctx,                       # EngineContext
    substory: SubstoryPlan | None,
    known: KnownFacts,
    char_state: dict[str, str],
    cost,                      # CostTracker
    dynamics: StoryDynamics,
    gate: dict | None = None,  # narration gate from the curator (may be None)
) -> str:
    """Execute one tool call. Mutates substory/known/char_state/cost in place.

    Returns the string content to attach as the tool message.
    """
    cfg = ctx.cfg
    world = ctx.world
    rag = ctx.rag
    locale = (cfg.general.locale or "de")
    from ..i18n import norm
    locale = norm(locale)

    if name == "retrieve_world_fact" and rag is not None:
        rows = rag.retrieve(world.id, args.get("query", ""),
                            fact_type=args.get("fact_type"), locale=locale)
        rows = _gate_filter(rows, gate, known)
        if not rows:
            return ("(nichts Passendes für DIESE Szene zugänglich — bleib "
                    "bei dem, was schon bekannt ist)")
        return json.dumps([r["content"] for r in rows], ensure_ascii=False)

    if name == "lookup_glossary":
        term = (args.get("term") or "").strip().lower()
        # Glossary lookups stay broadly available — terms are usually
        # established as soon as they're spoken. But honour an explicit
        # forbidden_topics entry that names the term.
        forbidden = [t.lower() for t in (gate or {}).get(
            "forbidden_topics") or []]
        if term and any(f and f in term for f in forbidden):
            return "(noch nicht verfügbar)"
        for g in getattr(world, "glossary", []):
            if term and term in g.term.lower():
                return f"{g.term}: {g.definition}"
        if rag is not None:
            rows = rag.retrieve(world.id, args.get("term", ""),
                                fact_type="glossary", locale=locale)
            if rows:
                return rows[0]["content"]
        return "(kein Glossareintrag gefunden)"

    if name == "get_world_overview":
        return json.dumps({
            "beschreibung": world.description,
            "ausgangssituation": world.starting_situation,
            "stimmung": world.mood,
            "ambiente": world.ambience,
            "physik_magie": world.magic_physics,
            "zufallslisten": [t.name for t in world.random_tables],
        }, ensure_ascii=False)

    if name == "roll_random_event":
        return RandomEvents(world).roll(args.get("table_name", ""))

    if name == "roll_story_dynamic":
        return f"{dynamics.roll()} — {INTEGRATION_RULE}"

    if name == "remember_fact":
        return known.remember(
            args.get("kind", "fakt"), args.get("name", ""),
            args.get("note", ""), cap=cfg.story.known_facts_cap)

    if name == "forget_fact":
        nm = (args.get("name") or "").strip()
        if not nm:
            return "(kein Name)"
        knd = (args.get("kind") or "").strip() or None
        return known.forget(nm, knd)

    if name == "list_known_facts":
        knd = (args.get("kind") or "").strip() or None
        return json.dumps(known.query(knd), ensure_ascii=False)

    if name == "advance_beat" and substory:
        substory.advance()
        b = substory.current_beat()
        return f"Sub-Beat -> {b.name if b else '?'}"

    if name == "complete_substory" and substory:
        substory.status = "complete"
        substory.closing_summary = args.get("summary", "")
        return "Substory abgeschlossen — der Architekt plant die nächste."

    if name == "get_substory_plan" and substory:
        # The narrator must not see `resolution_hint` — that is reserved
        # for the planner/curator. We return only navigational fields.
        return json.dumps(substory.model_dump(include={
            "title", "premise", "beats", "cursor",
            "adjustments"}), ensure_ascii=False)

    if name == "adjust_substory_plan" and substory:
        substory.adjustments.append(args.get("change", ""))
        return "Substory-Plan angepasst (wird weiter berücksichtigt)."

    if name == "track_character":
        nm = (args.get("name") or "").strip()
        stt_ = (args.get("state") or "").strip()
        if not nm:
            return "(kein Name)"
        if stt_:
            char_state[nm] = stt_[:160]
        else:
            char_state.pop(nm, None)
        if len(char_state) > 12:
            for k in list(char_state)[:-12]:
                char_state.pop(k, None)
        return f"Figur gemerkt: {nm}"

    return "(Tool nicht verfügbar)"
