"""Transcript deletion: per-file + per-world cleanup hooks.

These cover the new behaviours the user requested: a per-transcript
manual delete (admin frontend trash icon) and the automatic purge
when a world is deleted or its save state is reset.
"""

from __future__ import annotations

import storyteller_core.config as cfgmod
from storyteller_core.config import load_config
from storyteller_core.story.transcript import (
    Transcript,
    delete_transcripts_for_world,
)


def _seed_transcript(cfg, session: str, lines: int = 3) -> str:
    """Helper: write a small transcript and return its filename."""
    tr = Transcript(cfg, session)
    for i in range(lines):
        tr.note(f"line {i}")
    return tr.path.name


def test_delete_transcripts_for_world_removes_matching_prefix(
        tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    # Three sessions of the target world + one of another world
    _seed_transcript(cfg, "immerwald-20260101-100000")
    _seed_transcript(cfg, "immerwald-20260102-200000")
    _seed_transcript(cfg, "immerwald-20260103-150000")
    other = _seed_transcript(cfg, "sternenfahrt-20260101-100000")

    result = delete_transcripts_for_world(cfg, "immerwald")
    assert result["world_id"] == "immerwald"
    assert result["deleted"] == 3
    assert len(result["files"]) == 3
    # Other world's transcript untouched
    remaining = sorted(
        p.name for p in (tmp_path / "data" / "transcripts").glob("*.jsonl"))
    assert remaining == [other]


def test_delete_transcripts_for_world_empty_world_id_is_safe(
        tmp_path, monkeypatch):
    """Defensive guard — an empty world_id must NEVER nuke everything."""
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    _seed_transcript(cfg, "immerwald-20260101-100000")
    _seed_transcript(cfg, "sternenfahrt-20260101-100000")

    result = delete_transcripts_for_world(cfg, "")
    assert result["deleted"] == 0
    # Both files still present
    assert len(list(
        (tmp_path / "data" / "transcripts").glob("*.jsonl"))) == 2


def test_delete_transcripts_for_world_no_transcripts_dir(
        tmp_path, monkeypatch):
    """When data/transcripts/ doesn't exist yet, this must NOT crash."""
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    # Note: no transcripts written; the dir is created on first
    # Transcript() construction, so we test the cold-path here.
    result = delete_transcripts_for_world(cfg, "immerwald")
    assert result["deleted"] == 0
    assert result["files"] == []


def test_delete_transcripts_for_world_no_prefix_collision(
        tmp_path, monkeypatch):
    """`im` must NOT match `immerwald-…` — the trailing dash in the
    prefix is the discriminator. Otherwise deleting world `im` would
    accidentally take out world `immerwald`."""
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    _seed_transcript(cfg, "im-20260101-100000")
    _seed_transcript(cfg, "immerwald-20260101-100000")

    result = delete_transcripts_for_world(cfg, "im")
    assert result["deleted"] == 1
    remaining = [p.name for p in
                 (tmp_path / "data" / "transcripts").glob("*.jsonl")]
    assert any("immerwald" in r for r in remaining)
