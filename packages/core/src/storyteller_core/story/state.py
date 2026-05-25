"""StoryEngine LangGraph state schema and runtime context.

Two separate things:

- StoryState (TypedDict): the per-session, serializable state managed by
  LangGraph and persisted via SqliteSaver. Long-lived fields survive across
  turns; turn-scoped fields are reset by `init_turn`.

- EngineContext (dataclass): non-serializable per-session handles (Config,
  World, RAG, Transcript). Passed via RunnableConfig.configurable, never
  stored in state, never sent to the checkpointer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


@dataclass
class EngineContext:
    cfg: Any                  # storyteller_core.config.Config
    world: Any                # storyteller_core.worlds.schema.World
    rag: Any | None = None    # storyteller_core.story.rag.WorldRAG
    transcript: Any | None = None  # storyteller_core.story.transcript.Transcript


class StoryState(TypedDict, total=False):
    # ---------- persisted across turns ----------
    locale: str
    memory: list[dict]              # OpenAI-shaped chat messages
    substory: dict | None           # SubstoryPlan.model_dump()
    # When the soft plot-pressure drops below cfg.story.pressure_substory_plan
    # the active substory is moved here with status="dormant" — preserved,
    # not discarded — so the next time pressure climbs back the planner
    # can resume the same arc instead of inventing a fresh one. None when
    # there's nothing to revive (initial state or already in-flight).
    dormant_substory: dict | None
    # Continuous 0..1 plot-pressure (heuristic-driven EMA-smoothed value).
    # Read by ensure_substory / curate / build_prompt / narrate to decide
    # how much plot machinery to engage this turn. Default 1.0 = full plot.
    plot_pressure: float
    # Sliding window of the last N TurnSignals (see pressure.signal_to_dict)
    # — the recency-weighted aggregate of these IS the pressure target.
    # Capped at WINDOW_SIZE inside pressure.py.
    direction_window: list[dict]
    macro_index: int
    # Index into world.blueprints picked for the CURRENT substory arc
    # (single-variant worlds keep this at 0 implicitly via
    # World.active_blueprint's clamp + fallback). Set by the substory
    # planner when starting a new arc on a multi-variant world.
    blueprint_choice: int
    known_facts: list[dict]         # KnownFacts.to_list()
    synopsis: str
    char_state: dict[str, str]
    beat_turns: int
    cost: dict                      # CostTracker.snapshot()
    pending_fold: list[dict]

    # ---------- per-turn (reset by init_turn) ----------
    user_text: str
    moderation_ok: bool
    retrieved: list[dict]
    dyn_hint: str | None
    brief: bool
    transition: bool
    response: str
    system_prompt: str
    pending_tool_calls: list[dict]
    narrate_iter: int
    just_completed_substory: bool
    # Curator gate for this turn: {scene_intent, permitted_reveals,
    # forbidden_topics, tone_nudge}. Empty/missing => no gate active.
    gate: dict
    # Capitalised tokens the narrator introduced in its last few turns
    # that aren't in any world entity list and aren't tracked yet —
    # FIFO-capped at 6. The build_system_prompt step renders these as
    # a `track_character` hint so the narrator stops re-introducing the
    # same NPC every turn ("the Truppführer", "the Wirt", "JAM" …).
    # Names move out once `track_character` actually picks them up via
    # dispatch_tools. Kept per-session in state so the prompt remains
    # stable across the narrator's tool-call rounds within one turn.
    recent_npc_candidates: list[str]
    # Set by narrate() when the story-LLM call fails. engine.turn() reads
    # it after graph.invoke() and raises EndpointError so the Pi loop can
    # play the right pre-recorded prompt (offline_cloud / offline_local /
    # auth / busy / generic). Always None on a successful turn.
    endpoint_error: dict | None


TURN_SCOPED_KEYS: tuple[str, ...] = (
    "moderation_ok", "retrieved", "dyn_hint", "brief",
    "transition", "response", "system_prompt", "pending_tool_calls",
    "narrate_iter", "just_completed_substory", "gate", "endpoint_error",
)
