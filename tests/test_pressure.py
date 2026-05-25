"""Soft plot-pressure controller — classifier + aggregator + thresholds.

These tests cover the pure functions in storyteller_core.story.pressure
(no LangGraph, no LLM calls). They lock in the design from the
"Storymodus" feature: a continuous 0..1 dial driven by per-turn signals,
EMA-smoothed, with five threshold-based consumers (gate, substory
block tier, beat-nudge, substory tools, planning).
"""

from __future__ import annotations

import storyteller_core.config as cfgmod
from storyteller_core.config import load_config
from storyteller_core.story.pressure import (
    TurnSignal,
    beat_nudge_threshold,
    classify,
    compute_target_pressure,
    effective_pressure,
    gate_max_reveals,
    gate_should_run,
    is_valid_story_mode,
    signal_to_dict,
    substory_block_mode,
    substory_planning_enabled,
    substory_tools_visible,
    tiebreaker_should_run,
    update_pressure,
)
from storyteller_core.story.tools import (
    NARRATIVE_TOOLS,
    TOOLS,
    tools_for_pressure,
)

# ---- TurnSignal classifier ------------------------------------------------


def test_classify_advance_beat_is_strong_plot_pull():
    sig = classify(
        player_text="ich frage den Wirt",
        tool_calls=[{"name": "advance_beat", "args": {}}],
        substory={"involved_persons": ["Wirt"], "involved_places": []},
        beat_dwell=2,
    )
    assert sig.advanced is True
    assert sig.pull() >= 0.85


def test_classify_complete_substory_counts_as_advanced():
    sig = classify(
        player_text="...",
        tool_calls=[{"name": "complete_substory", "args": {"summary": "x"}}],
        substory={},
        beat_dwell=4,
    )
    assert sig.advanced is True


def test_classify_explicit_free_dominates():
    sig = classify(
        player_text="lass uns einfach durch den Markt laufen",
        tool_calls=[{"name": "advance_beat", "args": {}}],  # contradiction
        substory={"involved_persons": ["Otkar"]},
        beat_dwell=1,
    )
    assert sig.explicit_free is True
    # Explicit phrase wins over advanced tool call
    assert sig.pull() == 0.0


def test_classify_explicit_plot_pulls_up():
    sig = classify(
        player_text="was war nochmal die Mission?",
        tool_calls=[],
        substory={},
        beat_dwell=8,
    )
    assert sig.explicit_plot is True
    assert sig.pull() == 1.0


def test_classify_on_arc_lex_via_involved_person():
    sig = classify(
        player_text="Ich frage den Schiffsführer Otkar nach dem Boot.",
        tool_calls=[],
        substory={"involved_persons": ["Otkar"], "involved_places": []},
        beat_dwell=1,
    )
    assert sig.on_arc_lex is True
    assert sig.pull() == 0.8


def test_classify_off_arc_world_query():
    sig = classify(
        player_text="Erzähl mir mehr über die Geschichte der Stadt.",
        tool_calls=[{"name": "retrieve_world_fact",
                     "args": {"query": "Stadt", "fact_type": "history"}}],
        substory={"involved_persons": ["Otkar"]},
        beat_dwell=2,
    )
    assert sig.off_arc_world_query is True
    assert sig.pull() == 0.2


def test_classify_lateral_default():
    sig = classify(
        player_text="Ich bestelle ein Bier.",
        tool_calls=[],
        substory={"involved_persons": ["Otkar"]},
        beat_dwell=1,
    )
    assert sig.pull() == 0.5


def test_classify_thin_substory_biases_pull_positive():
    """The justus_scify session bug: a fallback-stub substory has
    empty involved_persons/places and generic beat names. With the old
    code that meant on_arc_lex was always False and the pressure
    drifted DOWN even though the player was deeply engaged with the
    plot. Fix: substory_lex_thin signal → default pull lifts to 0.65."""
    thin_sub = {
        # Same shape as the bug observed in production
        "title": "Eine unerwartete Wendung",
        "involved_persons": [],
        "involved_places": [],
        "hook": "Etwas zwingt zum Handeln.",
        "beats": [{"name": "Aufhänger", "goal": "Lage etablieren"},
                  {"name": "Zuspitzung", "goal": "Eskalation"}],
        "cursor": 1,
    }
    sig = classify(
        player_text="Ich gehe weiter, breche die Tür auf.",
        tool_calls=[],
        substory=thin_sub,
        beat_dwell=3,
    )
    assert sig.substory_lex_thin is True
    assert sig.pull() == 0.65   # plot-positive default, not 0.5


def test_classify_thin_substory_suppresses_off_arc_world_query():
    """When the arc is thin a history retrieve isn't really off-arc —
    there's no arc to be off from. Keeps the heuristic from punishing
    the player for the planner's mistake."""
    thin_sub = {
        "involved_persons": [],
        "involved_places": [],
        "hook": "x",
        "beats": [{"name": "a", "goal": "b"}],
    }
    sig = classify(
        player_text="erzähl mir mehr über die Geschichte",
        tool_calls=[{"name": "retrieve_world_fact",
                     "args": {"query": "stadt", "fact_type": "history"}}],
        substory=thin_sub,
        beat_dwell=2,
    )
    assert sig.substory_lex_thin is True
    assert sig.off_arc_world_query is False
    assert sig.pull() == 0.65


def test_classify_concrete_substory_not_thin():
    """A substory with concrete involved_persons is NOT thin even if
    the player input doesn't lexically match it (lateral happens)."""
    sub = {"involved_persons": ["Otkar"],
           "involved_places": ["Hafen"],
           "hook": "Schmuggler im Hafen finden",
           "beats": []}
    sig = classify(
        player_text="Ich bestelle ein Bier.",
        tool_calls=[],
        substory=sub,
        beat_dwell=1,
    )
    assert sig.substory_lex_thin is False
    assert sig.pull() == 0.5


def test_classify_tiebreaker_overrides_when_confident():
    sig = TurnSignal(off_arc_world_query=True,
                     tiebreaker_direction="toward_beat",
                     tiebreaker_confidence=0.8)
    # tiebreaker says on_arc → overrides the off_arc_world_query signal
    assert sig.pull() == 0.9


def test_classify_tiebreaker_ignored_low_confidence():
    sig = TurnSignal(off_arc_world_query=True,
                     tiebreaker_direction="toward_beat",
                     tiebreaker_confidence=0.4)
    # confidence below 0.7 → heuristic stands
    assert sig.pull() == 0.2


# ---- aggregator -----------------------------------------------------------


def test_compute_target_pressure_empty_window_is_warm():
    # Fresh session → bias toward planned mode
    assert compute_target_pressure([]) >= 0.8


def test_compute_target_pressure_recency_weighted():
    # Old off-arc signals get less weight than recent on-arc signals
    window = [
        signal_to_dict(TurnSignal(off_arc_world_query=True)),  # 0.2
        signal_to_dict(TurnSignal(off_arc_world_query=True)),  # 0.2
        signal_to_dict(TurnSignal(advanced=True)),             # 0.9
        signal_to_dict(TurnSignal(advanced=True)),             # 0.9
    ]
    # Linear weights 1,2,3,4 → (0.2 + 0.4 + 2.7 + 3.6) / 10 = 0.69
    p = compute_target_pressure(window)
    assert 0.65 < p < 0.75


def test_compute_target_pressure_dwell_penalty():
    # 4 off-arc signals + high beat_dwell → penalty kicks in
    window = [signal_to_dict(TurnSignal(off_arc_world_query=True,
                                         beat_dwell=6))
              for _ in range(4)]
    p = compute_target_pressure(window)
    assert p <= 0.2   # base 0.2 - 0.1 dwell penalty


def test_compute_target_pressure_clamped():
    window = [signal_to_dict(TurnSignal(explicit_plot=True))
              for _ in range(4)]
    assert compute_target_pressure(window) == 1.0
    window2 = [signal_to_dict(TurnSignal(explicit_free=True))
               for _ in range(4)]
    assert compute_target_pressure(window2) == 0.0


# ---- EMA smoothing --------------------------------------------------------


def test_update_pressure_ema():
    new = update_pressure(0.8, 0.2, alpha=0.5)
    assert new == 0.5  # halfway


def test_update_pressure_alpha_bounds():
    # Even with alpha 0.0 / 1.0, we clamp to [0.05, 0.95]
    assert 0.05 <= update_pressure(0.5, 0.9, alpha=0.0)
    assert update_pressure(0.5, 0.9, alpha=1.0) <= 0.95


# ---- effective_pressure (override) ----------------------------------------


def test_effective_pressure_auto_passes_through():
    assert effective_pressure(0.42, "auto") == 0.42


def test_effective_pressure_planner_pins_full():
    assert effective_pressure(0.05, "planner") == 1.0


def test_effective_pressure_frei_pins_zero():
    assert effective_pressure(0.95, "frei") == 0.0


def test_effective_pressure_unknown_defaults_to_auto():
    # Forward-compat: unknown mode → behaves like auto
    assert effective_pressure(0.55, "weirdsetting") == 0.55


def test_is_valid_story_mode():
    assert is_valid_story_mode("auto")
    assert is_valid_story_mode("planner")
    assert is_valid_story_mode("frei")
    assert not is_valid_story_mode("planned")
    assert not is_valid_story_mode("")


# ---- threshold consumers --------------------------------------------------


def test_gate_thresholds(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert gate_should_run(0.50, cfg)
    assert not gate_should_run(0.05, cfg)


def test_gate_max_reveals_scales_with_pressure(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    cap = cfg.story.narration_gate_max_reveals
    # At full pressure → use config cap
    assert gate_max_reveals(0.80, cfg) == cap
    # In the band → scaled down but never below 2
    assert 2 <= gate_max_reveals(0.30, cfg) < cap


def test_substory_block_mode_tiers(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert substory_block_mode(0.80, cfg) == "full"
    assert substory_block_mode(0.50, cfg) == "ambient"
    assert substory_block_mode(0.15, cfg) == "free"


def test_substory_tools_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert substory_tools_visible(0.50, cfg)
    assert not substory_tools_visible(0.15, cfg)


def test_substory_planning_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert substory_planning_enabled(0.50, cfg)
    assert not substory_planning_enabled(0.10, cfg)


def test_beat_nudge_threshold_scales_inverse(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    base = cfg.story.beat_nudge_after
    assert beat_nudge_threshold(1.0, cfg) == base
    # Lower pressure → larger threshold (nudge later)
    assert beat_nudge_threshold(0.5, cfg) > base
    # Zero pressure → effectively never (huge sentinel)
    assert beat_nudge_threshold(0.0, cfg) > 1000


# ---- tools_for_pressure ---------------------------------------------------


def test_tools_for_pressure_hides_substory_tools_below_threshold():
    full = tools_for_pressure(0.50)
    reduced = tools_for_pressure(0.10)
    assert len(full) == len(TOOLS)
    assert len(reduced) == len(TOOLS) - len(NARRATIVE_TOOLS)
    reduced_names = {t["function"]["name"] for t in reduced}
    assert NARRATIVE_TOOLS.isdisjoint(reduced_names)


# ---- tiebreaker decision --------------------------------------------------


def test_tiebreaker_fires_in_uncertain_band(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    # 3 turns of lateral (0.5 pull) → in uncertain band
    window = [signal_to_dict(TurnSignal()) for _ in range(3)]
    assert tiebreaker_should_run(window, cfg)


def test_tiebreaker_skips_decisive_signals(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    window = [signal_to_dict(TurnSignal()),
              signal_to_dict(TurnSignal()),
              signal_to_dict(TurnSignal(explicit_plot=True))]
    # Last signal is decisive — no tiebreaker
    assert not tiebreaker_should_run(window, cfg)


def test_tiebreaker_skips_short_window(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()
    assert not tiebreaker_should_run([], cfg)
    assert not tiebreaker_should_run(
        [signal_to_dict(TurnSignal())] * 2, cfg)


# ---- NPC-candidate extraction (Part C) -----------------------------------

def test_extract_npc_candidates_picks_obvious_names():
    """Capitalised tokens that aren't known world entities AND aren't
    German sentence-starters should surface as candidates."""
    from types import SimpleNamespace

    from storyteller_core.story.nodes import _extract_npc_candidates

    # Fake world with empty entity lists — nothing pre-filters
    world = SimpleNamespace(name="Sci", places=[], persons=[], items=[],
                             glossary=[], regions=[], factions=[],
                             random_tables=[])
    text = ("Der Truppführer schaut dich an. Otkar tritt aus dem "
            "Schatten und nickt. JAM bestätigt knapp.")
    out = _extract_npc_candidates(text, world, {})
    out_low = [c.lower() for c in out]
    assert "truppführer" in out_low
    assert "otkar" in out_low
    assert "jam" in out_low
    # "Der" / "Schatten" should be filtered (sentence-start / regular noun;
    # the latter would only slip in if there's no sentence-boundary trick —
    # here we accept that German nouns may leak. Just check we got the
    # interesting ones.)


def test_extract_npc_candidates_filters_world_entities():
    """Names already in world.places / world.glossary etc. must not
    appear as candidates — the curator/RAG layer handles those."""
    from types import SimpleNamespace

    from storyteller_core.story.nodes import _extract_npc_candidates

    glossary_entry = SimpleNamespace(term="Valucium", definition="ship")
    world = SimpleNamespace(name="Sci", places=[], persons=[], items=[],
                             glossary=[glossary_entry],
                             regions=[], factions=[], random_tables=[])
    text = "Die Valucium fliegt durch Kalar."
    out = _extract_npc_candidates(text, world, {})
    assert "valucium" not in [c.lower() for c in out]


def test_extract_npc_candidates_filters_already_tracked():
    """Names already in char_state should be filtered (no duplicate hint)."""
    from types import SimpleNamespace

    from storyteller_core.story.nodes import _extract_npc_candidates

    world = SimpleNamespace(name="Sci", places=[], persons=[], items=[],
                             glossary=[], regions=[], factions=[],
                             random_tables=[])
    out = _extract_npc_candidates(
        "Otkar nickt knapp und JAM bestätigt.",
        world,
        {"Otkar": "ruhig, abwartend"},
    )
    out_low = [c.lower() for c in out]
    assert "otkar" not in out_low      # already tracked
    assert "jam" in out_low            # new


def test_extract_npc_candidates_skips_long_compound_nouns():
    """Compound nouns longer than 18 chars are concepts, not NPCs."""
    from types import SimpleNamespace

    from storyteller_core.story.nodes import _extract_npc_candidates

    world = SimpleNamespace(name="Sci", places=[], persons=[], items=[],
                             glossary=[], regions=[], factions=[],
                             random_tables=[])
    out = _extract_npc_candidates(
        "Der Spiegelsplitter-Gürtel knirscht unter den Greifern.",
        world,
        {},
    )
    out_low = [c.lower() for c in out]
    assert "spiegelsplitter-gürtel" not in out_low


def test_extract_npc_candidates_dedupes():
    from types import SimpleNamespace

    from storyteller_core.story.nodes import _extract_npc_candidates

    world = SimpleNamespace(name="Sci", places=[], persons=[], items=[],
                             glossary=[], regions=[], factions=[],
                             random_tables=[])
    out = _extract_npc_candidates(
        "Otkar nickt. Dann hebt Otkar die Hand. Otkar schweigt.",
        world,
        {},
    )
    assert sum(1 for c in out if c.lower() == "otkar") == 1


def test_extract_npc_candidates_empty_text():
    from types import SimpleNamespace

    from storyteller_core.story.nodes import _extract_npc_candidates

    world = SimpleNamespace(name="Sci", places=[], persons=[], items=[],
                             glossary=[], regions=[], factions=[],
                             random_tables=[])
    assert _extract_npc_candidates("", world, {}) == []


# ---- planner coined-region detector --------------------------------------

def test_planner_coined_region_warns(tmp_path, monkeypatch):
    """Planner output containing 'Aurelion-Korridor' when the world has
    region 'Aurelion-System' should fire a [planner] transcript warning
    via SubstoryPlanner._warn_coined_region_names. Does NOT reject the
    plan — drift is surfaced, not blocked."""
    from types import SimpleNamespace

    import storyteller_core.config as cfgmod
    from storyteller_core.config import load_config
    from storyteller_core.story.substory import SubstoryPlanner

    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    # Fake transcript that records notes
    notes: list[str] = []
    transcript = SimpleNamespace(note=lambda t: notes.append(t))
    planner = SubstoryPlanner(cfg, transcript=transcript)
    world = SimpleNamespace(
        regions=[SimpleNamespace(name="Aurelion-System"),
                  SimpleNamespace(name="Karvoss-System")],
        places=[SimpleNamespace(name="Mirrava")],
        factions=[], persons=[], items=[], glossary=[],
    )
    planner._warn_coined_region_names(
        world,
        title="Kaltglas-Spur",
        premise="Das Signal kommt aus dem Aurelion-Korridor.",
        hook="",
        involved_places=["Rand des Aurelion-Korridors", "Mirrava"],
        beat_names=[],
        beat_goals=[],
    )
    assert notes, "expected at least one [planner] coined warning"
    txt = notes[-1]
    assert "[planner]" in txt
    assert "Aurelion-Korridor" in txt
    assert "Aurelion-System" in txt   # canonical name shown


def test_planner_no_warn_when_clean(tmp_path, monkeypatch):
    """Plans that only use canonical region names produce no warnings."""
    from types import SimpleNamespace

    import storyteller_core.config as cfgmod
    from storyteller_core.config import load_config
    from storyteller_core.story.substory import SubstoryPlanner

    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    notes: list[str] = []
    transcript = SimpleNamespace(note=lambda t: notes.append(t))
    planner = SubstoryPlanner(cfg, transcript=transcript)
    world = SimpleNamespace(
        regions=[SimpleNamespace(name="Aurelion-System")],
        places=[SimpleNamespace(name="Mirrava")],
        factions=[], persons=[], items=[], glossary=[],
    )
    planner._warn_coined_region_names(
        world,
        title="Eine Reise",
        premise="Im Aurelion-System bei Mirrava findet AIR Spuren.",
        hook="",
        involved_places=["Mirrava"],
        beat_names=[],
        beat_goals=[],
    )
    assert notes == []


def test_planner_existing_name_not_flagged(tmp_path, monkeypatch):
    """A region-shaped name that's actually IN the world (e.g. the
    world has a region called 'Veyron-Sektor') must not be flagged."""
    from types import SimpleNamespace

    import storyteller_core.config as cfgmod
    from storyteller_core.config import load_config
    from storyteller_core.story.substory import SubstoryPlanner

    monkeypatch.setattr(cfgmod, "ROOT", tmp_path)
    load_config.cache_clear()
    cfg = load_config()
    load_config.cache_clear()

    notes: list[str] = []
    transcript = SimpleNamespace(note=lambda t: notes.append(t))
    planner = SubstoryPlanner(cfg, transcript=transcript)
    world = SimpleNamespace(
        regions=[SimpleNamespace(name="Veyron-Sektor")],
        places=[], factions=[], persons=[], items=[], glossary=[],
    )
    planner._warn_coined_region_names(
        world,
        title="x", premise="Action im Veyron-Sektor.", hook="",
        involved_places=["Veyron-Sektor"],
        beat_names=[], beat_goals=[])
    assert notes == []
