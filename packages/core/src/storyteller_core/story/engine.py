"""Thin StoryEngine wrapper around the LangGraph story workflow.

Per-session state (memory, substory, known facts, synopsis, char_state,
cost, …) is owned by the LangGraph checkpointer (SqliteSaver). Per-session
non-serializable handles (Config, World, RAG, Transcript) live in
`EngineContext` and travel via `RunnableConfig.configurable`.

A `StoryEngine` instance is a thin per-session façade. Cheap to construct,
holds no story state of its own.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .graph import get_compiled
from .state import EngineContext


class StoryEngine:
    def __init__(self, cfg, world, *, rag=None, transcript=None,
                 thread_id: str = "local"):
        self.ctx = EngineContext(cfg=cfg, world=world, rag=rag,
                                  transcript=transcript)
        self.thread_id = thread_id

    # ---------------------------------------------------------------- core
    def _config(self, checkpoint_id: str | None = None) -> dict:
        cfg: dict[str, Any] = {
            "configurable": {
                "thread_id": self.thread_id,
                "ctx": self.ctx,
            }
        }
        if checkpoint_id:
            cfg["configurable"]["checkpoint_id"] = checkpoint_id
        return cfg

    def turn(self, user_text: str) -> str:
        # Daily cost cap is a HARD pause: we refuse the next turn so the
        # story state on disk stays consistent (player can resume after a
        # reset). Raised exception is `DailyCapExceeded`; the main loop
        # catches it and plays the pause announcement, then idles.
        from .ledger import CostLedger
        CostLedger(self.ctx.cfg).assert_under_cap()
        graph = get_compiled()
        result = graph.invoke({"user_text": user_text}, config=self._config())
        return (result.get("response") or "").strip()

    def opening(self) -> str:
        from ..i18n import OPENING_DIRECTIVE, norm

        locale = norm(self.ctx.cfg.general.locale)
        return self.turn(OPENING_DIRECTIVE[locale])

    def recap(self) -> str:
        """Short spoken "previously on…" for a RESUMED game. Read-only: makes
        one LLM call from the synopsis + last scene and does NOT advance the
        story or mutate the checkpoint. Empty for a fresh (no-memory) thread.
        Also notes the resulting text in the transcript so duplicate-narration
        bug reports are debuggable from the recorded session.
        """
        from ..i18n import RECAP_INTRO, RECAP_SYS, norm
        from ..oai import get_chat_client

        st = self.state()
        mem = st.get("memory") or []
        if not mem:
            return ""
        locale = norm(self.ctx.cfg.general.locale)
        synopsis = (st.get("synopsis") or "").strip()
        last = self.last_narration().strip()
        if not synopsis and not last:
            return ""
        ctx_txt = ""
        if synopsis:
            ctx_txt += f"Bisheriger Verlauf:\n{synopsis}\n\n"
        if last:
            ctx_txt += f"Letzte Szene:\n{last}"
        try:
            client = get_chat_client(self.ctx.cfg, "story")
            r = client.chat.completions.create(
                model=self.ctx.cfg.models.story_llm,
                temperature=self.ctx.cfg.models.llm_temperature,
                messages=[{"role": "system", "content": RECAP_SYS[locale]},
                          {"role": "user", "content": ctx_txt}],
            )
            from .ledger import CostLedger
            CostLedger(self.ctx.cfg).record_chat_usage(
                role="story", model=self.ctx.cfg.models.story_llm,
                usage=r.usage, thread_id=self.thread_id,
                world_id=getattr(self.ctx.world, "id", None))
            text = (r.choices[0].message.content or "").strip()
            if text:
                spoken = RECAP_INTRO[locale] + text
                if self.ctx.transcript:
                    self.ctx.transcript.assistant(spoken, "recap")
                return spoken
        except Exception:
            pass
        return last  # fall back to replaying the last narration

    def reset(self) -> dict:
        """Delete this thread's saved progress (start fresh next time).

        Uses the same default DB as the compiled graph (ROOT/data/
        checkpoints.db), so it stays in sync with the live checkpointer.
        """
        from .graph import delete_thread

        return delete_thread(self.thread_id)

    # ---------------------------------------------------------- read-only
    def state(self) -> dict:
        graph = get_compiled()
        snap = graph.get_state(self._config())
        return dict(snap.values) if snap and snap.values else {}

    def last_narration(self) -> str:
        for m in reversed(self.state().get("memory") or []):
            if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                return m["content"]
        return ""

    def history(self) -> Iterable[Any]:
        return get_compiled().get_state_history(self._config())

    # ---------------------------------------------------------- branching
    def rewind_to(self, checkpoint_id: str) -> str:
        """Return the narration as it was at `checkpoint_id`. The next
        `turn()` will resume from that point and create a new branch.
        """
        graph = get_compiled()
        snap = graph.get_state(self._config(checkpoint_id))
        mem = (snap.values.get("memory") if snap and snap.values else None) or []
        for m in reversed(mem):
            if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                return m["content"]
        return ""

    def undo_last(self) -> str:
        """Roll back to the checkpoint before the most recent narration.
        Returns the now-last narration.
        """
        history = list(self.history())
        # history[0] = just-finished turn snapshot
        # history[1] = pre-turn snapshot — resume from there
        if len(history) >= 2:
            target = history[1]
            cp_id = target.config.get("configurable", {}).get("checkpoint_id")
            if cp_id:
                return self.rewind_to(cp_id)
        return self.last_narration()
