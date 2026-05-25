"""LangGraph nodes for the story engine.

All nodes are sync (the OpenAI client used elsewhere is sync). They read state
fields, optionally pull non-serializable handles from `config["configurable"]["ctx"]`
(EngineContext), and return a partial state update (replace-semantics).
"""

from __future__ import annotations

import json
import logging

from langchain_core.runnables.config import RunnableConfig

from ..config import Config
from ..i18n import (
    BEAT_NUDGE,
    BEAT_NUDGE_HARD,
    CHARSTATE_LABEL,
    GATE_NARRATOR_RULE,
    LANG_INSTRUCTION,
    MODERATION_BLOCKED,
    NARRATION_GUIDANCE,
    Q_PREFIXES,
    REPAIR_LANGUAGE_SYS,
    SESSION_CONTINUITY_RULE,
    SUMMARIZER_SYS,
    SYNOPSIS_LABEL,
    VOICE_SAMPLE_LABEL,
    norm,
)
from ..oai import chat_extras, get_chat_client
from .blueprint import BlueprintTracker
from .cost import CostTracker
from .dynamics import INTEGRATION_RULE, StoryDynamics
from .knowledge import KnownFacts
from .ledger import CostLedger
from .moderation import Moderator
from .patterns import world_tone_line as _tone_line
from .state import EngineContext
from .substory import SubstoryPlan, SubstoryPlanner
from .tools import dispatch_tool, tools_for_pressure

log = logging.getLogger("storyteller.engine")


# --- language-drift safety net -------------------------------------------
# qwen-family models occasionally fall into Chinese mid-narration; the same
# pattern can happen with other multilingual LLMs (Cyrillic, Arabic). We
# detect that by counting characters outside Latin/Latin-Extended and, on
# clear drift, issue one repair call to translate the answer back into the
# locale's language while keeping voice and meaning.

def _has_language_drift(text: str) -> bool:
    if not text:
        return False
    drift = 0
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF        # CJK Unified Ideographs
                or 0x3400 <= cp <= 0x4DBF   # CJK Extension A
                or 0x3040 <= cp <= 0x30FF   # Hiragana + Katakana
                or 0x0400 <= cp <= 0x04FF   # Cyrillic
                or 0x0600 <= cp <= 0x06FF):  # Arabic
            drift += 1
            if drift >= 3:
                return True
    return False


def _repair_language(text: str, locale: str, cfg: Config) -> str:
    """One LLM call to clean drifted text. Falls back to the original on
    any error — the broken-language response is better than nothing."""
    try:
        r = get_chat_client(cfg, "story").chat.completions.create(
            model=cfg.models.story_llm,
            messages=[{"role": "system", "content": REPAIR_LANGUAGE_SYS[locale]},
                      {"role": "user", "content": text}],
            **chat_extras(cfg, "story", temperature=0.3),
        )
        CostLedger(cfg).record_chat_usage(
            role="story", model=cfg.models.story_llm, usage=r.usage)
        out = (r.choices[0].message.content or "").strip()
        return out or text
    except Exception as exc:  # pragma: no cover - network
        log.warning("language-repair call failed: %r", exc)
        return text


CO_CREATION = (
    "GRUNDHALTUNG: Du bist Erzähler, aber der eigentliche Sinn ist, den "
    "SPIELER aktiv einzubinden. Denke seine Aktionen, Absichten und Ideen "
    "konsequent mit, greife sie auf, baue darauf auf und lass sie die Welt "
    "verändern. Niemals Multiple-Choice, niemals auf Schienen. Schaffe "
    "lebendige, offene Situationen, auf die er frei reagieren kann."
)

BRIEF_RULE = (
    "\nDER SPIELER STELLT EINE RÜCKFRAGE: Antworte SEHR KURZ (1–2 Sätze), "
    "kläre nur die Frage sachlich. KEINE neue Szene, Handlung NICHT "
    "vorantreiben, keinen Beat wechseln, keine Story-Dynamik."
)

MAX_TOOL_ROUNDS = 8

_TURN_DEFAULTS: dict = {
    "moderation_ok": True,
    "retrieved": [],
    "dyn_hint": None,
    "brief": False,
    "endpoint_error": None,
    "transition": False,
    "response": "",
    "system_prompt": "",
    "pending_tool_calls": [],
    "narrate_iter": 0,
    "just_completed_substory": False,
    "gate": {},
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _thread_id(config: RunnableConfig) -> str | None:
    try:
        return config["configurable"].get("thread_id")
    except Exception:
        return None


def _ctx(config: RunnableConfig) -> EngineContext:
    return config["configurable"]["ctx"]


def _locale(state: dict, ctx: EngineContext) -> str:
    return norm(state.get("locale") or ctx.cfg.general.locale)


def _is_query(text: str, locale: str) -> bool:
    t = (text or "").strip().lower()
    return t.endswith("?") or t.startswith(Q_PREFIXES[locale])


def _is_internal(text: str) -> bool:
    s = (text or "").strip()
    return s.startswith("[") and s.endswith("]")


def _recent(memory: list[dict]) -> str:
    tail = [m["content"] for m in memory[-4:]
            if m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)]
    return " ".join(tail)[:600]


def _effective_pressure(state: dict, ctx) -> float:
    """Apply the global `story_mode` override on top of the heuristic
    pressure carried in state. Settings file is read lazily — it's
    edited by the admin UI and the Pi sysmenu without restarting."""
    from storyteller_hardware.runtime import load_settings

    from .pressure import effective_pressure
    raw = float(state.get("plot_pressure", 1.0))
    try:
        story_mode = (load_settings(ctx.cfg).get("story_mode") or "auto")
    except Exception:
        story_mode = "auto"
    return effective_pressure(raw, story_mode)


def _guidance(cfg: Config, locale: str) -> str:
    if locale == "de":
        return cfg.story.narration_guidance
    return NARRATION_GUIDANCE["en"]


def build_system_prompt(state: dict, ctx: EngineContext) -> str:
    cfg = ctx.cfg
    w = ctx.world
    locale = _locale(state, ctx)

    # Filter RAG hits before showing them to the narrator:
    # - fragment/history are AUTHORED reveal slots and stay hidden unless
    #   (a) the player already knows the topic OR (b) the curator's
    #   `permitted_reveals` mentions it. The curator sees the full list.
    # - place/person/item/glossary/system pass through.
    retrieved_all = state.get("retrieved") or []
    known_names = {(f.get("name") or "").lower()
                   for f in (state.get("known_facts") or [])
                   if isinstance(f.get("name"), str)}
    gate_state = state.get("gate") or {}
    permits = [s.lower() for s in (gate_state.get("permitted_reveals") or [])]

    def _visible(r: dict) -> bool:
        ft = (r.get("fact_type") or "").lower()
        if ft not in ("fragment", "history"):
            return True
        text = (r.get("content") or "").lower()
        if any(n and n in text for n in known_names):
            return True
        return any(p and p in text for p in permits)

    retrieved = [r for r in retrieved_all if _visible(r)]
    facts = "\n".join(f"- [{r['fact_type']}] {r['content']}" for r in retrieved)
    # The legacy "wrap_up" nudge was removed in favour of a hard daily-cap
    # pause handled at the engine boundary — see `engine.turn` and the
    # main idle loop. The story now either runs normally or is paused
    # entirely; there is no in-prompt instruction to wind it down.
    cap = ""
    dyn_hint = state.get("dyn_hint")
    dyn = (f"\n\nMÖGLICHE STORY-DYNAMIK (optional einweben): {dyn_hint}\n"
           f"{INTEGRATION_RULE}" if dyn_hint else "")
    gloss = "; ".join(f"{g.term}={g.definition}"
                      for g in getattr(w, "glossary", [])[:12])
    rtables = ", ".join(t.name for t in w.random_tables)
    # Compact lookup tables for the geography + politics layers. Only
    # names + 1-liner so the prompt stays bounded; full descriptions
    # land via RAG when a name actually surfaces in the scene.
    regions_brief = "; ".join(
        f"{r.name}: {(r.description or '').splitlines()[0]}"
        for r in (getattr(w, "regions", []) or [])[:12])
    factions_brief = "; ".join(
        f"{f.name} ({f.goals})" if f.goals else f.name
        for f in (getattr(w, "factions", []) or [])[:8])
    tm = getattr(w, "tech_magic", None)
    if tm is not None and (tm.description or tm.rules):
        rule_lines = "\n".join(f"  - {r}" for r in (tm.rules or [])[:7])
        tm_block = (
            f"\nTECH/MAGIE-SYSTEM ({tm.kind}): "
            f"{tm.description or '–'}\nREGELN:\n"
            f"{rule_lines or '  –'}"
            + (f"\nKOSTEN/RISIKO: {tm.cost_or_risk}\n"
               if tm.cost_or_risk else "\n"))
    else:
        tm_block = ""

    vsample = (f"{VOICE_SAMPLE_LABEL[locale]}\n{w.voice_sample}\n"
               if getattr(w, "voice_sample", "") else "")
    synopsis = state.get("synopsis") or ""
    syn = (f"{SYNOPSIS_LABEL[locale]}\n{synopsis}\n\n" if synopsis else "")

    char_state = state.get("char_state") or {}
    chars = "; ".join(f"{k}: {v}" for k, v in char_state.items())
    chars = f"{CHARSTATE_LABEL[locale]} {chars}\n\n" if chars else ""

    beat_turns = state.get("beat_turns", 0)
    brief = state.get("brief", False)
    # Pressure-aware beat-nudge threshold + substory-block tier.
    from storyteller_hardware.runtime import load_settings

    from .pressure import (
        beat_nudge_threshold,
        effective_pressure,
        substory_block_mode,
    )
    raw_pressure = float(state.get("plot_pressure", 1.0))
    try:
        _story_mode = (load_settings(cfg).get("story_mode") or "auto")
    except Exception:
        _story_mode = "auto"
    pressure = effective_pressure(raw_pressure, _story_mode)
    nudge_thr = beat_nudge_threshold(pressure, cfg)
    # Three nudge tiers, scaling with dwell:
    #   < threshold              → no nudge
    #   threshold .. 2× threshold→ soft BEAT_NUDGE (existing copy)
    #   >= 2× threshold OR last
    #     beat of the substory   → hard BEAT_NUDGE_HARD (imperative)
    # The hard tier exists because the soft nudge alone wasn't enough
    # to keep some narrators from looping (saw 18 dwell turns in the
    # field). At a high dwell the LLM needs an unambiguous directive.
    nudge = ""
    if not brief and nudge_thr < 10**5 and beat_turns >= nudge_thr:
        _sub = state.get("substory") or {}
        _beats = _sub.get("beats") or []
        _at_last = bool(_beats and int(_sub.get("cursor", 0))
                        >= len(_beats) - 1)
        if beat_turns >= 2 * nudge_thr or _at_last:
            nudge = BEAT_NUDGE_HARD[locale]
        else:
            nudge = BEAT_NUDGE[locale]
    block_mode = substory_block_mode(pressure, cfg)

    macro = BlueprintTracker(w.active_blueprint(state.get("blueprint_choice", 0)),
                              state.get("macro_index", 0))

    sub_dict = state.get("substory")
    sub_block = ""
    macro_block = ""
    if block_mode == "full":
        macro_block = f"MAKRO-SPANNUNGSBOGEN:\n{macro.guidance()}\n\n"
        if sub_dict:
            sub = SubstoryPlan(**sub_dict)
            sub_block = sub.as_prompt_block(state.get("transition", False))
    elif block_mode == "ambient":
        # Halbe Höhe: nur Hook + aktueller Beat-Name, kein Goal/Tension.
        # Der Erzähler weiß, dass es eine Mission im Hinterkopf gibt,
        # spürt aber keinen Druck sie aktiv voranzutreiben.
        if sub_dict:
            sub = SubstoryPlan(**sub_dict)
            cur = sub.current_beat()
            beat_name = cur.name if cur else "—"
            sub_block = (
                f"AKTIVE STORY-RICHTUNG (locker, nicht dringend): "
                f"{sub.hook}\n"
                f"Aktueller Beat: {beat_name}. Trag das im Hintergrund mit, "
                f"aber dräng den Spieler NICHT in diese Richtung — folge "
                f"seinen Initiativen.\n"
            )
    else:  # "free"
        sub_block = (
            "FREIE ERKUNDUNG: Es gibt aktuell keinen vorgegebenen "
            "Spannungsbogen. Greif Spieler-Initiativen ausdrücklich auf — "
            "sie sind jetzt der wichtigste Kompass. Lass die Welt "
            "REAGIEREN, nicht SCHIEBEN. Erfinde kleine Mikro-Momente "
            "und Beobachtungen, würfle gerne aus den Zufallslisten "
            "(`roll_random_event`) wenn die Szene Atem braucht. Wenn der "
            "Spieler einen Aufhänger entwickelt, der Substanz hat, bau "
            "leise darauf auf — aber niemals einen vor-geplanten Plot "
            "aufzwingen.\n"
        )

    known_summary = KnownFacts(state.get("known_facts") or []).summary()

    # --- recent NPC candidates → track_character hint ---
    # Names the narrator introduced in past turns that aren't yet
    # tracked in char_state. Populated by finalize() via
    # `_extract_npc_candidates`; cleared by dispatch_tools when
    # track_character actually fires for one of them.
    npc_hint = ""
    candidates = [c for c in (state.get("recent_npc_candidates") or [])
                  if c and c.lower() not in {
                      k.lower() for k in (state.get("char_state") or {})}]
    if candidates:
        npc_hint = (
            f"NEU AUFGETAUCHTE NPCs / Akteure (zuletzt von DIR eingeführt, "
            f"noch NICHT mit track_character vermerkt): "
            f"{', '.join(candidates[:6])}. "
            f"Wenn einer dieser weiter mitspielt oder reagiert, RUFE "
            f"jetzt `track_character` mit kurzer Stimmung/Status auf — "
            f"sonst reagiert er nächsten Zug ohne Erinnerung.\n\n")

    # --- gate block (only when the curator has produced one this turn) ---
    gate_block = ""
    if gate_state:
        intent = (gate_state.get("scene_intent") or "").strip()
        permitted = ", ".join(
            p for p in (gate_state.get("permitted_reveals") or []) if p)
        forbidden = ", ".join(
            t for t in (gate_state.get("forbidden_topics") or []) if t)
        nudge_tone = (gate_state.get("tone_nudge") or "").strip()
        gate_block = (
            f"{GATE_NARRATOR_RULE[locale]}\n"
            f"Szenen-Ziel: {intent or '–'}\n"
            f"Permitted reveals: {permitted or '(keine zusätzlichen)'}\n"
            f"Forbidden topics: {forbidden or '(keine)'}\n"
            + (f"Ton-Hinweis: {nudge_tone}\n" if nudge_tone else "")
            + "\n"
        )

    return (
        f"Du bist der ERZÄHLER der Welt {w.name} ({w.genre}).\n"
        f"{w.description}\nSpielerrolle: {w.player_role}\n"
        f"Erzählstil: {w.narration_style}\n"
        f"{vsample}"
        f"STIMMUNG: {w.mood or '–'}\nAMBIENTE: {w.ambience or '–'}\n"
        f"PHYSIK/MAGIE: {w.magic_physics or '–'}\n"
        f"{tm_block}"
        f"{_tone_line(w)}\n"
        f"AUSGANGSSITUATION: {w.starting_situation or '–'}\n"
        f"REGIONEN (Orte liegen in einer Region; Details via "
        f"retrieve_world_fact): {regions_brief or '–'}\n"
        f"FRAKTIONEN (Personen können einer angehören; Details via "
        f"retrieve_world_fact): {factions_brief or '–'}\n"
        f"GLOSSAR (Begriffe konsistent verwenden; vollständig via "
        f"lookup_glossary): {gloss or '–'}\n"
        f"ZUFALLSLISTEN (konkret, bei passender Gelegenheit via "
        f"roll_random_event ziehen): {rtables or '–'}\n\n"
        f"{CO_CREATION}\n\n"
        f"{macro_block}"
        f"{sub_block}\n\n"
        f"{syn}"
        f"Dem Spieler bereits bekannt: {known_summary}\n\n"
        f"{chars}"
        f"{npc_hint}"
        f"{gate_block}"
        f"Hintergrundwissen (nur einbauen, wenn es JETZT zur Szene passt; "
        f"NICHT aufzählen):\n{facts or '(keine Treffer)'}{cap}{dyn}\n\n"
        f"{_guidance(cfg, locale)}\n{LANG_INSTRUCTION[locale]}\n"
        f"{SESSION_CONTINUITY_RULE[locale]}\n"
        "Tools still nutzen, das Ergebnis IMMER in einfache, kurze "
        "Erzählung verwandeln, niemals Fakten oder Listen vorlesen.\n"
        "- BEI EXPLIZITER SPIELER-FRAGE nach Welt-Fakten (Wer ist…? Wo "
        "ist…? Was ist…? Was bedeutet…?) RUFE ZUERST das passende Tool "
        "auf (`retrieve_world_fact` für Orte/Personen/Geschichte, "
        "`lookup_glossary` für Begriffe). Antworte NICHT aus dem "
        "Stegreif — Konsistenz hängt davon ab.\n"
        # PROAKTIV nutzen (war vorher zu passiv formuliert — Narrator hat
        # die Tools komplett liegen lassen). Klare Trigger pro Tool, statt
        # generischem "nach Bedarf":
        "- ATMOSPHÄRE & WENDUNG (proaktiv, nicht warten):\n"
        "  • `roll_random_event` wenn die Szene einen Welt-Moment oder "
        "    eine Atem-Pause braucht (mind. 1× pro Substory anstreben).\n"
        "  • `roll_story_dynamic` wenn die Erzählung in einer Schleife "
        "    droht ODER beim Übergang in einen neuen Sub-Beat (subtil "
        "    einweben, NICHT als Hauptthema setzen).\n"
        "  • `track_character` IMMER wenn ein NPC zum ZWEITEN Mal "
        "    auftaucht oder eine klare Reaktion/Position zeigt "
        "    (Truppführer, Wirt, KI-Stimmen, Kapitän). State knapp "
        "    halten: Stimmung, Status, ein offenes Versprechen. "
        "    Ohne diese Tracks reagieren NPCs jeden Zug aus dem Nichts.\n"
        "  • `remember_fact` für DAUERHAFTE Welt-/Story-Bezugspunkte, "
        "    die der Spieler eingebracht oder gerade entdeckt hat "
        "    (Items, Hinweise, Verbündete, Schauplätze)."
        + nudge
        + (BRIEF_RULE if brief else "")
    )


# --------------------------------------------------------------------------
# nodes
# --------------------------------------------------------------------------

def init_turn(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    # Pick up admin/.env changes (models, endpoints, temperatures, key)
    # without restarting: load_config rebuilds only when a watched file
    # changed, so this is a few stat() calls per turn otherwise.
    from ..config import load_config
    ctx.cfg = load_config()
    out: dict = dict(_TURN_DEFAULTS)
    # Persist session defaults if missing
    if "memory" not in state:
        out["memory"] = []
    if "macro_index" not in state:
        out["macro_index"] = 0
    if "known_facts" not in state:
        out["known_facts"] = []
    if "synopsis" not in state:
        out["synopsis"] = ""
    if "char_state" not in state:
        out["char_state"] = {}
    if "beat_turns" not in state:
        out["beat_turns"] = 0
    if "cost" not in state:
        out["cost"] = {}
    if "pending_fold" not in state:
        out["pending_fold"] = []
    # Soft plot-pressure defaults — see storyteller_core.story.pressure.
    # Warm start at 1.0 so a fresh session begins with full plot machinery;
    # the heuristic in finalize() will pull it down only if the player
    # actually drifts.
    if "plot_pressure" not in state:
        out["plot_pressure"] = 1.0
    if "direction_window" not in state:
        out["direction_window"] = []
    if "dormant_substory" not in state:
        out["dormant_substory"] = None
    if "recent_npc_candidates" not in state:
        out["recent_npc_candidates"] = []
    if "locale" not in state:
        out["locale"] = _locale(state, ctx)
    return out


def moderate(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    user_text = state.get("user_text", "")
    if _is_internal(user_text):
        if ctx.transcript:
            # internal directives bypass moderation entirely
            ctx.transcript.note(f"[internal] {user_text[:80]}")
        return {"moderation_ok": True}
    # Skip the moderation HTTP round-trip for trivially short, benign-looking
    # turns ("Ja", "Nein", "Vielen Dank"). Saves ~1.3s/turn on the hot path.
    # Threshold is intentionally conservative — anything with > 3 words OR
    # > 24 chars OR any non-letter content goes through the full check.
    stripped = (user_text or "").strip()
    if 0 < len(stripped) <= 24:
        words = stripped.split()
        if len(words) <= 3 and all(
                all(c.isalpha() or c in "äöüÄÖÜß-'." for c in w)
                for w in words):
            if ctx.transcript:
                ctx.transcript.user(user_text)
                ctx.transcript.note("[moderate] skipped (short benign input)")
            return {"moderation_ok": True}
    if ctx.transcript:
        ctx.transcript.user(user_text)
    ok, flagged, _scores = Moderator(ctx.cfg).check(user_text)
    if ctx.transcript:
        ctx.transcript.moderation(ok, flagged)
    return {"moderation_ok": ok}


def route_after_moderate(state: dict) -> str:
    return "fanout" if state.get("moderation_ok", True) else "blocked_finalize"


def blocked_finalize(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    locale = _locale(state, ctx)
    msg = MODERATION_BLOCKED[locale]
    if ctx.transcript:
        cost = CostTracker.restore(ctx.cfg, state.get("cost") or {})
        ctx.transcript.assistant(msg, "blocked", cost.usd)
    return {"response": msg}


def fanout(state: dict, config: RunnableConfig) -> dict:
    """No-op pass-through; exists so the four pre-narrator nodes have a
    single deterministic source they can fan out from."""
    return {}


def compute_flags(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    locale = _locale(state, ctx)
    user_text = state.get("user_text", "")
    return {
        "brief": _is_query(user_text, locale),
    }


def ensure_substory(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    cfg = ctx.cfg
    locale = _locale(state, ctx)

    pressure = _effective_pressure(state, ctx)
    from .pressure import substory_planning_enabled

    sub_dict = state.get("substory")
    dormant = state.get("dormant_substory")

    # Below the planning threshold: skip the planner entirely. If a
    # substory is live, park it into dormant so the next pressure spike
    # can revive it instead of forcing a fresh plan.
    if not substory_planning_enabled(pressure, cfg):
        if sub_dict and sub_dict.get("status") != "dormant":
            parked = dict(sub_dict)
            parked["status"] = "dormant"
            if ctx.transcript:
                ctx.transcript.note(
                    f"[pressure] parking substory '{parked.get('title')}'"
                    f" — pressure={pressure:.2f}")
            return {"substory": None, "dormant_substory": parked}
        return {}

    # Above the planning threshold: if we have a dormant, revive it
    # rather than asking the planner for a brand-new arc.
    if (not sub_dict or sub_dict.get("status") == "complete") and dormant:
        revived = dict(dormant)
        revived["status"] = "active"
        if ctx.transcript:
            ctx.transcript.note(
                f"[pressure] reviving dormant substory "
                f"'{revived.get('title')}' — pressure={pressure:.2f}")
        return {"substory": revived, "dormant_substory": None,
                "transition": True, "beat_turns": 0}

    # A previously failed plan (`status="planning_failed"`) must be re-
    # attempted, not treated as an active arc. Same for "complete" and
    # "dormant" which we already handle above.
    if sub_dict and sub_dict.get("status") not in (
            "complete", "dormant", "planning_failed"):
        return {}  # no change

    cost = CostTracker.restore(cfg, state.get("cost") or {})
    planner = SubstoryPlanner(cfg, cost, ledger=CostLedger(cfg),
                              thread_id=_thread_id(config),
                              world_id=getattr(ctx.world, "id", None),
                              transcript=ctx.transcript)

    prev_summary = sub_dict.get("closing_summary", "") if sub_dict else ""
    macro_idx = state.get("macro_index", 0)
    transition = bool(sub_dict)
    known_summary = KnownFacts(state.get("known_facts") or []).summary()
    recent = _recent(state.get("memory") or [])

    # Multi-blueprint pick: on a transition (= previous substory just
    # ended), re-roll the variant choice so each arc can feel different.
    # On a fresh fan-out (no prior substory) we also pick once. Single-
    # variant worlds short-circuit inside choose_blueprint_variant.
    from .substory import choose_blueprint_variant
    blueprint_choice = choose_blueprint_variant(
        cfg, ctx.world,
        known_summary=known_summary, recent=recent,
        previous_summary=prev_summary, locale=locale,
        cost=cost, ledger=CostLedger(cfg),
        thread_id=_thread_id(config),
        world_id=getattr(ctx.world, "id", None),
        transcript=ctx.transcript)
    active_bp = ctx.world.active_blueprint(blueprint_choice)
    if transition:
        # advance the macro one beat after a substory completes
        if macro_idx < len(active_bp.beats) - 1:
            macro_idx += 1
        # Reset macro_index when switching to a different variant —
        # the old index referred to the previous variant's beat list,
        # which may not exist in the new variant.
        if blueprint_choice != state.get("blueprint_choice", 0):
            macro_idx = 0

    macro = BlueprintTracker(active_bp, macro_idx)

    dyn_hint = ""
    if cfg.story.dynamics_in_planning:
        dyn_hint = StoryDynamics().roll()

    new_sub = planner.plan_next(
        ctx.world, ctx.rag, macro.guidance(), known_summary, recent,
        prev_summary, dyn_hint, locale=locale,
    )

    out = {
        "substory": new_sub.model_dump(),
        "macro_index": macro_idx,
        "blueprint_choice": blueprint_choice,
        "transition": transition,
        "beat_turns": 0,
        "cost": cost.snapshot(),
    }
    if ctx.transcript:
        ctx.transcript.note(f"[planner] new substory: {new_sub.title}")
    return out


def retrieve_rag(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    if not ctx.rag:
        return {"retrieved": []}
    user_text = state.get("user_text", "")
    locale = _locale(state, ctx)
    recent = _recent(state.get("memory") or [])
    q = f"{user_text} {recent}".strip() if recent else user_text
    try:
        rows = ctx.rag.retrieve(ctx.world.id, q, locale=locale)
    except Exception as exc:
        log.warning("RAG retrieval failed: %r", exc)
        rows = []
    # Hits stay un-filtered here — the curator sees them all, and the
    # narrator-visible slice is filtered in build_system_prompt where the
    # gate's permitted_reveals + known_facts can be cross-referenced.
    return {"retrieved": rows}


def curate(state: dict, config: RunnableConfig) -> dict:
    """Run the narration "gate" — a small LLM call that decides per turn
    which AUTHORED reveals the narrator may use, and which authored topics
    must stay hidden today. Skipped when disabled OR when the soft
    plot-pressure is below the gate-on threshold (free-exploration tier)."""
    ctx = _ctx(config)
    cfg = ctx.cfg
    if not getattr(cfg.story, "narration_gate_enabled", True):
        return {}
    pressure = _effective_pressure(state, ctx)
    from .pressure import gate_max_reveals, gate_should_run
    if not gate_should_run(pressure, cfg):
        if ctx.transcript:
            ctx.transcript.note(
                f"[pressure] gate skipped (pressure={pressure:.2f})")
        return {}
    from .curator import Curator

    cost = CostTracker.restore(cfg, state.get("cost") or {})
    locale = _locale(state, ctx)
    sub_dict = state.get("substory")
    macro_idx = state.get("macro_index", 0) or 0
    active_bp = ctx.world.active_blueprint(state.get("blueprint_choice", 0))
    future_beats = list(active_bp.beats[macro_idx + 1:])
    known_summary = KnownFacts(state.get("known_facts") or []).summary()
    recent = _recent(state.get("memory") or [])
    max_reveals = gate_max_reveals(pressure, cfg)
    try:
        gate = Curator(cfg, cost, ledger=CostLedger(cfg),
                       thread_id=_thread_id(config),
                       world_id=getattr(ctx.world, "id", None)).gate(
            ctx.world, sub_dict, future_beats,
            state.get("retrieved") or [],
            known_summary, recent, state.get("user_text", ""),
            int(state.get("beat_turns", 0)), locale=locale,
            max_reveals=max_reveals)
    except Exception as exc:
        log.warning("curator gate failed: %r", exc)
        return {}
    # Log the gate decision as a transcript note so admins can see in
    # /transcripts which authored reveals were unlocked / which topics
    # were held back THIS turn.
    if ctx.transcript:
        permit = "; ".join(gate.permitted_reveals) or "(none)"
        forbid = "; ".join(gate.forbidden_topics) or "(none)"
        intent = gate.scene_intent or "—"
        tone = gate.tone_nudge or "—"
        ctx.transcript.note(
            f"[gate] intent={intent} | permit={permit} | "
            f"forbid={forbid} | tone={tone}")
    return {"gate": gate.model_dump(), "cost": cost.snapshot()}


def roll_dynamic(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    cfg = ctx.cfg
    user_text = state.get("user_text", "")
    locale = _locale(state, ctx)
    if _is_query(user_text, locale):
        return {"dyn_hint": None}
    dyn = StoryDynamics().maybe(cfg.story.dynamic_event_prob)
    return {"dyn_hint": dyn}


def build_prompt(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    sys_prompt = build_system_prompt(state, ctx)
    user_text = state.get("user_text", "")
    # Append user message to memory ONCE here, before the narrate loop starts.
    memory = list(state.get("memory") or [])
    memory.append({"role": "user", "content": user_text})
    return {"system_prompt": sys_prompt, "memory": memory}


def narrate(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    cfg = ctx.cfg
    iteration = state.get("narrate_iter", 0)
    use_tools = iteration < MAX_TOOL_ROUNDS

    sys_prompt = state.get("system_prompt", "")
    messages = [{"role": "system", "content": sys_prompt}] + list(state.get("memory") or [])

    kw: dict = {
        "model": cfg.models.story_llm,
        "messages": messages,
    }
    # chat_extras handles two OpenAI constraints: reasoning models reject
    # custom sampling knobs, AND chat completions rejects tools+reasoning
    # for gpt-5.x. We pass tools=use_tools so reasoning gets dropped on
    # turns that need function calls (every tool round), keeping
    # temperature/penalties — non-tool turns (final narration after tool
    # roundtrip) still get reasoning if configured.
    kw.update(chat_extras(
        cfg, "story",
        temperature=cfg.models.llm_temperature,
        frequency_penalty=cfg.models.frequency_penalty,
        presence_penalty=cfg.models.presence_penalty,
        tools=use_tools,
    ))
    if use_tools:
        # Hide substory-tools (advance_beat / complete_substory / get/adjust)
        # when pressure has dropped below the substory-tools threshold —
        # they don't apply when there's no active arc to drive.
        pressure = _effective_pressure(state, ctx)
        thr = float(getattr(cfg.story, "pressure_substory_tools", 0.30))
        kw["tools"] = tools_for_pressure(pressure,
                                          substory_tools_threshold=thr)

    if ctx.transcript and getattr(cfg, "transcripts", None) \
            and cfg.transcripts.capture_prompts:
        ctx.transcript.prompt(cfg.models.story_llm, messages, tools=use_tools)

    import time as _time
    t_call = _time.perf_counter()
    mode = ("reason=" + kw["reasoning_effort"]) if "reasoning_effort" in kw \
           else f"temp={kw.get('temperature', '?')}"
    log.info("narrate -> %s iter=%d tools=%s %s msgs=%d",
             cfg.models.story_llm, iteration, use_tools, mode, len(messages))
    try:
        resp = get_chat_client(cfg, "story").chat.completions.create(**kw)
        dt = _time.perf_counter() - t_call
        usage = getattr(resp, "usage", None)
        if usage is not None:
            log.info("narrate <- %.2fs in=%s out=%s reason_out=%s",
                     dt,
                     getattr(usage, "prompt_tokens", "?"),
                     getattr(usage, "completion_tokens", "?"),
                     getattr(getattr(usage, "completion_tokens_details",
                                     None), "reasoning_tokens", "?"))
        else:
            log.info("narrate <- %.2fs (no usage reported)", dt)
        from ..health import HealthRegistry
        HealthRegistry.get(cfg).record_ok(
            "story",
            base_url=getattr(cfg.models.story_endpoint, "base_url", "") or "",
            model=cfg.models.story_llm)
    except Exception as exc:
        dt = _time.perf_counter() - t_call
        log.warning("narrate FAILED after %.2fs: %r", dt, exc)
        # Roll back the user message we appended in build_prompt, so the
        # checkpoint has no hole. The engine layer raises EndpointError
        # after inspecting `endpoint_error` in the returned state — that
        # keeps LangGraph's commit semantics intact (this dict gets
        # persisted; the error surfaces only at engine.turn()).
        mem = list(state.get("memory") or [])
        if mem and mem[-1].get("role") == "user":
            mem.pop()
        from ..health import HealthRegistry, wrap
        err = wrap("story",
                   base_url=getattr(cfg.models.story_endpoint, "base_url",
                                    "") or "",
                   model=cfg.models.story_llm)(exc)
        HealthRegistry.get(cfg).record_error(err)
        return {
            "response": "",
            "memory": mem,
            "pending_tool_calls": [],
            "endpoint_error": {
                "role": err.role, "kind": err.kind,
                "http_status": err.http_status, "base_url": err.base_url,
                "model": err.model, "detail": err.detail,
            },
        }

    cost = CostTracker.restore(cfg, state.get("cost") or {})
    _usd = cost.record_chat(resp.usage, role="story",
                             model=cfg.models.story_llm)
    if resp.usage is not None:
        CostLedger(cfg).record(
            kind="chat", usd=_usd,
            thread_id=_thread_id(config),
            world_id=getattr(ctx.world, "id", None),
            model=cfg.models.story_llm,
            chat_in=getattr(resp.usage, "prompt_tokens", 0) or 0,
            chat_out=getattr(resp.usage, "completion_tokens", 0) or 0)
    cost_snap = cost.snapshot()

    msg = resp.choices[0].message

    if use_tools and msg.tool_calls:
        memory = list(state.get("memory") or [])
        memory.append(msg.model_dump(exclude_none=True))
        pending = [tc.model_dump() for tc in msg.tool_calls]
        return {
            "memory": memory,
            "cost": cost_snap,
            "pending_tool_calls": pending,
            "narrate_iter": iteration + 1,
        }

    text = (msg.content or "").strip()
    if _has_language_drift(text):
        locale = _locale(state, ctx)
        log.warning("Sprach-Drift im Erzähler-Output erkannt — Repair-Call (locale=%s)", locale)
        text = _repair_language(text, locale, cfg)
    memory = list(state.get("memory") or [])
    memory.append({"role": "assistant", "content": text})
    return {
        "memory": memory,
        "cost": cost_snap,
        "response": text,
        "pending_tool_calls": [],
    }


def route_after_narrate(state: dict) -> str:
    if state.get("pending_tool_calls"):
        return "dispatch_tools"
    return "finalize"


def dispatch_tools(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    cfg = ctx.cfg

    sub_dict = state.get("substory")
    substory = SubstoryPlan(**sub_dict) if sub_dict else None
    known = KnownFacts(list(state.get("known_facts") or []))
    char_state = dict(state.get("char_state") or {})
    cost = CostTracker.restore(cfg, state.get("cost") or {})
    dynamics = StoryDynamics()

    tool_messages: list[dict] = []
    just_completed = False
    advanced_beat = False

    for tc in state.get("pending_tool_calls") or []:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}

        result = dispatch_tool(
            name, args, ctx, substory, known, char_state, cost, dynamics,
            gate=state.get("gate") or {},
        )

        if name == "complete_substory" and substory is not None:
            just_completed = True
        if name == "advance_beat":
            advanced_beat = True
        # Once the narrator actually tracks a character, drop them from
        # the recent_npc_candidates hint list (they're now in char_state).
        if name == "track_character":
            tracked_name = (args.get("name") or "").strip().lower()
            if tracked_name:
                npc_cands = list(state.get("recent_npc_candidates") or [])
                npc_cands = [c for c in npc_cands
                             if c.strip().lower() != tracked_name]
                # We'll write this back at the end via `out["recent_npc_candidates"]`
                state["recent_npc_candidates"] = npc_cands

        tool_messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": str(result),
        })
        if ctx.transcript:
            ctx.transcript.tool(name, args, result)
            # Promote planner-shape tool calls to dedicated [planner]
            # markers in the transcript so admins scanning a session
            # don't have to expand each tool entry to see the arc beats.
            if substory is not None and name in (
                    "advance_beat", "complete_substory",
                    "adjust_substory_plan"):
                _beats = substory.beats or []
                _cur = int(substory.cursor)
                _name = (_beats[_cur].name
                         if 0 <= _cur < len(_beats) else "?")
                if name == "advance_beat":
                    ctx.transcript.note(
                        f"[planner] advance_beat → beat #{_cur + 1}/"
                        f"{len(_beats)} '{_name}'")
                elif name == "complete_substory":
                    summ = (args.get("summary") or "")[:120]
                    ctx.transcript.note(
                        f"[planner] complete_substory: '{substory.title}'"
                        + (f" — {summ}" if summ else ""))
                else:
                    chg = (args.get("change") or "")[:160]
                    ctx.transcript.note(
                        f"[planner] adjust_substory_plan: {chg}")

    memory = list(state.get("memory") or []) + tool_messages
    out: dict = {
        "memory": memory,
        "known_facts": known.to_list(),
        "char_state": char_state,
        "pending_tool_calls": [],
        "just_completed_substory": just_completed,
        # Persist any track_character-induced filtering of the NPC
        # candidate hint list (see the track_character branch above).
        "recent_npc_candidates": list(
            state.get("recent_npc_candidates") or []),
    }
    if substory is not None:
        out["substory"] = substory.model_dump()
    if advanced_beat:
        out["beat_turns"] = 0
    return out


def route_after_dispatch(state: dict) -> str:
    return "replan" if state.get("just_completed_substory") else "narrate"


def replan(state: dict, config: RunnableConfig) -> dict:
    """In-turn replan after the narrator called complete_substory.

    Reuses the same logic as `ensure_substory` but always runs; produced
    substory replaces the just-completed one. Sets transition=True so the
    next system prompt softly bridges the arcs.

    If the soft plot-pressure has fallen below the planning threshold,
    we skip the planner instead — the now-completed arc gets parked
    into dormant so a future pressure spike can revive it (the player
    just closed an arc and wants to breathe, not be marched into the
    next one).
    """
    ctx = _ctx(config)
    cfg = ctx.cfg
    locale = _locale(state, ctx)

    from .pressure import substory_planning_enabled
    pressure = _effective_pressure(state, ctx)
    if not substory_planning_enabled(pressure, cfg):
        # Park the just-completed substory as dormant; the engine returns
        # to a free-exploration tier with no active substory.
        sub = state.get("substory")
        parked = None
        if sub:
            parked = dict(sub)
            parked["status"] = "dormant"
        if ctx.transcript:
            ctx.transcript.note(
                f"[pressure] replan skipped (pressure={pressure:.2f}); "
                f"completed substory parked as dormant")
        return {
            "substory": None,
            "dormant_substory": parked,
            "transition": False,
            "beat_turns": 0,
            "just_completed_substory": False,
            "system_prompt": build_system_prompt(
                {**state, "substory": None, "dormant_substory": parked,
                 "transition": False}, ctx),
        }

    cost = CostTracker.restore(cfg, state.get("cost") or {})
    planner = SubstoryPlanner(cfg, cost, ledger=CostLedger(cfg),
                              thread_id=_thread_id(config),
                              world_id=getattr(ctx.world, "id", None),
                              transcript=ctx.transcript)

    sub_dict = state.get("substory") or {}
    prev_summary = sub_dict.get("closing_summary", "")
    macro_idx = state.get("macro_index", 0)
    known_summary = KnownFacts(state.get("known_facts") or []).summary()
    recent = _recent(state.get("memory") or [])

    # In-turn replan also re-rolls the variant choice so back-to-back
    # arcs in one session can structurally differ. choose_blueprint_variant
    # is a no-op for single-variant worlds.
    from .substory import choose_blueprint_variant
    blueprint_choice = choose_blueprint_variant(
        cfg, ctx.world,
        known_summary=known_summary, recent=recent,
        previous_summary=prev_summary, locale=locale,
        cost=cost, ledger=CostLedger(cfg),
        thread_id=_thread_id(config),
        world_id=getattr(ctx.world, "id", None),
        transcript=ctx.transcript)
    active_bp = ctx.world.active_blueprint(blueprint_choice)
    if macro_idx < len(active_bp.beats) - 1:
        macro_idx += 1
    if blueprint_choice != state.get("blueprint_choice", 0):
        macro_idx = 0

    macro = BlueprintTracker(active_bp, macro_idx)
    dyn_hint = StoryDynamics().roll() if cfg.story.dynamics_in_planning else ""

    new_sub = planner.plan_next(
        ctx.world, ctx.rag, macro.guidance(), known_summary, recent,
        prev_summary, dyn_hint, locale=locale,
    )
    if ctx.transcript:
        ctx.transcript.note(f"[planner/in-turn] new substory: {new_sub.title}")

    return {
        "substory": new_sub.model_dump(),
        "macro_index": macro_idx,
        "blueprint_choice": blueprint_choice,
        "transition": True,
        "beat_turns": 0,
        "cost": cost.snapshot(),
        "just_completed_substory": False,
        # System prompt must be rebuilt for the next narrate iteration.
        "system_prompt": build_system_prompt(
            {**state,
             "substory": new_sub.model_dump(),
             "macro_index": macro_idx,
             "transition": True},
            ctx,
        ),
    }


def finalize(state: dict, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    cfg = ctx.cfg
    text = state.get("response", "") or ""

    update: dict = {}
    # Bump beat_turns only on a real narration (not on a rückfrage / brief mode)
    if text and not state.get("brief", False):
        update["beat_turns"] = state.get("beat_turns", 0) + 1

    # Clear transition flag so the next turn doesn't keep saying "ÜBERGANG"
    update["transition"] = False

    # Auto-NPC-candidate extraction: scan the narrator's reply for
    # capitalised proper-noun-looking tokens that aren't world entities
    # AND aren't tracked yet. Merge into recent_npc_candidates (FIFO,
    # cap _NPC_CANDIDATE_CAP). build_system_prompt renders these as a
    # short track_character hint NEXT turn so the narrator doesn't
    # re-introduce the same NPC from scratch each turn. dispatch_tools
    # removes a name from this list when track_character actually fires.
    if text and not state.get("brief", False):
        new_candidates = _extract_npc_candidates(
            text, ctx.world, state.get("char_state") or {})
        if new_candidates:
            current = list(state.get("recent_npc_candidates") or [])
            # Skip duplicates, append at end, FIFO-cap.
            cur_low = {c.lower() for c in current}
            for n in new_candidates:
                if n.lower() not in cur_low:
                    current.append(n)
                    cur_low.add(n.lower())
            update["recent_npc_candidates"] = current[-_NPC_CANDIDATE_CAP:]

    # Soft-replan after extreme dwell: if the same sub-beat has run for
    # >= cfg.story.beat_stagnation_replan turns without advance_beat
    # firing, mark the current substory as `planning_failed`. The next
    # ensure_substory call treats that the same way as a fallback stub
    # — re-plans from scratch with the latest memory + synopsis.
    # Why this exists: even with hard BEAT_NUDGE some narrators get
    # stuck in a loop (saw 18 dwell turns in the wild). Auto-replanning
    # at a clear threshold breaks the loop without losing player state.
    if text and not state.get("brief", False):
        next_dwell = state.get("beat_turns", 0) + 1
        stag_thr = int(getattr(cfg.story, "beat_stagnation_replan", 0))
        sub = state.get("substory") or {}
        if (stag_thr > 0 and next_dwell >= stag_thr
                and sub and sub.get("status") == "active"):
            forced = dict(sub)
            forced["status"] = "planning_failed"
            update["substory"] = forced
            update["beat_turns"] = 0
            if ctx.transcript:
                ctx.transcript.note(
                    f"[planner] forced replan: {next_dwell} dwell turns "
                    f"on beat #{sub.get('cursor', 0) + 1} without "
                    f"advance_beat — re-planning next turn.")

    if ctx.transcript and text:
        from .state import EngineContext  # noqa: F401
        cost = CostTracker.restore(cfg, state.get("cost") or {})
        # state machine label: planning if no substory, else status
        sub = state.get("substory")
        label = "planning" if not sub else sub.get("status", "in_substory")
        ctx.transcript.assistant(text, label, cost.usd)

    # ---- soft plot-pressure update ---------------------------------------
    # Build this turn's TurnSignal from already-existing telemetry, slide
    # it into the window, recompute the target, EMA-smooth, and emit a
    # transcript line so the admin can see what the heuristic decided.
    if text and not state.get("brief", False):
        from .pressure import (
            WINDOW_SIZE,
            classify,
            compute_target_pressure,
            effective_pressure,
            signal_to_dict,
            tiebreaker_should_run,
            update_pressure,
        )
        tool_calls = _collect_tool_calls_this_turn(
            state.get("memory") or [])
        signal = classify(
            player_text=state.get("user_text", "") or "",
            tool_calls=tool_calls,
            substory=state.get("substory") or state.get("dormant_substory"),
            beat_dwell=int(state.get("beat_turns", 0)),
        )
        window = list(state.get("direction_window") or [])
        window.append(signal_to_dict(signal))
        window = window[-WINDOW_SIZE:]

        # Optional tiebreaker — fires only when the score has been in the
        # uncertain band 3 turns in a row.
        if tiebreaker_should_run(window, cfg):
            verdict = _engagement_tiebreaker(cfg, state, ctx)
            if verdict is not None:
                window[-1]["tiebreaker_direction"] = verdict["direction"]
                window[-1]["tiebreaker_confidence"] = verdict["confidence"]

        target = compute_target_pressure(window)
        cur = float(state.get("plot_pressure", 1.0))
        new = update_pressure(cur, target,
                              alpha=float(cfg.story.pressure_ema_alpha))
        update["direction_window"] = window
        update["plot_pressure"] = new
        if ctx.transcript:
            from storyteller_hardware.runtime import load_settings
            mode = (load_settings(cfg).get("story_mode") or "auto")
            eff = effective_pressure(new, mode)
            sig_kind = _signal_kind(signal)
            ctx.transcript.note(
                f"[pressure] mode={mode} signal={sig_kind} "
                f"target={target:.2f} smoothed={new:.2f} effective={eff:.2f}"
            )

    # Memory trim + synopsis fold
    memory, synopsis, pending_fold = _trim_and_fold(
        cfg=cfg,
        memory=list(state.get("memory") or []),
        synopsis=state.get("synopsis", "") or "",
        pending_fold=list(state.get("pending_fold") or []),
        transcript=ctx.transcript,
    )
    update["memory"] = memory
    update["synopsis"] = synopsis
    update["pending_fold"] = pending_fold

    return update


def _collect_tool_calls_this_turn(memory: list[dict]) -> list[dict]:
    """Walk back from the end of memory until the most recent user
    message; collect every tool call invoked along the way. Returns a
    list of {name, args} dicts the pressure classifier consumes."""
    out: list[dict] = []
    for m in reversed(memory):
        if m.get("role") == "user":
            break
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            fn = (tc.get("function") or {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            out.append({"name": fn.get("name") or "",
                        "args": args})
    return out


_NPC_CANDIDATE_CAP = 6                 # FIFO cap on the recent-candidates list
_NPC_MIN_LEN = 4                       # ignore tokens shorter than this
_NPC_SENTENCE_BOUNDARY = (".", "!", "?", "…", ":", ";", "\n", "—")
# Common German sentence-start words we filter out — they're capitalised
# because they sit at sentence start, not because they're proper nouns.
_NPC_DENY_STARTS = {
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer",
    "einen", "einem", "eines", "kein", "keine", "keinen", "keiner",
    "und", "oder", "aber", "doch", "denn", "weil", "wenn", "als",
    "auch", "noch", "schon", "nur", "bis", "seit", "ohne", "mit",
    "von", "vom", "zur", "zum", "für", "ihr", "ihre", "ihren",
    "sein", "seine", "seinen", "dein", "deine", "deinen", "mein",
    "meine", "meinen", "unser", "unsere", "euer", "diese", "dieser",
    "dieses", "diesen", "jene", "jener", "jenes", "jeden", "jeder",
    "alles", "alle", "allen", "viel", "viele", "wenige", "manche",
    "ich", "du", "er", "sie", "es", "wir", "the", "and", "or",
    "but", "with", "without", "from", "into", "onto", "this", "that",
    "these", "those", "what", "which", "where", "when", "while",
}


def _world_entity_names(world) -> set[str]:
    """Lowercase set of every named entity the world already knows about
    — places, persons, items, glossary terms, regions, factions,
    random-table names. Used to filter NPC-candidate extraction so we
    don't auto-track world objects that the curator/RAG layer already
    handles."""
    names: set[str] = set()
    for collection_name in ("places", "persons", "items", "glossary",
                             "regions", "factions", "random_tables"):
        for entry in (getattr(world, collection_name, None) or []):
            n = (getattr(entry, "name", None)
                 or getattr(entry, "term", None) or "")
            if isinstance(n, str) and n.strip():
                names.add(n.strip().lower())
    # World-level identity bits the narrator may say but never as an NPC:
    if getattr(world, "name", None):
        names.add(world.name.lower())
    return names


def _extract_npc_candidates(text: str,
                             world,
                             char_state: dict | None) -> list[str]:
    """Heuristic: pull capitalised proper-noun-looking tokens from the
    narrator's last reply, filter against known world entities + already-
    tracked characters + common sentence-start words. Returns at most a
    handful — the system prompt's `track_character` hint is just a
    suggestion, the narrator decides what's actually worth tracking."""
    import re
    if not text:
        return []
    denylist = _world_entity_names(world)
    denylist.update(k.lower() for k in (char_state or {}).keys())
    # Tokenise on whitespace + soft sentence boundaries. Strip trailing
    # punctuation but keep mid-word hyphens (so "WR-Frau" stays one
    # token).
    out: list[str] = []
    seen: set[str] = set()
    # Mark which tokens come right after a sentence boundary so we can
    # skip leading capitalised function-words ("Der Wirt schweigt." —
    # the "Der" is a sentence-starter, not a name).
    after_boundary = True
    for raw in re.split(r"(\s+)", text):
        if not raw or raw.isspace():
            if any(b in raw for b in ("\n",)):
                after_boundary = True
            continue
        # Strip leading/trailing punctuation (each char in this string
        # is removed independently; the noqa marks B005 — using a multi-
        # character string with .strip() is the intent here).
        tok = raw.strip(",.!?;:()[]\"'„«»…")  # noqa: B005
        if not tok:
            after_boundary = raw[-1:] in _NPC_SENTENCE_BOUNDARY
            continue
        is_first = after_boundary
        after_boundary = raw[-1:] in _NPC_SENTENCE_BOUNDARY
        # Length gate: mixed-case tokens need ≥4 chars (skips "Ich", "Mit"
        # etc.); ALL-UPPERCASE tokens are kept down to 3 chars because
        # short acronyms like "JAM", "AIR", "WR" are typical NPC/agent
        # names in sci-fi worlds.
        if len(tok) < 3:
            continue
        if len(tok) < _NPC_MIN_LEN and not tok.isupper():
            continue
        # Must be capitalised. German nouns ARE capitalised everywhere,
        # so we lean heavily on the world-entity denylist + the
        # sentence-start skip + a small stopword list.
        if not tok[0].isupper():
            continue
        if is_first and tok.lower() in _NPC_DENY_STARTS:
            continue
        low = tok.lower()
        if low in denylist:
            continue
        # Compound nouns longer than 18 chars are almost always concepts
        # (Spiegelsplitter-Gürtel) not NPCs — skip to keep the hint clean.
        if len(tok) > 18:
            continue
        if low in seen:
            continue
        seen.add(low)
        out.append(tok)
    return out[:6]


def _signal_kind(sig) -> str:
    """One-word label for the transcript so admins can scan a session
    quickly: which signal kind dominated this turn's classification."""
    if sig.explicit_plot:
        return "explicit_plot"
    if sig.explicit_free:
        return "explicit_free"
    if sig.advanced:
        return "advanced"
    if sig.on_arc_lex:
        return "on_arc"
    if sig.off_arc_world_query:
        return "off_arc"
    if sig.substory_lex_thin:
        return "thin_lateral"
    return "lateral"


def _engagement_tiebreaker(cfg: Config, state: dict, ctx) -> dict | None:
    """One cheap planner-LLM call that classifies the direction of the
    last few turns. Used only when the heuristic stayed in the uncertain
    band [0.30, 0.60] for 3 consecutive turns — answers JSON
    {direction: on_arc|lateral|off_arc, confidence: 0..1}. Failure-
    tolerant: any error returns None so the heuristic alone decides."""
    sub = state.get("substory") or state.get("dormant_substory") or {}
    locale = _locale(state, ctx)
    beat = (sub.get("beats") or [{}])[
        min(int(sub.get("cursor", 0)),
            len(sub.get("beats") or []) - 1)] if sub.get("beats") else {}
    goal = beat.get("goal") or "(kein Beat aktiv)"
    involved = ", ".join(
        (sub.get("involved_persons") or [])
        + (sub.get("involved_places") or [])) or "—"
    mem = state.get("memory") or []
    last_pairs: list[str] = []
    for m in mem[-6:]:
        r = m.get("role")
        c = m.get("content")
        if r in ("user", "assistant") and isinstance(c, str):
            last_pairs.append(f"{r.upper()}: {c[:300]}")
    if not last_pairs:
        return None
    sys_msg = (
        "Du klassifizierst Engagement mit einem Story-Bogen. WICHTIG: "
        "Welt-Fakten erfinden oder Welt-Fragen stellen ist NICHT "
        "automatisch off_arc — wenn das im Dienst des Beat-Ziels steht, "
        "ist es on_arc. Antworte JSON: "
        '{"direction": "on_arc"|"lateral"|"off_arc", "confidence": 0..1}.'
    )
    user_msg = (
        f"BEAT-ZIEL: {goal}\nBETEILIGTE: {involved}\n"
        f"LETZTE SPIELZÜGE:\n" + "\n".join(last_pairs)
    )
    try:
        client = get_chat_client(cfg, "planner")
        resp = client.chat.completions.create(
            model=cfg.models.planner,
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
            **chat_extras(cfg, "planner",
                          temperature=cfg.models.planner_temperature),
        )
        CostLedger(cfg).record_chat_usage(
            role="planner", model=cfg.models.planner, usage=resp.usage,
            thread_id=None,
            world_id=getattr(ctx.world, "id", None))
        data = json.loads(resp.choices[0].message.content or "{}")
        direction = data.get("direction")
        if direction not in ("on_arc", "lateral", "off_arc"):
            return None
        # NOTE: classifier uses `toward_beat` internally
        mapped = {"on_arc": "toward_beat", "lateral": "lateral",
                  "off_arc": "away_from_beat"}[direction]
        conf = float(data.get("confidence", 0.0) or 0.0)
        return {"direction": mapped, "confidence": max(0.0, min(1.0, conf))}
    except Exception as exc:
        log.warning("engagement tiebreaker failed: %r", exc)
    _ = locale  # currently unused — kept for future localised system prompts
    return None


# --------------------------------------------------------------------------
# trim / synopsis-fold (extracted from the old engine)
# --------------------------------------------------------------------------

def _trim_and_fold(
    cfg: Config,
    memory: list[dict],
    synopsis: str,
    pending_fold: list[dict],
    transcript,
) -> tuple[list[dict], str, list[dict]]:
    keep = cfg.story.short_term_memory_turns * 2
    if not cfg.story.long_term_memory:
        if len(memory) > keep:
            memory = memory[-keep:]
        return memory, synopsis, pending_fold

    batch = max(2, int(cfg.story.synopsis_batch))
    if len(memory) <= keep + batch:
        return memory, synopsis, pending_fold

    dropped = memory[:batch]
    to_fold = pending_fold + dropped
    ok, new_syn = _fold_into_synopsis(cfg, synopsis, to_fold, transcript)
    if ok:
        return memory[batch:], new_syn, []

    # summariser unreachable: queue for retry, but trim memory anyway so the
    # prompt doesn't grow unbounded. Content is preserved in pending_fold.
    pending_fold = pending_fold + dropped
    memory = memory[batch:]
    if len(pending_fold) >= batch * 3:
        synopsis = _heuristic_fold(cfg, synopsis, pending_fold, transcript)
        pending_fold = []
    return memory, synopsis, pending_fold


# Floor: if the new synopsis loses more than this fraction of the old
# synopsis's length, we assume the summariser dropped established
# content and retry / fall back. Tuned empirically — content density
# usually grows or stays constant when new turns get added, so a
# significant shrink almost always means lost facts.
_SYNOPSIS_SHRINK_FLOOR = 0.7
# Only enforce the floor when the old synopsis is already substantial;
# tiny synopses (early in a session) can legitimately get reshaped.
_SYNOPSIS_FLOOR_MIN_OLD = 300


def _fold_into_synopsis(
    cfg: Config, synopsis: str, dropped: list[dict], transcript,
) -> tuple[bool, str]:
    locale = norm(cfg.general.locale)
    convo = "\n".join(
        f"{'Spieler' if m.get('role') == 'user' else 'Erzähler'}: "
        f"{m.get('content', '')}"
        for m in dropped
        if isinstance(m.get("content"), str)
    ).strip()
    if not convo:
        return True, synopsis  # nothing worth keeping

    limit = int(cfg.story.synopsis_max_chars)
    old_len = len(synopsis or "")
    user_msg = (
        f"BISHERIGE ZUSAMMENFASSUNG:\n{synopsis or '(noch nichts)'}\n\n"
        f"NEUER ABSCHNITT (chronologisch danach):\n{convo}\n\n"
        f"Aktualisiere die Zusammenfassung. Maximal {limit} Zeichen, "
        f"knapp, faktentreu, nur Fließtext."
    )

    def _ask(extra_user: str = "") -> str:
        msgs = [{"role": "system", "content": SUMMARIZER_SYS[locale]},
                {"role": "user", "content": user_msg}]
        if extra_user:
            msgs.append({"role": "user", "content": extra_user})
        resp = get_chat_client(cfg, "planner").chat.completions.create(
            model=cfg.models.planner,
            messages=msgs,
            **chat_extras(cfg, "planner",
                          temperature=cfg.models.planner_temperature),
        )
        CostLedger(cfg).record_chat_usage(
            role="planner", model=cfg.models.planner, usage=resp.usage)
        return (resp.choices[0].message.content or "").strip()

    try:
        txt = _ask()
        if not txt:
            return False, synopsis
        new_syn = txt[:limit]

        # Shrink-floor: when the LLM came back with a much shorter
        # synopsis than the old one, it almost always silently
        # dropped established content. Re-ask once with a sharper
        # corrective; if it still shrinks too much, fall through to
        # heuristic_fold (lossless concat of old + dropped) via
        # returning False. Old synopsis IS preserved that way.
        if (old_len >= _SYNOPSIS_FLOOR_MIN_OLD
                and len(new_syn) < _SYNOPSIS_SHRINK_FLOOR * old_len):
            log.warning("synopsis shrink suspicious: old=%d new=%d "
                        "(<%.0f%%) — retrying", old_len, len(new_syn),
                        _SYNOPSIS_SHRINK_FLOOR * 100)
            correction = (
                "Deine vorige Antwort war ZU KURZ — du hast Inhalte "
                "aus der bisherigen Zusammenfassung verloren. "
                "Versuch's nochmal: die NEUE Zusammenfassung muss "
                "mindestens so lang sein wie die alte, und JEDEN "
                "etablierten Fakt, jede Person, jeden Ort, jede "
                "Beziehung und jeden offenen Faden aus der alten "
                "übernehmen. Ergänze sie um das Neue, lasse nichts "
                "weg."
                if locale == "de" else
                "Your previous reply was TOO SHORT — you lost "
                "content from the prior summary. Try again: the NEW "
                "summary must be at least as long as the old one, "
                "and retain EVERY established fact, person, place, "
                "relationship and open thread from the prior summary. "
                "Add the new part, drop nothing.")
            try:
                txt2 = _ask(extra_user=correction)
                cand = (txt2 or "")[:limit]
                if cand and len(cand) >= _SYNOPSIS_SHRINK_FLOOR * old_len:
                    new_syn = cand
                else:
                    log.warning("retry still shrunk (old=%d new=%d) "
                                "— falling back to heuristic_fold",
                                old_len, len(cand))
                    return False, synopsis
            except Exception as exc:
                log.warning("synopsis-retry failed: %r — falling "
                            "back to heuristic_fold", exc)
                return False, synopsis

        if transcript:
            transcript.note(
                f"[Langzeit-Synopse aktualisiert, {len(new_syn)} Zeichen]")
        return True, new_syn
    except Exception as exc:
        log.warning("Synopsis-Verdichtung fehlgeschlagen: %r", exc)
        return False, synopsis


def _heuristic_fold(
    cfg: Config, synopsis: str, dropped: list[dict], transcript,
) -> str:
    parts: list[str] = []
    for m in dropped:
        who = "Spieler" if m.get("role") == "user" else "Erzähler"
        txt = (m.get("content", "") or "")
        if not isinstance(txt, str):
            continue
        txt = txt.strip().replace("\n", " ")
        if len(txt) > 200:
            txt = txt[:200].rsplit(" ", 1)[0] + "…"
        parts.append(f"{who}: {txt}")
    addition = "[verdichtet ohne LLM] " + " | ".join(parts)
    sep = " || " if synopsis else ""
    limit = int(cfg.story.synopsis_max_chars)
    result = (synopsis + sep + addition)[:limit]
    if transcript:
        transcript.note(
            f"[Heuristik-Synopse: {len(dropped)} Nachrichten ohne LLM verdichtet]")
    return result
