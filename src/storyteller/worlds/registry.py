"""Welt-Laden: data/worlds/<id>.json bevorzugt, sonst Seed-Welt."""

from __future__ import annotations

from ..config import Config
from .schema import World
from .seed import SEED_WORLDS

_SEED = {w.id: w for w in SEED_WORLDS}


def all_world_ids(cfg: Config) -> list[str]:
    ids = set(_SEED)
    d = cfg.path(cfg.paths.worlds_dir)
    if d.exists():
        ids |= {p.stem for p in d.glob("*.json")}
    return sorted(ids)


def load_world(cfg: Config, world_id: str) -> World:
    p = cfg.path(cfg.paths.worlds_dir) / f"{world_id}.json"
    if p.exists():
        return World.model_validate_json(p.read_text())
    if world_id in _SEED:
        return _SEED[world_id]
    raise KeyError(f"unbekannte Welt: {world_id}")


def save_world(cfg: Config, world: World) -> str:
    import json

    d = cfg.path(cfg.paths.worlds_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{world.id}.json"
    p.write_text(json.dumps(world.model_dump(), ensure_ascii=False, indent=2))
    return str(p)
