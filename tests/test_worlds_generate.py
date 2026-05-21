"""World generation: a sparse first LLM response is hardened.

Mocks the generator client (no network): a minimal first pass must trigger
the second pass that fills the story-critical content lists, and all the
narrative fields (incl. voice_sample) must end up non-empty.
"""

import json
import types

import storyteller_core.worlds.generate as gen_mod
from storyteller_core.config import load_config


def _fake_client(calls):
    def create(**kw):
        calls.append(kw)
        m = types.SimpleNamespace(tool_calls=None)
        if len(calls) == 1:
            m.content = json.dumps(
                {"name": "Aurora", "description": "Eine Insel.", "genre": "Fantasy"})
        else:
            m.content = json.dumps({
                "places": [{"name": "Hafen", "description": "alt", "tags": []}],
                "persons": [{"name": "Lea", "role": "Wache", "description": "",
                             "relations": "", "tags": []}],
                "history": [{"when": "", "title": "Sturm", "description": ""}],
                "fragments": [{"title": "Gerücht", "text": "", "tags": []}],
                "random_tables": [{"name": "Wetter", "description": "",
                                   "entries": [{"weight": 1, "text": "Sturm"}]}],
            })
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=m)],
            usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))


def test_minimal_world_is_hardened(monkeypatch):
    calls: list = []
    monkeypatch.setattr(gen_mod, "get_gen_client", lambda cfg: _fake_client(calls))

    w = gen_mod.generate_world(load_config(), "Eine kleine Insel")

    assert len(calls) == 2                       # first pass + fill pass
    assert w.voice_sample.strip()
    assert w.starting_situation.strip()
    assert w.narration_style.strip()
    assert w.mood and w.ambience and w.magic_physics
    assert len(w.places) >= 1 and len(w.persons) >= 1
    assert len(w.history) >= 1 and len(w.fragments) >= 1
    assert len(w.random_tables) >= 1
    assert w.blueprint.beats                     # arc always present
