"""KnownFacts: cap eviction, update-in-place, and forget."""

from storyteller_core.story.knowledge import KnownFacts


def test_remember_updates_in_place():
    k = KnownFacts()
    assert k.remember("person", "Mara", "Heilerin").startswith("gemerkt")
    assert k.remember("person", "mara", "neue Notiz").startswith("aktualisiert")
    assert len(k.to_list()) == 1
    assert k.to_list()[0]["note"] == "neue Notiz"


def test_cap_evicts_noteless_first():
    k = KnownFacts()
    for i in range(5):
        k.remember("person", f"P{i}", note=("keep" if i == 2 else ""), cap=3)
    names = [f["name"] for f in k.to_list()]
    assert len(names) == 3
    assert "P2" in names              # the one with a note survives eviction


def test_forget():
    k = KnownFacts()
    k.remember("person", "Mara")
    k.remember("place", "Brunnen")
    assert k.forget("Mara").startswith("vergessen")
    assert k.forget("Nirgendwo") == "(nicht gefunden)"
    assert [f["name"] for f in k.to_list()] == ["Brunnen"]
