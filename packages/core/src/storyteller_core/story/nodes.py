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
from .tools import TOOLS, dispatch_tool

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
    nudge = (BEAT_NUDGE[locale]
             if (not brief and cfg.story.beat_nudge_after
                 and beat_turns >= cfg.story.beat_nudge_after) else "")

    macro = BlueprintTracker(w.active_blueprint(state.get("blueprint_choice", 0)),
                              state.get("macro_index", 0))

    sub_dict = state.get("substory")
    sub_block = ""
    if sub_dict:
        sub = SubstoryPlan(**sub_dict)
        sub_block = sub.as_prompt_block(state.get("transition", False))

    known_summary = KnownFacts(state.get("known_facts") or []).summary()

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
        f"MAKRO-SPANNUNGSBOGEN:\n{macro.guidance()}\n\n"
        f"{sub_block}\n\n"
        f"{syn}"
        f"Dem Spieler bereits bekannt: {known_summary}\n\n"
        f"{chars}"
        f"{gate_block}"
        f"Hintergrundwissen (nur einbauen, wenn es JETZT zur Szene passt; "
        f"NICHT aufzählen):\n{facts or '(keine Treffer)'}{cap}{dyn}\n\n"
        f"{_guidance(cfg, locale)}\n{LANG_INSTRUCTION[locale]}\n"
        f"{SESSION_CONTINUITY_RULE[locale]}\n"
        "Tools still nutzen, das Ergebnis IMMER in einfache, kurze "
        "Erzählung verwandeln, niemals Fakten oder Listen vorlesen:\n"
        "- BEI EXPLIZITER SPIELER-FRAGE nach Welt-Fakten (Wer ist…? Wo "
        "ist…? Was ist…? Was bedeutet…?) RUFE ZUERST das passende Tool "
        "auf (`retrieve_world_fact` für Orte/Personen/Geschichte, "
        "`lookup_glossary` für Begriffe). Antworte NICHT aus dem "
        "Stegreif — Konsistenz hängt davon ab.\n"
        "- Andere Tools nach Bedarf: `get_world_overview` für "
        "Atmosphäre-Reset, `roll_random_event`/`roll_story_dynamic` für "
        "Wendungen, `track_character` für NPC-Zustände."
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

    sub_dict = state.get("substory")
    if sub_dict and sub_dict.get("status") != "complete":
        return {}  # no change

    cost = CostTracker.restore(cfg, state.get("cost") or {})
    planner = SubstoryPlanner(cfg, cost, ledger=CostLedger(cfg),
                              thread_id=_thread_id(config),
                              world_id=getattr(ctx.world, "id", None))

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
        world_id=getattr(ctx.world, "id", None))
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
    must stay hidden today. Skipped when disabled."""
    ctx = _ctx(config)
    cfg = ctx.cfg
    if not getattr(cfg.story, "narration_gate_enabled", True):
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
    try:
        gate = Curator(cfg, cost, ledger=CostLedger(cfg),
                       thread_id=_thread_id(config),
                       world_id=getattr(ctx.world, "id", None)).gate(
            ctx.world, sub_dict, future_beats,
            state.get("retrieved") or [],
            known_summary, recent, state.get("user_text", ""),
            int(state.get("beat_turns", 0)), locale=locale)
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
        kw["tools"] = TOOLS

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
    except Exception as exc:
        dt = _time.perf_counter() - t_call
        log.warning("narrate FAILED after %.2fs: %r", dt, exc)
        # Roll back the user message we appended, so the conversation has no hole.
        mem = list(state.get("memory") or [])
        if mem and mem[-1].get("role") == "user":
            mem.pop()
        return {
            "response": ("Einen Augenblick — die Verbindung stockt gerade. "
                         "Sag es bitte gleich noch einmal."),
            "memory": mem,
            "pending_tool_calls": [],
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

        tool_messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": str(result),
        })
        if ctx.transcript:
            ctx.transcript.tool(name, args, result)

    memory = list(state.get("memory") or []) + tool_messages
    out: dict = {
        "memory": memory,
        "known_facts": known.to_list(),
        "char_state": char_state,
        "pending_tool_calls": [],
        "just_completed_substory": just_completed,
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
    """
    ctx = _ctx(config)
    cfg = ctx.cfg
    locale = _locale(state, ctx)

    cost = CostTracker.restore(cfg, state.get("cost") or {})
    planner = SubstoryPlanner(cfg, cost, ledger=CostLedger(cfg),
                              thread_id=_thread_id(config),
                              world_id=getattr(ctx.world, "id", None))

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
        world_id=getattr(ctx.world, "id", None))
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

    if ctx.transcript and text:
        from .state import EngineContext  # noqa: F401
        cost = CostTracker.restore(cfg, state.get("cost") or {})
        # state machine label: planning if no substory, else status
        sub = state.get("substory")
        label = "planning" if not sub else sub.get("status", "in_substory")
        ctx.transcript.assistant(text, label, cost.usd)

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
