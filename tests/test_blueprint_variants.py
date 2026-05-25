"""Multi-variant blueprint plumbing.

Covers:
- World.active_blueprint legacy fallback (single-arc worlds with empty
  blueprints[] still resolve to the bare `blueprint` field).
- World.active_blueprint clamps invalid indices instead of raising
  (a stale checkpoint with blueprint_choice past the variant count
  must still produce a valid Blueprint, not crash mid-turn).
- generate.py's _generate_blueprints turns a 3-variant LLM response
  into the correct BlueprintVariant shape, validates length /
  structure / twist_kind, and falls back to one default variant on
  total LLM failure.
- substory.choose_blueprint_variant short-circuits to 0 for single-
  variant worlds (no LLM call) and respects an LLM JSON pick.
"""

from __future__ import annotations

import json
import types

import storyteller_core.worlds.generate as gen_mod
from storyteller_core.config import load_config
from storyteller_core.story.substory import choose_blueprint_variant
from storyteller_core.worlds.schema import (
    Beat,
    Blueprint,
    BlueprintVariant,
    World,
)


def _legacy_world() -> World:
    """A single-arc world (blueprints=[], blueprint set) — same shape
    every existing seed world ships with today."""
    return World(
        id="legacy", name="Legacy", genre="Fantasy",
        description="…", player_role="Held:in",
        blueprint=Blueprint(
            premise="A.", escalation_rule="rise",
            beats=[Beat(name="Hook", goal="x", tension=2),
                   Beat(name="Climax", goal="y", tension=9)]),
    )


def _multi_world() -> World:
    """A world with 2 variants — both have distinct beats so we can
    tell which one active_blueprint returned."""
    a = BlueprintVariant(
        name="A", length="short", structure="linear", twist_kind="",
        blueprint=Blueprint(
            premise="short arc", escalation_rule="rise",
            beats=[Beat(name="A1", goal="a1", tension=2),
                   Beat(name="A2", goal="a2", tension=9)]))
    b = BlueprintVariant(
        name="B", length="long", structure="spiral", twist_kind="betrayal",
        blueprint=Blueprint(
            premise="long arc", escalation_rule="rise",
            beats=[Beat(name="B1", goal="b1", tension=1),
                   Beat(name="B2", goal="b2", tension=4),
                   Beat(name="B3", goal="b3", tension=8),
                   Beat(name="B4", goal="b4", tension=3)]))
    return World(
        id="multi", name="Multi", genre="SF",
        description="…", player_role="Held:in",
        blueprint=a.blueprint,         # legacy field mirrors variants[0]
        blueprints=[a, b])


def test_active_blueprint_legacy_fallback() -> None:
    w = _legacy_world()
    bp = w.active_blueprint(0)
    assert bp.premise == "A."
    # choice is ignored when blueprints is empty — same arc returned
    assert w.active_blueprint(99).premise == "A."
    assert w.variant_count() == 1


def test_active_blueprint_picks_variant() -> None:
    w = _multi_world()
    assert w.active_blueprint(0).beats[0].name == "A1"
    assert w.active_blueprint(1).beats[0].name == "B1"
    # out-of-range -> clamped to last variant (defensive against stale
    # checkpoints with blueprint_choice past the current variant count)
    assert w.active_blueprint(42).beats[0].name == "B1"
    assert w.active_blueprint(-1).beats[0].name == "A1"
    assert w.variant_count() == 2


def _mock_chat_client(responses: list[dict]):
    """OpenAI-shaped chat client whose .chat.completions.create returns
    canned JSON from `responses` in order. Tracks how many calls
    were made via `calls`."""
    calls: list[dict] = []

    def create(**kw):
        idx = len(calls)
        calls.append(kw)
        payload = responses[idx] if idx < len(responses) else {}
        msg = types.SimpleNamespace(content=json.dumps(payload),
                                     tool_calls=None)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=msg)],
            usage=types.SimpleNamespace(prompt_tokens=1,
                                         completion_tokens=1))

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create)))
    return client, calls


def test_choose_variant_skips_llm_for_single_arc(monkeypatch) -> None:
    cfg = load_config()
    w = _legacy_world()
    # Sabotage the chat client — must NOT be called for single arc.
    def boom(*a, **kw):
        raise AssertionError("LLM was called for a single-variant world")
    monkeypatch.setattr("storyteller_core.story.substory.get_chat_client",
                        boom)
    assert choose_blueprint_variant(cfg, w) == 0


def test_choose_variant_picks_llm_index(monkeypatch) -> None:
    cfg = load_config()
    w = _multi_world()
    client, calls = _mock_chat_client([{"choice": 1, "why": "fits better"}])
    monkeypatch.setattr("storyteller_core.story.substory.get_chat_client",
                        lambda cfg, role="planner": client)
    out = choose_blueprint_variant(cfg, w, known_summary="some hint")
    assert out == 1
    assert len(calls) == 1


def test_choose_variant_clamps_invalid_index(monkeypatch) -> None:
    cfg = load_config()
    w = _multi_world()
    client, _ = _mock_chat_client([{"choice": 99}])
    monkeypatch.setattr("storyteller_core.story.substory.get_chat_client",
                        lambda cfg, role="planner": client)
    # 99 is out-of-range -> falls back to safe 0
    assert choose_blueprint_variant(cfg, w) == 0


def test_generate_blueprints_normalises_three_variants(monkeypatch) -> None:
    cfg = load_config()
    payload = {
        "variants": [
            {"name": "Schnell", "length": "short", "structure": "linear",
             "twist_kind": "revelation",
             "trigger_hints": ["erstes mal"],
             "premise": "Kurz.", "escalation_rule": "rise",
             "beats": [{"name": "Hook", "goal": "x", "tension": 2},
                       {"name": "End", "goal": "y", "tension": 9}]},
            {"name": "Mittel", "length": "medium", "structure": "spiral",
             "twist_kind": "betrayal", "trigger_hints": [],
             "premise": "Mittel.", "escalation_rule": "rise",
             "beats": [{"name": "B1", "goal": "g", "tension": 3},
                       {"name": "B2", "goal": "g", "tension": 6},
                       {"name": "B3", "goal": "g", "tension": 9}]},
            # Variant with bogus field values — should be coerced to defaults.
            {"name": "Voll", "length": "bogus", "structure": "weird",
             "twist_kind": "??", "trigger_hints": "not a list",
             "premise": "", "escalation_rule": "",
             "beats": []},
        ]
    }
    client, calls = _mock_chat_client([payload])
    monkeypatch.setattr(gen_mod, "get_chat_client",
                        lambda cfg, role="gen": client)

    variants = gen_mod._generate_blueprints(
        cfg, {"name": "Aurora"}, "prompt", None)
    assert len(calls) == 1
    assert len(variants) == 3
    assert variants[0]["name"] == "Schnell"
    assert variants[0]["length"] == "short"
    assert variants[0]["twist_kind"] == "revelation"
    # Bogus values coerced
    assert variants[2]["length"] == "medium"     # bogus -> default
    assert variants[2]["structure"] == "linear"  # bogus -> default
    assert variants[2]["twist_kind"] == ""       # bogus -> default
    assert variants[2]["trigger_hints"] == []    # non-list -> default
    # Empty beats fall back to the default skeleton
    assert len(variants[2]["blueprint"]["beats"]) >= 4


def test_generate_blueprints_fallback_on_total_failure(monkeypatch) -> None:
    cfg = load_config()
    # Empty {} -> no `variants` key -> one safe default variant
    client, _ = _mock_chat_client([{}])
    monkeypatch.setattr(gen_mod, "get_chat_client",
                        lambda cfg, role="gen": client)
    variants = gen_mod._generate_blueprints(
        cfg, {"name": "Aurora"}, "prompt", None)
    assert len(variants) == 1
    assert variants[0]["name"] == "Hauptbogen"
    assert variants[0]["blueprint"]["beats"]


def test_full_pipeline_populates_blueprints(monkeypatch) -> None:
    """Sanity-check generate_world end-to-end: the 3-variant blueprint
    call lands in `world.blueprints` AND the legacy `world.blueprint`
    mirrors variants[0]."""
    cfg = load_config()
    skeleton_payload = {
        "name": "Aurora", "genre": "Fantasy",
        "description": "Eine windige Inselkette.",
        "player_role": "Kartograf:in"}
    tech_magic_payload = {"kind": "magic", "description": "",
                           "rules": [], "cost_or_risk": ""}
    blueprints_payload = {
        "variants": [
            {"name": "Erster Bogen", "length": "short", "structure": "linear",
             "twist_kind": "", "trigger_hints": [],
             "premise": "Auftakt.", "escalation_rule": "rise",
             "beats": [{"name": "Hook", "goal": "x", "tension": 2},
                       {"name": "End", "goal": "y", "tension": 9}]},
            {"name": "Zweiter Bogen", "length": "medium", "structure": "spiral",
             "twist_kind": "betrayal", "trigger_hints": [],
             "premise": "Vertiefung.", "escalation_rule": "rise",
             "beats": [{"name": "B1", "goal": "g", "tension": 3}]},
        ]}
    list_payload = {"places": [{"name": "Hafen", "description": "alt",
                                  "region": "", "contains": [],
                                  "adjacent": [], "tags": []}]}
    responses = [skeleton_payload, tech_magic_payload, blueprints_payload]
    # 10 lists (regions/places/factions/persons/items/creatures/glossary/
    # history/fragments/random_tables) get the same minimal payload —
    # the test only cares about the blueprint part.
    responses += [list_payload] * 10
    client, calls = _mock_chat_client(responses)
    monkeypatch.setattr(gen_mod, "get_chat_client",
                        lambda cfg, role="gen": client)

    w = gen_mod.generate_world(cfg, "Eine kleine Inselkette")
    assert len(w.blueprints) == 2
    assert w.blueprints[0].name == "Erster Bogen"
    # Legacy field mirrors variants[0]
    assert w.blueprint.premise == "Auftakt."
    # active_blueprint helpers dispatch correctly
    assert w.active_blueprint(0).beats[0].name == "Hook"
    assert w.active_blueprint(1).beats[0].name == "B1"
    # Still exactly 13 LLM calls — multi-variant doesn't multiply cost
    assert len(calls) == 13
