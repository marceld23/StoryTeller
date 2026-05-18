"""Generate a complete world from a single text prompt (LLM, admin use)."""

from __future__ import annotations

import json
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
    "tone values are integers 0-5. tension is 0-10. Give 2-4 each of "
    "places/persons/items/glossary/history/fragments and 4-6 blueprint "
    "beats with a rising tension curve. Write all content in the same "
    "language as the user's prompt."
)


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")
    return s or "welt"


def generate_world(cfg: Config, prompt: str) -> World:
    """One prompt -> a validated World. Raises on hard failure."""
    r = get_client(cfg).chat.completions.create(
        model=cfg.models.story_llm,
        messages=[{"role": "system", "content": _SYS},
                  {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    data = json.loads(r.choices[0].message.content or "{}")

    data.setdefault("name", "Neue Welt")
    data["id"] = _slug(data.get("id") or data["name"])
    data.setdefault("genre", "")
    data.setdefault("description", prompt[:400])
    data.setdefault("player_role", "Hauptfigur")
    bp = data.get("blueprint") or {}
    beats = bp.get("beats") or []
    if not beats:
        beats = [{"name": "Aufhänger", "goal": "Lage etablieren",
                  "tension": 2},
                 {"name": "Zuspitzung", "goal": "Eskalation", "tension": 7},
                 {"name": "Auflösung", "goal": "Abschluss", "tension": 3}]
    data["blueprint"] = Blueprint(
        premise=bp.get("premise") or f"Eine Geschichte in {data['name']}.",
        beats=[Beat(name=b.get("name", f"Beat {i+1}"),
                    goal=b.get("goal", ""),
                    tension=max(0, min(10, int(b.get("tension", 5)))))
               for i, b in enumerate(beats[:8])]).model_dump()
    return World.model_validate(data)
