"""Per-session transcript recorder (JSONL) for the admin view.

Captures the full played story for traceability: player input, moderation
result, every LLM tool call + its result, and the narrator replies (with
state + running cost). One file per session: data/transcripts/<session>.jsonl

Session filenames follow ``<world_id>-<YYYYMMDD>-<HHMMSS>.jsonl`` (set
by the Pi loop). This shape lets `delete_transcripts_for_world` purge
all transcripts of a given world when the world is deleted or its save
state is reset.
"""

from __future__ import annotations

import json
import logging
import re
import time

from ..config import Config

log = logging.getLogger("storyteller.transcript")


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-")
    return s or f"session-{int(time.time())}"


def delete_transcripts_for_world(cfg: Config, world_id: str) -> dict:
    """Remove every transcript file whose name starts with ``<world_id>-``.

    Called from worlds.registry.delete_world and engine.reset so that
    deleting a world or wiping its saved progress also removes the
    historical play traces. Best-effort: a single unlink failure logs
    a warning but doesn't abort the rest. Returns
    ``{world_id, deleted, files}`` for the caller to surface to the UI.
    """
    out: dict = {"world_id": world_id, "deleted": 0, "files": []}
    if not (world_id or "").strip():
        return out
    d = cfg.path("data/transcripts")
    if not d.exists():
        return out
    prefix = f"{world_id}-"
    for p in d.glob(f"{prefix}*.jsonl"):
        # Defensive: glob already requires the prefix, but double-check
        # the filename can never escape the transcripts dir (paranoia).
        if not p.name.startswith(prefix):
            continue
        try:
            p.unlink()
            out["deleted"] += 1
            out["files"].append(p.name)
        except OSError as exc:                          # pragma: no cover
            log.warning("transcript delete failed (%s): %r", p, exc)
    log.info("delete_transcripts_for_world: %s", out)
    return out


class Transcript:
    def __init__(self, cfg: Config, session: str):
        d = cfg.path("data/transcripts")
        d.mkdir(parents=True, exist_ok=True)
        self.session = _slug(session)
        self.path = d / f"{self.session}.jsonl"

    def _w(self, obj: dict) -> None:
        try:
            obj = {"ts": round(time.time(), 3), **obj}
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        except Exception:
            pass  # transcript must never break play

    def note(self, text: str) -> None:
        self._w({"type": "note", "text": text})

    def user(self, text: str) -> None:
        self._w({"type": "user", "text": text})

    def moderation(self, ok: bool, flagged: list) -> None:
        self._w({"type": "moderation", "ok": ok, "flagged": flagged})

    def tool(self, name: str, args: dict, result) -> None:
        self._w({"type": "tool", "name": name, "args": args,
                 "result": str(result)[:2000]})

    def assistant(self, text: str, state: str = "", cost: float = 0.0) -> None:
        self._w({"type": "assistant", "text": text, "state": state,
                 "cost": round(float(cost), 4)})

    def prompt(self, model: str, messages: list[dict], tools: bool = False) -> None:
        """The exact request sent to the narrator LLM: system prompt + the
        follow-up messages (memory + tool round-trips). Long content fields
        are trimmed to keep the transcript file manageable."""
        def _trim(m: dict) -> dict:
            m = dict(m)
            c = m.get("content")
            if isinstance(c, str) and len(c) > 6000:
                m["content"] = c[:6000] + " …[gekürzt]"
            return m
        self._w({"type": "prompt", "model": model, "tools": tools,
                 "messages": [_trim(m) for m in messages]})
