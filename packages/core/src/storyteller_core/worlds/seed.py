"""Seed worlds — content lives in JSON resources inside this package.

The actual world data sits in `worlds/seeds/<id>.<locale>.json`, one
file per world per locale, generated/maintained via
`scripts/augment_seed_worlds.py`. seed.py is a thin loader so we get
machine-mergeable diffs in PRs (JSON), zero risk of Python literal
typos, and a single re-runnable script to refresh the seeds when the
schema grows.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from ..i18n import LOCALES, norm
from .schema import World

# Resource package: importlib.resources understands "package.subpackage"
# paths even when the wheel is installed elsewhere. For source installs
# it resolves to <repo>/packages/core/src/storyteller_core/worlds/seeds/.
_SEEDS_PKG = "storyteller_core.worlds.seeds"


def _load_locale(locale: str) -> list[World]:
    """Read every `*.<locale>.json` under the seeds resource dir,
    parse + validate each into a World. Returns them sorted by id so
    the order is stable across filesystems. Falls back to DE when the
    requested locale has no files at all (preserves the old
    seed_worlds() default behaviour)."""
    loc = norm(locale)
    suffix = f".{loc}.json"
    try:
        files = sorted(
            res for res in resources.files(_SEEDS_PKG).iterdir()
            if res.is_file() and res.name.endswith(suffix))
    except (ModuleNotFoundError, FileNotFoundError):
        files = []
    out: list[World] = []
    for res in files:
        try:
            data = json.loads(res.read_text(encoding="utf-8"))
            out.append(World.model_validate(data))
        except Exception as exc:
            import logging
            logging.getLogger("storyteller.seeds").warning(
                "could not load seed %s: %r", res.name, exc)
    return out


# Eagerly load both locales at import — cheap (a handful of JSON files,
# only on the first import) and keeps the public surface a plain list.
_BY_LOCALE: dict[str, list[World]] = {
    loc: _load_locale(loc) for loc in LOCALES
}
SEED_WORLDS: list[World] = _BY_LOCALE.get("de", [])


def seed_worlds(locale: str = "de") -> list[World]:
    return _BY_LOCALE.get(norm(locale), _BY_LOCALE.get("de", []))


def _fname(world_id: str, locale: str) -> str:
    return f"{world_id}.json" if norm(locale) == "de" \
        else f"{world_id}.{norm(locale)}.json"


def write_seed(worlds_dir: Path) -> list[Path]:
    """Materialize every seed world (both locales) into the user's
    `data/worlds/` directory using the operator-facing naming
    convention (bare `<id>.json` for DE, `<id>.<loc>.json` for the
    rest). Used by `storyteller-cli seed`."""
    worlds_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for loc in LOCALES:
        for w in seed_worlds(loc):
            p = worlds_dir / _fname(w.id, loc)
            p.write_text(json.dumps(w.model_dump(), ensure_ascii=False,
                                    indent=2))
            written.append(p)
    return written
