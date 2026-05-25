"""Admin /api/worlds/{id}/suggest — verify the rich world-context
block actually flows into the gen-LLM's system prompt.

Before the rich-context patch, suggest only knew name + genre +
description + mood and could neither reference existing regions /
factions / persons / places nor avoid duplicating existing entries.
These tests pin the new behaviour by inspecting the system message
the endpoint sends to the mocked chat client.
"""

from __future__ import annotations

import json
import types

from storyteller_core.worlds.schema import (
    Beat,
    Blueprint,
    Creature,
    Faction,
    GlossaryEntry,
    HistoryEvent,
    Item,
    Person,
    Place,
    Region,
    TechMagic,
    World,
)
from storyteller_web_admin_backend.main import _suggest_context


def _rich_world() -> World:
    """A world populated with at least one entry per content kind +
    structured tech_magic so every branch of _suggest_context gets
    exercised."""
    return World(
        id="testwelt", name="Testwelt", genre="Mystery",
        description="Eine kleine düstere Inselkette.",
        player_role="Wandernde:r Notar:in",
        starting_situation="Ankunft im Hafen, ein Brief fehlt.",
        mood="melancholisch", ambience="Salz, ferne Glocken",
        magic_physics="leichte Magie über Schrift",
        narration_style="ruhig, zweite Person",
        regions=[Region(name="Nordmeer"), Region(name="Schattengründe")],
        places=[
            Place(name="Hafen", description="alt", region="Nordmeer"),
            Place(name="Leuchtturm", description="windig",
                  region="Schattengründe"),
        ],
        factions=[
            Faction(name="Notars-Gilde", goals="Verträge wahren"),
            Faction(name="Schmuggler", goals="Steuern umgehen"),
        ],
        persons=[
            Person(name="Lea", role="Wache",
                   faction="Notars-Gilde", faction_role="Späherin"),
            Person(name="Otkar", role="Bibliothekar"),
        ],
        items=[Item(name="Tintenkompass")],
        creatures=[Creature(name="Sturmaal", habitat="Nordmeer")],
        glossary=[GlossaryEntry(term="Sprung",
                                  definition="Inselwechsel")],
        history=[HistoryEvent(when="vor 100 Jahren",
                                title="Der Sturm")],
        fragments=[],
        tech_magic=TechMagic(kind="magic", description="Schrift bindet.",
                              rules=["Tinte verliert Macht ohne Berührung."],
                              cost_or_risk="Vergessen eines Namens"),
        blueprint=Blueprint(
            premise="Auftakt", escalation_rule="rise",
            beats=[Beat(name="Hook", goal="x", tension=2)]),
    )


def test_context_includes_world_wide_fields() -> None:
    w = _rich_world()
    ctx = _suggest_context(w, "place")
    # Every world-wide field shows up somewhere in the context block.
    assert "Testwelt" in ctx and "Mystery" in ctx
    assert "Wandernde" in ctx                   # SPIELERROLLE
    assert "Ankunft im Hafen" in ctx            # AUSGANGSSITUATION
    assert "melancholisch" in ctx               # STIMMUNG
    assert "ferne Glocken" in ctx               # AMBIENTE
    assert "Schrift" in ctx                     # PHYSIK/MAGIE
    assert "ruhig, zweite Person" in ctx        # ERZÄHLSTIL


def test_context_lists_regions_and_factions_verbatim() -> None:
    w = _rich_world()
    ctx = _suggest_context(w, "person")
    assert "Nordmeer" in ctx and "Schattengründe" in ctx
    assert "Notars-Gilde" in ctx and "Schmuggler" in ctx
    # The cross-cutting registries explicitly instruct verbatim use.
    assert "Namen verbatim verwenden" in ctx


def test_context_includes_techmagic_rules() -> None:
    w = _rich_world()
    ctx = _suggest_context(w, "item")
    assert "TECH/MAGIE-SYSTEM (magic)" in ctx
    assert "Schrift bindet" in ctx
    assert "Tinte verliert Macht ohne Berührung" in ctx
    assert "Vergessen eines Namens" in ctx       # cost_or_risk


def test_context_place_lists_existing_places_with_region() -> None:
    w = _rich_world()
    ctx = _suggest_context(w, "place")
    assert "BESTEHENDE ORTE" in ctx
    assert "Hafen" in ctx and "Region: Nordmeer" in ctx
    assert "Leuchtturm" in ctx and "Region: Schattengründe" in ctx


def test_context_person_lists_existing_persons_with_faction() -> None:
    w = _rich_world()
    ctx = _suggest_context(w, "person")
    assert "BESTEHENDE PERSONEN" in ctx
    assert "Lea" in ctx and "Wache" in ctx and "Notars-Gilde" in ctx
    assert "Otkar" in ctx and "Bibliothekar" in ctx


def test_context_kind_specific_catalogues_exclusive() -> None:
    """Place context shows places but NOT the persons / creatures
    catalogues (cross-cutting registries like regions still show)."""
    w = _rich_world()
    ctx_place = _suggest_context(w, "place")
    assert "BESTEHENDE ORTE" in ctx_place
    assert "BESTEHENDE PERSONEN" not in ctx_place
    assert "BESTEHENDE KREATUREN" not in ctx_place
    # Cross-cutting registries DO show on every kind.
    assert "REGIONEN" in ctx_place
    assert "FRAKTIONEN" in ctx_place


def test_context_faction_creature_history_glossary_fragment_branches() -> None:
    w = _rich_world()
    assert "BESTEHENDE FRAKTIONEN" in _suggest_context(w, "faction")
    assert "BESTEHENDE KREATUREN" in _suggest_context(w, "creature")
    assert "BESTEHENDE REGIONEN" in _suggest_context(w, "region")
    assert "BESTEHENDE GEGENSTÄNDE" in _suggest_context(w, "item")
    assert "BESTEHENDE BEGRIFFE" in _suggest_context(w, "glossary")
    assert "BESTEHENDE HISTORIE" in _suggest_context(w, "history")
    # Fragments are empty in the test world -> branch produces no
    # "BESTEHENDE FRAGMENTE" header (correct, nothing to dedupe against).
    assert "BESTEHENDE FRAGMENTE" not in _suggest_context(w, "fragment")


def test_context_caps_long_catalogues() -> None:
    """A 60-place world only shows the first 50 + a '(… und 10 weitere)'
    marker so the suggest prompt can't grow unbounded."""
    base = _rich_world()
    base.places = [Place(name=f"Ort {i}", description="x")
                   for i in range(60)]
    ctx = _suggest_context(base, "place")
    assert "Ort 0" in ctx and "Ort 49" in ctx
    assert "Ort 50" not in ctx                  # past the cap
    assert "und 10 weitere" in ctx


def _stub_chat_client_capturing():
    """Capture chat completion kwargs (especially `messages`) so the
    end-to-end suggest_piece test can assert what the LLM saw."""
    captured: list[dict] = []

    def create(**kw):
        captured.append(kw)
        payload = {"name": "Hafenmeister",
                   "description": "alt", "tags": []}
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=json.dumps(payload), tool_calls=None))],
            usage=types.SimpleNamespace(prompt_tokens=10,
                                         completion_tokens=10))

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=create)))
    return client, captured


def test_suggest_endpoint_sends_canon_rule_and_world_context(monkeypatch,
                                                              tmp_path) -> None:
    """End-to-end on the FastAPI route: load a rich world, hit POST
    /api/worlds/<id>/suggest, assert the captured system message
    carries the new CANON RULE wording + the rich context block."""
    import storyteller_core.config as config_mod

    monkeypatch.setattr(config_mod, "ROOT", tmp_path)
    (tmp_path / "data" / "worlds").mkdir(parents=True)
    config_mod.load_config.cache_clear()

    from storyteller_core.worlds.registry import save_world
    cfg = config_mod.load_config()
    w = _rich_world()
    save_world(cfg, w)

    client, captured = _stub_chat_client_capturing()
    from storyteller_core import oai as oai_mod
    monkeypatch.setattr(oai_mod, "get_chat_client",
                        lambda cfg, role="gen": client)

    from fastapi.testclient import TestClient
    from storyteller_web_admin_backend.main import app
    resp = TestClient(app).post(
        f"/api/worlds/{w.id}/suggest",
        json={"kind": "person",
              "prompt": "Schlage einen blinden Heiler vor"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["piece"]["name"] == "Hafenmeister"

    assert len(captured) == 1
    sys_msg = captured[0]["messages"][0]["content"]
    assert "CANON RULE" in sys_msg
    assert "verbatim" in sys_msg.lower()
    assert "WELT-KONTEXT" in sys_msg
    assert "BESTEHENDE PERSONEN" in sys_msg
    assert "Lea" in sys_msg
    assert "Notars-Gilde" in sys_msg

    # User's free-text hint ends up unchanged in the user message.
    user_msg = captured[0]["messages"][1]["content"]
    assert user_msg == "Schlage einen blinden Heiler vor"
