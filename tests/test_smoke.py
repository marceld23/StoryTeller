"""Smoke-Tests für das Gerüst (Phase 0)."""

from storyteller_core.config import load_config
from storyteller_core.worlds.seed import SEED_WORLDS


def test_config_loads():
    cfg = load_config()
    assert cfg.models.story_llm
    assert cfg.audio.backend in {"alsa_softvol", "pipewire"}


def test_two_seed_worlds():
    ids = {w.id for w in SEED_WORLDS}
    assert ids == {"sternenfahrt", "immerwald"}
    for w in SEED_WORLDS:
        assert w.blueprint.beats
        assert w.player_role
