"""Generate a complete world from a single text prompt (LLM, admin use).

Hardened: a minimal/sparse LLM response is filled in instead of producing
a thin world that breaks RAG + narration.
- All narrative fields get sensible defaults if the LLM leaves them empty.
- If any of the story-critical content lists is empty (places, persons,
  history, fragments, random_tables), a SECOND targeted LLM call fills
  ONLY the missing parts. Worst-case +1 call per generation; worlds are
  generated rarely.
"""

from __future__ import annotations

import json
import logging
import re

from ..config import Config
from ..oai import get_client
from .schema import Beat, Blueprint, World

_SYS = (
    "You are a world designer for an interactive audio storyteller. From the "
    "user's idea, design ONE complete, self-consistent game world and answer "
    "with JSON ONLY, matching this shape:\n"
    '{"id":"short_slug","name":"","genre":"","description":"",'
    '"player_role":"","starting_situation":"","narration_style":"",'
    '"voice_sample":"",'
    '"mood":"","ambience":"","magic_physics":"",'
    '"complexity":"simple|standard|rich","audience":"e.g. 12+ / erwachsene",'
    '"story_patterns":[],'
    '"tone":{"darkness":0,"humor":0,"romance":0,"action":0,"horror":0,'
    '"pacing":"slow|medium|fast","notes":""},'
    '"places":[{"name":"","description":"","tags":[]}],'
    '"persons":[{"name":"","role":"","description":"","relations":"",'
    '"tags":[]}],'
    '"items":[{"name":"","description":"","properties":"","tags":[]}],'
    '"glossary":[{"term":"","definition":""}],'
    '"history":[{"when":"","title":"","description":""}],'
    '"fragments":[{"title":"","text":"","tags":[]}],'
    '"blueprint":{"premise":"","beats":[{"name":"","goal":"",'
    '"tension":0}]},'
    '"random_tables":[{"name":"","description":"",'
    '"entries":[{"weight":1,"text":""}]}]}\n'
    "Field rules: voice_sample = 1-2 example sentences that demonstrate the "
    "narrative TONE and rhythm of this world (style only, not plot). "
    "starting_situation, narration_style, mood, ambience and magic_physics "
    "MUST be non-empty. tone values are integers 0-5. tension is 0-10. "
    "Give 2-4 each of places/persons/items/glossary/history/fragments and "
    "4-6 blueprint beats with a rising tension curve. random_tables: at "
    "least 2 concrete tables. Write all content in the same language as "
    "the user's prompt."
)

# Content lists whose absence makes RAG + narration weak.
_STORY_LISTS = ("places", "persons", "history", "fragments", "random_tables")
_ALL_LISTS = (
    "places", "persons", "items", "glossary", "history", "fragments",
    "random_tables",
)
_LIST_SHAPES = {
    "places": '[{"name":"","description":"","tags":[]}]',
    "persons": '[{"name":"","role":"","description":"","relations":"",'
               '"tags":[]}]',
    "items": '[{"name":"","description":"","properties":"","tags":[]}]',
    "glossary": '[{"term":"","definition":""}]',
    "history": '[{"when":"","title":"","description":""}]',
    "fragments": '[{"title":"","text":"","tags":[]}]',
    "random_tables": '[{"name":"","description":"",'
                     '"entries":[{"weight":1,"text":""}]}]',
}


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "welt"


def _fill(data: dict, key: str, default: str) -> None:
    if not (data.get(key) or "").strip():
        data[key] = default


def _fill_missing_lists(cfg: Config, prompt: str, data: dict) -> None:
    """Second pass: ask the LLM to fill ONLY the missing content lists.

    Triggered when story-critical lists are empty after the first pass.
    Fail-soft: on any error, leaves the lists empty (schema defaults []).
    """
    missing = [k for k in _ALL_LISTS if not data.get(k)]
    if not any(k in _STORY_LISTS for k in missing):
        return
    shape = "{" + ", ".join(f'"{k}":{_LIST_SHAPES[k]}' for k in missing) + "}"
    sys = (
        "You complete a partially designed world. Return JSON ONLY in this "
        "exact shape:\n" + shape + "\nGive 2-3 concrete entries per list, "
        "consistent with the world below. Same language as the world "
        "description. Do NOT repeat fields that already exist."
    )
    user = (
        f"WORLD: {data.get('name', '')} ({data.get('genre', '')})\n"
        f"{data.get('description', '')}\n"
        f"Spielerrolle: {data.get('player_role', '')}\n"
        f"Stimmung: {data.get('mood', '')} / Ambiente: "
        f"{data.get('ambience', '')}\n"
        f"Physik/Magie: {data.get('magic_physics', '')}\n"
        f"Original prompt: {prompt[:400]}\n\n"
        f"Add the missing parts ONLY: {', '.join(missing)}."
    )
    try:
        r = get_client(cfg).chat.completions.create(
            model=cfg.models.gen,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        extra = json.loads(r.choices[0].message.content or "{}")
        for k in missing:
            if extra.get(k):
                data[k] = extra[k]
    except Exception as exc:  # pragma: no cover - network/API path
        logging.getLogger("storyteller").warning(
            "Welt-Fill-Pass fehlgeschlagen: %r", exc)


def generate_world(cfg: Config, prompt: str) -> World:
    """One prompt -> a validated, fully-populated World. Raises on hard failure."""
    r = get_client(cfg).chat.completions.create(
        model=cfg.models.gen,
        messages=[{"role": "system", "content": _SYS},
                  {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(r.choices[0].message.content or "{}")

    # --- Identity / required-by-schema scaffolding ---
    data.setdefault("name", "Neue Welt")
    data["id"] = _slug(data.get("id") or data["name"])
    data.setdefault("genre", "")
    data.setdefault("description", prompt[:400])
    data.setdefault("player_role", "Hauptfigur")

    # --- Narrative fields: never leave empty (head-of-prompt content) ---
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
    # voice_sample is the optional style anchor (added by P4).
    _fill(data, "voice_sample",
          "Die Welt atmet langsam. Etwas wartet — du musst es nur "
          "bemerken.")

    # --- Blueprint: enforce a usable arc ---
    bp = data.get("blueprint") or {}
    beats = bp.get("beats") or []
    if not beats:
        beats = [{"name": "Aufhänger", "goal": "Lage etablieren",
                  "tension": 2},
                 {"name": "Zuspitzung", "goal": "Eskalation", "tension": 7},
                 {"name": "Auflösung", "goal": "Abschluss", "tension": 3}]
    data["blueprint"] = Blueprint(
        premise=bp.get("premise") or f"Eine Geschichte in {name}.",
        beats=[Beat(name=b.get("name", f"Beat {i+1}"),
                    goal=b.get("goal", ""),
                    tension=max(0, min(10, int(b.get("tension", 5)))))
               for i, b in enumerate(beats[:8])]).model_dump()

    # --- Content lists: second LLM pass if anything narratively load-
    # bearing is missing (RAG depends on places/persons/fragments etc.).
    _fill_missing_lists(cfg, prompt, data)

    return World.model_validate(data)
