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
