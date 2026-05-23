"""World generation: the multi-step pipeline produces a complete world
even when the LLM under-delivers on individual steps.

Mocks the generator client (no network). Verifies:
- Exactly one LLM call per pipeline step (skeleton + blueprint + 7 lists).
- Narrative fallbacks fill empty fields.
- Blueprint always ends up with beats (functional fallback if LLM was empty).
- Lists populate from per-list calls.
"""

import json
import types

import storyteller_core.worlds.generate as gen_mod
from storyteller_core.config import load_config


def _fake_client(calls):
    """Returns canned JSON per call index, mimicking each pipeline step."""
    responses = [
        # 1: skeleton
        {"name": "Aurora", "genre": "Fantasy",
         "description": "Eine windige Inselkette.",
         "player_role": "Kartograf:in"},
        # 2: blueprint (empty -> triggers fallback)
        {},
        # 3: places
        {"places": [{"name": "Hafen", "description": "alt", "tags": []},
                    {"name": "Leuchtturm", "description": "windig",
                     "tags": []}]},
        # 4: persons
        {"persons": [{"name": "Lea", "role": "Wache", "description": "",
                      "relations": "", "tags": []}]},
        # 5: items
        {"items": [{"name": "Kompass", "description": "alt",
                    "properties": "", "tags": []}]},
        # 6: glossary
        {"glossary": [{"term": "Sprung", "definition": "Inselwechsel"}]},
        # 7: history
        {"history": [{"when": "vor 100 Jahren", "title": "Der Sturm",
                      "description": ""}]},
        # 8: fragments
        {"fragments": [{"title": "Gerücht", "text": "Etwas treibt im "
                        "Wasser.", "tags": []}]},
        # 9: random_tables
        {"random_tables": [{"name": "Wetter", "description": "",
                            "entries": [{"weight": 1, "text": "Sturm"}]}]},
    ]

    def create(**kw):
        idx = len(calls)
        calls.append(kw)
        payload = responses[idx] if idx < len(responses) else {}
        m = types.SimpleNamespace(
            content=json.dumps(payload), tool_calls=None)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=m)],
            usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create)))


def test_multistep_pipeline_produces_full_world(monkeypatch):
    calls: list = []
    monkeypatch.setattr(gen_mod, "get_chat_client",
                        lambda cfg, role="gen": _fake_client(calls))

    w = gen_mod.generate_world(load_config(), "Eine kleine Inselkette")

    # 9 calls: skeleton + blueprint + 7 lists
    assert len(calls) == 9

    # Narrative fields filled (some from LLM, some via fallback)
    assert w.name == "Aurora"
    assert w.voice_sample.strip()
    assert w.starting_situation.strip()
    assert w.narration_style.strip()
    assert w.mood and w.ambience and w.magic_physics

    # Blueprint fallback kicked in (LLM returned empty)
    assert w.blueprint.beats
    assert len(w.blueprint.beats) >= 4

    # Per-list calls populated all lists
    assert len(w.places) >= 2
    assert len(w.persons) >= 1
    assert len(w.items) >= 1
    assert len(w.glossary) >= 1
    assert len(w.history) >= 1
    assert len(w.fragments) >= 1
    assert len(w.random_tables) >= 1
