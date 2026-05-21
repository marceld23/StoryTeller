"""Admin model overrides (data/models.json) must actually reach cfg.models.

Regression test: this was silently broken after the monorepo migration
(core imported a non-existent .runtime), so overrides were ignored.
"""

import json

import storyteller_core.config as cfgmod
from storyteller_core.config import load_config


def test_model_overrides_apply(tmp_path, monkeypatch):
    # Isolate ROOT so we touch a temp data/ dir, not the real repo.
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "models.json").write_text(json.dumps({
        "story_llm": "gpt-5.4",
        "gen_llm": "",                # empty -> falls back to story_llm
        "frequency_penalty": 0.25,
        "bogus_key": "ignored",       # unknown key must be skipped, not crash
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    assert cfg.models.story_llm == "gpt-5.4"
    assert cfg.models.gen == "gpt-5.4"          # gen_llm "" -> story_llm
    assert cfg.models.frequency_penalty == 0.25


def test_no_override_file_is_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert cfg.models.story_llm  # defaults load without an override file
