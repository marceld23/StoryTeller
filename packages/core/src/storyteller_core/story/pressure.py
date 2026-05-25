"""Soft plot-pressure controller.

Continuous 0..1 dial replacing the prior binary "planned vs free" mode:
the narrator's full plot machinery (substory planning, curator gate,
beat-nudges, substory-tools) gradually fades in and out with the
player's apparent direction. The pressure is computed from a sliding
window of per-turn signals (`TurnSignal`) — derived from already-
existing engine telemetry (tools fired this turn + lexical match
against the active arc + a handful of explicit phrase patterns).

The mapping is intentionally simple: each turn yields a single
"pull-toward-plot" value 0..1, the window is recency-weighted, and an
EMA smoothing on the resulting target prevents jitter. Five threshold
parameters in `StoryCfg` then govern what each downstream consumer
does at the current pressure.

A `story_mode` setting in `data/settings.json` can hard-pin the
pressure (auto | planner=1.0 | frei=0.0) — `effective_pressure()`
applies the pin.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

from ..config import Config

# Sliding window of TurnSignals carried in StoryState["direction_window"].
WINDOW_SIZE = 6

# Pull-value per signal "kind" — recency-weighted mean of these is the
# target pressure.
_PULL_EXPLICIT_PLOT = 1.0
_PULL_ADVANCED = 0.9
_PULL_ON_ARC = 0.7
_PULL_LATERAL = 0.5
_PULL_OFF_ARC = 0.2
_PULL_EXPLICIT_FREE = 0.0

# Phrase patterns. Case-insensitive substring match — intentionally
# narrow so spurious matches stay rare.
_PHRASE_EXPLICIT_FREE = (
    # German
    "lass uns einfach", "ohne plot", "kein plot", "frei spielen",
    "frei rum", "einfach erkunden", "einfach explorieren",
    "lass uns rumlaufen", "lass uns gucken", "pause vom plot",
    "vergiss die mission", "nicht so wichtig",
    # English
    "let's just", "no plot", "explore freely", "free roam",
    "forget the mission", "skip the plot",
)
_PHRASE_EXPLICIT_PLOT = (
    # German
    "was war nochmal", "was sollte ich", "die mission",
    "weiter mit der", "zurück zur geschichte", "zurück zum plot",
    "wie geht's weiter", "weiter im plot",
    # English
    "what was the mission", "what should i", "back to the story",
    "back to the plot", "continue the story", "carry on with",
)


Direction = Literal["toward_beat", "lateral", "away_from_beat"]


@dataclass
class TurnSignal:
    """Per-turn telemetry from which the target pressure is computed.

    All bool fields except `beat_dwell` (int) — they classify what just
    happened in ONE turn. Aggregation across turns happens in
    compute_target_pressure().
    """
    advanced: bool = False               # advance_beat OR complete_substory fired
    on_arc_lex: bool = False             # player text mentions arc-relevant terms
    off_arc_world_query: bool = False    # retrieve_world_fact on non-arc fact_type
    explicit_free: bool = False
    explicit_plot: bool = False
    # True when the active substory carries no concrete arc terms
    # (involved_persons / involved_places empty AND hook/beat-names
    # generic). The lexical heuristic can't reliably tell on-arc from
    # off-arc in that case, so we shift the default pull toward plot-
    # positive instead of penalising the player for the planner having
    # produced a thin plan.
    substory_lex_thin: bool = False
    # Tiebreaker LLM verdict — populated only when run; overrides the
    # heuristic pull when confidence >= threshold.
    tiebreaker_direction: Direction | None = None
    tiebreaker_confidence: float = 0.0
    beat_dwell: int = 0                  # state.beat_turns at end of this turn

    def pull(self) -> float:
        """Single-turn pull value 0..1 — bigger = pulls pressure toward
        plot, smaller = pulls away. Explicit phrases dominate; otherwise
        tool/lexical signals; tiebreaker overrides if confident."""
        if self.explicit_plot:
            return _PULL_EXPLICIT_PLOT
        if self.explicit_free:
            return _PULL_EXPLICIT_FREE
        if (self.tiebreaker_direction is not None
                and self.tiebreaker_confidence >= 0.7):
            return {"toward_beat": _PULL_ADVANCED,
                    "lateral": _PULL_LATERAL,
                    "away_from_beat": _PULL_OFF_ARC}[self.tiebreaker_direction]
        if self.advanced:
            return _PULL_ADVANCED
        if self.on_arc_lex:
            return _PULL_ON_ARC
        if self.off_arc_world_query:
            return _PULL_OFF_ARC
        # Default when no specific signal fires: lateral (0.5). EXCEPT
        # when the substory is lexically thin — then absence of
        # on_arc_lex doesn't mean the player drifted, it means we
        # couldn't measure. Bias slightly plot-positive (0.65) so the
        # pressure doesn't drag down on a thin plan.
        if self.substory_lex_thin:
            return 0.65
        return _PULL_LATERAL


# ----------------------------------------------------------------- classifier


def _phrase_hit(text: str, phrases: tuple[str, ...]) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in phrases)


def _arc_terms(substory: dict | None) -> set[str]:
    """Words / proper nouns that, if mentioned in player text, signal
    on-arc engagement (matches the active substory's involved people +
    places + hook + current beat name/goal)."""
    if not substory:
        return set()
    terms: set[str] = set()
    for k in ("involved_persons", "involved_places"):
        for item in substory.get(k) or []:
            if isinstance(item, str) and item.strip():
                # Tokenise so "Otkar der Wirt" matches just "Otkar" too.
                for tok in re.split(r"\W+", item.lower()):
                    if len(tok) >= 3:
                        terms.add(tok)
    hook = (substory.get("hook") or "").lower()
    for tok in re.split(r"\W+", hook):
        # Hook is free text — only keep capitalized-in-original (proper
        # nouns); discard verbs/prepositions. Already lowercased here, so
        # this is approximate — keep tokens 4+ chars.
        if len(tok) >= 4:
            terms.add(tok)
    beats = substory.get("beats") or []
    cur_idx = int(substory.get("cursor", 0))
    if 0 <= cur_idx < len(beats):
        bn = (beats[cur_idx].get("name") or "").lower()
        bg = (beats[cur_idx].get("goal") or "").lower()
        for tok in re.split(r"\W+", bn + " " + bg):
            if len(tok) >= 4:
                terms.add(tok)
    return terms


def _player_mentions_arc(player_text: str, substory: dict | None) -> bool:
    terms = _arc_terms(substory)
    if not terms:
        return False
    low = (player_text or "").lower()
    return any(t in low for t in terms)


def _off_arc_world_query(tool_calls: list[dict], substory: dict | None) -> bool:
    """`retrieve_world_fact` on history/glossary/fragment IS off-arc; on a
    place/person that IS in the substory's involved_* IS on-arc. The
    discriminator is the fact_type + name vs the arc."""
    if not tool_calls:
        return False
    involved = set()
    if substory:
        for k in ("involved_persons", "involved_places"):
            for v in substory.get(k) or []:
                if isinstance(v, str):
                    involved.add(v.lower())
    for tc in tool_calls:
        name = tc.get("name") or tc.get("function", {}).get("name") or ""
        if name != "retrieve_world_fact":
            continue
        args = tc.get("args") or {}
        ft = (args.get("fact_type") or "").lower()
        if ft in ("history", "fragment", "glossary"):
            return True
        if ft in ("place", "person"):
            q = (args.get("query") or "").lower()
            if involved and not any(i in q for i in involved):
                return True
    return False


def _substory_lex_thin(substory: dict | None) -> bool:
    """A substory is "lexically thin" when it lacks the concrete terms
    the heuristic needs to detect on-arc engagement — primarily no
    `involved_persons` and no `involved_places`. Hook and beat-name
    tokens DO get extracted by _arc_terms(), but words like
    "Aufhänger" / "Zuspitzung" / "Eskalation" are never what a player
    naturally says back to the narrator, so they can't actually drive
    on_arc_lex matches. The empty-involved-* state is the reliable
    indicator that the substory was a fallback stub (or a thinly-
    planned arc) — both cases need the classifier to bias plot-
    positive instead of penalising the player."""
    if not substory:
        return False
    persons = substory.get("involved_persons") or []
    places = substory.get("involved_places") or []
    # Treat empty-or-only-whitespace as empty (defensive against the
    # planner returning [""] etc.)
    has_persons = any(isinstance(p, str) and p.strip() for p in persons)
    has_places = any(isinstance(p, str) and p.strip() for p in places)
    return not (has_persons or has_places)


def classify(*, player_text: str,
             tool_calls: list[dict],
             substory: dict | None,
             beat_dwell: int) -> TurnSignal:
    """Build a TurnSignal from one turn's telemetry. Pure function —
    side-effect-free, easy to test. Tiebreaker fields default empty;
    caller (`finalize`) optionally fills them after an LLM call."""
    names = {tc.get("name") or tc.get("function", {}).get("name") or ""
             for tc in (tool_calls or [])}
    thin = _substory_lex_thin(substory)
    return TurnSignal(
        advanced=("advance_beat" in names) or ("complete_substory" in names),
        on_arc_lex=_player_mentions_arc(player_text, substory),
        # When the substory itself is thin, we cannot reliably tell that
        # a world-fact retrieve was off-arc (no "arc" to be off from).
        # Suppress the false off-arc signal in that case.
        off_arc_world_query=(False if thin
                              else _off_arc_world_query(tool_calls, substory)),
        explicit_free=_phrase_hit(player_text, _PHRASE_EXPLICIT_FREE),
        explicit_plot=_phrase_hit(player_text, _PHRASE_EXPLICIT_PLOT),
        substory_lex_thin=thin,
        beat_dwell=int(beat_dwell or 0),
    )


# ------------------------------------------------------------------- aggregate


def compute_target_pressure(window: list[dict]) -> float:
    """Recency-weighted mean of per-turn pulls + dwell penalty.

    `window` is a list of `TurnSignal.__dict__` (LangGraph state can't
    store dataclasses, so the serialised form lives in state and gets
    reconstituted here)."""
    if not window:
        return 0.85   # warm start — bias toward plot when nothing is known
    signals = [TurnSignal(**{k: v for k, v in d.items()
                              if k in TurnSignal.__dataclass_fields__})
               for d in window]
    weights = list(range(1, len(signals) + 1))  # linear: 1, 2, 3, …
    weight_sum = sum(weights)
    weighted = sum(s.pull() * w for s, w in zip(signals, weights, strict=True))
    base = weighted / weight_sum
    # Dwell penalty: stuck on the same beat AND signals aren't pro-plot.
    last = signals[-1]
    if last.beat_dwell >= 5 and base < 0.5:
        base = max(0.0, base - 0.1)
    return max(0.0, min(1.0, base))


def update_pressure(current: float, target: float, *, alpha: float = 0.4) -> float:
    """EMA smoothing — actual pressure follows target with lag so a
    single noisy turn can't yank the whole machinery."""
    a = max(0.05, min(0.95, alpha))
    return current * (1.0 - a) + target * a


# ---------------------------------------------------------------- override


_STORY_MODE_VALUES = ("auto", "planner", "frei")


def effective_pressure(state_pressure: float, story_mode: str) -> float:
    """Apply the global `story_mode` pin on top of the heuristic value.

    `story_mode`:
      * "auto"    → pass through (the EMA-smoothed value drives the engine)
      * "planner" → pin to 1.0 (full plot pressure)
      * "frei"    → pin to 0.0 (no plot pressure)
      * anything else → treat as "auto" (forward compatibility)
    """
    mode = (story_mode or "auto").strip().lower()
    if mode == "planner":
        return 1.0
    if mode == "frei":
        return 0.0
    return max(0.0, min(1.0, float(state_pressure)))


def is_valid_story_mode(value: str) -> bool:
    return (value or "").strip().lower() in _STORY_MODE_VALUES


# ----------------------------------------------------------------- thresholds


def gate_should_run(pressure: float, cfg: Config) -> bool:
    """Curator/gate fires when pressure ≥ threshold. Below, the gate is
    skipped entirely (no LLM call, no `forbidden_topics`)."""
    return pressure >= float(getattr(cfg.story,
                                      "pressure_gate_min", 0.10))


def gate_max_reveals(pressure: float, cfg: Config) -> int:
    """Curator scales `max_reveals` linearly with pressure between gate-on
    threshold and full-strict threshold. Above the full-strict threshold
    the configured cfg.story.narration_gate_max_reveals is used as-is."""
    full = float(getattr(cfg.story, "pressure_gate_strict", 0.70))
    cap = int(cfg.story.narration_gate_max_reveals)
    if pressure >= full:
        return cap
    # Below the strict band: 2..cap proportionally
    low = float(getattr(cfg.story, "pressure_gate_min", 0.10))
    span = max(0.01, full - low)
    frac = max(0.0, (pressure - low) / span)
    return max(2, int(round(2 + (cap - 2) * frac)))


def substory_block_mode(pressure: float, cfg: Config) -> str:
    """Three tiers for what goes into the narrator system prompt:
      * "full"    — current behaviour (full substory block)
      * "ambient" — one-liner: hook + current beat name, no goals/tension
      * "free"    — no substory block at all; FREE_EXPLORATION block instead
    """
    if pressure >= float(getattr(cfg.story, "pressure_substory_full", 0.70)):
        return "full"
    if pressure >= float(getattr(cfg.story, "pressure_substory_ambient", 0.30)):
        return "ambient"
    return "free"


def substory_tools_visible(pressure: float, cfg: Config) -> bool:
    """`advance_beat` / `complete_substory` / `get_substory_plan` /
    `adjust_substory_plan` are hidden from the tool list below this
    threshold — they don't apply when there's no active arc to drive."""
    return pressure >= float(getattr(cfg.story,
                                      "pressure_substory_tools", 0.30))


def substory_planning_enabled(pressure: float, cfg: Config) -> bool:
    """Below this threshold neither `ensure_substory` nor `replan` makes
    a planner-LLM call. The active substory gets parked into
    `dormant_substory`."""
    return pressure >= float(getattr(cfg.story,
                                      "pressure_substory_plan", 0.20))


def beat_nudge_threshold(pressure: float, cfg: Config) -> int:
    """Inverse scaling: lower pressure = nudge after more turns; pressure
    = 0 disables nudges entirely (returns a huge sentinel value)."""
    if pressure <= 0.01:
        return 10**6
    base = int(cfg.story.beat_nudge_after or 0)
    if base <= 0:
        return 10**6
    return max(base, int(round(base / max(0.10, pressure))))


# ---------------------------------------------------------------- tiebreaker


def tiebreaker_should_run(window: list[dict], cfg: Config) -> bool:
    """Whether to invoke the optional planner-LLM tiebreaker on this
    turn. Fires when:
      * the feature is enabled,
      * the recent pressure has been hovering in [0.30, 0.60] for at
        least 3 consecutive turns (uncertain zone), AND
      * the LATEST turn wasn't an explicit phrase (those are decisive
        anyway).
    """
    if not getattr(cfg.story, "engagement_tiebreaker_enabled", True):
        return False
    if len(window) < 3:
        return False
    tail = window[-3:]
    last_pulls = []
    for d in tail:
        if d.get("explicit_plot") or d.get("explicit_free"):
            return False
        last_pulls.append(TurnSignal(**{k: v for k, v in d.items()
                                         if k in TurnSignal.__dataclass_fields__}).pull())
    return all(0.30 <= p <= 0.60 for p in last_pulls)


def signal_to_dict(sig: TurnSignal) -> dict:
    """Serialisable form for StoryState. Keeps only the dataclass fields
    (drops methods)."""
    return asdict(sig)
