"""Cost tracking: paid-cloud detection, per-model pricing, world rollup.

Covers the OpenRouter regression (every call counted as $0 when base_url
was non-empty) and the per-model price overlay used on hybrid stacks.
"""

import json
from types import SimpleNamespace

import storyteller_core.config as cfgmod
from storyteller_core.config import load_config
from storyteller_core.story.cost import (
    CostTracker,
    chat_unit_prices,
    is_local_role,
    is_paid_cloud,
)
from storyteller_core.story.ledger import CostLedger


# ----------------------------- paid-cloud host detection -------------------


def test_is_paid_cloud_known_hosts():
    assert is_paid_cloud("https://api.openai.com/v1")
    assert is_paid_cloud("https://openrouter.ai/api/v1")
    # suffix matches catch shards / regional variants
    assert is_paid_cloud("https://eu.openai.com/v1")
    assert is_paid_cloud("https://my-deploy.openai.azure.com/")
    assert is_paid_cloud("https://shard-7.openrouter.ai/api/v1")


def test_is_paid_cloud_local_hosts():
    assert not is_paid_cloud("")
    assert not is_paid_cloud("http://192.168.1.50:8000/v1")
    assert not is_paid_cloud("http://localhost:11434/v1")
    assert not is_paid_cloud("http://ollama.lan:11434/v1")


def test_is_local_role_openrouter_is_paid(tmp_path, monkeypatch):
    """Regression: OpenRouter (non-empty base_url) must NOT be treated
    as local/free — otherwise the daily cap is silently disabled."""
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "models.json").write_text(json.dumps({
        "story_endpoint": {"base_url": "https://openrouter.ai/api/v1",
                           "api_key": "sk-or-…"},
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert not is_local_role(cfg, "story")


def test_is_local_role_empty_is_paid(tmp_path, monkeypatch):
    """Empty base_url means OpenAI default — paid."""
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert not is_local_role(cfg, "story")


def test_is_local_role_self_hosted_is_free(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "models.json").write_text(json.dumps({
        "story_endpoint": {"base_url": "http://192.168.1.50:8000/v1"},
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert is_local_role(cfg, "story")


# ----------------------------- per-model price lookup ----------------------


def test_chat_unit_prices_uses_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cost.json").write_text(json.dumps({
        "model_prices": {
            "gpt-5.4-mini": {"input": 0.075, "output": 0.30},
            "deepseek/deepseek-v4-pro": {"input": 0.14, "output": 0.28},
        },
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    pin, pout = chat_unit_prices(cfg, "gpt-5.4-mini")
    assert (pin, pout) == (0.075, 0.30)

    pin, pout = chat_unit_prices(cfg, "deepseek/deepseek-v4-pro")
    assert (pin, pout) == (0.14, 0.28)


def test_chat_unit_prices_falls_back_to_globals(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    pin, pout = chat_unit_prices(cfg, "some-unknown-model")
    assert pin == cfg.cost.usd_per_1m_input
    assert pout == cfg.cost.usd_per_1m_output


def test_cost_tracker_uses_model_specific_price(tmp_path, monkeypatch):
    """A chat call with a model in the overlay must be billed at the
    overlay's rate, not the global default."""
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "cost.json").write_text(json.dumps({
        "model_prices": {
            "expensive-model": {"input": 100.0, "output": 200.0},
        },
    }))
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    tr = CostTracker(cfg)
    usage = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    usd = tr.record_chat(usage, role="story", model="expensive-model")
    # 1M in @ $100 + 1M out @ $200 = $300
    assert abs(usd - 300.0) < 1e-6


# ----------------------------- world rollup --------------------------------


def test_worlds_for_aggregates_by_world(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    led = CostLedger(cfg)
    led.record(kind="chat", usd=0.01, world_id="immerwald",
               thread_id="t1", model="gpt-5.4-mini",
               chat_in=100, chat_out=50)
    led.record(kind="chat", usd=0.02, world_id="immerwald",
               thread_id="t1", model="gpt-5.4-mini",
               chat_in=200, chat_out=100)
    led.record(kind="chat", usd=0.05, world_id="sternenfahrt",
               thread_id="t2", model="gpt-5.4",
               chat_in=500, chat_out=250)
    led.record(kind="chat", usd=0.03, world_id=None,
               thread_id="t3", model="gpt-5.4")

    worlds = led.worlds_for(days=7)
    by_id = {w["world_id"]: w for w in worlds}

    assert abs(by_id["immerwald"]["usd"] - 0.03) < 1e-9
    assert by_id["immerwald"]["calls"] == 2
    assert by_id["immerwald"]["chat_in"] == 300
    assert by_id["immerwald"]["chat_out"] == 150

    assert abs(by_id["sternenfahrt"]["usd"] - 0.05) < 1e-9
    assert by_id["sternenfahrt"]["calls"] == 1

    assert "(ohne Welt)" in by_id
    assert abs(by_id["(ohne Welt)"]["usd"] - 0.03) < 1e-9

    # Sorted by usd descending
    assert worlds[0]["world_id"] == "sternenfahrt"
