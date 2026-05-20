"""World loading — locale aware.

Files: data/worlds/<id>.json (de) and data/worlds/<id>.<loc>.json (others).
Falls back to the de file and then the built-in seed world.
"""

from __future__ import annotations

import json

from ..config import Config
from ..i18n import LOCALES, norm
from .schema import World
from .seed import seed_worlds


def _fname(world_id: str, loc: str) -> str:
    return f"{world_id}.json" if loc == "de" else f"{world_id}.{loc}.json"


def _seed_map(loc: str) -> dict[str, World]:
    return {w.id: w for w in seed_worlds(loc)}


def all_world_ids(cfg: Config) -> list[str]:
    ids = set(_seed_map("de"))
    d = cfg.path(cfg.paths.worlds_dir)
    if d.exists():
        for p in d.glob("*.json"):
            stem = p.stem  # evtl. "<id>.<loc>"
            base = stem.rsplit(".", 1)[0] if stem.rsplit(".", 1)[-1] in \
                LOCALES else stem
            ids.add(base)
    return sorted(ids)


def load_world(cfg: Config, world_id: str) -> World:
    loc = norm(cfg.general.locale)
    d = cfg.path(cfg.paths.worlds_dir)
    for cand in (d / _fname(world_id, loc), d / _fname(world_id, "de")):
        if cand.exists():
            return World.model_validate_json(cand.read_text())
    sm = _seed_map(loc)
    if world_id in sm:
        return sm[world_id]
    if world_id in _seed_map("de"):
        return _seed_map("de")[world_id]
    raise KeyError(f"unbekannte Welt: {world_id}")


def save_world(cfg: Config, world: World, locale: str | None = None) -> str:
    loc = norm(locale or cfg.general.locale)
    d = cfg.path(cfg.paths.worlds_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / _fname(world.id, loc)
    p.write_text(json.dumps(world.model_dump(), ensure_ascii=False, indent=2))
    return str(p)
