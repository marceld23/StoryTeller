"""Generate a complete world from a single text prompt (LLM, admin use).

Multi-step pipeline (serial), each step is its own LLM call so that the
model can think about ONE thing at a time and produce richer output than a
monolithic JSON dump would:

    1. skeleton         — identity + narrative fields + long description
    2. blueprint        — premise + functional beats (NO proper nouns)
    3. places           — ~10 entries
    4. persons          — ~10 entries
    5. items            — ~8 entries
    6. glossary         — ~18 entries
    7. history          — ~8 entries
    8. fragments        — ~18 entries (the main pool of vignette material)
    9. random_tables    — ~5 tables, each with 20+ entries

Calls route through `get_chat_client(cfg, "gen")` (long HTTP timeout, low
retry count) because big-model JSON-mode generation can take ~60-90 s and
would otherwise time out on the live-loop client. An optional `progress`
callback receives short status strings the admin UI surfaces on the job
status page.

Hardening: every step has a fallback that fills sensible defaults so a
flaky LLM response cannot produce a broken world. If the LLM under-
delivers on a list (e.g. returns 3 places instead of 10) we keep what it
gave us — the admin can use the "+N more" button in the world editor to
top up afterwards.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from ..config import Config
from ..oai import get_chat_client
from .schema import Beat, Blueprint, World

_log = logging.getLogger("storyteller.gen")

ProgressFn = Callable[[str], None]


# ---------------- Step 1: skeleton ----------------

_SYS_SKELETON = (
    "You are a world designer for an interactive audio storyteller. From "
    "the user's idea, design the IDENTITY + ATMOSPHERE of ONE complete, "
    "self-consistent game world. NO content lists, NO blueprint — only "
    "the fields below. Answer with JSON ONLY:\n"
    '{"id":"short_slug","name":"","display_name":"","genre":"",'
    '"description":"",'
    '"player_role":"","starting_situation":"","narration_style":"",'
    '"voice_sample":"","mood":"","ambience":"","magic_physics":"",'
    '"complexity":"simple|standard|rich","audience":"e.g. 12+ / erwachsene",'
    '"tone":{"darkness":0,"humor":0,"romance":0,"action":0,"horror":0,'
    '"pacing":"slow|medium|fast","notes":""}}\n'
    "Field rules:\n"
    "- description: A SUBSTANTIAL world description, 250-500 words, "
    "covering geography/society/conflict/everyday life/what makes this "
    "world feel different. This text feeds the RAG + narrator, so the "
    "richer the better. No headings, fluent prose.\n"
    "- starting_situation: 2-4 sentences. A concrete opening tableau.\n"
    "- narration_style: 1-2 sentences, technical style notes (rhythm, "
    "tone, perspective).\n"
    "- voice_sample: 1-2 example sentences that DEMONSTRATE the tone "
    "(style only, no plot).\n"
    "- mood, ambience, magic_physics: 1-2 sentences each, non-empty.\n"
    "- tone values are integers 0-5. pacing is slow|medium|fast.\n"
    "Write all content in the same language as the user's prompt."
)


# ---------------- Step 2: blueprint ----------------

_SYS_BLUEPRINT = (
    "You design the MACRO TENSION ARC for an interactive audio "
    "storyteller. The arc is replayed across many sessions in the same "
    "world, so it MUST be GENERIC and FUNCTIONAL — describing the role "
    "each beat plays in dramaturgy, NOT the specific story content.\n"
    "\n"
    "STRICT RULES:\n"
    "- Beat names use functional labels (e.g. 'Aufhänger / Inciting "
    "Incident', 'Steigende Spannung / Rising Action', 'Erste Wende / "
    "First Turn', 'Mittelpunkt / Midpoint', 'Krise / Crisis', "
    "'Höhepunkt / Climax', 'Ausklang / Resolution').\n"
    "- Beat goals describe FUNCTION ('a hook pulls the player into the "
    "conflict', 'pressure mounts and stakes become visible', 'an "
    "assumption is overturned'), NOT specific characters, places, items "
    "or plot points.\n"
    "- DO NOT name any person, place, faction, item or event that "
    "belongs in the world content — those vary per session and are "
    "filled in via RAG.\n"
    "- premise: 1-2 sentences, genre-flavoured but abstract (no proper "
    "nouns).\n"
    "- escalation_rule: 1 sentence on how tension should escalate in "
    "this world's pacing.\n"
    "- 6-8 beats with a rising-then-falling tension curve (start low, "
    "peak 9-10 near the climax, drop on resolution).\n"
    "\n"
    "Answer with JSON ONLY:\n"
    '{"premise":"","escalation_rule":"",'
    '"beats":[{"name":"","goal":"","tension":0}]}\n'
    "Same language as the world data given below."
)


# ---------------- Steps 3-9: content lists ----------------

# Target sizes per list. The LLM is asked for these counts; we keep what
# it returns even if it under-delivers (the admin can top up later).
_LIST_SPECS = {
    "places": {
        "count": 10,
        "shape": '[{"name":"","description":"","tags":[]}]',
        "instruction": (
            "Generate {count} distinct, vivid PLACES (locations) for "
            "this world. Mix scales: hubs, hidden spots, dangerous "
            "frontiers, mundane corners. 1-3 sentence descriptions. "
            "Tags are short keywords (e.g. 'hub', 'danger', 'ruin')."
        ),
    },
    "persons": {
        "count": 10,
        "shape": ('[{"name":"","role":"","description":"","relations":""'
                  ',"tags":[]}]'),
        "instruction": (
            "Generate {count} distinct PERSONS / NPCs for this world. "
            "Mix roles: allies, rivals, neutrals, antagonists, "
            "bystanders with their own agendas. Describe quirks, "
            "motivation, look. relations: 1 sentence on who they trust "
            "or oppose. Tags = short keywords."
        ),
    },
    "items": {
        "count": 8,
        "shape": ('[{"name":"","description":"","properties":"",'
                  '"tags":[]}]'),
        "instruction": (
            "Generate {count} distinct ITEMS / ARTIFACTS for this "
            "world. Mix everyday gear, plot devices, rumoured "
            "treasures. properties: what the item DOES (rules, "
            "trade-offs). Tags = short keywords."
        ),
    },
    "glossary": {
        "count": 18,
        "shape": '[{"term":"","definition":""}]',
        "instruction": (
            "Generate {count} GLOSSARY entries — world-specific terms, "
            "factions, technologies, customs, slang. Each definition "
            "is 1-2 sentences. The glossary is the world's vocabulary "
            "anchor, so cover a wide spread."
        ),
    },
    "history": {
        "count": 8,
        "shape": '[{"when":"","title":"","description":""}]',
        "instruction": (
            "Generate {count} HISTORICAL EVENTS / ERAS. Mix ancient, "
            "recent, mythic, mundane. when = free-text era ('vor 200 "
            "Jahren', 'im letzten Sommer', 'im Mythenzeitalter'). "
            "Descriptions are 1-3 sentences."
        ),
    },
    "fragments": {
        "count": 18,
        "shape": '[{"title":"","text":"","tags":[]}]',
        "instruction": (
            "Generate {count} FRAGMENTS — short narrative seeds the "
            "narrator can weave in: rumours, vignettes, ominous "
            "details, hooks, dreams, overheard talk, environmental "
            "storytelling. Each text is 2-5 sentences, atmospheric "
            "and CONCRETE. This list is the main pool of variety, so "
            "make every entry distinct. Tags = short keywords."
        ),
    },
    "random_tables": {
        "count": 5,
        "shape": ('[{"name":"","description":"",'
                  '"entries":[{"weight":1,"text":""}]}]'),
        "instruction": (
            "Generate {count} RANDOM TABLES. Each table covers ONE "
            "kind of in-world event (e.g. 'street encounters', "
            "'weather omens', 'tavern rumours', 'cargo finds', 'minor "
            "complications'). EACH TABLE MUST HAVE AT LEAST 20 "
            "entries, each entry one concrete short sentence. Weights "
            "are integers >=1. The narrator rolls these as a tool, so "
            "more entries = more variety."
        ),
    },
}

# Lists where we accept smaller outputs (LLM-dependent) but warn.
_LIST_ORDER = ("places", "persons", "items", "glossary", "history",
               "fragments", "random_tables")


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "welt"


def _fill(data: dict, key: str, default: str) -> None:
    if not (data.get(key) or "").strip():
        data[key] = default


def _p(progress: ProgressFn | None, msg: str) -> None:
    _log.info("%s", msg)
    if progress is not None:
        try:
            progress(msg)
        except Exception:
            pass


def _llm_json(cfg: Config, system: str, user: str) -> dict:
    """One LLM call, JSON object response, no streaming. Raises on bad JSON.

    Checks the daily cost cap BEFORE the call (so an exhausted budget
    aborts world generation cleanly) and logs the actual usage to the
    cost ledger afterwards. World generation is one of the cost-heaviest
    operations the admin can trigger — multiple calls per world — so
    both checks matter even though no per-session tracker is involved.
    """
    from ..story.ledger import CostLedger

    ledger = CostLedger(cfg)
    ledger.assert_under_cap()
    r = get_chat_client(cfg, "gen").chat.completions.create(
        model=cfg.models.gen,
        temperature=cfg.models.gen_temperature,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    ledger.record_chat_usage(role="gen", model=cfg.models.gen, usage=r.usage)
    return json.loads(r.choices[0].message.content or "{}")


def _world_context(skeleton: dict, prompt: str) -> str:
    """Compact context anchor for every per-list call — keeps lists
    consistent with the established world flavour."""
    name = skeleton.get("name", "")
    genre = skeleton.get("genre", "")
    desc = (skeleton.get("description") or "")[:800]
    mood = skeleton.get("mood", "")
    ambience = skeleton.get("ambience", "")
    magic = skeleton.get("magic_physics", "")
    role = skeleton.get("player_role", "")
    return (
        f"WORLD: {name} ({genre})\n"
        f"DESCRIPTION: {desc}\n"
        f"PLAYER ROLE: {role}\n"
        f"MOOD: {mood}\n"
        f"AMBIENCE: {ambience}\n"
        f"PHYSICS/MAGIC: {magic}\n"
        f"ORIGINAL PROMPT: {prompt[:300]}"
    )


def _generate_skeleton(cfg: Config, prompt: str,
                       progress: ProgressFn | None) -> dict:
    _p(progress, f"1/9 Welt-Skelett ({cfg.models.gen})…")
    try:
        data = _llm_json(cfg, _SYS_SKELETON, prompt)
    except Exception as exc:
        _log.warning("skeleton call failed: %r", exc)
        data = {}

    data.setdefault("name", "Neue Welt")
    data["id"] = _slug(data.get("id") or data["name"])
    data.setdefault("genre", "")
    data.setdefault("description", prompt[:400])
    data.setdefault("player_role", "Hauptfigur")
    name = data["name"]
    _fill(data, "starting_situation",
          f"Die Geschichte beginnt im Zentrum von {name} — die Lage ist "
          "ruhig, aber etwas liegt in der Luft.")
    _fill(data, "narration_style", "ruhig, bildhaft, knapp")
    _fill(data, "mood", "stimmungsvoll, leicht gespannt")
    _fill(data, "ambience",
          "vereinzelte Geräusche, sanftes Licht, ein Hauch Bewegung")
    _fill(data, "magic_physics",
          "weitgehend realistisch; Ausnahmen werden im Spiel erklärt")
    _fill(data, "voice_sample",
          "Die Welt atmet langsam. Etwas wartet — du musst es nur "
          "bemerken.")
    return data


def _generate_blueprint(cfg: Config, skeleton: dict, prompt: str,
                        progress: ProgressFn | None) -> dict:
    _p(progress, "2/9 Spannungsbogen (funktional)…")
    user = (
        _world_context(skeleton, prompt) + "\n\n"
        "Design the macro tension arc for this world. Remember: NO "
        "proper nouns in beats, only functional roles."
    )
    try:
        bp = _llm_json(cfg, _SYS_BLUEPRINT, user)
    except Exception as exc:
        _log.warning("blueprint call failed: %r", exc)
        bp = {}

    beats = bp.get("beats") or []
    if not beats:
        beats = [
            {"name": "Aufhänger", "goal":
             "Ein Ereignis zieht die Hauptfigur in den Konflikt.",
             "tension": 2},
            {"name": "Steigende Spannung", "goal":
             "Der Druck nimmt zu, die Einsätze werden sichtbar.",
             "tension": 4},
            {"name": "Erste Wende", "goal":
             "Eine Annahme über die Lage wird widerlegt.", "tension": 6},
            {"name": "Krise", "goal":
             "Ein Vertrauensbruch zwingt zu einer schwierigen Wahl.",
             "tension": 8},
            {"name": "Höhepunkt", "goal":
             "Konfrontation mit der Wurzel des Konflikts.",
             "tension": 10},
            {"name": "Ausklang", "goal":
             "Konsequenzen, eine neue offene Frage.", "tension": 3},
        ]
    premise = (bp.get("premise") or
               f"Eine Geschichte aus der Welt {skeleton.get('name', '')}.")
    escal = (bp.get("escalation_rule")
             or Blueprint.model_fields["escalation_rule"].default)
    return Blueprint(
        premise=premise,
        escalation_rule=escal,
        beats=[Beat(name=b.get("name", f"Beat {i+1}"),
                    goal=b.get("goal", ""),
                    tension=max(0, min(10, int(b.get("tension", 5)))))
               for i, b in enumerate(beats[:10])]).model_dump()


def _generate_list(cfg: Config, kind: str, skeleton: dict, prompt: str,
                   step_idx: int, progress: ProgressFn | None) -> list:
    spec = _LIST_SPECS[kind]
    _p(progress, f"{step_idx}/9 {kind} (~{spec['count']})…")
    sys = (
        "You expand ONE list of an existing world. Return JSON ONLY:\n"
        '{"' + kind + '":' + spec["shape"] + "}\n"
        + spec["instruction"].format(count=spec["count"]) +
        "\nSame language as the world data. Vary every entry — no near-"
        "duplicates. Output the list ONLY, no commentary."
    )
    user = _world_context(skeleton, prompt) + (
        f"\n\nNow generate the '{kind}' list described in the system "
        "prompt."
    )
    try:
        data = _llm_json(cfg, sys, user)
    except Exception as exc:
        _log.warning("list call %s failed: %r", kind, exc)
        return []
    out = data.get(kind) or []
    if not isinstance(out, list):
        _log.warning("list call %s returned non-list: %r", kind, type(out))
        return []
    return out


def generate_world(cfg: Config, prompt: str,
                   progress: ProgressFn | None = None) -> World:
    """One prompt -> a validated, fully-populated World via 9 LLM calls."""
    skeleton = _generate_skeleton(cfg, prompt, progress)
    blueprint = _generate_blueprint(cfg, skeleton, prompt, progress)

    lists: dict[str, list] = {}
    for i, kind in enumerate(_LIST_ORDER, start=3):
        lists[kind] = _generate_list(cfg, kind, skeleton, prompt, i,
                                     progress)

    data = {**skeleton, "blueprint": blueprint, **lists}
    _p(progress, "Welt validieren…")
    return World.model_validate(data)
