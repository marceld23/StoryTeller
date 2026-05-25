"""Generate a complete world from a single text prompt (LLM, admin use).

Multi-step pipeline (serial), each step is its own LLM call so that the
model can think about ONE thing at a time and produce richer output than a
monolithic JSON dump would:

    1.  skeleton       — identity + narrative fields + long description
    2.  tech_magic     — structured tech/magic system (kind, rules, …)
    3.  blueprint      — premise + functional beats (NO proper nouns)
    4.  regions        — ~6 large areas / domains (places live in them)
    5.  places         — ~10 entries, each linked to a region
    6.  factions       — ~5 groups with goals + allies/enemies
    7.  persons        — ~10 entries, optionally linked to a faction
    8.  items          — ~8 entries
    9.  creatures      — ~6 beings keyed to regions / habitats
    10. glossary       — ~18 entries
    11. history        — ~8 entries
    12. fragments      — ~18 entries (the main pool of vignette material)
    13. random_tables  — ~5 tables, each with 20+ entries

The extra structured steps (regions / factions / creatures) feed
downstream prompts so places can reference an existing region, persons
can declare a faction, and creatures get a known habitat — keeps the
named entities self-consistent across the generated world.

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
from ..oai import chat_extras, get_chat_client
from .schema import Beat, Blueprint, BlueprintVariant, World

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
    "You design THREE MACRO TENSION ARCS for an interactive audio "
    "storyteller — each one a self-contained story arc that COULD be "
    "the next session in this world. The arcs are picked at substory-"
    "planning time, so they MUST stay GENERIC and FUNCTIONAL (describe "
    "the role each beat plays in dramaturgy, NOT the specific story "
    "content). Each arc has its own length / structure / twist "
    "signature so the player gets variety across replays.\n"
    "\n"
    "STRICT RULES (apply to EVERY arc):\n"
    "- Beat names use functional labels (e.g. 'Aufhänger / Inciting "
    "Incident', 'Steigende Spannung / Rising Action', 'Erste Wende / "
    "First Turn', 'Mittelpunkt / Midpoint', 'Krise / Crisis', "
    "'Höhepunkt / Climax', 'Ausklang / Resolution').\n"
    "- Beat goals describe FUNCTION ('a hook pulls the player into the "
    "conflict', 'pressure mounts and stakes become visible', 'an "
    "assumption is overturned'), NOT specific characters, places, items "
    "or plot points.\n"
    "- DO NOT name any person, place, faction, item or event that "
    "belongs in the world content.\n"
    "- premise: 1-2 sentences, genre-flavoured but abstract (no proper "
    "nouns).\n"
    "- escalation_rule: 1 sentence on how tension should escalate.\n"
    "- Tension curve per arc: rising-then-falling, starts low, peaks "
    "9-10 near the climax, drops on resolution.\n"
    "\n"
    "DIVERSITY ACROSS ARCS (the picker depends on it):\n"
    "- LENGTHS: one arc short (3-4 beats), one medium (5-7), one long "
    "(8-10). Use the matching `length` field exactly: short | medium | "
    "long.\n"
    "- STRUCTURES: pick from linear | parallel | spiral | frame | "
    "mosaic. Do NOT make all three linear. Vary explicitly.\n"
    "- TWIST_KINDS: pick from betrayal | revelation | sacrifice | "
    "hidden_enemy | red_herring | role_reversal | circular | \"\" "
    "(empty = no explicit twist, a quieter slice-of-life arc). No two "
    "arcs should share the same twist_kind.\n"
    "- name: short distinctive label (\"Schmuggler-Run\", "
    "\"Erkenntnis-Bogen\", \"Stiller Verlust\").\n"
    "- description: 1-2 sentences — when does this arc feel right for "
    "the player (e.g. \"good for a first-time visitor: an external "
    "hook drags them into local politics\").\n"
    "- trigger_hints: 2-4 short themes / cues (\"erstes mal\", "
    "\"player kennt fraktionen\", \"intimer ton\", …).\n"
    "\n"
    "Answer with JSON ONLY:\n"
    '{"variants":[{"name":"","description":"","length":"short|medium|long",'
    '"structure":"linear|parallel|spiral|frame|mosaic",'
    '"twist_kind":"","trigger_hints":[""],'
    '"premise":"","escalation_rule":"",'
    '"beats":[{"name":"","goal":"","tension":0}]}]}\n'
    "Same language as the world data given below."
)


# ---------------- Steps 3-9: content lists ----------------

# Target sizes per list. The LLM is asked for these counts; we keep what
# it returns even if it under-delivers (the admin can top up later).
_LIST_SPECS = {
    "regions": {
        "count": 6,
        "shape": '[{"name":"","description":"","tags":[]}]',
        "instruction": (
            "Generate {count} distinct REGIONS — larger geographies, "
            "domains, biomes, or political areas of this world. Each "
            "is a containing space that places will live IN (e.g. a "
            "city district, a forest zone, a star system, a nation, "
            "an underground level). 1-3 sentence descriptions. Tags "
            "are short keywords."
        ),
    },
    "places": {
        "count": 10,
        "shape": ('[{"name":"","description":"","region":"",'
                  '"contains":[],"adjacent":[],"tags":[]}]'),
        "instruction": (
            "Generate {count} distinct, vivid PLACES (specific "
            "locations) for this world. Mix scales: hubs, hidden "
            "spots, dangerous frontiers, mundane corners. 1-3 "
            "sentence descriptions. EVERY place MUST set `region` to "
            "the name of one of the regions listed in the world data "
            "above. `contains` is a list of sub-place names that the "
            "narrator should treat as inside this place (also listed "
            "elsewhere here when they exist). `adjacent` is a list of "
            "neighbouring place names. Use empty lists when none "
            "apply. Tags are short keywords."
        ),
    },
    "factions": {
        "count": 5,
        "shape": ('[{"name":"","description":"","goals":"",'
                  '"allies":[],"enemies":[],"relations":"","tags":[]}]'),
        "instruction": (
            "Generate {count} distinct FACTIONS — groups, orders, "
            "guilds, houses, governments, cabals, or any organised "
            "powers that drive the world's politics. `goals` is what "
            "each faction wants (1 sentence). `allies` / `enemies` "
            "are lists of OTHER faction names from this same output "
            "(empty when standalone). `relations` is a free-text "
            "1-sentence nuance. Tags are short keywords."
        ),
    },
    "persons": {
        "count": 10,
        "shape": ('[{"name":"","role":"","description":"","relations":"",'
                  '"faction":"","faction_role":"","tags":[]}]'),
        "instruction": (
            "Generate {count} distinct PERSONS / NPCs for this world. "
            "Mix roles: allies, rivals, neutrals, antagonists, "
            "bystanders with their own agendas. Describe quirks, "
            "motivation, look. `relations` (1 sentence): who they "
            "trust or oppose. `faction` (string): name of the faction "
            "they belong to from the world data above, or empty if "
            "unaffiliated. `faction_role`: their role inside that "
            "faction (e.g. 'leader', 'agent', 'novice'), empty if no "
            "faction. Tags = short keywords."
        ),
    },
    "creatures": {
        "count": 6,
        "shape": ('[{"name":"","description":"","habitat":"",'
                  '"threat_level":"medium","tags":[]}]'),
        "instruction": (
            "Generate {count} distinct CREATURES — non-person beings "
            "of this world (animals, monsters, spirits, machines, "
            "anything that lives or moves but isn't an NPC). 1-3 "
            "sentence descriptions of look + behaviour. `habitat` "
            "names a region from the world data above (or a place "
            "type like 'tunnels', 'deep sea', 'orbit'). "
            "`threat_level` is exactly one of `low`, `medium`, "
            "`high`. Mix mundane and dangerous."
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

# Order matters: regions before places (places reference them), factions
# before persons (persons reference them), creatures get regions as
# habitat context (so generated AFTER regions). Anything purely
# descriptive comes after the structural lists.
_LIST_ORDER = ("regions", "places", "factions", "persons", "items",
               "creatures", "glossary", "history", "fragments",
               "random_tables")


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
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        **chat_extras(cfg, "gen", temperature=cfg.models.gen_temperature),
    )
    ledger.record_chat_usage(role="gen", model=cfg.models.gen, usage=r.usage)
    return json.loads(r.choices[0].message.content or "{}")


def _world_context(skeleton: dict, prompt: str,
                   *, regions: list | None = None,
                   factions: list | None = None) -> str:
    """Full context anchor passed to every per-list and blueprint call.
    The user's original prompt is the primary source of flavour; the
    skeleton fields nail down established names + tone. No truncation:
    the prompt cap (web.max_prompt_chars, default 300k) is enforced at
    the entry point, and modern LLMs comfortably take that per step.

    Optional `regions` / `factions` are appended so downstream steps
    (places need regions, persons need factions, creatures need
    habitat-able regions) can cite existing named entities by their
    canonical names instead of inventing new ones."""
    name = skeleton.get("name", "")
    genre = skeleton.get("genre", "")
    desc = skeleton.get("description") or ""
    mood = skeleton.get("mood", "")
    ambience = skeleton.get("ambience", "")
    magic = skeleton.get("magic_physics", "")
    role = skeleton.get("player_role", "")
    lines = [
        f"WORLD: {name} ({genre})",
        f"DESCRIPTION: {desc}",
        f"PLAYER ROLE: {role}",
        f"MOOD: {mood}",
        f"AMBIENCE: {ambience}",
        f"PHYSICS/MAGIC: {magic}",
    ]
    if regions:
        lines.append("REGIONS (use these names verbatim — every Place's "
                     "`region` MUST match one):")
        for r in regions:
            rn = (r.get("name") or "").strip()
            rd = (r.get("description") or "").strip()
            if rn:
                lines.append(f"- {rn}: {rd}" if rd else f"- {rn}")
    if factions:
        lines.append("FACTIONS (use these names verbatim when a person "
                     "belongs to one):")
        for f in factions:
            fn = (f.get("name") or "").strip()
            fg = (f.get("goals") or "").strip()
            if fn:
                lines.append(f"- {fn}: {fg}" if fg else f"- {fn}")
    lines.append(f"ORIGINAL PROMPT: {prompt}")
    return "\n".join(lines)


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


_VALID_LENGTHS = {"short", "medium", "long", "epic"}
_VALID_STRUCTURES = {"linear", "parallel", "spiral", "frame", "mosaic"}
_VALID_TWISTS = {"", "betrayal", "revelation", "sacrifice", "hidden_enemy",
                 "red_herring", "role_reversal", "circular"}

_DEFAULT_BEATS = [
    {"name": "Aufhänger", "goal":
     "Ein Ereignis zieht die Hauptfigur in den Konflikt.", "tension": 2},
    {"name": "Steigende Spannung", "goal":
     "Der Druck nimmt zu, die Einsätze werden sichtbar.", "tension": 4},
    {"name": "Erste Wende", "goal":
     "Eine Annahme über die Lage wird widerlegt.", "tension": 6},
    {"name": "Krise", "goal":
     "Ein Vertrauensbruch zwingt zu einer schwierigen Wahl.",
     "tension": 8},
    {"name": "Höhepunkt", "goal":
     "Konfrontation mit der Wurzel des Konflikts.", "tension": 10},
    {"name": "Ausklang", "goal":
     "Konsequenzen, eine neue offene Frage.", "tension": 3},
]


def _coerce_blueprint_dict(world_name: str, raw: dict) -> dict:
    """Turn one LLM-shaped variant dict into a Blueprint model_dump
    with sane defaults for missing fields."""
    beats = raw.get("beats") or _DEFAULT_BEATS
    return Blueprint(
        premise=(raw.get("premise")
                 or f"Eine Geschichte aus der Welt {world_name}."),
        escalation_rule=(raw.get("escalation_rule")
                          or Blueprint.model_fields["escalation_rule"].default),
        beats=[Beat(name=b.get("name", f"Beat {i+1}"),
                    goal=b.get("goal", ""),
                    tension=max(0, min(10, int(b.get("tension", 5)))))
               for i, b in enumerate(beats[:12])]).model_dump()


def _generate_blueprints(cfg: Config, skeleton: dict, prompt: str,
                          progress: ProgressFn | None) -> list[dict]:
    """Generate 3 macro arcs in one LLM call (the diversity prompt is
    inside `_SYS_BLUEPRINT`). Returns a list of BlueprintVariant
    model_dump dicts ready for World.blueprints. On any failure the
    pipeline still returns at least ONE variant from the same default
    skeleton so the engine never sees an empty list."""
    _p(progress, "3/13 Spannungsbögen (3 Varianten)…")
    user = (
        _world_context(skeleton, prompt) + "\n\n"
        "Design 3 diverse macro tension arcs for this world. Remember: "
        "NO proper nouns in beats, only functional roles. Vary length, "
        "structure and twist_kind across the arcs."
    )
    try:
        data = _llm_json(cfg, _SYS_BLUEPRINT, user)
    except Exception as exc:
        _log.warning("blueprints call failed: %r", exc)
        data = {}

    raw_variants = data.get("variants") or []
    world_name = skeleton.get("name", "")
    out: list[dict] = []
    for i, v in enumerate(raw_variants[:4]):  # cap at 4 just in case
        if not isinstance(v, dict):
            continue
        length = (v.get("length") or "medium").strip().lower()
        if length not in _VALID_LENGTHS:
            length = "medium"
        structure = (v.get("structure") or "linear").strip().lower()
        if structure not in _VALID_STRUCTURES:
            structure = "linear"
        twist = (v.get("twist_kind") or "").strip().lower()
        if twist not in _VALID_TWISTS:
            twist = ""
        trigger = v.get("trigger_hints") or []
        if not isinstance(trigger, list):
            trigger = []
        variant = BlueprintVariant(
            name=v.get("name") or f"Variante {i+1}",
            description=v.get("description") or "",
            length=length, structure=structure, twist_kind=twist,
            trigger_hints=[str(t) for t in trigger][:6],
            blueprint=Blueprint.model_validate(
                _coerce_blueprint_dict(world_name, v)),
        )
        out.append(variant.model_dump())

    if not out:
        # Hard fallback: one default arc so the engine still works even
        # if the LLM completely failed.
        out.append(BlueprintVariant(
            name="Hauptbogen", description="",
            length="medium", structure="linear", twist_kind="",
            trigger_hints=[],
            blueprint=Blueprint.model_validate(
                _coerce_blueprint_dict(world_name, {})),
        ).model_dump())
    return out


def _generate_list(cfg: Config, kind: str, skeleton: dict, prompt: str,
                   step_idx: int, step_total: int,
                   progress: ProgressFn | None,
                   *, regions: list | None = None,
                   factions: list | None = None) -> list:
    spec = _LIST_SPECS[kind]
    _p(progress, f"{step_idx}/{step_total} {kind} (~{spec['count']})…")
    sys = (
        "You expand ONE list of an existing world. Return JSON ONLY:\n"
        '{"' + kind + '":' + spec["shape"] + "}\n"
        + spec["instruction"].format(count=spec["count"]) +
        "\n\nCANON RULE: The user's brief in the world data below "
        "(DESCRIPTION and ORIGINAL PROMPT) may already mention specific "
        "entries for this list BY NAME (proper nouns, named places / "
        "characters / items / factions / terms / events). You MUST "
        "include every one of those named entries in your output "
        "verbatim — same spelling, same name. Flesh them out with the "
        "description / fields the schema requires; do not rename, "
        "translate, or 'improve' them. Then fill the remaining slots "
        "up to the requested count with new entries that fit the world "
        "tone. If the user's brief already provides more named entries "
        "than the requested count, return ALL of them (the count is a "
        "lower bound when canon is rich)."
        "\nSame language as the world data. Vary every entry — no near-"
        "duplicates. Output the list ONLY, no commentary."
    )
    user = _world_context(skeleton, prompt, regions=regions,
                          factions=factions) + (
        f"\n\nNow generate the '{kind}' list described in the system "
        "prompt. Preserve any user-named entries first, then fill."
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


_SYS_TECH_MAGIC = (
    "You design the TECH / MAGIC SYSTEM of an existing world. From the "
    "user's brief and skeleton, write a structured spec. Answer JSON "
    "ONLY:\n"
    '{"kind":"technology|magic|both|neither",'
    '"description":"","rules":[""],"cost_or_risk":""}\n'
    "Field rules:\n"
    "- kind: one of the four values. Pick the dominant flavour; use "
    "'both' for science-fantasy; 'neither' if the world is mundane.\n"
    "- description: 2-4 sentences on how the system FEELS in play.\n"
    "- rules: 3-7 short rules the narrator can rely on. Each rule is "
    "ONE sentence describing what's POSSIBLE or IMPOSSIBLE (e.g. "
    "'Teleportation requires a known anchor point.'). Be concrete.\n"
    "- cost_or_risk: 1-2 sentences on what using the system costs the "
    "user (mana, fuel, attention from a power, side effects).\n"
    "Same language as the world data. Output the JSON only.")


def _generate_tech_magic(cfg: Config, skeleton: dict, prompt: str,
                         step_idx: int, step_total: int,
                         progress: ProgressFn | None) -> dict | None:
    _p(progress, f"{step_idx}/{step_total} tech_magic…")
    user = _world_context(skeleton, prompt) + (
        "\n\nNow generate the tech/magic system spec described in the "
        "system prompt.")
    try:
        data = _llm_json(cfg, _SYS_TECH_MAGIC, user)
    except Exception as exc:
        _log.warning("tech_magic call failed: %r", exc)
        return None
    if not isinstance(data, dict):
        return None
    kind = (data.get("kind") or "neither").strip().lower()
    if kind not in ("technology", "magic", "both", "neither"):
        kind = "neither"
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        rules = []
    return {
        "kind": kind,
        "description": (data.get("description") or "").strip(),
        "rules": [str(r).strip() for r in rules if str(r).strip()],
        "cost_or_risk": (data.get("cost_or_risk") or "").strip(),
    }


def generate_world(cfg: Config, prompt: str,
                   progress: ProgressFn | None = None) -> World:
    """One prompt -> a validated, fully-populated World via 13 LLM calls.

    Pipeline order is structurally constrained: regions feed places +
    creature habitats; factions feed person memberships. The dependent
    steps see the already-generated names through `_world_context()` and
    are told to use them verbatim.
    """
    total = 3 + len(_LIST_ORDER)               # skeleton + tech + blueprints + lists
    skeleton = _generate_skeleton(cfg, prompt, progress)
    tech_magic = _generate_tech_magic(cfg, skeleton, prompt, 2, total,
                                      progress)
    # 3 diverse macro arcs in a single LLM call. The first one also
    # populates `world.blueprint` for back-compat with code paths that
    # may still read the legacy singular field.
    variants = _generate_blueprints(cfg, skeleton, prompt, progress)

    lists: dict[str, list] = {}
    regions_ctx: list = []
    factions_ctx: list = []
    for offset, kind in enumerate(_LIST_ORDER):
        step_idx = 4 + offset
        # Threading: places + creatures see regions, persons see factions.
        ctx_regions = regions_ctx if kind in ("places", "creatures") else None
        ctx_factions = factions_ctx if kind == "persons" else None
        lists[kind] = _generate_list(
            cfg, kind, skeleton, prompt, step_idx, total, progress,
            regions=ctx_regions, factions=ctx_factions)
        # Latch the freshly generated lists for downstream steps.
        if kind == "regions":
            regions_ctx = lists[kind]
        elif kind == "factions":
            factions_ctx = lists[kind]

    data = {
        **skeleton,
        "blueprint": variants[0]["blueprint"],   # legacy single
        "blueprints": variants,                   # new multi-variant list
        **lists,
    }
    if tech_magic is not None:
        data["tech_magic"] = tech_magic
    _p(progress, "Welt validieren…")
    return World.model_validate(data)
