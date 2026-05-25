"""World loading + lifecycle — locale aware.

Files: data/worlds/<id>.json (de) and data/worlds/<id>.<loc>.json (others).
Falls back to the de file and then the built-in seed world.

Lifecycle helpers (delete / copy / rename) orchestrate the cleanup
across the three places a world leaves traces in:
  1. data/worlds/<id>.json        — the world JSON (one per locale)
  2. data/rag.db                  — RAG embeddings (`world_id` partition)
  3. data/checkpoints.db          — LangGraph saves (thread_id `pi-<id>`)
"""

from __future__ import annotations

import json
import logging
import re

from ..config import Config
from ..i18n import LOCALES, norm
from .schema import World
from .seed import seed_worlds

log = logging.getLogger("storyteller.worlds")

# Valid world id pattern: lowercase ASCII slug, must start with a letter
# so the file name is always a safe stem and never conflicts with the
# `<id>.<locale>.json` parser.
_WORLD_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


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


# --- lifecycle helpers ------------------------------------------------

def slugify_world_id(text: str) -> str:
    """Turn arbitrary spoken / typed input into a valid world id.
    German umlauts get ASCII-replaced first so "Justus' zweite Welt"
    becomes "justus_zweite_welt" instead of "justus___zweite_welt"."""
    s = (text or "").lower().strip()
    for src, dst in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(src, dst)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    # ID must start with a letter — prefix when it doesn't.
    if s and not s[0].isalpha():
        s = "w_" + s
    return s or "welt"


def is_valid_world_id(world_id: str) -> bool:
    return bool(_WORLD_ID_RE.match(world_id or ""))


def world_exists(cfg: Config, world_id: str) -> bool:
    """True iff a world by that id is loadable (file or built-in seed)."""
    d = cfg.path(cfg.paths.worlds_dir)
    for loc in LOCALES:
        if (d / _fname(world_id, loc)).exists():
            return True
    return world_id in _seed_map("de")


def delete_world(cfg: Config, world_id: str) -> dict:
    """Remove a world cleanly: JSON file(s) per locale + RAG embeddings
    + LangGraph checkpoints (`pi-<id>` and `pi-<id>-<ts>` variants).
    Returns a small report dict for callers to log / show in the UI.
    Web sessions (UUID thread_ids) are unaffected — they have no
    world correlation in their thread_id and are short-lived anyway."""
    from ..story.graph import delete_threads_matching
    from ..story.rag import WorldRAG
    from ..story.transcript import delete_transcripts_for_world

    d = cfg.path(cfg.paths.worlds_dir)
    files_removed: list[str] = []
    for loc in LOCALES:
        p = d / _fname(world_id, loc)
        if p.exists():
            p.unlink()
            files_removed.append(p.name)

    rag_rows = 0
    try:
        rag_rows = WorldRAG(cfg).purge_world(world_id)
    except Exception as exc:
        log.warning("purge_world failed for %r: %r", world_id, exc)

    threads = delete_threads_matching(f"pi-{world_id}")
    transcripts = delete_transcripts_for_world(cfg, world_id)
    out = {
        "world_id": world_id,
        "files_removed": files_removed,
        "rag_rows_removed": rag_rows,
        "checkpoint_rows_removed": (threads.get("checkpoints_deleted", 0)
                                     + threads.get("writes_deleted", 0)),
        "transcripts_removed": transcripts.get("deleted", 0),
    }
    log.info("delete_world: %s", out)
    return out


def copy_world(cfg: Config, source_id: str, new_id: str,
               new_name: str | None = None) -> World:
    """Duplicate a world JSON under `new_id` (and optionally rename it
    in the process). The copy is a fresh world definition — saved
    games of the source are NOT carried over (they remain attached
    to the source via `pi-<source_id>`). RAG is rebuilt for the copy
    from its content so it's queryable immediately."""
    from ..story.rag import WorldRAG

    if not is_valid_world_id(new_id):
        raise ValueError(f"invalid world id: {new_id!r}")
    if world_exists(cfg, new_id):
        raise ValueError(f"world id already in use: {new_id!r}")

    src = load_world(cfg, source_id)
    payload = src.model_dump()
    payload["id"] = new_id
    if new_name:
        payload["name"] = new_name
        payload["display_name"] = new_name
    elif src.name:
        # Disambiguate the duplicate name so the voice menu can tell
        # them apart even when the operator didn't supply a new label.
        payload["name"] = f"{src.name} (Kopie)"
        payload["display_name"] = payload["name"]
    copy = World.model_validate(payload)

    # Persist the copy in every locale that had a source file (plus
    # the default locale, since save_world picks the active locale).
    d = cfg.path(cfg.paths.worlds_dir)
    save_world(cfg, copy)
    for loc in LOCALES:
        src_p = d / _fname(source_id, loc)
        if loc != norm(cfg.general.locale) and src_p.exists():
            save_world(cfg, copy, locale=loc)

    try:
        WorldRAG(cfg).index_world(copy, force=True)
    except Exception as exc:
        log.warning("index_world failed for copy %r: %r", new_id, exc)

    log.info("copy_world: %s -> %s (%s)", source_id, new_id, copy.name)
    return copy


def rename_world(cfg: Config, source_id: str, new_id: str,
                 new_name: str | None = None) -> World:
    """Rename a world id (and optionally its display name). Saves are
    migrated by repointing `pi-<source_id>*` thread_ids to
    `pi-<new_id>*`; RAG partitions are moved server-side instead of
    being rebuilt from scratch (avoids the OpenAI embedding cost)."""
    from ..story.graph import migrate_thread_prefix
    from ..story.rag import WorldRAG

    if source_id == new_id and not new_name:
        return load_world(cfg, source_id)
    if not is_valid_world_id(new_id):
        raise ValueError(f"invalid world id: {new_id!r}")
    if new_id != source_id and world_exists(cfg, new_id):
        raise ValueError(f"world id already in use: {new_id!r}")

    src = load_world(cfg, source_id)
    payload = src.model_dump()
    payload["id"] = new_id
    if new_name:
        payload["name"] = new_name
        payload["display_name"] = new_name
    renamed = World.model_validate(payload)

    d = cfg.path(cfg.paths.worlds_dir)
    # Write the new files first (so a crash leaves both copies on disk
    # rather than losing data), then unlink the old files per locale.
    save_world(cfg, renamed)
    for loc in LOCALES:
        old_p = d / _fname(source_id, loc)
        new_p = d / _fname(new_id, loc)
        if loc != norm(cfg.general.locale) and old_p.exists():
            save_world(cfg, renamed, locale=loc)
        if new_id != source_id and old_p.exists() and old_p != new_p:
            old_p.unlink()

    if new_id != source_id:
        try:
            WorldRAG(cfg).move_world(source_id, new_id)
        except Exception as exc:
            log.warning("move_world failed: %r", exc)
        migrate_thread_prefix(f"pi-{source_id}", f"pi-{new_id}")

    log.info("rename_world: %s -> %s (%s)", source_id, new_id, renamed.name)
    return renamed
