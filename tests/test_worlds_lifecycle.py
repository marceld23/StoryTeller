"""Round-trip tests for the registry lifecycle helpers
(delete_world / copy_world / rename_world).

Uses a temp ROOT so the real on-disk worlds + checkpoints + RAG DB
stay untouched. Verifies:
- delete cleans JSON + checkpoint threads (and reports row counts)
- copy duplicates the world, keeps the original, names the duplicate
- rename moves the JSON, preserves the world body, returns the new id
- slugify + is_valid_world_id sanity
- 409-style conflict when new id is already taken
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import storyteller_core.config as config_mod
from storyteller_core.worlds.registry import (
    all_world_ids,
    copy_world,
    delete_world,
    is_valid_world_id,
    load_world,
    rename_world,
    save_world,
    slugify_world_id,
    world_exists,
)
from storyteller_core.worlds.schema import Blueprint, World


def _minimal_world(world_id: str, name: str = "Testwelt") -> World:
    """Smallest valid World we can persist + reload."""
    return World(
        id=world_id, name=name, genre="Fantasy",
        description="Eine kleine Testwelt.", player_role="Held:in",
        blueprint=Blueprint(premise="Eine Spannung."),
    )


@pytest.fixture
def tmp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Repoint ROOT at a tmp dir so registry helpers operate on
    isolated worlds/ + rag.db + checkpoints.db. Clears load_config's
    cache so the patched ROOT is picked up immediately."""
    monkeypatch.setattr(config_mod, "ROOT", tmp_path)
    (tmp_path / "data" / "worlds").mkdir(parents=True)
    config_mod.load_config.cache_clear()
    return tmp_path


def _checkpoint_db(root: Path) -> Path:
    p = root / "data" / "checkpoints.db"
    if not p.exists():
        # Pre-create the same schema delete_threads_matching expects.
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p))
        conn.executescript(
            "CREATE TABLE checkpoints (thread_id TEXT, payload TEXT);"
            "CREATE TABLE writes (thread_id TEXT, payload TEXT);"
        )
        conn.commit()
        conn.close()
    return p


def _seed_checkpoints(root: Path, thread_ids: list[str]) -> None:
    p = _checkpoint_db(root)
    conn = sqlite3.connect(str(p))
    for tid in thread_ids:
        conn.execute("INSERT INTO checkpoints VALUES (?, ?)", (tid, "x"))
        conn.execute("INSERT INTO writes VALUES (?, ?)", (tid, "y"))
    conn.commit()
    conn.close()


def _count_threads(root: Path, like: str) -> int:
    p = _checkpoint_db(root)
    conn = sqlite3.connect(str(p))
    n = conn.execute("SELECT count(*) FROM checkpoints WHERE thread_id LIKE ?",
                     (like,)).fetchone()[0]
    conn.close()
    return n


def test_slugify_and_validation() -> None:
    assert slugify_world_id("Justus zweite Welt") == "justus_zweite_welt"
    assert slugify_world_id("Mörder & Diebe") == "moerder_diebe"
    assert slugify_world_id("123 Test") == "w_123_test"  # leading digit prefixed
    assert slugify_world_id("   ") == "welt"             # fallback
    assert is_valid_world_id("sternenfahrt")
    assert is_valid_world_id("a")
    assert not is_valid_world_id("")
    assert not is_valid_world_id("123foo")               # must start with letter
    assert not is_valid_world_id("foo-bar")              # no dashes


def test_copy_world_creates_independent_copy(tmp_root: Path) -> None:
    cfg = config_mod.load_config()
    src = _minimal_world("ursprung", name="Ursprungswelt")
    save_world(cfg, src)

    # Copy without explicit new_name → "(Kopie)" suffix auto-applied
    new = copy_world(cfg, "ursprung", "kopie_eins")
    assert new.id == "kopie_eins"
    assert "Kopie" in new.name
    # Both files coexist
    assert (tmp_root / "data" / "worlds" / "ursprung.json").exists()
    assert (tmp_root / "data" / "worlds" / "kopie_eins.json").exists()
    # Loadable round-trip
    reloaded = load_world(cfg, "kopie_eins")
    assert reloaded.id == "kopie_eins"
    assert reloaded.genre == "Fantasy"

    # Conflict: copying again to the same id raises
    with pytest.raises(ValueError, match="already in use"):
        copy_world(cfg, "ursprung", "kopie_eins")


def test_copy_world_with_explicit_new_name(tmp_root: Path) -> None:
    cfg = config_mod.load_config()
    save_world(cfg, _minimal_world("ursprung", name="Quelle"))
    new = copy_world(cfg, "ursprung", "ziel", new_name="Ziel-Welt")
    assert new.name == "Ziel-Welt"
    assert new.display_name == "Ziel-Welt"


def test_rename_world_moves_files_and_keeps_body(tmp_root: Path) -> None:
    cfg = config_mod.load_config()
    save_world(cfg, _minimal_world("alt", name="Alte Welt"))
    new = rename_world(cfg, "alt", "neu", new_name="Neue Welt")
    assert new.id == "neu"
    assert new.name == "Neue Welt"
    assert not (tmp_root / "data" / "worlds" / "alt.json").exists()
    assert (tmp_root / "data" / "worlds" / "neu.json").exists()
    body: dict[str, Any] = json.loads(
        (tmp_root / "data" / "worlds" / "neu.json").read_text())
    assert body["id"] == "neu"
    assert body["genre"] == "Fantasy"


def test_rename_world_migrates_checkpoints(tmp_root: Path) -> None:
    cfg = config_mod.load_config()
    save_world(cfg, _minimal_world("alt"))
    _seed_checkpoints(tmp_root, [
        "pi-alt",
        "pi-alt-1700000000",
        "pi-andereswelt",       # unrelated, must NOT be touched
        "web-uuid-abcdef",      # unrelated
    ])
    rename_world(cfg, "alt", "neu")
    # Old pi-alt* gone, pi-neu* present, others untouched
    assert _count_threads(tmp_root, "pi-alt%") == 0
    assert _count_threads(tmp_root, "pi-neu%") == 2
    assert _count_threads(tmp_root, "pi-andereswelt%") == 1
    assert _count_threads(tmp_root, "web-%") == 1


def test_delete_world_cleans_files_and_checkpoints(tmp_root: Path) -> None:
    cfg = config_mod.load_config()
    save_world(cfg, _minimal_world("zumloeschen"))
    _seed_checkpoints(tmp_root, [
        "pi-zumloeschen",
        "pi-zumloeschen-1700000000",
        "pi-bleibtdraussen",
    ])

    report = delete_world(cfg, "zumloeschen")
    assert report["world_id"] == "zumloeschen"
    assert "zumloeschen.json" in report["files_removed"]
    assert report["checkpoint_rows_removed"] == 4  # 2 threads × (checkpoints+writes)

    assert not (tmp_root / "data" / "worlds" / "zumloeschen.json").exists()
    assert _count_threads(tmp_root, "pi-zumloeschen%") == 0
    assert _count_threads(tmp_root, "pi-bleibtdraussen%") == 1
    assert "zumloeschen" not in all_world_ids(cfg)


def test_world_exists_checks_files_and_seed(tmp_root: Path) -> None:
    cfg = config_mod.load_config()
    assert not world_exists(cfg, "ganz_neue_welt")
    save_world(cfg, _minimal_world("ganz_neue_welt"))
    assert world_exists(cfg, "ganz_neue_welt")
