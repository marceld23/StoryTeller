"""Compiled LangGraph story workflow.

Topology:

    START → init_turn → moderate
    moderate ──(blocked?)──→ blocked_finalize → END
             └──(ok)────→ fanout
    fanout ─┬→ ensure_substory ─┐
            ├→ retrieve_rag ────┤ (parallel pre-narrator phase)
            ├→ roll_dynamic ────┤
            └→ compute_flags ───┘
                                ↓
                          build_prompt → narrate
                          narrate ─(tool_calls?)─→ dispatch_tools
                                  └(text)──────→ finalize → END
                          dispatch_tools ─(complete_substory?)─→ replan → narrate
                                         └(other)──────────────→ narrate
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import StoryState


def build_graph() -> StateGraph:
    g = StateGraph(StoryState)

    g.add_node("init_turn", nodes.init_turn)
    g.add_node("moderate", nodes.moderate)
    g.add_node("blocked_finalize", nodes.blocked_finalize)
    g.add_node("fanout", nodes.fanout)
    g.add_node("ensure_substory", nodes.ensure_substory)
    g.add_node("retrieve_rag", nodes.retrieve_rag)
    g.add_node("roll_dynamic", nodes.roll_dynamic)
    g.add_node("compute_flags", nodes.compute_flags)
    g.add_node("build_prompt", nodes.build_prompt)
    g.add_node("narrate", nodes.narrate)
    g.add_node("dispatch_tools", nodes.dispatch_tools)
    g.add_node("replan", nodes.replan)
    g.add_node("finalize", nodes.finalize)

    g.add_edge(START, "init_turn")
    g.add_edge("init_turn", "moderate")

    g.add_conditional_edges("moderate", nodes.route_after_moderate, {
        "blocked_finalize": "blocked_finalize",
        "fanout": "fanout",
    })
    g.add_edge("blocked_finalize", END)

    # Fan-out: four independent pre-narrator branches run in parallel.
    g.add_edge("fanout", "ensure_substory")
    g.add_edge("fanout", "retrieve_rag")
    g.add_edge("fanout", "roll_dynamic")
    g.add_edge("fanout", "compute_flags")

    # Fan-in: build_prompt waits for all four.
    g.add_edge("ensure_substory", "build_prompt")
    g.add_edge("retrieve_rag", "build_prompt")
    g.add_edge("roll_dynamic", "build_prompt")
    g.add_edge("compute_flags", "build_prompt")

    g.add_edge("build_prompt", "narrate")
    g.add_conditional_edges("narrate", nodes.route_after_narrate, {
        "dispatch_tools": "dispatch_tools",
        "finalize": "finalize",
    })
    g.add_conditional_edges("dispatch_tools", nodes.route_after_dispatch, {
        "replan": "replan",
        "narrate": "narrate",
    })
    g.add_edge("replan", "narrate")
    g.add_edge("finalize", END)

    return g


# --------------------------------------------------------------------------
# checkpointer + compiled graph (module-level singletons)
# --------------------------------------------------------------------------

_compiled = None
_checkpointer = None


def _open_checkpointer(db_path: Path) -> SqliteSaver:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def get_compiled(db_path: Path | None = None):
    """Return the compiled graph, opening a SqliteSaver on first call.

    `db_path` is honored only on the first call (subsequent calls reuse
    the singleton). Tests can reset via `reset_compiled()`.
    """
    global _compiled, _checkpointer
    if _compiled is None:
        from ..config import ROOT  # local import: avoid load at import time
        path = db_path or (ROOT / "data" / "checkpoints.db")
        _checkpointer = _open_checkpointer(path)
        _checkpointer.setup()
        _compiled = build_graph().compile(checkpointer=_checkpointer)
    return _compiled


def reset_compiled() -> None:
    """Drop the cached graph + checkpointer (useful for tests)."""
    global _compiled, _checkpointer
    _compiled = None
    _checkpointer = None


# --------------------------------------------------------------------------
# retention / maintenance
# --------------------------------------------------------------------------

def delete_thread(thread_id: str, db_path: Path | None = None) -> dict:
    """Delete ALL checkpoints + writes for one thread (reset a saved game).

    The next `state()` for this thread is empty, so the engine starts a fresh
    opening. Uses a short busy_timeout so it doesn't fail if the live service
    holds the other connection. No VACUUM (would need exclusive access).
    Returns {"checkpoints_deleted", "writes_deleted", "thread_id"}.
    """
    import logging

    log = logging.getLogger("storyteller.maintenance")
    out = {"checkpoints_deleted": 0, "writes_deleted": 0,
           "thread_id": thread_id}
    from ..config import ROOT

    path = db_path or (ROOT / "data" / "checkpoints.db")
    if not Path(path).exists():
        return out
    try:
        conn = sqlite3.connect(str(path), timeout=5)
        conn.execute("PRAGMA busy_timeout=5000")
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "checkpoints" in tables:
            cur = conn.execute(
                "DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
            out["checkpoints_deleted"] = cur.rowcount
        if "writes" in tables:
            cur = conn.execute(
                "DELETE FROM writes WHERE thread_id=?", (thread_id,))
            out["writes_deleted"] = cur.rowcount
        conn.commit()
        conn.close()
        log.info("deleted thread: %s", out)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("thread delete failed: %r", exc)
    return out


def list_threads(db_path: Path | None = None) -> list[dict]:
    """Inventory of saved sessions: [{thread_id, checkpoints, last_narration}].

    Read-only; used by the admin UI to show/reset saves. The per-thread count
    comes from raw SQL; the last narration is read via the compiled graph's
    checkpointer (correct serde), best-effort."""
    from ..config import ROOT

    path = db_path or (ROOT / "data" / "checkpoints.db")
    out: list[dict] = []
    if not Path(path).exists():
        return out
    try:
        conn = sqlite3.connect(str(path), timeout=5)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "checkpoints" not in tables:
            conn.close()
            return out
        rows = conn.execute(
            "SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id "
            "ORDER BY thread_id").fetchall()
        conn.close()
    except Exception:  # pragma: no cover - defensive
        return out

    graph = get_compiled(db_path)
    for tid, n in rows:
        last = ""
        try:
            snap = graph.get_state({"configurable": {"thread_id": tid}})
            mem = (snap.values.get("memory") if snap and snap.values else None)
            for m in reversed(mem or []):
                if (m.get("role") == "assistant"
                        and isinstance(m.get("content"), str)):
                    last = m["content"][:160].replace("\n", " ")
                    break
        except Exception:
            pass
        out.append({"thread_id": tid, "checkpoints": n,
                    "last_narration": last})
    return out


def prune_checkpoints(db_path: Path | None = None,
                      keep_per_thread: int = 100) -> dict:
    """Bound checkpoint DB growth: keep the newest `keep_per_thread`
    checkpoints per (thread, namespace), delete older ones + orphaned writes.

    `checkpoint_id` is time-ordered, so newest = max id. `keep_per_thread<=0`
    disables pruning. Defensive: a no-op if the expected tables are absent.
    Returns {"checkpoints_deleted", "writes_deleted", "kept_per_thread"}.
    """
    import logging

    log = logging.getLogger("storyteller.maintenance")
    out = {"checkpoints_deleted": 0, "writes_deleted": 0,
           "kept_per_thread": keep_per_thread}
    if keep_per_thread <= 0:
        return out
    from ..config import ROOT

    path = db_path or (ROOT / "data" / "checkpoints.db")
    if not Path(path).exists():
        return out
    try:
        conn = sqlite3.connect(str(path))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "checkpoints" not in tables:
            conn.close()
            return out
        cur = conn.execute(
            "DELETE FROM checkpoints WHERE rowid IN ("
            "  SELECT rowid FROM ("
            "    SELECT rowid, ROW_NUMBER() OVER ("
            "      PARTITION BY thread_id, checkpoint_ns "
            "      ORDER BY checkpoint_id DESC) AS rn FROM checkpoints"
            "  ) WHERE rn > ?)", (keep_per_thread,))
        out["checkpoints_deleted"] = cur.rowcount
        if "writes" in tables:
            cur = conn.execute(
                "DELETE FROM writes WHERE (thread_id, checkpoint_ns, "
                "checkpoint_id) NOT IN (SELECT thread_id, checkpoint_ns, "
                "checkpoint_id FROM checkpoints)")
            out["writes_deleted"] = cur.rowcount
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
        conn.close()
        log.info("pruned checkpoints: %s", out)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("checkpoint prune failed: %r", exc)
    return out
