"""World generation: the multi-step pipeline produces a complete world
even when the LLM under-delivers on individual steps.

Mocks the generator client (no network). Verifies:
- Exactly one LLM call per pipeline step (skeleton + tech_magic +
  blueprint + 10 lists incl. regions, factions, creatures).
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
        # 2: tech_magic
        {"kind": "magic", "description": "Windrituale binden Routen.",
         "rules": ["Karten verlieren Tinte ohne Berührung."],
         "cost_or_risk": "Ein Ritual kostet einen Atemzug Erinnerung."},
        # 3: blueprint (empty -> triggers fallback)
        {},
        # 4: regions
        {"regions": [{"name": "Nordmeer", "description": "rau", "tags": []},
                     {"name": "Schattengründe", "description": "tief",
                      "tags": []}]},
        # 5: places
        {"places": [{"name": "Hafen", "description": "alt",
                     "region": "Nordmeer", "contains": [], "adjacent": [],
                     "tags": []},
                    {"name": "Leuchtturm", "description": "windig",
                     "region": "Nordmeer", "contains": [], "adjacent": [],
                     "tags": []}]},
        # 6: factions
        {"factions": [{"name": "Kartografen-Gilde", "description": "alt",
                       "goals": "Karten retten", "allies": [],
                       "enemies": [], "relations": "", "tags": []}]},
        # 7: persons
        {"persons": [{"name": "Lea", "role": "Wache", "description": "",
                      "relations": "", "faction": "Kartografen-Gilde",
                      "faction_role": "Späherin", "tags": []}]},
        # 8: items
        {"items": [{"name": "Kompass", "description": "alt",
                    "properties": "", "tags": []}]},
        # 9: creatures
        {"creatures": [{"name": "Sturmaal", "description": "blass",
                        "habitat": "Nordmeer", "threat_level": "medium",
                        "tags": []}]},
        # 10: glossary
        {"glossary": [{"term": "Sprung", "definition": "Inselwechsel"}]},
        # 11: history
        {"history": [{"when": "vor 100 Jahren", "title": "Der Sturm",
                      "description": ""}]},
        # 12: fragments
        {"fragments": [{"title": "Gerücht", "text": "Etwas treibt im "
                        "Wasser.", "tags": []}]},
        # 13: random_tables
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

    # 13 calls: skeleton + tech_magic + blueprint + 10 lists.
    assert len(calls) == 13

    # Narrative fields filled (some from LLM, some via fallback)
    assert w.name == "Aurora"
    assert w.voice_sample.strip()
    assert w.starting_situation.strip()
    assert w.narration_style.strip()
    assert w.mood and w.ambience and w.magic_physics

    # Blueprint fallback kicked in (LLM returned empty)
    assert w.blueprint.beats
    assert len(w.blueprint.beats) >= 4

    # Structured tech/magic system landed.
    assert w.tech_magic is not None
    assert w.tech_magic.kind == "magic"
    assert w.tech_magic.rules

    # Per-list calls populated all lists.
    assert len(w.regions) >= 2
    assert len(w.places) >= 2
    assert w.places[0].region == "Nordmeer"          # canon constraint held
    assert len(w.factions) >= 1
    assert len(w.persons) >= 1
    assert w.persons[0].faction == "Kartografen-Gilde"
    assert len(w.items) >= 1
    assert len(w.creatures) >= 1
    assert w.creatures[0].habitat == "Nordmeer"
    assert len(w.glossary) >= 1
    assert len(w.history) >= 1
    assert len(w.fragments) >= 1
    assert len(w.random_tables) >= 1
